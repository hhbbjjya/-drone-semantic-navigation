# 房間多視角語意掃描 v2.1：完整類別表

**全類別使用者先讀 [ALL_CLASSES.md](ALL_CLASSES.md)。預設已從原五類改為 LVIS 1,203 類；也可選 COCO 80 類或自訂。**

用 YOLOE-26s-seg、Qwen2.5-VL-3B 與 Gradio／Plotly，處理房間 RGB 視角，查看框、Mask、VLM 額外觀察、3D 房間及掃描進度。這是離線資料掃描，不需要 Gazebo、ROS 或 PX4。

**已有 v1 的使用者，先讀 [UPGRADE_V2.md](UPGRADE_V2.md)。** 新 ZIP 解壓後為 `room-scanner-v2`，與舊版並存；不要覆寫原研究腳本、模型或 `.venv`。

## 在你的 WSL 啟動

將程式解壓到 `/home/user/vlm-research/room-scanner-v2`。已有正常 CUDA／模型環境時直接沿用：

```bash
cd ~/vlm-research
source .venv/bin/activate
python -m pip check
bash room-scanner-v2/run_room_scan.sh \
  --room "$HOME/vlm-research/3DTexture-master/dataset/rgbd_dataset_freiburg1_room" \
  --output "$HOME/vlm-research/room_scan_outputs_v2" \
  --port 7864 \
  --views 0000,0008,0011,0016,0017
```

在本機瀏覽器開啟終端機列出的位址（以上升級指令使用埠 7864，可與舊版並存），選「YOLOE + VLM 房間分析」後開始。五張確認後，移除 `--views ...` 重啟即可掃描全部影像。新程式不會自動修改舊版結果。

