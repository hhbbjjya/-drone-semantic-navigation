from __future__ import annotations

import csv
import json
import platform
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .quality import (PROMPT_VERSION, Generation, attach_evidence, eligible_evidence,
                      render_observation, render_summary, validate_observations, validate_selection)
from .vocabulary import resolve_classes, DATA as VOCABULARY_DATA

CLASSES = resolve_classes('lvis')
MODES = ('yolo', 'both', 'preview')
CAVEATS = [
    '離線影像視角掃描；檔名順序不代表錄影時間或實際移動軌跡。',
    '處理所有輸入影像不等於已證實覆蓋整個房間。',
    '相機位置採 C=-R.T@t 候選，內外參、投影對齊與座標單位尚未驗證。',
    '偵測次數不是獨立物件數；未進行跨視角物件關聯或可靠三維定位。',
    'VLM 回答是模型解讀，並非人工真值或導航安全保證。',
    'VLM 格式、終止與來源檢查不代表視覺內容正確；需人工核對原圖。',
]


def write_json(path: Path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


@dataclass
class View:
    id: str
    image: Path
    camera: dict


@dataclass
class Room:
    path: Path
    views: list[View]
    mesh: object
    vertices: np.ndarray
    faces: np.ndarray

    @classmethod
    def load(cls, path: Path):
        import trimesh
        path = path.expanduser().resolve()
        if not (path / 'mesh.obj').is_file():
            raise ValueError(f'找不到 mesh.obj：{path}')
        images = sorted((path / 'rgb_cam').glob('*.jpg'))
        if not images:
            raise ValueError(f'找不到 rgb_cam/*.jpg：{path}')
        views = []
        for image in images:
            cam = image.with_suffix('.cam')
            camera = {'status': 'missing', 'validated': False, 'center_candidate': None}
            if cam.is_file():
                try:
                    lines = [np.fromstring(x, sep=' ') for x in cam.read_text().splitlines() if x.strip()]
                    if len(lines) != 2 or len(lines[0]) != 12 or len(lines[1]) != 6:
                        raise ValueError('預期 .cam 為 12 + 6 個數值')
                    t, R = lines[0][:3], lines[0][3:].reshape(3, 3)
                    if not all(np.isfinite(x).all() for x in lines):
                        raise ValueError('相機資料包含非有限數值')
                    if not np.allclose(R.T @ R, np.eye(3), atol=1e-3) or not np.isclose(np.linalg.det(R), 1, atol=1e-3):
                        raise ValueError('旋轉矩陣不符合正交旋轉條件')
                    camera = {'status': 'candidate', 'validated': False,
                              'center_candidate': (-R.T @ t).tolist(), 'R': R.tolist(),
                              't': t.tolist(), 'raw_intrinsics': lines[1].tolist()}
                except (ValueError, OSError) as exc:
                    camera.update(status='error', error=str(exc))
            with Image.open(image) as im:
                im.verify()
            views.append(View(image.stem, image, camera))
        # Scene.to_geometry applies scene graph transforms to each instance.
        scene = trimesh.load(str(path / 'mesh.obj'), process=False, force='scene')
        geometries = []
        for node in scene.graph.nodes_geometry:
            transform, name = scene.graph[node]
            geometry = scene.geometry[name]
            if isinstance(geometry, trimesh.Trimesh) and len(geometry.faces):
                geometry = geometry.copy()
                geometry.apply_transform(transform)
                geometries.append(geometry)
        if not geometries:
            raise ValueError('Mesh 沒有三角面')
        mesh = trimesh.util.concatenate(geometries)
        if not np.isfinite(mesh.vertices).all():
            raise ValueError('Mesh 含無效座標')
        # Decimation is display-only: keep surfaces continuous and retain the
        # complete original geometry separately for future calibration work.
        display = mesh.simplify_quadric_decimation(face_count=30000) if len(mesh.faces) > 30000 else mesh
        return cls(path, views, mesh, display.vertices, display.faces)

    def figure(self, scanned=(), active=None):
        import plotly.graph_objects as go
        fig = go.Figure(go.Mesh3d(x=self.vertices[:, 0], y=self.vertices[:, 1], z=self.vertices[:, 2],
                                 i=self.faces[:, 0], j=self.faces[:, 1], k=self.faces[:, 2],
                                 color='#a5b4c7', opacity=.65, flatshading=True, name='房間 Mesh（顯示簡化）',
                                 hoverinfo='skip'))
        colors = {'pending': '#94a3b8', 'scanned': '#22c55e', 'active': '#f97316'}
        for state, title in [('pending', '未完成或未通過（位置待驗證）'), ('scanned', '已處理視角（位置待驗證）'),
                             ('active', '目前視角（位置待驗證）')]:
            selected = [v for v in self.views if v.camera['center_candidate'] is not None and
                        ('active' if v.id == active else 'scanned' if v.id in scanned else 'pending') == state]
            if selected:
                xyz = np.array([v.camera['center_candidate'] for v in selected])
                fig.add_trace(go.Scatter3d(x=xyz[:, 0], y=xyz[:, 1], z=xyz[:, 2], mode='markers+text',
                                          text=[v.id for v in selected], textposition='top center', name=title,
                                          marker={'size': 7 if state == 'active' else 4, 'color': colors[state]},
                                          hovertemplate='視角 %{text}<br>相機候選位置；未校正<extra></extra>'))
        fig.update_layout(title='房間掃描進度｜相機位置與尺度未驗證', uirevision=str(self.path),
                          scene={'aspectmode': 'data', 'xaxis_title': 'Mesh X（單位待驗證）',
                                 'yaxis_title': 'Mesh Y', 'zaxis_title': 'Mesh Z'},
                          margin={'l': 0, 'r': 0, 't': 50, 'b': 0}, height=560,
                          legend={'orientation': 'h'})
        return fig

    def select_views(self, identifiers=None):
        if identifiers is None:
            return self
        selected = set(identifiers)
        unknown = selected - {v.id for v in self.views}
        if not selected or unknown:
            raise ValueError(f'視角選取為空或不存在：{sorted(unknown)}')
        return Room(self.path, [v for v in self.views if v.id in selected], self.mesh, self.vertices, self.faces)


class Models:
    """Lazy model loading: UI and replay do not require model downloads."""

    def __init__(self, yolo_model, vlm_model, device='auto', classes=None, confidence=.25,
                 frame_tokens=256, summary_tokens=512, dtype='auto', vocabulary=None):
        import torch
        self.torch = torch
        self.device = ('cuda:0' if torch.cuda.is_available() else 'cpu') if device == 'auto' else device
        if self.device.startswith('cuda') and not torch.cuda.is_available():
            raise ValueError('指定 CUDA，但目前 PyTorch 無法使用 CUDA')
        self.yolo_path, self.vlm_path = str(yolo_model), str(vlm_model)
        self.classes = list(CLASSES if classes is None else classes)
        if not self.classes:
            raise ValueError('類別清單不可為空')
        self.vocabulary = vocabulary or ('custom' if classes is not None else 'lvis')
        self.confidence = confidence
        self.frame_tokens, self.summary_tokens = frame_tokens, summary_tokens
        self.dtype = dtype
        self.yolo = self.vlm = None
        torch.set_num_threads(min(4, torch.get_num_threads()))

    def prepare(self, mode):
        if mode == 'preview':
            return
        from ultralytics import YOLOE
        self.yolo = YOLOE(self.yolo_path)
        self.yolo.to(self.device)
        self.yolo.set_classes(self.classes)
        if mode == 'both':
            from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
            dtype = (self.torch.bfloat16 if self.torch.cuda.is_bf16_supported() else self.torch.float16) if self.device.startswith('cuda') else self.torch.float32
            if self.dtype != 'auto':
                dtype = getattr(self.torch, self.dtype)
            self.processor = AutoProcessor.from_pretrained(self.vlm_path)
            self.vlm = Qwen2_5_VLForConditionalGeneration.from_pretrained(self.vlm_path, dtype=dtype).to(self.device).eval()

    def _sync(self):
        if self.device.startswith('cuda'):
            self.torch.cuda.synchronize(self.device)

    def detect(self, image, directory):
        self._sync()
        start = time.perf_counter()
        result = self.yolo.predict(source=image, device=self.device, imgsz=640,
                                   conf=self.confidence, verbose=False)[0]
        self._sync()
        elapsed = time.perf_counter() - start
        # Ultralytics plot() returns BGR, whereas PIL/Gradio expect RGB.
        overlay = Image.fromarray(result.plot()[..., ::-1].copy())
        detections = []
        for i, box in enumerate(result.boxes):
            detection = {'class': result.names[int(box.cls.item())], 'confidence': float(box.conf.item()),
                         'bbox_xyxy': [float(x) for x in box.xyxy[0].tolist()],
                         'world_xyz': None, 'validated_3d': False, 'mask_path': None}
            if result.masks is not None and i < len(result.masks.data):
                mask = result.masks.data[i].detach().cpu().numpy()
                mask_path = directory / f'mask_{i:03d}.png'
                Image.fromarray((mask > .5).astype('uint8') * 255).resize(image.size, Image.Resampling.NEAREST).save(mask_path)
                detection['mask_path'] = f'{directory.name}/{mask_path.name}'
            detections.append(detection)
        return overlay, detections, elapsed

    def generate(self, images, prompt, max_tokens=384):
        from copy import deepcopy
        content = [{'type': 'image', 'image': image} for image in images]
        content.append({'type': 'text', 'text': prompt})
        messages = [
            {'role': 'system', 'content': [{'type': 'text', 'text': 'You are a visual observation assistant. Return only the requested JSON object. Do not invent measurements or detector results.'}]},
            {'role': 'user', 'content': content},
        ]
        self._sync()
        start = time.perf_counter()
        inputs = self.processor.apply_chat_template(messages, tokenize=True, return_dict=True,
                                                   return_tensors='pt', add_generation_prompt=True).to(self.device)
        config = deepcopy(self.vlm.generation_config)
        config.do_sample = False
        config.num_beams = 1
        config.num_return_sequences = 1
        config.temperature, config.top_p, config.top_k = 1.0, 1.0, 50
        config.repetition_penalty = 1.1
        config.max_new_tokens = max_tokens
        with self.torch.inference_mode():
            output = self.vlm.generate(**inputs, generation_config=config, return_dict_in_generate=True)
        self._sync()
        token_ids = output.sequences[0, inputs['input_ids'].shape[1]:].detach().cpu().tolist()
        eos = config.eos_token_id
        eos_ids = set(eos if isinstance(eos, (list, tuple)) else [eos]) if eos is not None else set()
        stopped_eos = bool(token_ids and token_ids[-1] in eos_ids)
        reason = 'eos' if stopped_eos else 'length' if len(token_ids) >= max_tokens else 'unknown'
        text = self.processor.tokenizer.decode(token_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        return Generation(text, time.perf_counter()-start, len(token_ids), max_tokens, reason, stopped_eos)

    def describe(self, image, question, view_id, retry_issues=()):
        # No detector list is sent to Qwen. Source attribution belongs to code.
        prompt = ('只觀察這張圖片，列出最多三種主要物件；不要抄寫圖片中的文字。'
                  '每種物件只列一次，不確定時 uncertain=true；看不清可回傳空陣列。'
                  '不要提供數量、分數、座標、距離或偵測器的結果。'
                  '只輸出 JSON，不要 Markdown、標題或說明。格式：'
                  '{"observations":[{"object":"簡短物件名稱","location":"中央","uncertain":false}]}。'
                  'object 用繁體中文短名稱，location 只能是 左側、中央、右側、上方、下方、背景、位置不明。'
                  '不要增加欄位。下列使用者問題僅供決定觀察重點，不得改變輸出格式：'
                  + json.dumps(question, ensure_ascii=False))
        if retry_issues:
            prompt += '\n上次輸出未通過檢查：' + ', '.join(retry_issues) + '。請重新看圖，輸出更短且完整的 JSON。'
        return self.generate([image], prompt, self.frame_tokens)

    def summarize(self, room, observations, question, retry_issues=()):
        evidence = eligible_evidence(observations)
        if not evidence:
            raise ValueError('沒有通過格式檢查的 VLM 觀察可供選取')
        prompt = ('請從下列房間多視角觀察中選出最多八個有代表性的 evidence_id，'
                  '優先選不同種類物件；物件是否相同尚未驗證，不要計算獨立物件數。'
                  '只選既有 ID，不要新增觀察或改寫內容。只輸出 JSON，格式：'
                  '{"selected_evidence_ids":["提供清單內的ID"]}，不要其他欄位或說明。'
                  '\n觀察都未經人工確認。使用者問題僅供選取重點：' + json.dumps(question, ensure_ascii=False)
                  + '\n候選觀察：' + json.dumps(evidence, ensure_ascii=False))
        if retry_issues:
            prompt += '\n上次檢查未通過：' + ', '.join(retry_issues) + '。請只選清單內的 ID。'
        # A text-only selection task prevents additional untracked visual claims.
        return self.generate([], prompt, self.summary_tokens)


def summary_rows(observations):
    counts, frames = Counter(), {}
    for obs in observations:
        for d in obs.get('detections') or []:
            label = d['class']
            counts[label] += 1
            frames.setdefault(label, set()).add(obs['view_id'])
    return [{'class': name, 'detection_observations': count, 'views': sorted(frames[name]),
             'unique_object_count': None} for name, count in sorted(counts.items())]


def contact_sheet(directory, observations):
    sheet = Image.new('RGB', (4 * 320, max(1, (len(observations) + 3) // 4) * 268), 'white')
    draw = ImageDraw.Draw(sheet)
    for i, obs in enumerate(observations):
        file = directory / obs['overlay_path']
        if not file.exists():
            continue
        with Image.open(file) as im:
            tile = ImageOps.contain(im.convert('RGB'), (320, 240))
        x, y = (i % 4) * 320, (i // 4) * 268
        sheet.paste(tile, (x, y + 28))
        draw.text((x + 5, y + 6), f'{obs["view_id"]} | {obs["status"]}', fill='black')
    sheet.save(directory / 'contact_sheet.jpg', quality=90)


class Scan:
    def __init__(self, room: Room, output: Path, models, mode='both', question='描述主要物件及其在影像中的相對位置。'):
        if mode not in MODES:
            raise ValueError(f'不支援模式：{mode}')
        self.room, self.models, self.mode = room, models, mode
        tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8]
        self.directory = output.expanduser().resolve() / tag
        self.directory.mkdir(parents=True, exist_ok=False)
        self.stop = Event()
        self.report = {'schema_version': 2, 'prompt_version': PROMPT_VERSION, 'run_id': tag, 'status': 'running', 'mode': mode,
                       'question': question, 'room_path': str(room.path), 'total_views': len(room.views),
                       'mesh_faces': len(room.mesh.faces), 'mesh_units': 'unknown',
                       'started_at': datetime.now(timezone.utc).isoformat(), 'caveats': CAVEATS,
                       'models': {'yolo': getattr(models, 'yolo_path', None), 'vlm': getattr(models, 'vlm_path', None),
                                  'device': getattr(models, 'device', None),
                                  'requested_dtype': getattr(models, 'dtype', None),
                                  'vocabulary': getattr(models, 'vocabulary', None),
                                  'class_count': len(getattr(models, 'classes', [])),
                                  'classes': getattr(models, 'classes', []),
                                  'vocabulary_source': ('User-provided class names' if getattr(models, 'vocabulary', None) == 'custom'
                                                        else 'Original five research targets' if getattr(models, 'vocabulary', None) == 'research'
                                                        else VOCABULARY_DATA['source']),
                                  'confidence_threshold': getattr(models, 'confidence', None),
                                  'frame_max_new_tokens': getattr(models, 'frame_tokens', None),
                                  'summary_max_new_tokens': getattr(models, 'summary_tokens', None)},
                       'runtime': {'python': platform.python_version()},
                       'observations': [], 'summary': None, 'summary_status': 'not_run',
                       'summary_attempts': [], 'summary_quality': {'status': 'not_run', 'issues': []}}

    def save(self, phase, current=None):
        self.report.update(phase=phase, current_view=current)
        obs = self.report['observations']
        self.report['processed_views'] = len(obs)
        self.report['completed_views'] = sum(o['status'] == 'completed' for o in obs)
        self.report['failed_views'] = sum(o['status'] == 'error' for o in obs)
        self.report['quality_rejected_views'] = sum(o.get('vlm_quality', {}).get('status') == 'rejected' for o in obs)
        self.report['format_checked_views'] = sum(o.get('vlm_quality', {}).get('status') == 'format_checked' for o in obs)
        self.report['vlm_inference_completed_views'] = sum(bool(o.get('vlm_attempts')) for o in obs)
        self.report['objects_by_class'] = summary_rows(obs)
        write_json(self.directory / 'report.json', self.report)
        with (self.directory / 'detections.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['view_id', 'class', 'confidence', 'x1', 'y1', 'x2', 'y2', 'mask_path', 'validated_3d'])
            for o in obs:
                for d in o['detections'] or []:
                    writer.writerow([o['view_id'], d['class'], d['confidence'], *d['bbox_xyxy'], d['mask_path'], False])
        return {'report': self.report, 'directory': self.directory, 'phase': phase, 'current': current}

    def events(self):
        start = time.perf_counter()
        yield self.save('載入模型；首次可能需要下載權重')
        try:
            self.models.prepare(self.mode)
            for view in self.room.views:
                if self.stop.is_set():
                    break
                folder = self.directory / view.id
                folder.mkdir()
                with Image.open(view.image) as im:
                    image = im.convert('RGB')
                image.save(folder / 'input.jpg')
                image.save(folder / 'overlay.jpg')
                obs = {'view_id': view.id, 'source_image': str(view.image.relative_to(self.room.path)),
                       'input_path': f'{view.id}/input.jpg', 'overlay_path': f'{view.id}/overlay.jpg',
                       'camera': view.camera, 'status': 'running', 'detections': None,
                       'yolo_status': 'not_run', 'vlm_status': 'not_run', 'vlm_answer': None, 'errors': [],
                       'timing_seconds': {}, 'vlm_attempts': [], 'vlm_observations': [],
                       'vlm_quality': {'status': 'not_run', 'issues': [], 'visual_truth_verified': False}}
                self.report['observations'].append(obs)
                yield self.save('處理視角', view.id)
                if self.mode != 'preview':
                    try:
                        overlay, detections, elapsed = self.models.detect(image, folder)
                        overlay.save(folder / 'overlay.jpg')
                        obs.update(detections=detections, yolo_status='completed')
                        obs['timing_seconds']['yolo_predict'] = elapsed
                    except Exception as exc:
                        obs['yolo_status'] = 'error'
                        obs['errors'].append(f'YOLO: {type(exc).__name__}: {exc}')
                    yield self.save('YOLO 偵測完成' if obs['yolo_status'] == 'completed' else 'YOLO 失敗', view.id)
                if self.stop.is_set():
                    obs['status'] = 'cancelled'
                    break
                if self.mode == 'both':
                    # Do not present missing/failed YOLO as an empty successful detection.
                    if obs['yolo_status'] == 'completed':
                        try:
                            issues = []
                            for attempt in range(2):
                                if self.stop.is_set():
                                    break
                                generation = self.models.describe(image, self.report['question'], view.id, retry_issues=issues)
                                check = validate_observations(generation)
                                obs['vlm_attempts'].append(dict(generation.record(), quality=check))
                                obs['vlm_quality'] = check
                                obs['timing_seconds']['vlm'] = sum(x['seconds'] for x in obs['vlm_attempts'])
                                if check['status'] == 'format_checked':
                                    obs['vlm_observations'] = attach_evidence(check, view.id)
                                    yield self.save('VLM 格式檢查通過（內容仍待人工確認）', view.id)
                                    break
                                issues = check['issues']
                                yield self.save('VLM 格式未通過，準備重試' if attempt == 0 else 'VLM 格式未通過，保留原文', view.id)
                            if self.stop.is_set():
                                obs.update(status='cancelled', vlm_status='cancelled')
                            else:
                                obs['vlm_status'] = 'completed' if obs['vlm_quality']['status'] == 'format_checked' else 'quality_rejected'
                            obs['vlm_answer'] = render_observation(obs)
                        except Exception as exc:
                            obs['vlm_status'] = 'error'
                            obs['errors'].append(f'VLM: {type(exc).__name__}: {exc}')
                    else:
                        obs['vlm_status'] = 'skipped_yolo_error'
                if self.stop.is_set():
                    obs['status'] = 'cancelled'
                else:
                    obs['status'] = 'error' if obs['errors'] else 'quality_rejected' if obs['vlm_status'] == 'quality_rejected' else 'completed'
                if self.mode == 'both' and not obs['vlm_answer']:
                    obs['vlm_answer'] = render_observation(obs)
                write_json(folder / 'observation.json', obs)
                yield self.save('視角處理完成', view.id)
            if self.stop.is_set():
                self.report['status'] = 'cancelled'
            else:
                if self.mode == 'both':
                    yield self.save('彙整房間 VLM 摘要（可能需要較長時間）')
                    try:
                        issues = []
                        if not eligible_evidence(self.report['observations']):
                            self.report.update(summary_status='insufficient_evidence',
                                               summary_quality={'status': 'rejected', 'issues': ['no_eligible_evidence']})
                        else:
                            for attempt in range(2):
                                if self.stop.is_set():
                                    break
                                generation = self.models.summarize(self.room, self.report['observations'], self.report['question'], retry_issues=issues)
                                check = validate_selection(generation, eligible_evidence(self.report['observations']))
                                self.report['summary_attempts'].append(dict(generation.record(), quality=check))
                                self.report['summary_quality'] = check
                                if check['status'] == 'format_checked':
                                    break
                                issues = check['issues']
                            self.report['summary_status'] = 'completed' if self.report['summary_quality']['status'] == 'format_checked' else 'quality_rejected'
                            self.report['summary_seconds'] = sum(x['seconds'] for x in self.report['summary_attempts'])
                        self.report['summary'] = render_summary(self.report['observations'], self.report['summary_quality'])
                    except Exception as exc:
                        self.report.update(summary_status='error', summary_error=f'{type(exc).__name__}: {exc}',
                                           summary_quality={'status': 'error', 'issues': ['inference_error']})
                        self.report['summary'] = render_summary(self.report['observations'], self.report['summary_quality'])
                self.report['status'] = ('cancelled' if self.stop.is_set() else
                                         'partial' if any(o['status'] in ('error', 'quality_rejected') for o in self.report['observations'])
                                         or self.report['summary_status'] in ('error', 'quality_rejected', 'insufficient_evidence') else 'completed')
        except Exception as exc:
            self.report.update(status='error', error=f'{type(exc).__name__}: {exc}')
        finally:
            self.report['wall_seconds'] = time.perf_counter() - start
            self.report['finished_at'] = datetime.now(timezone.utc).isoformat()
            self.save('已停止' if self.report['status'] == 'cancelled' else '掃描結束')
            self.export()
        yield self.save('已停止' if self.report['status'] == 'cancelled' else '掃描結束')

    def export(self):
        observations = self.report['observations']
        contact_sheet(self.directory, observations)
        scanned = [o['view_id'] for o in observations if o['status'] == 'completed']
        fig = self.room.figure(scanned)
        # Include an animation over camera progress; no trajectory or coverage claim.
        import plotly.graph_objects as go
        camera_views = [v for v in self.room.views if v.camera['center_candidate'] is not None]
        if camera_views:
            xyz = np.array([v.camera['center_candidate'] for v in camera_views])
            animation = go.Figure(fig.data[:1])
            marker = go.Scatter3d(x=xyz[:,0], y=xyz[:,1], z=xyz[:,2], mode='markers',
                                  text=[v.id for v in camera_views], marker={'size': 6, 'color': '#94a3b8'},
                                  name='候選相機；未驗證', hovertemplate='%{text}<extra></extra>')
            animation.add_trace(marker)
            animation.update_layout(fig.layout)
            animation.frames = [go.Frame(name=str(i), data=[go.Scatter3d(marker={'color': [
                '#22c55e' if v.id in scanned[:i] else '#94a3b8' for v in camera_views], 'size': 6})], traces=[1])
                for i in range(len(scanned)+1)]
            animation.update_layout(updatemenus=[{'type': 'buttons', 'buttons': [
                {'label': '播放掃描進度', 'method': 'animate', 'args': [None, {'frame': {'duration': 500, 'redraw': True}, 'fromcurrent': True}]},
                {'label': '暫停', 'method': 'animate', 'args': [[None], {'mode': 'immediate', 'frame': {'duration': 0}}]}]}])
            fig = animation
        fig.write_html(self.directory / 'room_progress.html', include_plotlyjs=True)
        self.report['summary'] = self.report['summary'] or ('尚未執行 VLM。以下統計只代表 YOLO 偵測觀測。' if self.mode == 'yolo' else '未產生 VLM 摘要。')
        write_json(self.directory / 'report.json', self.report)
        write_json(self.directory / 'quality_report.json', {
            'prompt_version': PROMPT_VERSION, 'format_checks_are_not_visual_truth': True,
            'views': [{'view_id': o['view_id'], 'quality': o['vlm_quality'], 'attempts': o['vlm_attempts']} for o in observations],
            'summary_quality': self.report['summary_quality'], 'summary_attempts': self.report['summary_attempts']})
        lines = ['# 房間掃描報告', f'狀態：{self.report["status"]}；模式：{self.mode}',
                 f'已完成 {self.report["completed_views"]}/{self.report["total_views"]} 個視角',
                 self.report['summary'], '\n## 限制', *['- ' + x for x in CAVEATS], '\n## 逐視角紀錄']
        for obs in observations:
            lines += [f'### {obs["view_id"]}：{obs["status"]}', obs['vlm_answer'] or 'VLM 未完成',
                      *obs['errors'], f'![{obs["view_id"]}]({obs["overlay_path"]})']
        (self.directory / 'report.md').write_text('\n\n'.join(lines), encoding='utf-8')
        from .export import write_replay
        write_replay(self.room, self.directory, self.report)
        with ZipFile(self.directory / 'results.zip', 'w', ZIP_DEFLATED) as z:
            for file in sorted(self.directory.rglob('*')):
                if file.is_file() and file.name != 'results.zip' and not file.name.endswith('.tmp'):
                    z.write(file, str(file.relative_to(self.directory)))
