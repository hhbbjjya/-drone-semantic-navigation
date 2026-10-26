"""Frozen official vocabularies keep class IDs stable across library upgrades."""
import json
from pathlib import Path

DATA=json.loads(Path(__file__).with_name('vocabularies.json').read_text(encoding='utf-8'))
RESEARCH_CLASSES=['laptop','computer monitor','keyboard','chair','desk']
VOCABULARIES={**DATA['vocabularies'],'research':RESEARCH_CLASSES}
LABELS={'lvis':'LVIS 全部 1,203 類（預設）','coco':'COCO 全部 80 類',
        'research':'原研究 5 類','custom':'自訂類別'}


def resolve_classes(vocabulary='lvis', custom=None):
    if vocabulary=='custom':
        names=custom.split(',') if isinstance(custom,str) else list(custom or [])
        names=list(dict.fromkeys(x.strip() for x in names if isinstance(x,str) and x.strip()))
        if not names:raise ValueError('自訂類別不可為空；請以英文逗號分隔')
        return names
    if vocabulary not in VOCABULARIES:raise ValueError(f'未知詞彙表：{vocabulary}')
    return list(VOCABULARIES[vocabulary])
