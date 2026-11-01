"""python -m docsage.cli --repo . --base HEAD~1 --head HEAD   (or --scan)"""
from __future__ import annotations

import argparse
import json
import sys

from . import git_diff
from .detector import run_compare, run_scan
from .llm import DEFAULT_HOST, DEFAULT_MODEL, OllamaClient


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="docsage")
    ap.add_argument("--repo", default=".", help="local path or GitHub URL")
    ap.add_argument("--base", default="HEAD~1")
    ap.add_argument("--head", default="HEAD", help="revision, or WORKTREE for uncommitted changes")
    ap.add_argument("--scan", action="store_true", help="full scan of documented defaults instead of a diff")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on-drift", action="store_true", help="exit 1 if confirmed drift is found")
    a = ap.parse_args(argv)
    try:
        repo = git_diff.clone(a.repo) if a.repo.startswith(("http", "git@")) else git_diff.validate_repo(a.repo)
        client, note = None, ""
        if not a.no_llm:
            c = OllamaClient(a.model, a.host)
            note = c.status()
            client = None if note else c
        if a.scan:
            rep = run_scan(*git_diff.load_scan(repo, None), client=client)
        else:
            rep = run_compare(*git_diff.load_compare(repo, a.base, a.head), client=client)
    except git_diff.RepoError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    rep.llm_note = note
    if a.json:
        print(json.dumps(rep.to_dict(), indent=2))
    else:
        print(f"DocSage: {rep.py_files} Python / {rep.md_files} Markdown files, "
              f"{len(rep.confirmed)} confirmed, {len(rep.potential)} potential")
        if note:
            print(f"(Gemma disabled: {note})")
        for f in rep.findings:
            print(f"\n[{f.status.upper()}] {f.doc_path}:{f.doc_line}\n  doc : {f.doc_text}\n"
                  f"  code: {f.code_path}:{f.code_line}  {f.change}\n  why : {f.explanation}")
            if f.suggested_fix:
                print(f"  fix : {f.suggested_fix}")
        if not rep.findings:
            print("No drift found. (This does not prove the docs are correct.)")
    return 1 if a.fail_on_drift and rep.confirmed else 0


if __name__ == "__main__":
    sys.exit(main())
