# v2 更新：先跑五張比較，不覆寫 v1

新版不需要重裝 CUDA、PyTorch，也不需要重新下載本機已快取的 Qwen 模型。解壓後是獨立的 `room-scanner-v2` 資料夾，舊程式與舊結果保留。

假設下載在 Windows `F:\room_scanner_v2.zip`，在 WSL Ubuntu 執行：

```bash
cd ~/vlm-research
source .venv/bin/activate
python -m zipfile -e /mnt/f/room_scanner_v2.zip "$HOME/vlm-research"

bash room-scanner-v2/run_room_scan.sh \
  --room "$HOME/vlm-research/3DTexture-master/dataset/rgbd_dataset_freiburg1_room" \
  --output "$HOME/vlm-research/room_scan_outputs_v2" \
  --port 7864 \
  --views 0000,0008,0011,0016,0017
```

開啟終端機顯示的本機介面，選擇「YOLOE + VLM 房間分析」，按開始。這五張包含 v1 的來源誤認與重複案例。若要掃描全部 20 張，關閉程式後用相同指令啟動，移除 `--views ...` 即可。

## 改了什麼

- Qwen 不再接收 YOLO 清單；逐張只回傳最多三筆 JSON 視覺觀察。
- 模型漏填不確定性時，明確標成「模型未提供」，不預設為可信。
- YOLO 類別、信心與框只從偵測器結果讀取；視角編號由程式附加。
- 等價的 JSON 陣列／單一程式碼框可正規化並記錄轉換；不修補內容。結構、來源詞、重複、UTF-8 解碼及實際生成停止原因有檢查。失敗最多重試一次；仍失敗標為 `quality_rejected`，保留原文但不納入摘要。
- 改用模型 `generate()`，從實際生成 token 記錄 EOS／上限與精確 token 數，不再根據文字長度猜測截斷。
- 房間 VLM 步驟僅選取既有觀察 ID；程式依原紀錄呈現物件、影像相對位置、來源，不允許模型新增摘要敘述。這是有來源的摘錄，還不是自由問答或三維語意推理。
- 所有原始回答與每次重試、品質檢查結果寫入 `quality_report.json`。

## 怎麼判斷這次有沒有改善

對照同一張圖片的 v1 與 v2：

1. `0016` 若 YOLO 為空，介面一定顯示未偵測指定類別；Qwen 若觀察到櫃子，會在另一區列為「VLM 觀察」。
2. `0011`／`0017` 若仍出現重複或觸及 token 上限，應顯示品質未通過，不得變成成功摘要內容。
3. 摘錄每項來源是程式填的實際視角 ID，不依賴模型自行引用。
4. **格式通過不表示物件真的存在。** 仍要檢查原圖；程式不會自動證實幻覺、準確率、物件數或三維位置。

完成後上傳 v2 的 `results.zip`，可比較 `format_checked_views`、`quality_rejected_views`、實際 raw outputs 與圖片。v1 結果不會因為程式更新而自動變正確，需要重新推論。
