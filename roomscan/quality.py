"""Constrain attribution and output shape; this is NOT a visual-truth judge."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from collections import Counter

PROMPT_VERSION = '2.0'
LOCATIONS = ('左側', '中央', '右側', '上方', '下方', '背景', '位置不明')


@dataclass
class Generation:
    text: str
    seconds: float
    generated_tokens: int | None = None
    max_new_tokens: int | None = None
    finish_reason: str = 'unknown'
    eos_observed: bool | None = None

    def record(self):
        return asdict(self)


def text_issues(text):
    issues = []
    if not text.strip():
        issues.append('empty_output')
    if '\ufffd' in text:
        issues.append('invalid_unicode')
    # Detect loops both across list items and inside an unbroken string.
    lines = [re.sub(r'^[\s\-*\d.]+', '', line).strip() for line in text.splitlines()]
    # Repeated JSON keys/indentation are normal for a list of observations.
    repeated = Counter(line for line in lines if len(line) >= 2 and not re.match(r'^["{}\[\],]', line))
    if any(count >= 3 for count in repeated.values()) or re.search(r'(.{3,80}?)\1\1', text):
        issues.append('repetition')
    if re.search(r'YOLO(?:E)?', text, re.I):
        issues.append('model_claims_yolo_provenance')
    return issues


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def parse_json(text):
    return json.loads(text, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def parse_payload(text):
    text = text.strip()
    normalizations = []
    fenced = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
        normalizations.append('removed_single_json_fence')
    return parse_json(text), normalizations


def validate_observations(generation: Generation):
    issues = text_issues(generation.text)
    if generation.finish_reason == 'length':
        issues.append('token_limit')
    # v2 deliberately requires measured termination, not an inference from text length.
    if generation.finish_reason not in ('eos', 'length'):
        issues.append('termination_unverified')
    payload = None
    normalizations = []
    try:
        payload, normalizations = parse_payload(generation.text)
        if isinstance(payload, list):
            payload = {'observations': payload}
            normalizations.append('wrapped_observation_array')
    except (ValueError, TypeError):
        issues.append('invalid_json')
    observations = []
    if 'invalid_json' not in issues:
        if not isinstance(payload, dict) or set(payload) != {'observations'} or not isinstance(payload['observations'], list):
            issues.append('invalid_schema')
        elif len(payload['observations']) > 3:
            issues.append('too_many_observations')
        else:
            seen = set()
            for index, item in enumerate(payload['observations']):
                uncertainty_source = 'model'
                if isinstance(item, dict) and set(item) == {'object', 'location'}:
                    item = dict(item, uncertain=True)
                    uncertainty_source = 'missing_default_true'
                    normalizations.append(f'observation_{index}_missing_uncertainty_marked_unknown')
                if (not isinstance(item, dict) or set(item) != {'object', 'location', 'uncertain'}
                    or not isinstance(item['object'], str) or not 1 <= len(item['object'].strip()) <= 24
                    or not re.fullmatch(r'[\w\u3400-\u9fff ()/\-]+', item['object'])
                    or item['location'] not in LOCATIONS or type(item['uncertain']) is not bool):
                    issues.append('invalid_observation')
                    continue
                name = item['object'].strip()
                if name.casefold() in seen:
                    issues.append('duplicate_object')
                seen.add(name.casefold())
                observations.append({'object': name, 'location': item['location'], 'uncertain': item['uncertain'],
                                     'uncertainty_source': uncertainty_source,
                                     'source': 'vlm_visual_observation', 'human_verified': False})
    issues = list(dict.fromkeys(issues))
    return {'status': 'rejected' if issues else 'format_checked', 'issues': issues,
            'normalizations': normalizations, 'visual_truth_verified': False, 'observations': [] if issues else observations}


def attach_evidence(check, view_id):
    return [dict(item, evidence_id=f'{view_id}:vlm:{i+1}', view_id=view_id)
            for i, item in enumerate(check['observations'])] if check['status'] == 'format_checked' else []


def eligible_evidence(observations):
    # Require both explicit v2 quality status and successful inference.
    return [item for obs in observations if obs.get('vlm_status') == 'completed'
            and obs.get('vlm_quality', {}).get('status') == 'format_checked'
            for item in obs.get('vlm_observations', [])]


def validate_selection(generation, evidence):
    issues = text_issues(generation.text)
    if generation.finish_reason == 'length':
        issues.append('token_limit')
    elif generation.finish_reason != 'eos':
        issues.append('termination_unverified')
    selected = []
    normalizations = []
    try:
        payload, normalizations = parse_payload(generation.text)
        if isinstance(payload, list):
            payload = {'selected_evidence_ids': payload}
            normalizations.append('wrapped_selection_array')
        if (not isinstance(payload, dict) or set(payload) != {'selected_evidence_ids'}
            or not isinstance(payload['selected_evidence_ids'], list)
            or len(payload['selected_evidence_ids']) > 8
            or not all(isinstance(x, str) for x in payload['selected_evidence_ids'])):
            issues.append('invalid_selection_schema')
        else:
            selected = payload['selected_evidence_ids']
            allowed = {item['evidence_id'] for item in evidence}
            if any(x not in allowed for x in selected):
                issues.append('unknown_evidence_id')
            if len(selected) != len(set(selected)):
                issues.append('duplicate_evidence_id')
    except (ValueError, TypeError):
        issues.append('invalid_json')
    issues = list(dict.fromkeys(issues))
    return {'status': 'rejected' if issues else 'format_checked', 'issues': issues,
            'normalizations': normalizations, 'selected_evidence_ids': [] if issues else selected, 'visual_truth_verified': False}


def render_observation(obs):
    if 'vlm_quality' not in obs:
        return '舊版模型原文（尚未通過 v2 檢查）：\n' + (obs.get('vlm_answer') or 'VLM 未執行。')
    lines = [f'視角 {obs["view_id"]}｜來源編號由程式附加', 'YOLOE 偵測紀錄（由程式直接列出；仍可能誤判）：']
    if obs.get('yolo_status') != 'completed':
        lines.append('未完成 YOLO 推論。')
    elif not obs.get('detections'):
        lines.append('沒有偵測到指定類別；不代表畫面沒有物件。')
    else:
        lines += [f'- {d["class"]}｜score={d["confidence"]:.3f}｜2D 框={d["bbox_xyxy"]}' for d in obs['detections']]
    check = obs['vlm_quality']
    lines.append('\nVLM 額外觀察（格式檢查不等於內容正確，尚未人工確認）：')
    if check['status'] == 'format_checked':
        lines += [f'- {x["object"]}｜{x["location"]}｜{uncertainty_label(x)} [{x["view_id"]}]'
                  for x in obs.get('vlm_observations', [])]
        if not obs.get('vlm_observations'):
            lines.append('模型未提供可列出的觀察。')
    else:
        lines.append('未納入摘要；檢查狀態：' + check['status'])
        lines += ['- ' + issue for issue in check.get('issues', [])]
    return '\n'.join(lines)


def uncertainty_label(item):
    if item.get('uncertainty_source') == 'missing_default_true':
        return '模型未提供不確定性（程式保守標記）'
    return '模型標為不確定' if item['uncertain'] else '模型未標不確定'


def render_summary(observations, selection):
    # YOLO facts and citations are never generated or rewritten by the VLM.
    grouped = {}
    for obs in observations:
        for d in obs.get('detections') or []:
            entry = grouped.setdefault(d['class'], {'count': 0, 'views': set()})
            entry['count'] += 1
            entry['views'].add(obs['view_id'])
    lines = ['YOLOE 偵測觀測統計（程式彙整；非獨立物件數，偵測可能誤判）：']
    lines += [f'- {label}：{item["count"]} 次；來源 [{", ".join(sorted(item["views"]))}]'
              for label, item in sorted(grouped.items())]
    if not grouped:
        lines.append('沒有可彙整的 YOLO 偵測。')
    lines.append('\nVLM 觀察摘錄（未經人工確認；只接受有來源的既有紀錄）：')
    evidence = {item['evidence_id']: item for item in eligible_evidence(observations)}
    chosen = selection.get('selected_evidence_ids', []) if selection.get('status') == 'format_checked' else []
    for key in chosen:
        if key in evidence:
            item = evidence[key]
            lines.append(f'- {item["object"]}｜{item["location"]}｜{uncertainty_label(item)} [{item["view_id"]}]')
    if not chosen:
        lines.append('未產生通過檢查的 VLM 摘錄；請檢查各視角及品質紀錄。')
    lines.append('\n相同物件可能出現在多個視角；未驗證物件數量、三維位置或房間覆蓋率。')
    return '\n'.join(lines)
