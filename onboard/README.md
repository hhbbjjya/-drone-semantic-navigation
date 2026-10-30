# onboard/ — 機載 Jetson Orin Nano 的硬體介面

職責：雙目 IMX477 擷取與時間戳、與 Pixhawk 4 的 MAVLink 橋接、系統健康監控與安全降級。
SLAM 前端程式在 `slam/frontend/`，同樣部署在這台。

預計子目錄：

| 目錄 | 內容 |
|---|---|
| `mavlink/` | Pixhawk 讀取（HEARTBEAT、姿態、IMU）、外部視覺位姿送入 PX4 |
| `camera/` | 雙目擷取、硬體/軟體同步、時間戳 |
| `health/` | 溫度、功率模式、與筆電的連線狀態、降級切換 |

Git 權限分兩階段（ADR 0002）：
- **bring-up 階段（現在）**：本 repo 限定、可寫入的 Deploy key，可直接在這台開發與推送
- **飛行階段**：改成唯讀 Deploy key；現場修改 commit 到 `field/<日期>` 分支推到筆電

部署前：`bash scripts/git/check_clean.sh --strict`。TensorRT engine 在本機編譯，不進 Git。
