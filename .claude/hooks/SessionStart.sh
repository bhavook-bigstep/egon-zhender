#!/bin/bash
# Injected into context at the start of every Claude Code session.
# Keep this fast (< 2s) and resilient to running outside a git repo.

echo "=== Session Context ==="
echo "Branch: $(git branch --show-current 2>/dev/null || echo 'N/A (not a git repo)')"
echo "Last 5 commits:"
git log --oneline -5 2>/dev/null || echo "  (no commits yet)"
echo ""

CHANGES=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
echo "Uncommitted changes: ${CHANGES:-0} files"
if [ "${CHANGES:-0}" -gt "0" ]; then
  echo "Changed files:"
  git status --porcelain 2>/dev/null | head -10
fi
echo ""

echo "Prince Houston Data Cleansing — POC (RFP EZ-PH-DC-2026-01)."
echo "Contracts: source is READ-ONLY | no external inference without written approval |"
echo "every output row explainable + scored | runs reproducible (manifest+config+ledger)."

if [ -f docs/solutions/INDEX.md ]; then
  echo "Reminder: search docs/solutions/INDEX.md before implementing."
fi

if [ -d tasks ] && [ -f tasks/todo.md ]; then
  echo "Open tasks: see tasks/todo.md"
fi
echo "======================"
