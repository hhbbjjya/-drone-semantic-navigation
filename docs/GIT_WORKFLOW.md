# Git 工作流程（三台機器）

> 權限與拓撲的理由見 [ADR 0002](decisions/0002-git-access-per-machine.md)。

## 一、每台機器第一次設定

```bash
# 三台都一樣：先 clone（桌機請在 WSL 家目錄，不要放 /mnt/c）
git clone https://github.com/hhbbjjya/-drone-semantic-navigation.git ~/drone-semantic-navigation
cd ~/drone-semantic-navigation
cp .env.example .env            # 填入 DSN_ROLE 等

# 依角色執行（先加 --dry-run 看會做什麼）
bash scripts/git/setup_machine.sh vlm                                   # 桌機
bash scripts/git/setup_machine.sh backend                               # 筆電
bash scripts/git/setup_machine.sh onboard --laptop-host user@nb-backend.local   # 機載

# 筆電額外一次：建立現場 bare repo，並授權機載金鑰
bash scripts/git/setup_field_remote.sh --onboard-pubkey /path/to/dsn_onboard_ed25519.pub

# 每台都做：環境檢查
python3 scripts/env_check.py
```

## 二、日常開發（桌機、筆電）

```bash
git switch main && git pull
git switch -c feat/stereo-capture     # 短命分支，一個主題一條
# ...修改、測試...
git add -p && git commit              # pre-commit hook 會擋大檔與機密
git push                              # 到 GitHub 開 PR，自己 review 後合併
```

Commit 訊息格式建議：`<範圍>: <做了什麼>`，例如 `onboard: 加入雙目時間戳同步`、`interfaces: semantic_goal 升到 v2`。

## 三、實驗

```bash
# 1. 寫實驗設定
cp config/experiments/_template.yaml config/experiments/2026-11-05-hover01.yaml
git add config/experiments/2026-11-05-hover01.yaml && git commit -m "exp: hover01 設定"

# 2. 打標籤（會先檢查工作區乾淨）
bash scripts/git/tag_experiment.sh hover01 "室內定高懸停，無 VLM"
git push origin --tags

# 3. 三台都切到同一個標籤
git fetch --tags && git switch --detach exp/2026-11-05-hover01
bash scripts/git/check_clean.sh --strict
```

論文的圖表與表格一律註明標籤名稱。

## 四、現場（沒有外網）

```bash
# 出發前，在筆電
git push field main --tags

# 現場，在機載
git fetch field --tags && git switch --detach exp/2026-11-05-hover01

# 現場必須改程式時（機載或筆電）
git switch -c field/2026-11-05
git commit -am "field: 降低前端特徵數，解決 CPU 滿載"
git push field field/2026-11-05       # 機載推到筆電

# 回到有網路，在筆電
bash scripts/git/sync_field.sh        # 推上 GitHub，再開 PR 審查
```

## 五、不能做的事

| 不要 | 原因 | 改成 |
|---|---|---|
| 在機載電腦上長期開發 | 無法推 GitHub、容易遺失 | 在桌機/筆電開發，機載只拉取 |
| 帶著未提交修改跑正式實驗 | 結果無法追溯 | `check_clean.sh --strict` |
| `git push --force` 到 main | 改寫別台機器已拉取的歷史 | 新增修正 commit |
| commit 權重、rosbag、`.ulg`、`.env` | 體積、隱私、機密 | hook 會擋；放 NAS 或 `.env` |
| 用 `--no-verify` 當習慣 | 繞過檢查 | 只在緊急時用，事後補查 |

## 六、萬一機密被 commit 了

1. **先撤銷**該金鑰/Token（GitHub、Hugging Face 後台），這是唯一真正有效的步驟。
2. 再清理歷史（`git filter-repo`），並通知所有機器重新 clone。
3. 已推到公開 repo 的內容，要假設已被複製。
