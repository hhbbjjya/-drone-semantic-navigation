import argparse
import os
from pathlib import Path

# Put writable caches outside tracked source; no credential values are read or copied.
os.environ.setdefault('MPLCONFIGDIR', str(Path.home() / '.cache' / 'matplotlib'))
os.environ.setdefault('YOLO_AUTOINSTALL', 'false')

from .core import Models, Room, Scan
from .vocabulary import resolve_classes


def main():
    parser = argparse.ArgumentParser(description='房間多視角 YOLOE + Qwen VLM 掃描')
    parser.add_argument('command', choices=['ui', 'scan'])
    parser.add_argument('--room', type=Path, required=True, help='包含 mesh.obj 及 rgb_cam 的目錄')
    parser.add_argument('--output', type=Path, default=Path('room_scan_outputs'))
    parser.add_argument('--yolo-model', default='yoloe-26s-seg.pt')
    parser.add_argument('--vlm-model', default='Qwen/Qwen2.5-VL-3B-Instruct')
    parser.add_argument('--device', default='auto')
    parser.add_argument('--dtype', choices=['auto', 'float32', 'bfloat16'], default='auto', help='預設依裝置選擇；CPU 可明確測試 bfloat16')
    parser.add_argument('--mode', choices=['both', 'yolo', 'preview'], default='both')
    parser.add_argument('--question', default='描述主要物件及其在影像中的相對位置。')
    parser.add_argument('--vocab', choices=['lvis','coco','research','custom'], default='lvis', help='完整 LVIS 1203 類（預設）、COCO 80 類、研究5類或自訂')
    parser.add_argument('--classes', help='英文逗號分隔；明確指定時使用自訂詞彙表')
    parser.add_argument('--conf', type=float, default=.25)
    parser.add_argument('--frame-tokens', type=int, default=256, help='逐視角回答的 token 上限')
    parser.add_argument('--summary-tokens', type=int, default=512, help='房間摘要的 token 上限')
    parser.add_argument('--views', help='只掃描指定視角，例如 0000,0008,0011,0016,0017；預設全部')
    parser.add_argument('--port', type=int, default=7863)
    parser.add_argument('--review', type=Path, help='UI 啟動時載入先前的 report.json')
    args = parser.parse_args()
    args.output = args.output.expanduser().resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    view_ids = [x.strip() for x in args.views.split(',') if x.strip()] if args.views is not None else None
    if not 0 < args.conf < 1:
        parser.error('--conf 必須介於 0 與 1')
    vocabulary = 'custom' if args.classes is not None else args.vocab
    try:
        classes = resolve_classes(vocabulary,args.classes)
    except ValueError as exc:
        parser.error(str(exc))
    if not 32 <= args.frame_tokens <= 2048 or not 32 <= args.summary_tokens <= 4096:
        parser.error('frame-tokens 必須為 32..2048，summary-tokens 必須為 32..4096')
    if args.command == 'ui':
        from .ui import build_app
        app = build_app(args.room, args.output, args.yolo_model, args.vlm_model, args.device, args.review,
                        args.mode, classes, args.conf, args.frame_tokens, args.summary_tokens, view_ids, args.dtype, vocabulary)
        app.queue().launch(server_name='127.0.0.1', server_port=args.port, share=False,
                           allowed_paths=[str(args.output), str(args.review.resolve().parent)] if args.review else [str(args.output)])
    else:
        room = Room.load(args.room).select_views(view_ids)
        job = Scan(room, args.output, Models(args.yolo_model, args.vlm_model, args.device, classes, args.conf,
                                           args.frame_tokens, args.summary_tokens, args.dtype, vocabulary), args.mode, args.question)
        try:
            for event in job.events():
                print(f'{event["phase"]} | {job.report["completed_views"]}/{len(room.views)} | {event["current"] or ""}', flush=True)
        except KeyboardInterrupt:
            job.stop.set()
            job.report['status'] = 'cancelled'
            for obs in job.report['observations']:
                if obs['status'] == 'running':
                    obs['status'] = 'cancelled'
            job.save('使用者中斷')
            job.export()
            print(f'已中斷，部分結果保存在 {job.directory}', flush=True)
            raise SystemExit(130)
        print(f'報告：{job.directory / "report.json"}', flush=True)
        if job.report['status'] != 'completed':
            print(job.report.get('error') or job.report.get('summary_error') or '部分視角處理失敗', flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()
