from __future__ import annotations

import json
import threading
from pathlib import Path

import gradio as gr
import pandas as pd
from PIL import Image

from .core import Models, Room, Scan, summary_rows
from .quality import render_observation
from .vocabulary import LABELS, RESEARCH_CLASSES, resolve_classes

MODES = {'YOLOE + VLM 房間分析': 'both', '僅 YOLOE（不執行 VLM）': 'yolo', '僅資料預覽（不執行模型）': 'preview'}
COLUMNS = ['視角', '處理狀態', 'YOLO', 'VLM', '偵測數', 'YOLO 秒', 'VLM 秒']
ACTIVE: dict[str, Scan] = {}
LOCK = threading.Lock()


def safe_file(root, relative):
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('報告引用了輸出目錄以外的檔案')
    return path


def image_value(path):
    if not path.is_file():
        return None
    with Image.open(path) as im:
        return im.convert('RGB')


def frame_table(observations):
    return pd.DataFrame([[o['view_id'], o['status'], o['yolo_status'], o['vlm_status'],
                          len(o['detections']) if o['detections'] is not None else None,
                          o['timing_seconds'].get('yolo_predict'), o['timing_seconds'].get('vlm')]
                         for o in observations], columns=COLUMNS)


def evidence_table(observations):
    return pd.DataFrame([[x['class'], x['detection_observations'], ', '.join(x['views'])]
                         for x in summary_rows(observations)], columns=['類別', '偵測觀測次數（非獨立物件數）', '來源視角'])


def review(report_path, index):
    if not report_path:
        return None, None, '請先執行掃描。'
    path = Path(report_path)
    report = json.loads(path.read_text(encoding='utf-8'))
    observations = report['observations']
    if not observations:
        return None, None, report.get('error', '尚無視角結果')
    obs = observations[max(0, min(int(index)-1, len(observations)-1))]
    text = f"視角 {obs['view_id']}｜{obs['status']}\n\n" + render_observation(obs)
    if obs['errors']:
        text += '\n\n' + '\n'.join(obs['errors'])
    return image_value(safe_file(path.parent, obs['input_path'])), image_value(safe_file(path.parent, obs['overlay_path'])), text


