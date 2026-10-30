#!/usr/bin/env bash
# 為一次實驗建立附註標籤：exp/YYYY-MM-DD-<名稱>
#   bash scripts/git/tag_experiment.sh hover01 "第一次定高懸停，室內，無 VLM"
set -euo pipefail
name="${1:?用法：$0 <名稱> [說明]}"
msg="${2:-$name}"
case "$name" in *[!a-z0-9_-]*) echo "名稱只用小寫英數、- 與 _" >&2; exit 2 ;; esac

REPO_ROOT="$(git rev-parse --show-toplevel)"
bash "$REPO_ROOT/scripts/git/check_clean.sh"

tag="exp/$(date +%F)-$name"
git -C "$REPO_ROOT" tag -a "$tag" -m "$msg"
echo "已建立 $tag"
echo "推送：git push origin $tag   （現場無網路：git push field $tag）"
