#!/usr/bin/env bash
# Enable repo-tracked git hooks (.githooks/). Run once per clone.
set -e
cd "$(dirname "$0")/.."
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "✓ Git hooks enabled — auto-bump SW VERSION on UI commits."
echo "  To disable: git config --unset core.hooksPath"
