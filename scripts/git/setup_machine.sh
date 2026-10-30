#!/usr/bin/env bash
# 每台機器第一次設定 Git。用法：
#   bash scripts/git/setup_machine.sh <onboard|vlm|backend> [--laptop-host HOST] [--dry-run]
#
# 角色與權限（依 docs/decisions/0002-git-access-per-machine.md）：
#   vlm     桌機 5070 Ti（WSL 內執行）  帳號 SSH 金鑰，可 push，金鑰需設 passphrase
#   backend 筆電 5070（SLAM 重型最佳化） 帳號 SSH 金鑰，可 push，並兼任現場 Git 伺服器
#   onboard 機載 Orin Nano（SLAM 前端） repo 限定 Deploy key：bring-up 可寫，飛行階段改唯讀；現場改動推到筆電
set -euo pipefail

GITHUB_REPO="${DSN_GITHUB_REPO:-hhbbjjya/-drone-semantic-navigation}"
HOST_ALIAS="github-dsn"
LAPTOP_HOST=""
DRY=0
ROLE="${1:-}"; shift || true

while [ $# -gt 0 ]; do
  case "$1" in
    --laptop-host) LAPTOP_HOST="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "未知參數：$1" >&2; exit 2 ;;
  esac
done

case "$ROLE" in onboard|vlm|backend) ;; *)
  echo "用法：$0 <onboard|vlm|backend> [--laptop-host HOST] [--dry-run]" >&2; exit 2 ;;
esac

run() { if [ "$DRY" = 1 ]; then printf '[dry-run] %s\n' "$*"; else "$@"; fi; }
info() { printf '\n== %s\n' "$*"; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$REPO_ROOT" ] || { echo "請在 repo 內執行" >&2; exit 1; }
SSH_DIR="${DSN_SSH_DIR:-$HOME/.ssh}"
KEY="$SSH_DIR/dsn_${ROLE}_ed25519"

# ---- 0. 環境檢查 ----
info "環境"
printf 'host=%s arch=%s git=%s\n' "$(hostname)" "$(uname -m)" "$(git --version | awk '{print $3}')"
case "$REPO_ROOT" in /mnt/[a-z]/*)
  echo "警告：repo 位於 Windows 磁碟（$REPO_ROOT）。WSL 下請 clone 到 ~ 以避免權限與效能問題。" >&2 ;;
esac

# ---- 1. 全域 Git 設定（只補未設定的身分，不覆蓋）----
info "全域 Git 設定"
if [ -z "$(git config --global user.name || true)" ] || [ -z "$(git config --global user.email || true)" ]; then
  echo "尚未設定 user.name / user.email。請執行（三台使用相同身分；機器由 provenance 紀錄區分）："
  echo "  git config --global user.name  \"你的名字\""
  echo "  git config --global user.email \"你的 GitHub email\""
fi
run git config --global init.defaultBranch main
run git config --global pull.ff only          # 部署機不會意外產生合併 commit
run git config --global fetch.prune true
run git config --global push.autoSetupRemote true
run git config --global core.autocrlf input   # WSL/Linux：提交時轉 LF，不轉回 CRLF

# ---- 2. Repo 層級設定 ----
info "Repo 設定"
run git -C "$REPO_ROOT" config core.hooksPath .githooks
run chmod +x "$REPO_ROOT/.githooks/pre-commit"

# ---- 3. SSH 金鑰（每台、每用途一把）----
info "SSH 金鑰：$KEY"
run mkdir -p "$SSH_DIR"; run chmod 700 "$SSH_DIR"
if [ -f "$KEY" ]; then
  echo "已存在，沿用。"
elif [ "$ROLE" = onboard ]; then
  # 機載需無人值守開機拉取：無 passphrase，但權限僅限單一 repo 唯讀
  run ssh-keygen -t ed25519 -N "" -C "dsn-${ROLE}@$(hostname)" -f "$KEY"
else
  echo "開發機金鑰請設定 passphrase（接著會提示輸入）"
  run ssh-keygen -t ed25519 -C "dsn-${ROLE}@$(hostname)" -f "$KEY"
fi

# ---- 4. ~/.ssh/config 主機別名：讓這個 repo 固定用這把鑰匙 ----
CFG="$SSH_DIR/config"
if ! grep -qs "^Host $HOST_ALIAS\$" "$CFG"; then
  BLOCK="
Host $HOST_ALIAS
    HostName github.com
    User git
    IdentityFile $KEY
    IdentitiesOnly yes
"
  if [ "$DRY" = 1 ]; then printf '[dry-run] append to %s:%s' "$CFG" "$BLOCK"
  else printf '%s' "$BLOCK" >> "$CFG"; chmod 600 "$CFG"; fi
fi

# ---- 5. Remote ----
info "Remote"
run git -C "$REPO_ROOT" remote set-url origin "git@${HOST_ALIAS}:${GITHUB_REPO}.git"
if [ "$ROLE" = onboard ]; then
  if [ -n "$LAPTOP_HOST" ]; then
    url="${LAPTOP_HOST}:repos/drone-semantic-navigation.git"
    if git -C "$REPO_ROOT" remote get-url field >/dev/null 2>&1; then
      run git -C "$REPO_ROOT" remote set-url field "$url"
    else
      run git -C "$REPO_ROOT" remote add field "$url"
    fi
  else
    echo "提示：加上 --laptop-host user@筆電主機名 以設定現場 remote（field）。"
  fi
fi

# ---- 6. 接下來要手動做的事 ----
info "請完成以下步驟"
PUB="$KEY.pub"
[ -f "$PUB" ] && { echo "公鑰："; cat "$PUB"; }
case "$ROLE" in
  vlm|backend)
    echo "→ GitHub > Settings > SSH and GPG keys > New SSH key，貼上公鑰（標題寫 dsn-${ROLE}）" ;;
  onboard)
    echo "→ GitHub repo > Settings > Deploy keys > Add deploy key，貼上公鑰"
    echo "  標題 dsn-onboard。權限分兩階段（ADR 0002）："
    echo "    bring-up 階段（在機上開發 SLAM 前端/硬體介面）：勾選 Allow write access，只推功能分支"
    echo "    飛行階段（會帶出去、可能墜機之前）：刪除後以【不勾選】寫入權限重新加入同一把公鑰"
    echo "→ 建議同時在 GitHub 為 main 開啟分支保護，機載金鑰就無法直接改 main"
    echo "→ 飛行階段前，在筆電執行 scripts/git/setup_field_remote.sh，把上面公鑰加入筆電授權（腳本會印出格式）" ;;
esac
echo "→ 驗證：ssh -T git@${HOST_ALIAS}   以及   git -C \"$REPO_ROOT\" fetch origin"
echo "→ 環境檢查：python3 scripts/env_check.py"
