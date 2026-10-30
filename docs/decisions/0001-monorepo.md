# ADR 0001：三台機器共用單一 repo（monorepo）

- 狀態：採用
- 日期：2026-10-30

## 背景
系統分佈在機載 Orin Nano、桌機 5070 Ti、筆電 5070 三台機器。三者之間有介面合約（訊息格式、座標系、時間戳、JSON schema）。論文要求每個結果可追溯到確切的程式版本。

## 選項
1. **三個 repo**：各自獨立、權限可分開。但介面變更要跨 repo 同步，容易出現版本錯配，且「系統版本」需要額外記錄三個 hash。
2. **單一 repo**：一個 commit 就是整個系統的狀態；介面變更可原子化提交。代價是機載電腦也會拉到用不到的程式碼。

## 決定
採用單一 repo，以頂層目錄區分角色（onboard/、slam/、semantic/；SLAM 前後端同在 slam/，見 ADR 0004），共用部分放 common/ 與 interfaces/。

## 後果
- 機載電腦 clone 整個 repo；目前體積小，可接受。若日後過大，可用 sparse checkout 只取需要的目錄。
- 第三方大型程式（SLAM 系統）不直接放入，以 fork + 固定 commit 引用。
