#!/usr/bin/env bash
# Builds a throwaway git repo from examples/input (v1, then v2) and runs DocSage on that change.
# Output goes to examples/output/. Set DOCSAGE_ARGS=--no-llm to skip Gemma.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HERE/.."
PY="${PYTHON:-python}"
TMP="$(mktemp -d)"
cd "$TMP"
git init -q
git config user.name demo
git config user.email demo@example.com
cp "$HERE"/input/v1/* . && git add . && git commit -qm "v1"
cp "$HERE"/input/v2/* . && git add . && git commit -qm "v2: new defaults, rename, removal"
cd "$ROOT"
mkdir -p "$HERE/output"
$PY -m docsage.cli --repo "$TMP" --base HEAD~1 --head HEAD ${DOCSAGE_ARGS:-} | tee "$HERE/output/report.txt"
$PY -m docsage.cli --repo "$TMP" --base HEAD~1 --head HEAD ${DOCSAGE_ARGS:-} --json > "$HERE/output/report.json"
