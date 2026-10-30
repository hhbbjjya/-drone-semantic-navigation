#!/usr/bin/env bash
# 部署/實驗前的守門：工作區必須乾淨，否則結果無法對應到任何 commit。
#   bash scripts/git/check_clean.sh            # 乾淨即通過
#   bash scripts/git/check_clean.sh --strict   # 另外要求 HEAD 正好在一個標籤上
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
  echo "✗ 工作區有未提交的修改或未追蹤檔案：" >&2
  git status --short >&2
  echo "請先 commit（現場請用 field/日期 分支），或確認檔案應列入 .gitignore。" >&2
  exit 1
fi

if [ "${1:-}" = "--strict" ] && ! git describe --exact-match --tags HEAD >/dev/null 2>&1; then
  echo "✗ --strict：HEAD 不在任何標籤上。請先執行 scripts/git/tag_experiment.sh <名稱>" >&2
  exit 1
fi

echo "✓ $(git describe --always --tags --dirty)  ($(git rev-parse --short HEAD))"
