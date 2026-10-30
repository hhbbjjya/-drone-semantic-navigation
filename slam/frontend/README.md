# slam/frontend/ — 機載 Orin Nano

- 雙目＋IMU 追蹤、局部建圖／VIO，輸出位姿給 PX4（外部視覺）
- 選出關鍵幀送往筆電後端；接收後端修正並平滑套用
- 筆電失聯時維持運作，並透過 `onboard/` 回報降級狀態

效能測試請在**實際飛行時的電源模式**下進行（Orin Nano 不同功率模式的算力差很多），並記錄在實驗設定檔。
C++ 編譯在 Nano 上原生進行（aarch64），`build/ install/ log/` 不進 Git。