啟動腳本沿用 `~/vlm-research/.venv`、YOLO／MobileCLIP 權重與 Hugging Face 快取，不自動安裝套件。缺少依賴時參考 `requirements.txt`；不要為此重裝 CUDA。若需隔離套件，可另建虛擬環境，依 [PyTorch 官方指引](https://pytorch.org/get-started/locally/) 安裝符合硬體的 torch／torchvision，再安裝 requirements。不要把雲端 CPU 版 torch 覆蓋到原有 GPU 環境。

```bash
# 新環境才需要安裝；在目前專案目錄執行：
python -m pip install -r requirements.txt
# 使用其他 Python 或既有完整 Qwen snapshot：
ROOM_SCAN_PYTHON=/path/to/venv/bin/python \
ROOM_SCAN_VLM_MODEL=/path/to/Qwen/snapshots/revision \
  bash run_room_scan.sh --room /path/to/room
```

## v2 的資訊來源與檢查

- **YOLO 紀錄由程式直接呈現**，包括類別、信心、2D 框與 Mask；不交給 Qwen 改寫。
- **Qwen 只觀察原圖**，回傳最多三筆 JSON：物件名稱、影像相對方位、不確定標記。它不再收到 YOLO 清單、信心或框。
- 模型漏填 `uncertain` 時，程式只會保守標為未知，記錄 `uncertainty_source=missing_default_true`，不當成模型已確認。
- 程式填入視角 ID 與來源標記；`human_verified=false` 永遠不由模型自行更改。
- 直接呼叫模型 `generate()`，記錄實際新 token 數、EOS／長度上限，使用 greedy decoding、repetition penalty 1.1。
- 單一 JSON 程式碼框與等價的頂層陣列可以正規化，轉換會記錄；不修補缺字、不抽取夾在自由文字中的 JSON。空白、非法 JSON／欄位、來源冒稱、重複、Unicode 異常、觸及上限或無法確認停止原因時，最多重試一次。仍失敗則 `quality_rejected`，原文保留，不能進入摘要。
- 房間摘要改為**既有觀察的摘錄**：模型只能選已有 evidence ID，程式依原文附來源；不能生成額外位置、數量或偵測事實。YOLO 統計完全由程式計算。
- 格式／來源檢查**不是視覺真值驗證**。合法 JSON 裡的「櫃子」仍可能看錯，要對照原圖人工確認；不聲稱已消除幻覺或提升辨識準確率。

## 命令列

資料格式：`<room>/mesh.obj`、`<room>/rgb_cam/*.jpg`，相機資料為同名 `.cam`。

```bash
# 從程式目錄執行
python -m roomscan scan --room /path/to/room --mode both --device auto \
  --yolo-model /path/to/yoloe-26s-seg.pt --views 0000,0008,0011,0016,0017
python -m roomscan ui --room /path/to/room --mode both --port 7863
python -m roomscan scan --room /path/to/room --mode yolo
python -m roomscan scan --room /path/to/room --mode preview
python -m roomscan ui --room /path/to/room --review /path/to/run/report.json
```

其他選項：`--vocab lvis`（預設 1,203 類）、`--vocab coco`（80 類）、`--vocab research`（原五類）、`--output`、`--classes 'laptop,computer monitor,keyboard,chair,desk'`、`--conf 0.25`、`--question '描述主要物件與相對位置'`、`--frame-tokens 256`、`--summary-tokens 512`。不指定 `--views` 就處理所有 JPG。UI 的選取視角由啟動參數固定，重新啟動可切換全部／部分影像。

`--dtype auto` 依裝置選擇精度；GPU 優先 BF16，CPU 預設 FP32。在已確認支援 BF16 的 CPU 可明確測試 `--dtype bfloat16`，並在報告記錄該選項；這不影響本機 GPU 的預設啟動方式。

一次只執行一個掃描；按停止後，會等目前模型呼叫結束並保存部分結果。關閉瀏覽器不等於取消。每次建立新的 run 目錄。整體 `partial` 可能代表模型錯誤，也可能只是品質檢查拒絕；兩者分開計數。CLI 部分失敗回傳非零，Ctrl+C 為 130。

## 輸出與重播

- `report.json`：schema 2、prompt 版本、偵測事實、結構化 VLM 觀察與摘錄。
- `quality_report.json`：每次原始回答、重試、精確 token 數、停止原因、接受／拒絕理由。格式通過不等於人工驗證。
- `scan_review.html`：自包含圖片與 Plotly，解壓後離線開啟，可逐張播放。
- `room_progress.html`：3D 處理進度；`contact_sheet.jpg`：視角總覽。
- `detections.csv`、`report.md`、每張的原圖／overlay／Mask／`observation.json`。
- `results.zip`：完整可分享結果。

`vlm_inference_completed_views` 表示有模型回傳紀錄；`format_checked_views` 表示最終輸出通過機械檢查；`quality_rejected_views` 表示兩次都未通過。這些指標都不是辨識正確率。

## 幾何限制

全部影像已處理不代表完整覆蓋房間。檔名順序不是已驗證的時間序列。相機 `C=-R.T@t`、內參、投影對齊與 Mesh 尺度仍待驗證；綠點表示視角已處理，不表示位置校正成功。

原始 Mesh 保持完整，僅用 fast-simplification 簡化顯示。此流程不執行 Stage 4 大批次 raycast，不據此宣稱已解決原先 `Killed`。`world_xyz=null`、`validated_3d=false`；尚無跨視角去重、獨立物件數、三維定位或導航安全保證。

## 驗證

```bash
python -m unittest discover -s tests -v
```

回歸案例包括使用者上傳的 v1 `0008/0011/0014/0016/0017` 問題回答。測試覆蓋拒絕污染摘要、單次重試、EOS／上限區分、固定來源、取消、錯誤保存、檔案匯出與重播。測試替代模型不代表真實 Qwen 辨識通過；新模型回答應在同一圖片集另行比較。v1 本機 GPU 實測為 20/20 呼叫完成、39 筆偵測，但其回答存在誤認與重複，不能作正確率證據。
