#!/usr/bin/env bash
# install-hooks.sh — copy the repo's pre-commit hook into .git/hooks/
# Run once after cloning: bash scripts/install-hooks.sh
set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
SRC="$REPO_ROOT/scripts/pre-commit.hook"
DST="$REPO_ROOT/.git/hooks/pre-commit"
cp "$SRC" "$DST"
chmod +x "$DST"
echo "pre-commit hook installed at $DST"
echo "It will block commits containing hardcoded passwords or secrets."
