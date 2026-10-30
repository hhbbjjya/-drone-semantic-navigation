# ADR 0003：ROS 2 發行版

- 狀態：提議（待確認 Jetson 實際 JetPack 版本）
- 日期：2026-10-30

## 背景
三台機器以 ROS 2 跨機通訊時，發行版必須一致；不同發行版間的訊息定義與 DDS 行為不保證相容。
Jetson 的 Ubuntu 版本由 JetPack 決定，無法自由選擇；其他兩台可以配合。

## 待確認
- [ ] Orin Nano：`cat /etc/nv_tegra_release` → L4T / JetPack 版本 → 對應 Ubuntu 版本
- [ ] 桌機：原生 Ubuntu 或 WSL？Ubuntu 版本？
- [ ] 筆電：Ubuntu 版本？

## 決定（暫定原則）
以 Jetson 原生支援的發行版為準；其他機器版本不同時，使用 Docker 執行同一發行版。
WSL2 預設 NAT 網路會阻礙 DDS 自動探索，若桌機維持 WSL，需測試 mirrored 網路模式或改為原生 Ubuntu。
