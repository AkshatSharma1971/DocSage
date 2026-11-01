"""Rule-based matching of code changes to documentation claims (no LLM)."""
from __future__ import annotations

import re
from typing import Optional

from .code_facts import Change, Facts, norm_value, same_value, show
from .doc_claims import Claim


def term_re(t: str):
    return re.compile(rf"(?<!\w){re.escape(t)}(?!\w)")


def value_pattern(val: str):
    v = norm_value(val)
    if not v:
        return None
    tail = r"(?!\w)" if v[-1].isalpha() else r"(?!\d)(?!\.\d)"
    return re.compile(rf"(?<![\w.]){re.escape(v)}{tail}", re.I)


def value_in(text: str, val: Optional[str]) -> bool:
    p = value_pattern(val) if val is not None else None
    return bool(p and p.search(text))


def func_mentioned(ch: Change, cl: Claim, ctx: bool = True) -> bool:
    text = cl.text + (" " + cl.context if ctx else "")
    parts = ch.symbol.split(".")
    simple = parts[-1]
    if len(parts) == 1:
        return bool(term_re(simple).search(text))
    if term_re(ch.symbol).search(text) or re.search(rf"(?<!\w){re.escape(simple)}\(", cl.text):
        return True
    return bool(term_re(parts[-2]).search(text) and term_re(simple).search(text))


def _code_ref(ch: Change, text: str) -> bool:
    simple = ch.symbol.split(".")[-1]
    token = ch.symbol if "." in ch.symbol else simple
    return bool(re.search(rf"`[^`]*(?<!\w){re.escape(token)}(?!\w)[^`]*`", text)
                or re.search(rf"(?<!\w){re.escape(simple)}\(", text))


def match(ch: Change, cl: Claim):
    """Return (status, reason) for a rule-based finding, else None."""
    k, t = ch.kind, cl.text
    if k in ("default_changed", "const_changed"):
        if ch.old is None or not value_in(t, ch.old):
            return None
        has_new = value_in(t, ch.new)
        if k == "const_changed":
            if not term_re(ch.symbol.split(".")[-1]).search(t):
                return None
            strong = True
        else:
            fm, pm = func_mentioned(ch, cl), bool(term_re(ch.param).search(t))
            if not (fm or pm):
                return None
            strong = fm and (pm or "default" in t.lower())
        status = "confirmed" if strong and not has_new else "potential"
        return status, f"Documentation states {norm_value(ch.old)}, but the code now has {norm_value(ch.new) or show(ch.new)}."
    if k in ("param_renamed", "param_removed"):
        if not term_re(ch.param).search(t) or (ch.new and term_re(ch.new).search(t)):
            return None
        if func_mentioned(ch, cl):
            return "confirmed", f"Documentation references parameter `{ch.param}`, which no longer exists."
        if f"`{ch.param}`" in t:
            return "potential", f"`{ch.param}` is documented but was removed/renamed in `{ch.symbol}()`; check it is the same function."
        return None
    if k in ("function_removed", "function_renamed"):
        if k == "function_renamed" and term_re(ch.new.split(".")[-1]).search(t):
            return None
        if _code_ref(ch, t):
            return "confirmed", f"Documentation references `{ch.symbol}`, which no longer exists in the code."
        if func_mentioned(ch, cl, ctx=False):
            return "potential", f"Documentation mentions `{ch.symbol}`, which was removed or renamed."
    return None


def suggest_fix(ch: Change, cl: Claim) -> Optional[str]:
    if ch.kind in ("default_changed", "const_changed") and ch.new is not None:
        p = value_pattern(ch.old)
        return p.sub(lambda _: norm_value(ch.new), cl.text, count=1) if p else None
    if ch.kind == "param_renamed":
        return term_re(ch.old).sub(ch.new, cl.text, count=1)
    if ch.kind == "function_renamed":
        return term_re(ch.symbol.split(".")[-1]).sub(ch.new.split(".")[-1], cl.text, count=1)
    return None


# ---- Full-repository scan: documented defaults vs. current code ------------------
_LITERAL = re.compile(r"""-?\d+(?:\.\d+)?|True|False|None|true|false|null|'[^']*'|"[^"]*\"""")
_DEF_A = r"default(?:s)?(?:\s+(?:to|is|of|value\s+of|value))?\s*[:=]?\s*`?([\w.\-'\"]+)"
_DEF_B = r"default\s+(?:value\s+)?(?:of\s+|for\s+)?`?{p}`?\s*(?:is|=|:|of)\s*`?([\w.\-'\"]+)"
_SIG = re.compile(r"def\s+(\w+)\s*\(([^)]*)\)")


def scan_claims(facts: Facts, claims: list) -> list:
    """Yield (Change, Claim) where a documented default contradicts the current code."""
    by_param = {}
    for f in facts.funcs.values():
        for p, d in f.params.items():
            if d is not None:
                by_param.setdefault(p, []).append(f)
    out = []
    for cl in claims:
        tokens = set(re.findall(r"[A-Za-z_]\w*", cl.text))
        for p in tokens & by_param.keys():
            for f in by_param[p]:
                ch = Change("default_changed", f.qualname, param=p, path=f.path, line=f.line)
                if not func_mentioned(ch, cl):
                    continue
                m = (re.search(rf"(?<!\w){re.escape(p)}(?!\w)[^.;]{{0,40}}?{_DEF_A}", cl.text, re.I)
                     or re.search(_DEF_B.format(p=re.escape(p)), cl.text, re.I))
                if not m:
                    continue
                doc_v = m.group(1).strip("`'\".,;:)")
                if _LITERAL.fullmatch(m.group(1).strip("`.,;:)")) and not same_value(doc_v, f.params[p]):
                    out.append((Change("default_changed", f.qualname, param=p, old=doc_v, new=f.params[p],
                                       path=f.path, line=f.line), cl))
        m = _SIG.search(cl.text)
        if m:
            for f in facts.funcs.values():
                if f.qualname.split(".")[-1] != m.group(1):
                    continue
                for kw in re.finditer(r"(\w+)\s*(?::[^=,]+)?=\s*([^,)\s]+)", m.group(2)):
                    p, v = kw.group(1), kw.group(2)
                    if f.params.get(p) is not None and not same_value(v, f.params[p]):
                        out.append((Change("default_changed", f.qualname, param=p, old=v, new=f.params[p],
                                           path=f.path, line=f.line), cl))
    return out
