"""Markdown -> sentence-level claims with file and line numbers."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Claim:
    path: str
    line: int
    text: str
    context: str = ""     # nearest heading above (e.g. "`fetch()`")
    in_code: bool = False


_HEAD = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_LEAD = re.compile(r"^\s*(?:[-*+>]\s+|\d+[.)]\s+|#{1,6}\s+)+")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\[(])")
_END = re.compile(r"[.!?:]$")


def parse_markdown(path: str, text: str) -> list:
    """One claim per sentence. Hard-wrapped lines that continue a sentence are joined."""
    claims, fence, ctx = [], False, ""
    buf, start = [], 0

    def emit(s: str, line: int) -> None:
        for sent in _SENT.split(s):
            if sent.strip():
                claims.append(Claim(path, line, sent.strip(), ctx))

    def flush() -> None:
        nonlocal buf, start
        if buf:
            emit(" ".join(buf), start)
        buf, start = [], 0

    for i, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if s.startswith(("```", "~~~")):
            flush()
            fence = not fence
            continue
        if not s:
            flush()
            continue
        if fence:
            claims.append(Claim(path, i, s, ctx, True))
            continue
        m = _HEAD.match(raw)
        body = _LEAD.sub("", raw).strip()
        if re.fullmatch(r"[\s|:\-]+", body):
            flush()
            continue  # table separator row
        if m:
            flush()
            ctx = m.group(1).strip()
            emit(body, i)
            continue
        if body.startswith("|"):
            flush()
            emit(" | ".join(c.strip() for c in body.strip("|").split("|")), i)
            continue
        if _LEAD.match(raw) or (buf and _END.search(buf[-1])):
            flush()  # new list item, or the previous line ended a sentence
        if not buf:
            start = i
        buf.append(body)
    flush()
    return claims
