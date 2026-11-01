"""Read repository snapshots at two revisions using the git CLI (no code is executed)."""
from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import tempfile

SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "site-packages", "build", "dist"}
DOC_EXT = (".md", ".markdown")
_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")   # never hang waiting for a password
_CLONES: list = []
_PR_URL = re.compile(r"^(https://github\.com/[\w.-]+/[\w.-]+?)(?:\.git)?/pull/(\d+)(?:[/?#].*)?$")


class RepoError(Exception):
    pass


@atexit.register
def _cleanup() -> None:
    for d in _CLONES:
        shutil.rmtree(d, ignore_errors=True)


def _run(cmd: list, timeout: int = 300, data: bytes = None):
    try:
        return subprocess.run(cmd, capture_output=True, env=_ENV, timeout=timeout, input=data)
    except subprocess.TimeoutExpired:
        raise RepoError("Git timed out. The repository may be very large or need a login (private repo).")
    except FileNotFoundError:
        raise RepoError("git is not installed or not on PATH.")


def _safe_rev(rev):
    if rev and (str(rev).startswith("-") or "\0" in str(rev)):
        raise RepoError(f"Invalid revision: {rev!r}")
    return rev


def _git(repo: str, *args: str) -> bytes:
    r = _run(["git", "-C", repo, "-c", "core.quotepath=off", *args], timeout=120)
    if r.returncode != 0:
        raise RepoError(r.stderr.decode(errors="replace").strip() or "git command failed")
    return r.stdout


def parse_pr_url(url: str):
    """'https://github.com/o/r/pull/12' -> ('https://github.com/o/r', 12), else None."""
    m = _PR_URL.match(url.strip())
    return (m.group(1), int(m.group(2))) if m else None


def clone(url: str) -> str:
    if not url.startswith(("https://", "http://", "git@")):
        raise RepoError("Enter a valid GitHub URL (https://github.com/owner/repo) or a local path.")
    dest = tempfile.mkdtemp(prefix="docsage_")
    _CLONES.append(dest)
    r = _run(["git", "clone", "--quiet", url, dest])
    if r.returncode != 0:
        raise RepoError("Could not clone repository: " + r.stderr.decode(errors="replace").strip())
    return dest


def clone_pr(url: str):
    """Clone a repo and fetch pull request N. Returns (repo_path, base, head) for load_compare."""
    pr = parse_pr_url(url)
    if not pr:
        raise RepoError("Not a pull request URL.")
    repo_url, n = pr
    repo = clone(repo_url)
    ref = f"docsage-pr-{n}"
    r = _run(["git", "-C", repo, "fetch", "--quiet", "origin", f"pull/{n}/head:{ref}"])
    if r.returncode != 0:
        raise RepoError(f"Could not fetch pull request #{n}: " + r.stderr.decode(errors="replace").strip())
    base = _git(repo, "merge-base", "origin/HEAD", ref).decode().strip()
    return repo, base, ref


def validate_repo(path: str) -> str:
    if not os.path.isdir(path):
        raise RepoError(f"Not a directory: {path}")
    return path


def _worktree(repo: str) -> dict:
    files = {}
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            if n.endswith((".py",) + DOC_EXT):
                p = os.path.join(root, n)
                with open(p, encoding="utf-8", errors="replace") as fh:
                    files[os.path.relpath(p, repo).replace(os.sep, "/")] = fh.read()
    return files


def _read_blobs(repo: str, rev: str, names: list) -> dict:
    """Read many files at a revision with a single git process."""
    if not names:
        return {}
    spec = "".join(f"{rev}:{n}\n" for n in names).encode()
    r = _run(["git", "-C", repo, "cat-file", "--batch"], timeout=180, data=spec)
    out, i, files = r.stdout, 0, {}
    for n in names:
        nl = out.find(b"\n", i)
        if nl < 0:
            break
        head = out[i:nl].split()
        if len(head) == 3 and head[1] == b"blob":
            size = int(head[2])
            files[n] = out[nl + 1:nl + 1 + size].decode(errors="replace")
            i = nl + 1 + size + 1
        else:
            i = nl + 1
    return files


def snapshot(repo: str, rev, only=None) -> dict:
    """{path: text} for .py and Markdown files at `rev` (None = working tree)."""
    if rev in (None, "", "WORKTREE"):
        files = _worktree(repo)
        return {k: v for k, v in files.items() if only is None or k in only}
    _safe_rev(rev)
    names = _git(repo, "ls-tree", "-r", "-z", "--name-only", rev).decode().split("\0")
    wanted = [n for n in names
              if n.endswith((".py",) + DOC_EXT) and not (set(n.split("/")) & SKIP_DIRS)
              and (only is None or n in only)]
    return _read_blobs(repo, rev, wanted)


def changed_files(repo: str, base: str, head) -> set:
    _safe_rev(base), _safe_rev(head)
    args = ["diff", "--name-only", "--no-renames", "-z", base] + ([head] if head not in (None, "", "WORKTREE") else [])
    return {n for n in _git(repo, *args).decode().split("\0") if n}


def load_compare(repo: str, base: str, head):
    """Return (old_py, new_py, docs). Old code is limited to files changed in the diff."""
    changed = changed_files(repo, base, head)
    old = {k: v for k, v in snapshot(repo, base, only=changed).items() if k.endswith(".py")}
    new_all = snapshot(repo, head)
    new_py = {k: v for k, v in new_all.items() if k.endswith(".py")}
    docs = {k: v for k, v in new_all.items() if k.endswith(DOC_EXT)}
    return old, new_py, docs


def load_scan(repo: str, rev=None):
    files = snapshot(repo, rev)
    return ({k: v for k, v in files.items() if k.endswith(".py")},
            {k: v for k, v in files.items() if k.endswith(DOC_EXT)})
