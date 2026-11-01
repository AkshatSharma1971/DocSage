"""Combine deterministic rules and optional Gemma analysis into evidence-backed findings."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

from .code_facts import Change, diff_facts, extract_facts, norm_value
from .doc_claims import parse_markdown
from .matcher import func_mentioned, match, scan_claims, suggest_fix, term_re, value_in

ORDER = {"confirmed": 0, "potential": 1}


@dataclass
class Finding:
    status: str            # confirmed | potential
    kind: str
    symbol: str
    doc_path: str
    doc_line: int
    doc_text: str
    code_path: str
    code_line: int
    change: str
    old_value: Optional[str]
    new_value: Optional[str]
    explanation: str
    suggested_fix: Optional[str] = None
    source: str = "rules"  # rules | gemma


@dataclass
class Report:
    mode: str
    py_files: int
    md_files: int
    findings: list = field(default_factory=list)
    changes: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    llm_note: str = ""

    @property
    def confirmed(self): return [f for f in self.findings if f.status == "confirmed"]
    @property
    def potential(self): return [f for f in self.findings if f.status == "potential"]

    def to_dict(self):
        return {"mode": self.mode, "py_files": self.py_files, "md_files": self.md_files,
                "skipped": self.skipped, "llm_note": self.llm_note,
                "findings": [asdict(f) for f in self.findings]}


def _mk(ch: Change, cl, status, reason, fix, source="rules") -> Finding:
    return Finding(status, ch.kind, ch.symbol, cl.path, cl.line, cl.text, ch.path, ch.line, ch.describe(),
                   ch.old, ch.new, reason, fix, source)


def _fix_ok(ch: Change, fix: str) -> bool:
    if not fix:
        return False
    if ch.kind in ("default_changed", "const_changed"):
        return ch.new is not None and value_in(fix, ch.new)
    if ch.kind in ("param_renamed", "function_renamed"):
        return bool(term_re(ch.new.split(".")[-1]).search(fix))
    return True


def _polish(f: Finding, ch: Change, cl, client) -> None:
    """Gemma writes the explanation and rewrite; the verdict stays deterministic."""
    r = client.explain(ch, cl)
    if not r:
        return
    if r.get("explanation", "").strip():
        f.explanation, f.source = r["explanation"].strip(), "rules+gemma"
    if _fix_ok(ch, r.get("suggested_fix", "")):
        f.suggested_fix = r["suggested_fix"].strip()


def _semantic(changes, claims, matched, client, budget, findings) -> None:
    for ch in changes:
        if ch.kind in ("function_removed", "function_renamed"):
            continue
        for cl in claims:
            if budget <= 0:
                return
            if (id(ch), id(cl)) in matched or not func_mentioned(ch, cl):
                continue
            if ch.new and (value_in(cl.text, ch.new) if ch.kind in ("default_changed", "const_changed")
                           else term_re(norm_value(ch.new).split(".")[-1]).search(cl.text)):
                continue  # already documents the new state
            budget -= 1
            r = client.judge(ch, cl)
            ev = ((r or {}).get("evidence") or "").strip()
            if r and r.get("drifted") and len(ev) >= 4 and ev.lower() in cl.text.lower():
                fix = (r.get("suggested_fix") or "").strip()
                findings.append(_mk(ch, cl, "potential", (r.get("explanation") or "").strip()
                                    or "Gemma flagged this sentence as inconsistent with the change.",
                                    fix or None, "gemma"))


def _finish(findings: list) -> list:
    seen, out = set(), []
    for f in findings:
        k = (f.doc_path, f.doc_line, f.doc_text, f.change)
        if k not in seen:
            seen.add(k)
            out.append(f)
    return sorted(out, key=lambda f: (ORDER[f.status], f.doc_path, f.doc_line))


def _claims(docs: dict) -> list:
    return [c for p, t in docs.items() for c in parse_markdown(p, t)]


def run_compare(old_py: dict, new_py: dict, docs: dict, client=None, max_llm: int = 25) -> Report:
    old, new = extract_facts(old_py), extract_facts(new_py)
    changes, claims = diff_facts(old, new), _claims(docs)
    rep = Report("pr", len(new_py), len(docs), changes=changes, skipped=old.skipped + new.skipped)
    findings, matched, pairs = [], set(), []
    for ch in changes:
        for cl in claims:
            m = match(ch, cl)
            if m:
                matched.add((id(ch), id(cl)))
                f = _mk(ch, cl, m[0], m[1], suggest_fix(ch, cl))
                findings.append(f)
                pairs.append((f, ch, cl))
    if client:
        for f, ch, cl in pairs:
            _polish(f, ch, cl, client)
        _semantic(changes, claims, matched, client, max_llm, findings)
    rep.findings = _finish(findings)
    return rep


def run_scan(py: dict, docs: dict, client=None) -> Report:
    facts, claims = extract_facts(py), _claims(docs)
    rep = Report("scan", len(py), len(docs), skipped=facts.skipped)
    findings = []
    for ch, cl in scan_claims(facts, claims):
        f = _mk(ch, cl, "confirmed",
                f"Documentation says the default of `{ch.param}` is {norm_value(ch.old)}, "
                f"but `{ch.symbol}()` defines {norm_value(ch.new)}.", suggest_fix(ch, cl))
        if client:
            _polish(f, ch, cl, client)
        findings.append(f)
    rep.findings = _finish(findings)
    return rep
