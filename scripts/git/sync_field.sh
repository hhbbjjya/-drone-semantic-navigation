#!/usr/bin/env bash
# 在【筆電】執行：把 Jetson 推到現場 bare repo 的 field/* 分支與實驗標籤，同步回 GitHub。
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

git fetch field --tags
branches=$(git for-each-ref --format='%(refname:strip=4)' 'refs/remotes/field/field/*')
if [ -z "$branches" ]; then
  echo "現場沒有新的 field/* 分支。"
else
  for b in $branches; do
    echo "同步 field/$b → origin"
    git push origin "refs/remotes/field/field/$b:refs/heads/field/$b"
  done
fi
git push origin --tags
echo "完成。現場分支請在 GitHub 開 PR 審查後再合併進 main。"
