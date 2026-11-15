#!/usr/bin/env bash
# PostToolUse hook: run the relevant pytest suite after a .py or .md file is edited.
#
# Output is deliberately a short summary (result line + failing test names), never the
# raw test log, so the session that made the edit gets a signal without a log dump.
#   exit 0 -> tests passed or nothing to run (silent)
#   exit 2 -> tests failed; summary on stderr is fed back to the agent that edited
#   exit 1 -> could not run (no interpreter); shown to the user only

input="$(cat)"
file_path="$(printf '%s' "$input" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"

# Only Python and Markdown edits trigger a test run.
case "$file_path" in
  *.py|*.md) ;;
  *) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Pick an interpreter that has pytest and streamhub: $PYTHON, project venv, then PATH.
py=""
for cand in "$PYTHON" ".venv/Scripts/python.exe" ".venv/bin/python" "venv/Scripts/python.exe" "venv/bin/python" python python3 py; do
  [ -z "$cand" ] && continue
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import pytest, streamhub" >/dev/null 2>&1; then
    py="$cand"; break
  fi
done
if [ -z "$py" ]; then
  echo "run-tests hook: no Python with pytest and streamhub found (set \$PYTHON or run make install); tests skipped." >&2
  exit 1
fi

# Markdown edits run the doc-link check; Python edits run everything except the integration
# tests, which start a real hub and its apps (run them with `make test` before finishing).
case "$file_path" in
  *.md)
    suite="doc links (tests/test_docs.py)"
    log="$("$py" -m pytest -q -p no:cacheprovider tests/test_docs.py 2>&1)"; rc=$? ;;
  *)
    suite="unit and handler tests (tests/, without test_integration.py)"
    log="$("$py" -m pytest -q -p no:cacheprovider --ignore=tests/test_integration.py 2>&1)"; rc=$? ;;
esac

[ $rc -eq 0 ] && exit 0

{
  echo "Tests FAILED after editing $file_path — $suite."
  printf '%s\n' "$log" | grep -E '[0-9]+ (passed|failed|errors?)' | tail -n 1
  printf '%s\n' "$log" | grep -E '^(FAILED|ERROR) ' | head -n 15
  echo "Run the suite yourself for details."
} >&2
exit 2
