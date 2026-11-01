"""DocSage dashboard.  Run:  streamlit run app.py"""
import pandas as pd
import streamlit as st

from docsage import git_diff
from docsage.detector import run_compare, run_scan
from docsage.llm import DEFAULT_HOST, DEFAULT_MODEL, OllamaClient
from docsage.theme import CSS, header

st.set_page_config(page_title="DocSage", page_icon="📖", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown(header(), unsafe_allow_html=True)

with st.sidebar:
    st.header("Repository")
    source = st.text_input("GitHub URL, PR URL or local path", value="/Users/akshatsharma/docsage-demo2")
    mode = st.radio("Mode", ["Pull request / commit range", "Full repository scan"])
    base, head = "HEAD~1", "HEAD"
    if mode.startswith("Pull"):
        base = st.text_input("Base revision", "HEAD~1", help="e.g. main, origin/main, a commit SHA")
        head = st.text_input("Head revision", "HEAD", help="Use WORKTREE for uncommitted changes")
    st.header("Gemma (Ollama)")
    use_llm = st.toggle("Use Gemma", value=True)
    model = st.text_input("Model", DEFAULT_MODEL)
    host = st.text_input("Ollama host", DEFAULT_HOST, disabled=True)
    max_llm = st.slider("Max semantic checks", 0, 50, 15, help="Each is one local Gemma call.")
    go = st.button("Analyze", type="primary", width="stretch")

if go:
    client, note = None, ""
    if use_llm:
        c = OllamaClient(model, host)
        note = c.status()
        client = None if note else c
        if note:
            st.warning(f"Gemma is off for this run: {note} Rule-based detection still works.")
    try:
        with st.spinner("Analyzing…"):
            pr_mode = bool(git_diff.parse_pr_url(source))
            if pr_mode:
                repo, base, head = git_diff.clone_pr(source)
            else:
                repo = git_diff.clone(source) if source.startswith(("http", "git@")) else git_diff.validate_repo(source)
            if mode.startswith("Pull") or pr_mode:
                rep = run_compare(*git_diff.load_compare(repo, base, head), client=client, max_llm=max_llm)
            else:
                rep = run_scan(*git_diff.load_scan(repo, None), client=client)
    except git_diff.RepoError as e:
        st.error(str(e))
        st.stop()
    st.session_state["rep"] = rep

rep = st.session_state.get("rep")
if rep is None:
    st.info("Press **Analyze** in the sidebar.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Python files scanned", rep.py_files)
c2.metric("Markdown files scanned", rep.md_files)
c3.metric("Confirmed drift", len(rep.confirmed))
c4.metric("Potential drift", len(rep.potential))
if rep.skipped:
    st.warning("Could not parse (skipped): " + ", ".join(rep.skipped))

if not rep.findings:
    st.success("No drift found for the analyzed change. This does not prove all documentation is correct.")
    st.stop()

fc, fs = st.columns(2)
show = fc.multiselect("Status", ["confirmed", "potential"], default=["confirmed", "potential"])
sort = fs.selectbox("Sort by", ["Status", "Doc file / line"])
items = [f for f in rep.findings if f.status in show]
if sort != "Status":
    items.sort(key=lambda f: (f.doc_path, f.doc_line))

st.dataframe(pd.DataFrame([{
    "Status": f.status, "Doc": f"{f.doc_path}:{f.doc_line}", "Code": f"{f.code_path}:{f.code_line}",
    "Documented": f.old_value if f.old_value is not None else "—",
    "Actual": f.new_value if f.new_value is not None else "—", "Change": f.change} for f in items]),
    width="stretch", hide_index=True)

for f in items:
    icon = "🔴" if f.status == "confirmed" else "🟡"
    with st.expander(f"{icon} {f.status.title()} drift · {f.doc_path}:{f.doc_line} · {f.change}"):
        st.markdown("**Documentation says**")
        st.code(f.doc_text, language="markdown")
        st.markdown(f"**Code** · `{f.code_path}:{f.code_line}` · {f.change}")
        if f.old_value is not None or f.new_value is not None:
            a, b = st.columns(2)
            a.metric("Old / documented", f.old_value if f.old_value is not None else "—")
            b.metric("New / actual", f.new_value if f.new_value is not None else "—")
        st.markdown(f"**Why:** {f.explanation}")
        if f.suggested_fix:
            st.markdown("**Suggested rewrite**")
            st.code(f.suggested_fix, language="markdown")
        st.caption(f"Source: {f.source}")
