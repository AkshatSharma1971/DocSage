"""Deterministic code facts via Python's ast. Repository code is never executed."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FuncFact:
    qualname: str
    params: dict  # param name -> default source text, or None if required
    path: str
    line: int


@dataclass
class ConstFact:
    qualname: str
    value: str
    path: str
    line: int


@dataclass
class Facts:
    funcs: dict = field(default_factory=dict)   # "path::qualname" -> FuncFact
    consts: dict = field(default_factory=dict)  # "path::qualname" -> ConstFact
    skipped: list = field(default_factory=list)  # files that failed to parse


@dataclass
class Change:
    kind: str  # default_changed | param_renamed | param_removed | function_removed | function_renamed | const_changed
    symbol: str
    param: Optional[str] = None
    old: Optional[str] = None
    new: Optional[str] = None
    path: str = ""
    line: int = 0

    def describe(self) -> str:
        s = f"`{self.symbol}`"
        if self.kind == "default_changed":
            return f"Default of parameter `{self.param}` in {s}() changed from {show(self.old)} to {show(self.new)}"
        if self.kind == "param_renamed":
            return f"Parameter `{self.old}` of {s}() was renamed to `{self.new}`"
        if self.kind == "param_removed":
            return f"Parameter `{self.param}` was removed from {s}()"
        if self.kind == "function_removed":
            return f"{s}() was removed"
        if self.kind == "function_renamed":
            return f"{s}() was renamed to `{self.new}`"
        if self.kind == "const_changed":
            return f"Constant {s} changed from {show(self.old)} to {show(self.new)}"
        return self.kind


def show(v: Optional[str]) -> str:
    return "no default (required)" if v is None else v


def norm_value(v: Optional[str]) -> str:
    """Normalize a Python literal's source text: "'abc'" -> abc, "10" -> 10."""
    if v is None:
        return ""
    try:
        return str(ast.literal_eval(v))
    except Exception:
        return str(v).strip().strip("`")


def same_value(a: str, b: str) -> bool:
    a, b = norm_value(a).lower(), norm_value(b).lower()
    a, b = {"null": "none"}.get(a, a), {"null": "none"}.get(b, b)
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def is_public(qualname: str) -> bool:
    return not any(p.startswith("_") and not (p.startswith("__") and p.endswith("__"))
                   for p in qualname.split("."))


def _params(a: ast.arguments) -> dict:
    out = {}
    pos = a.posonlyargs + a.args
    defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    for arg, d in zip(pos, defaults):
        out[arg.arg] = ast.unparse(d) if d is not None else None
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        out[arg.arg] = ast.unparse(d) if d is not None else None
    out.pop("self", None)
    out.pop("cls", None)
    return out


def _visit(body, prefix: str, path: str, facts: Facts) -> None:
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if n.name == "__init__" and prefix:
                continue  # constructor params are recorded on the class itself
            q = prefix + n.name
            facts.funcs[f"{path}::{q}"] = FuncFact(q, _params(n.args), path, n.lineno)
        elif isinstance(n, ast.ClassDef):
            q = prefix + n.name
            init = next((b for b in n.body if isinstance(b, ast.FunctionDef) and b.name == "__init__"), None)
            facts.funcs[f"{path}::{q}"] = FuncFact(q, _params(init.args) if init else {}, path, n.lineno)
            _visit(n.body, q + ".", path, facts)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            if n.value is None:
                continue
            for t in targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    q = prefix + t.id
                    facts.consts[f"{path}::{q}"] = ConstFact(q, ast.unparse(n.value), path, n.lineno)


def extract_facts(files: dict) -> Facts:
    facts = Facts()
    for path, src in files.items():
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            facts.skipped.append(path)
            continue
        _visit(tree.body, "", path, facts)
    return facts


def _removed_or_renamed(of: FuncFact, new: Facts, old_quals: set) -> Change:
    prefix = of.qualname.rsplit(".", 1)[0] if "." in of.qualname else ""
    cands = [f for f in new.funcs.values()
             if f.qualname not in old_quals and is_public(f.qualname)
             and (f.qualname.rsplit(".", 1)[0] if "." in f.qualname else "") == prefix
             and list(f.params) == list(of.params)]
    if len(cands) == 1:
        return Change("function_renamed", of.qualname, new=cands[0].qualname, path=of.path, line=of.line)
    return Change("function_removed", of.qualname, path=of.path, line=of.line)


def diff_facts(old: Facts, new: Facts) -> list:
    """Public-API changes between two snapshots. Private symbols are ignored."""
    changes = []
    new_quals = {f.qualname for f in new.funcs.values()}
    old_quals = {f.qualname for f in old.funcs.values()}
    new_paths = {f.path for f in new.funcs.values()} | {c.path for c in new.consts.values()}
    new_by_q: dict = {}
    for f in new.funcs.values():
        new_by_q.setdefault(f.qualname, []).append(f)
    new_c_by_q: dict = {}
    for c in new.consts.values():
        new_c_by_q.setdefault(c.qualname, []).append(c)
    for key, of in old.funcs.items():
        if not is_public(of.qualname):
            continue
        nf = new.funcs.get(key)
        if nf is None:
            if of.qualname in new_quals:
                # Moved to another file. If the old file is gone (renamed), compare it with its new home.
                cands = new_by_q.get(of.qualname, [])
                if of.path not in new_paths and len(cands) == 1:
                    nf = cands[0]
            else:
                changes.append(_removed_or_renamed(of, new, old_quals))
            if nf is None:
                continue
        rem = [p for p in of.params if p not in nf.params]
        add = [p for p in nf.params if p not in of.params]
        if len(rem) == 1 and len(add) == 1:
            changes.append(Change("param_renamed", of.qualname, param=rem[0], old=rem[0], new=add[0],
                                  path=nf.path, line=nf.line))
        else:
            for p in rem:
                changes.append(Change("param_removed", of.qualname, param=p, old=p, path=nf.path, line=nf.line))
        for p, d in of.params.items():
            if p in nf.params and d != nf.params[p] and not same_value(d, nf.params[p]):
                changes.append(Change("default_changed", of.qualname, param=p, old=d, new=nf.params[p],
                                      path=nf.path, line=nf.line))
    for key, oc in old.consts.items():
        nc = new.consts.get(key)
        if nc is None and oc.path not in new_paths and len(new_c_by_q.get(oc.qualname, [])) == 1:
            nc = new_c_by_q[oc.qualname][0]  # constant moved with its renamed file
        if nc and is_public(oc.qualname) and not same_value(oc.value, nc.value):
            changes.append(Change("const_changed", oc.qualname, old=oc.value, new=nc.value,
                                  path=nc.path, line=nc.line))
    return changes
