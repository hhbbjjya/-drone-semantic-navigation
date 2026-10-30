# ADR 0002：每台機器的 Git 存取權限與 remote 拓撲

- 狀態：採用
- 日期：2026-10-30（同日修訂：機載權限改為分階段）

## 背景
三台機器都需要 Git，但風險不同：

| 機器 | 角色 | 風險 | 是否需要推送 |
|---|---|---|---|
| 桌機（WSL） | `vlm` | 實驗室共用、可能多人使用 | 是，主要開發機 |
| 筆電 | `backend` | 會帶到現場、可能遺失 | 是，開發機＋現場伺服器 |
| 機載 Orin Nano | `onboard` | 可能墜機、遺失、被他人拿到；開機需無人值守拉取 | bring-up 階段需要；飛行階段不需要 |

第一性原理：**一把金鑰被偷時，損失範圍應該等於那台機器在「當下」真正需要的權限**（最小權限）。
「當下」很重要：SLAM 前端與硬體介面都在機載上，bring-up 階段必須能直接在機上開發。

## 選項
1. 三台都用帳號層級 SSH 金鑰：最簡單；但無人機上的無密碼金鑰外流＝整個 GitHub 帳號所有 repo 可被讀寫。
2. 在機載用 `gh auth login`（HTTPS Token）：Token 通常涵蓋整個帳號，風險同上。
3. Fine-grained Personal Access Token：可設到期日與範圍；但需定期更新，過期會在現場突然失效。
4. **混合＋分階段（採用）**：開發機用帳號金鑰（有 passphrase）；機載用本 repo 限定的 Deploy key，bring-up 可寫、飛行唯讀。

## 決定
- **桌機、筆電**：各自產生一把 ed25519 金鑰，設 passphrase，加到 GitHub 帳號。桌機的金鑰產生在 WSL 內，而非 Windows。
- **機載**：一把無 passphrase 的 ed25519 金鑰，加為本 repo 的 Deploy key。
  - **bring-up 階段**：勾選 Allow write access，可直接推送功能分支。
  - **飛行階段**（第一次會帶到戶外或可能墜機之前）：到 GitHub 取消寫入權限（刪除後以唯讀重新加入同一把公鑰）。
- 每台以 `~/.ssh/config` 的 `github-dsn` 主機別名綁定專用金鑰（`IdentitiesOnly yes`）。
- 三台使用相同 `user.name / user.email`；機器差異由 provenance 的 `host` / `role` 欄位記錄，不靠 Git 身分區分。

### Remote 拓撲（飛行階段）

```
              GitHub（唯一真相來源）
             ▲ push/pull      ▲ push/pull      ▲ pull（唯讀 deploy key）
           桌機              筆電               機載
                              │ bare repo ~/repos/drone-semantic-navigation.git
                              └──── field remote ◀── push field/* 分支、pull ── 機載（現場無外網）
```

- 機載對筆電的推送使用 `authorized_keys` 中的 `restrict` + `git-shell` 限制，只能做 Git 操作。
- 筆電上的 bare repo 拒絕非快轉與刪除。
- 現場修改一律在 `field/<日期>` 分支，回到有網路後由筆電 `sync_field.sh` 推上 GitHub，再以 PR 合併。

## 後果
- 機載金鑰外流時：最多影響這一個 repo（飛行階段只能讀），且只能對筆電做受限 Git 操作。處理方式：在 GitHub 刪除該 Deploy key、從筆電 authorized_keys 移除該行。
- bring-up 階段的寫入金鑰外流：攻擊者可推送到本 repo。對策：`main` 開啟分支保護（需 PR 才能合併），機載只推功能分支。
- 筆電遺失時：passphrase 爭取時間；立即在 GitHub 撤銷該金鑰。
- 若 repo 轉為 private，機載 Deploy key 仍可運作，無需改設定。

## 金鑰紀錄

| 角色 | 主機名 | 指紋（`ssh-keygen -lf <key>.pub`） | 加入日期 | 寫入權限 | 撤銷日期 |
|---|---|---|---|---|---|
| vlm | | | | 帳號金鑰 | |
| backend | | | | 帳號金鑰 | |
| onboard | | | | bring-up：是 → 飛行：否 | |
