# 系統架構

> 狀態標示：✅ 已完成　🚧 進行中　📋 規劃中

## 角色與機器

| 角色 | 機器 | 職責 | 程式位置 | 狀態 |
|---|---|---|---|---|
| `onboard` | Jetson Orin Nano（機載） | 雙目擷取、Pixhawk MAVLink 橋接、**SLAM 前端（即時）** | `onboard/`、`slam/frontend/` | 🚧 MAVLink 讀取已驗證 |
| `backend` | 筆電 RTX 5070 | **SLAM 重型最佳化**（迴圈閉合、全域 BA）；現場 Git 伺服器 | `slam/backend/` | 📋 |
| `vlm` | 桌機 RTX 5070 Ti | VLM / VLA 語意推論 | `roomscan/`（之後移到 `semantic/`） | ✅ 離線房間語意掃描 v2.1 |

共用：`slam/core/`（前後端資料結構）、`interfaces/`（跨機介面）、`common/`（provenance、設定）。

**為什麼按功能、不按機器分目錄：** 程式的功能是穩定的，部署在哪台機器會隨硬體改變（例如之後換更強的 Jetson，或後端改到桌機）。機器與角色的對應只寫在 `config/hosts/` 一處，換硬體時只改設定，不必搬程式、不打亂 Git 歷史。

## 資料流與失效模式

見 [interfaces/README.md](../interfaces/README.md) 與 [ADR 0004](decisions/0004-slam-compute-split.md)。

核心原則：**機載在筆電與桌機都失聯時仍能安全飛行**；越不即時的層，越不能被即時的層依賴。

## 設計決策索引

| ADR | 主題 | 狀態 |
|---|---|---|
| [0001](decisions/0001-monorepo.md) | 單一 repo | 採用 |
| [0002](decisions/0002-git-access-per-machine.md) | 每台機器的 Git 權限（機載分階段） | 採用 |
| [0003](decisions/0003-ros2-distro.md) | ROS 2 發行版 | 待確認 JetPack 版本 |
| [0004](decisions/0004-slam-compute-split.md) | SLAM 前端機載、最佳化在筆電 | 採用；SLAM 系統與 IMU 來源待定 |
