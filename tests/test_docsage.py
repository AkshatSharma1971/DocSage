import os
import subprocess
import tempfile

from docsage import git_diff
from docsage.detector import run_compare, run_scan

CODE_V1 = "def fetch(url, timeout=10, retries=3):\n    return _helper(url)\n\ndef _helper(x):\n    return x\n\nMAX_SIZE = 100\n"
DOC_V1 = "# API\n\n## `fetch()`\n\nThe `timeout` parameter defaults to 10 seconds.\n"


def analyze(old, new, doc, client=None):
    return run_compare({"lib.py": old}, {"lib.py": new}, {"README.md": doc}, client=client)


def test_1_changed_default():
    r = analyze(CODE_V1, CODE_V1.replace("timeout=10", "timeout=30"), DOC_V1)
    assert len(r.confirmed) == 1
    f = r.confirmed[0]
    assert (f.doc_path, f.doc_line, f.old_value, f.new_value) == ("README.md", 5, "10", "30")
    assert "30" in f.suggested_fix and "10" not in f.suggested_fix


def test_2_internal_change():
    r = analyze(CODE_V1, CODE_V1.replace("return _helper(url)", "y = _helper(url)\n    return y"), DOC_V1)
    assert r.findings == []


def test_3_removed_function():
    new = "def other():\n    pass\n"
    r = analyze(CODE_V1, new, "Call `fetch(url)` to download a file.\n")
    assert [f.kind for f in r.findings] == ["function_removed"]


def test_4_docs_updated_alongside_code():
    r = analyze(CODE_V1, CODE_V1.replace("timeout=10", "timeout=30"), DOC_V1.replace("10", "30"))
    assert r.findings == []


def test_5_unrelated_private_helper():
    r = analyze(CODE_V1, CODE_V1.replace("def _helper(x):\n    return x", "def _helper(x, extra=10):\n    return x"),
                "The helper uses 10 as a limit. `_helper` is internal.\n")
    assert r.findings == []


def test_param_rename():
    r = analyze(CODE_V1, CODE_V1.replace("retries=3", "attempts=3"), "Set `retries` on `fetch` to retry failures.\n")
    assert r.confirmed and r.confirmed[0].kind == "param_renamed"
    assert "attempts" in r.confirmed[0].suggested_fix


def test_constant_change():
    r = analyze(CODE_V1, CODE_V1.replace("MAX_SIZE = 100", "MAX_SIZE = 500"), "`MAX_SIZE` is 100 bytes.\n")
    assert r.confirmed and r.confirmed[0].new_value == "500"


def test_full_scan_finds_stale_default():
    py = {"lib.py": CODE_V1.replace("timeout=10", "timeout=30")}
    r = run_scan(py, {"README.md": DOC_V1})
    assert len(r.confirmed) == 1 and r.confirmed[0].old_value == "10"
    assert run_scan({"lib.py": CODE_V1}, {"README.md": DOC_V1}).findings == []


class FakeGemma:
    def __init__(self, judge): self._judge = judge
    def explain(self, ch, cl): return {"explanation": "Because.", "suggested_fix": "garbage"}
    def judge(self, ch, cl): return self._judge


def test_gemma_evidence_must_be_in_sentence():
    doc = "Calling `fetch` retries until the server answers.\n"
    new = CODE_V1.replace("retries=3", "retries=0")
    bad = FakeGemma({"drifted": True, "evidence": "invented quote", "explanation": "x", "suggested_fix": "y"})
    assert analyze(CODE_V1, new, doc, bad).findings == []
    good = FakeGemma({"drifted": True, "evidence": "retries until the server answers",
                      "explanation": "Retries are now off.", "suggested_fix": "Calling `fetch` does not retry."})
    r = analyze(CODE_V1, new, doc, good)
    assert len(r.potential) == 1 and r.potential[0].source == "gemma"


def test_gemma_fix_without_new_value_is_rejected():
    r = analyze(CODE_V1, CODE_V1.replace("timeout=10", "timeout=30"), DOC_V1, FakeGemma({"drifted": False}))
    assert r.confirmed[0].explanation == "Because." and "30" in r.confirmed[0].suggested_fix


def test_git_pipeline():
    d = tempfile.mkdtemp()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    def sh(*a): subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, env=env)
    sh("init", "-q")
    open(f"{d}/lib.py", "w").write(CODE_V1); open(f"{d}/README.md", "w").write(DOC_V1)
    sh("add", "."); sh("commit", "-qm", "v1")
    open(f"{d}/lib.py", "w").write(CODE_V1.replace("timeout=10", "timeout=30"))
    sh("commit", "-qam", "v2")
    r = run_compare(*git_diff.load_compare(d, "HEAD~1", "HEAD"))
    assert len(r.confirmed) == 1 and r.confirmed[0].doc_line == 5


def test_pr_url_parsing_and_safe_revisions():
    assert git_diff.parse_pr_url("https://github.com/o/r/pull/12") == ("https://github.com/o/r", 12)
    assert git_diff.parse_pr_url(" https://github.com/o/r.git/pull/3/files ") == ("https://github.com/o/r", 3)
    assert git_diff.parse_pr_url("https://github.com/o/r") is None
    assert git_diff.parse_pr_url("https://evil.com/o/r/pull/1") is None
    try:
        git_diff._safe_rev("--upload-pack=x")
        assert False
    except git_diff.RepoError:
        pass


def test_hard_wrapped_sentence_is_one_claim():
    from docsage.doc_claims import parse_markdown
    cl = parse_markdown("R.md", "## `fetch()`\n\nThe `timeout` parameter defaults to\n10 seconds.\nNext sentence.\n")
    assert [(c.line, c.text) for c in cl][1:] == [(3, "The `timeout` parameter defaults to 10 seconds."), (5, "Next sentence.")]


def test_default_change_survives_file_rename():
    d = tempfile.mkdtemp()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    def sh(*a): subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, env=env)
    sh("init", "-q")
    pad = "".join(f"def helper{i}(x):\n    return x + {i}\n\n" for i in range(8))
    src = pad + "MAX_SIZE = 100\n\ndef fetch(url, timeout=10):\n    return url\n"
    with open(f"{d}/lib.py", "w") as fh: fh.write(src)
    with open(f"{d}/README.md", "w") as fh:
        fh.write("## `fetch()`\n\nThe `timeout` parameter defaults to 10 seconds.\n\n`MAX_SIZE` is 100 bytes.\n")
    sh("add", "."); sh("commit", "-qm", "v1")
    sh("mv", "lib.py", "core.py")
    with open(f"{d}/core.py", "w") as fh: fh.write(src.replace("timeout=10", "timeout=30").replace("= 100", "= 500"))
    sh("add", "-A"); sh("commit", "-qm", "rename + change")
    r = run_compare(*git_diff.load_compare(d, "HEAD~1", "HEAD"))
    assert sorted(f.kind for f in r.confirmed) == ["const_changed", "default_changed"]
