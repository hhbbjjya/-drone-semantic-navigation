#!/usr/bin/env bash
set -euo pipefail
SCANNER_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RESEARCH_ROOT="${VLM_PROJECT_DIR:-$HOME/vlm-research}"
PYTHON_BIN="${ROOM_SCAN_PYTHON:-$RESEARCH_ROOT/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  printf '找不到 Python：%s\n請用 ROOM_SCAN_PYTHON 指定已安裝依賴的 Python。\n' "$PYTHON_BIN" >&2
  exit 1
fi
cd "$RESEARCH_ROOT"
export PYTHONPATH="$SCANNER_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON_BIN" -m roomscan ui \
  --room "$RESEARCH_ROOT/datasets/3DTexture/dataset/rgbd_dataset_freiburg1_room" \
  --output "$RESEARCH_ROOT/room_scan_outputs" \
  --yolo-model "$RESEARCH_ROOT/yoloe-26s-seg.pt" \
  --vlm-model "${ROOM_SCAN_VLM_MODEL:-Qwen/Qwen2.5-VL-3B-Instruct}" \
  --device "${ROOM_SCAN_DEVICE:-auto}" "$@"
