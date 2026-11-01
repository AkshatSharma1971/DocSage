# DocSage 📖

Keeps documentation in sync with code. Compares two versions of a Python repo (or a GitHub pull request), finds
public-API changes (defaults, parameters, removed or renamed functions, constants), and flags the exact Markdown
sentence that is now wrong. Runs fully local: **Ollama + Gemma** (`gemma4:e2b` by default). No cloud AI.

## Setup
```bash
pip install -r requirements.txt
ollama pull gemma4:e2b        # optional: without Ollama, rule-based detection still works
streamlit run app.py
```
In the dashboard, enter a local path, a GitHub repo URL, or a pull request URL
(`https://github.com/owner/repo/pull/N`).

## CLI / CI
```bash
python -m docsage.cli --repo . --base HEAD~1 --head HEAD      # PR / commit range
python -m docsage.cli --repo . --scan                          # documented defaults vs. current code
python -m docsage.cli --repo https://github.com/owner/repo --base v1.0 --head v1.1 --json
```
`--no-llm` skips Gemma, `--fail-on-drift` exits 1 on confirmed drift. See `.github-workflow-example.yml` for
using it in a pull request check.

## Example
`bash examples/run_example.sh` builds a small two-commit repo from `examples/input/` and writes DocSage's real
output to `examples/output/`. See `examples/README.md`.

## How it works
| Layer | Does | Trusted for |
|---|---|---|
| `code_facts.py` (AST) | functions, params, defaults, constants, class `__init__`, diffing | code truth |
| `doc_claims.py` | Markdown → sentences with file/line + heading context | doc locations |
| `matcher.py` | symbol + value matching, public-API filter | **Confirmed** drift |
| `llm.py` (Gemma) | explanations, rewrites, semantic judgement (JSON schema, temp 0) | **Potential** drift |

Gemma guardrails: it only sees one change + one sentence; semantic findings need an evidence quote that
literally appears in the sentence; rewrites must contain the new value/name or they are discarded;
Gemma never upgrades a finding to *Confirmed*.

## Statuses
- **Confirmed**: deterministic contradiction (doc says 10, code says 30).
- **Potential**: needs human review (Gemma-flagged, or weaker symbol match).
- **No drift found**: not proof the docs are correct.

## Tests
`python -m pytest -q` covers the five acceptance cases (changed default, internal change, removed function,
docs updated alongside code, unrelated private helper) plus renames, constants, full scan, file renames, PR URL
parsing, the git pipeline, and the Gemma guardrails (with a fake client, so no Ollama is needed). CI runs them
on every pull request.

## Limits
Python + Markdown only; static analysis only (nothing is executed); behavior changes inside function
bodies are not detected unless the docs are about a signature, default, or constant. The tool never posts
comments or issues to real projects.

## License
MIT
