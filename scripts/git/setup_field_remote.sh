#!/usr/bin/env bash
# 在【筆電】執行一次：建立現場用的 bare repo，讓 Jetson 在沒有外網時從筆電拉程式、推回現場修改。
#   bash scripts/git/setup_field_remote.sh [--onboard-pubkey /path/to/dsn_onboard_ed25519.pub] [--dry-run]
set -euo pipefail

BARE="${DSN_FIELD_BARE:-$HOME/repos/drone-semantic-navigation.git}"
PUBKEY=""
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --onboard-pubkey) PUBKEY="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "未知參數：$1" >&2; exit 2 ;;
  esac
done
run() { if [ "$DRY" = 1 ]; then printf '[dry-run] %s\n' "$*"; else "$@"; fi; }

REPO_ROOT="$(git rev-parse --show-toplevel)"

if [ ! -d "$BARE" ]; then
  run mkdir -p "$(dirname "$BARE")"
  run git init --bare -b main "$BARE"
  # 現場只允許快轉更新 main，避免 Jetson 意外覆蓋歷史
  run git -C "$BARE" config receive.denyNonFastForwards true
  run git -C "$BARE" config receive.denyDeletes true
fi

if git -C "$REPO_ROOT" remote get-url field >/dev/null 2>&1; then
  run git -C "$REPO_ROOT" remote set-url field "$BARE"
else
  run git -C "$REPO_ROOT" remote add field "$BARE"
fi
if ! git -C "$REPO_ROOT" show-ref --verify --quiet refs/heads/main; then
  echo "本機沒有 main 分支。先執行：git fetch origin && git switch main" >&2
  exit 1
fi
run git -C "$REPO_ROOT" push field main --tags

echo
echo "現場 bare repo：$BARE"
echo "出發前更新：git push field main --tags"
echo "回到有網路時：bash scripts/git/sync_field.sh"

if [ -n "$PUBKEY" ]; then
  [ -f "$PUBKEY" ] || { echo "找不到公鑰：$PUBKEY" >&2; exit 1; }
  echo
  echo "把下面這一行加入筆電的 ~/.ssh/authorized_keys。"
  echo "restrict + git-shell 讓 Jetson 的金鑰只能做 git 操作，拿不到筆電的 shell："
  printf 'command="git-shell -c \\"$SSH_ORIGINAL_COMMAND\\"",restrict %s\n' "$(cat "$PUBKEY")"
fi