def build_app(room_path: Path, output: Path, yolo_model: str, vlm_model: str, device: str, review_path=None,
              default_mode='both', classes=None, conf=.25, frame_tokens=256, summary_tokens=512, view_ids=None, dtype='auto', vocabulary='lvis'):
    room = Room.load(room_path).select_views(view_ids)
    initial = None
    if review_path:
        initial = json.loads(Path(review_path).read_text(encoding='utf-8'))
    with gr.Blocks(title='房間多視角語意掃描') as app:
        gr.Markdown('# 房間多視角語意掃描 v2\nYOLO 紀錄由程式固定呈現；VLM 額外觀察通過格式檢查後仍需人工確認。')
        gr.Markdown('**離線資料掃描；相機與三維定位待驗證。** 處理全部影像不代表覆蓋整個房間；綠點表示已處理視角，不表示位置已校正。')
        with gr.Row():
            room_box = gr.Textbox(value=str(room.path), label='房間資料夾（內含 mesh.obj 與 rgb_cam）', scale=3)
            mode = gr.Dropdown(choices=list(MODES), value=next(k for k, v in MODES.items() if v == default_mode), label='分析模式')
        question = gr.Textbox(value='描述主要物件及其在影像中的相對位置。', label='觀察重點（來源編號由程式附加）')
        vocabulary_box = gr.Dropdown(choices=[(label,key) for key,label in LABELS.items()],value=vocabulary,
                                     label='YOLOE 偵測類別範圍（不影響 Qwen 的三筆觀察上限）')
        class_info = gr.Markdown(f'本次候選類別：**{len(classes or resolve_classes(vocabulary))} 類**。類別表較大時，首次載入較久；偵測仍可能漏判或誤判。')
        with gr.Accordion('模型設定', open=False):
            yolo_box = gr.Textbox(value=yolo_model, label='YOLOE 權重路徑')
            vlm_box = gr.Textbox(value=vlm_model, label='Qwen 模型 ID 或本機模型目錄')
            device_box = gr.Textbox(value=device, label='執行裝置：auto / cpu / cuda:0')
            classes_box = gr.Textbox(value=', '.join(classes if vocabulary == 'custom' and classes else RESEARCH_CLASSES),
                                     label='自訂類別（英文逗號分隔）', visible=vocabulary == 'custom')
            confidence = gr.Slider(.01, .99, value=conf, step=.01, label='YOLO 信心門檻')
        with gr.Row():
            start = gr.Button('開始掃描所有視角', variant='primary')
            stop = gr.Button('停止（目前推論結束後生效）')
        status = gr.Markdown('尚未掃描。模型第一次載入可能需要下載權重；CPU 執行 Qwen 較慢。')
        with gr.Row():
            with gr.Column():
                original = gr.Image(label='目前原圖', type='pil')
                overlay = gr.Image(label='YOLO 框與 Mask（預覽模式為原圖）', type='pil')
            with gr.Column():
                plot = gr.Plot(value=room.figure(), label='房間與候選相機位置')
                answer = gr.Textbox(label='目前視角 VLM 分析／錯誤', lines=8)
        frames = gr.Dataframe(headers=COLUMNS, interactive=False, label='逐視角執行紀錄')
        objects = gr.Dataframe(interactive=False, label='跨視角偵測觀測統計（尚未去重）')
        summary = gr.Textbox(label='房間 VLM 摘要與證據來源', lines=10)
        with gr.Accordion('結果重播與下載', open=True):
            report_path = gr.Textbox(value=str(review_path or ''), label='本次 report.json（可保留供下次重播）', interactive=False)
            slider = gr.Slider(1, max(2, len(room.views)), value=1, step=1, label='重播已處理視角（第幾張）')
            replay = gr.Button('顯示選定視角')
            files = gr.Files(label='下載完整 ZIP、3D 進度動畫、報告與偵測表')

        def scan(path, selected_mode, query, yolo, vlm, chosen_device, class_text, conf, selected_vocab, request: gr.Request):
            key = request.session_hash or 'local'
            try:
                classes = resolve_classes(selected_vocab, class_text)
                selected_room = Room.load(Path(path)).select_views(view_ids)
                backend = Models(yolo, vlm, chosen_device, classes, float(conf), frame_tokens, summary_tokens, dtype, selected_vocab)
                job = Scan(selected_room, output, backend, MODES[selected_mode], query)
            except Exception as exc:
                raise gr.Error(str(exc)) from exc
            with LOCK:
                ACTIVE[key] = job
            try:
                for event in job.events():
                    report = event['report']
                    observations = report['observations']
                    current = observations[-1] if observations else None
                    scanned = [o['view_id'] for o in observations if o['status'] == 'completed']
                    completed = report['completed_views']
                    processed = sum(o['status'] in ('completed', 'error', 'cancelled', 'quality_rejected') for o in observations)
                    bar = '█' * int(20*processed/report['total_views']) + '░' * (20-int(20*processed/report['total_views']))
                    message = f'`{bar}` 已處理 {processed}/{report["total_views"]}｜成功 {completed}｜失敗 {report["failed_views"]}｜{event["phase"]}｜{report["status"]}'
                    message += f'｜VLM 格式未通過 {report.get("quality_rejected_views", 0)}'
                    if report.get('error'):
                        message += '\n\n錯誤：' + report['error'] + '\n\n若模型無法下載，請指定本機權重／Qwen 快取目錄，或明確切換僅 YOLOE 模式。'
                    if report.get('summary_error'):
                        message += '\n\n房間摘要失敗：' + report['summary_error']
                    input_im = image_value(job.directory / current['input_path']) if current else None
                    overlay_im = image_value(job.directory / current['overlay_path']) if current else None
                    text = (render_observation(current) + '\n' + '\n'.join(current['errors'])) if current else ''
                    available = [str(job.directory / name) for name in ['results.zip','scan_review.html','room_progress.html','report.md','report.json','quality_report.json','detections.csv','contact_sheet.jpg'] if (job.directory / name).exists()]
                    yield (message, input_im, overlay_im, selected_room.figure(scanned, event['current']), text,
                           frame_table(observations), evidence_table(observations), report['summary'] or '',
                           str(job.directory / 'report.json'), available,
                           gr.update(maximum=max(2, len(observations)), value=max(1, len(observations))))
            finally:
                with LOCK:
                    ACTIVE.pop(key, None)

        def cancel(request: gr.Request):
            with LOCK:
                job = ACTIVE.get(request.session_hash or 'local')
                if job:
                    job.stop.set()
            gr.Info('已要求停止；目前模型推論結束後會保存部分結果。' if job else '目前沒有正在執行的掃描。')

        def vocabulary_changed(selected, custom):
            try:
                count=len(resolve_classes(selected,custom))
                note=f'本次候選類別：**{count} 類**。這是指定詞彙表的全部類別，不代表涵蓋世界所有物件。'
            except ValueError as exc:
                note=str(exc)
            return gr.update(visible=selected=='custom'),note

        vocabulary_box.change(vocabulary_changed,inputs=[vocabulary_box,classes_box],outputs=[classes_box,class_info],api_name='vocabulary')
        classes_box.change(vocabulary_changed,inputs=[vocabulary_box,classes_box],outputs=[classes_box,class_info],api_name=False)

        start.click(scan, inputs=[room_box, mode, question, yolo_box, vlm_box, device_box, classes_box, confidence, vocabulary_box],
                    outputs=[status, original, overlay, plot, answer, frames, objects, summary, report_path, files, slider],
                    concurrency_limit=1, concurrency_id='models', api_name='scan')
        stop.click(cancel, inputs=[], outputs=[], queue=False, api_name='stop')
        replay.click(review, inputs=[report_path, slider], outputs=[original, overlay, answer], api_name='review')
        if initial:
            def load_initial():
                obs = initial['observations']
                image, over, text = review(str(review_path), 1)
                legacy = initial.get('schema_version', 1) < 2
                title = '已載入舊版報告（未經 v2 品質檢查）' if legacy else '已載入報告'
                summary_text = ('舊版模型摘要（未經 v2 品質檢查）：\n' if legacy else '') + (initial['summary'] or '')
                return (f'{title}：{initial["status"]}；{initial["completed_views"]}/{initial["total_views"]} 視角',
                        image, over, text, frame_table(obs), evidence_table(obs), summary_text,
                        room.figure([o['view_id'] for o in obs if o['status'] == 'completed']))
            app.load(load_initial, outputs=[status, original, overlay, answer, frames, objects, summary, plot])
    return app
