# 全類別版：預設 LVIS 1,203 類

原版只將五種名稱傳給 YOLOE，因此風扇、櫃子等不在候選類別中。全類別版沿用現有 `yoloe-26s-seg.pt`，將官方 LVIS 的全部 1,203 個名稱傳入文字提示。這是完整 LVIS 詞彙，不是宣稱涵蓋世界所有物件，也不是自動發現無限類別。

網頁新增「YOLOE 偵測類別範圍」選項：

| 選項 | 類別數 |
|---|---:|
| LVIS 全部（預設） | 1,203 |
| COCO 全部 | 80 |
| 原研究類別 | 5 |
| 自訂 | 依輸入清單 |

選擇 LVIS／COCO 時，自訂文字欄不會限制或覆蓋完整清單。類別表固定於 `roomscan/vocabularies.json`，取自 Ultralytics 8.4.189 的官方 `cfg/datasets/lvis.yaml`、`coco.yaml`，保留原始順序與同義詞；不會因你本機版本不同而悄悄改變名稱或類別 ID。

## 在你的 WSL 使用

將程式下載為 `F:\room_scanner_allclasses.zip`，在 Ubuntu 執行：

```bash
cd ~/vlm-research
source .venv/bin/activate
python -m zipfile -e /mnt/f/room_scanner_allclasses.zip "$HOME/vlm-research"

bash room-scanner-allclasses/run_room_scan.sh \
  --room "$HOME/vlm-research/3DTexture-master/dataset/rgbd_dataset_freiburg1_room" \
  --output "$HOME/vlm-research/room_scan_outputs_allclasses" \
  --port 7865 \
  --vocab lvis
```

在介面選「LVIS 全部 1,203 類」。可先選「僅 YOLOE」檢查輸出，再執行「YOLOE + VLM」；Qwen 仍只獨立列最多三筆觀察，不會因 YOLO 類別增加而重寫偵測紀錄。影像掃描數預設全部，若只想測試可加 `--views 0000,0009`。

命令列範例（在程式資料夾執行）：

```bash
python -m roomscan scan --room /path/to/room --vocab lvis --mode yolo
python -m roomscan scan --room /path/to/room --vocab coco --mode yolo
python -m roomscan scan --room /path/to/room --classes 'fan,cabinet,whiteboard' --mode yolo
```

明確提供 `--classes` 會採用自訂清單，取代 `--vocab`，保留舊指令的相容性。LVIS 不含的名稱可透過自訂提示測試；可提示不代表該類一定辨識準確。

完整候選名稱、類別數、所選詞彙表與信心門檻均寫入 `report.json` 的 `models` 欄位。1203 類的文字特徵載入比原本五類久，偵測也可能更慢或出現新誤判；目前維持 0.25 門檻，請檢查影像後決定是否調整。

## 本次驗證

- 27 項自動測試通過，包含詞彙數量、複本隔離、空白自訂拒絕與原 v2 品質檢查。
- 真實 YOLOE CPU 測試 `0000`、`0009` 完成，模型載入全部 1,203 類；`0009` 的風扇偵測為 `fan`、信心約 0.908。
- 介面已驗證 LVIS／COCO 類別數顯示及自訂清單切換；選取 LVIS 時不會沿用原五類限制。
- 全類別也產生額外候選，沒有人工真值或全資料集準確率結論；這不是新的 Qwen 20 張推論測試。
