"""Build a self-contained HTML replay; no external services or model required."""
import base64
import json

import numpy as np
import plotly.graph_objects as go

from .quality import render_observation


def write_replay(room, directory, report):
    figure = go.Figure(room.figure().data[:1])
    cameras = [view for view in room.views if view.camera['center_candidate'] is not None]
    if cameras:
        xyz = np.array([v.camera['center_candidate'] for v in cameras])
        figure.add_trace(go.Scatter3d(x=xyz[:, 0], y=xyz[:, 1], z=xyz[:, 2], mode='markers+text',
                                     text=[v.id for v in cameras], marker={'size': 5, 'color': '#94a3b8'},
                                     name='候選相機；尚未校正', hovertemplate='%{text}<extra></extra>'))
    figure.update_layout(room.figure().layout)
    figure.update_layout(height=540)
    plot = figure.to_html(full_html=False, include_plotlyjs=True, div_id='room-scene')
    frames = []
    for observation in report['observations']:
        item = dict(observation)
        item["display_text"] = render_observation(observation)
        for key in ['input_path', 'overlay_path']:
            path = directory / item[key]
            item[key] = 'data:image/jpeg;base64,' + base64.b64encode(path.read_bytes()).decode() if path.is_file() else ''
        frames.append(item)
    data = json.dumps({'report': report, 'frames': frames, 'cameras': [v.id for v in cameras]}, ensure_ascii=False).replace('<', '\\u003c')
    html = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>房間掃描結果重播</title>
<style>
body{margin:0;background:#0d1422;color:#e5eaf2;font:16px system-ui,sans-serif}main{max-width:1500px;margin:auto;padding:24px}
h1{margin:0 0 12px}h2{font-size:19px}section{background:#172235;padding:18px;border-radius:12px;margin:16px 0}
.notice{color:#fbd38d}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}img{width:100%;object-fit:contain;max-height:440px}
button{padding:10px 16px;background:#2563eb;color:white;border:0;border-radius:7px;cursor:pointer;margin:4px}
input{width:100%;margin:16px 0}pre{white-space:pre-wrap;font:inherit;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse}
th,td{padding:8px;text-align:left;border-bottom:1px solid #334155}progress{width:100%;height:24px}.small{font-size:14px;color:#bbc9da}
@media(max-width:850px){.grid{grid-template-columns:1fr}main{padding:12px}}
</style><main><h1>房間多視角語意掃描</h1><p id="status"></p>
<p class="notice">離線視角掃描；處理全部影像不代表完整覆蓋房間。相機位置、尺度與物件三維定位尚未驗證。</p>
<section><button id="previous">上一視角</button><button id="play">播放</button><button id="next">下一視角</button>
<label for="timeline" id="view-label"></label><input type="range" id="timeline" min="0" value="0" step="1">
<progress id="progress" value="0" max="1"></progress><p class="small">播放反映視角處理次序，不代表相機實際移動軌跡。</p></section>
<div class="grid"><section><h2>原始 RGB</h2><img id="rgb" alt="來源影像"></section>
<section><h2>YOLO 框與 Mask</h2><img id="overlay" alt="偵測輸出；預覽模式為原圖"></section></div>
<div class="grid"><section>__PLOT__</section><section><h2>此視角分析</h2><pre id="answer"></pre>
<h2>YOLO 偵測觀測</h2><table><thead><tr><th>類別</th><th>信心分數</th><th>影像框</th></tr></thead><tbody id="detections"></tbody></table></section></div>
<section><h2>房間觀測摘錄（來源由程式引用）</h2><pre id="summary"></pre></section>
<section><h2>各類別觀測統計（未跨視角去重）</h2><pre id="counts"></pre></section>
<section><h2>限制與執行錯誤</h2><pre id="caveats"></pre></section></main>
<script>const DATA=__DATA__;
const $=id=>document.getElementById(id);let index=0,timer=null;
const report=DATA.report,frames=DATA.frames;
$('status').textContent=`模式：${report.mode}｜狀態：${report.status}｜成功 ${report.completed_views}/${report.total_views} 個視角｜失敗 ${report.failed_views}`;
$('summary').textContent=report.summary||'VLM 摘要未完成。';
$('counts').textContent=report.objects_by_class.map(x=>`${x.class}：${x.detection_observations} 次觀測；來源 ${x.views.join(', ')}`).join('\\n')||'沒有成功的 YOLO 偵測紀錄。';
$('caveats').textContent=report.caveats.join('\\n')+'\\n'+[report.error,report.summary_error].filter(Boolean).join('\\n');
$('timeline').max=Math.max(0,frames.length-1);$('timeline').disabled=frames.length===0;
function show(n){if(!frames.length){$('view-label').textContent='沒有已處理視角';return;}
index=Math.max(0,Math.min(n,frames.length-1));const f=frames[index];$('timeline').value=index;
$('view-label').textContent=`第 ${index+1}/${frames.length} 張｜視角 ${f.view_id}｜${f.status}`;
$('progress').value=(index+1)/report.total_views;$('rgb').src=f.input_path;$('overlay').src=f.overlay_path;
$('answer').textContent=`YOLO：${f.yolo_status}｜VLM：${f.vlm_status}\\nYOLO predict：${f.timing_seconds.yolo_predict??'未執行'} 秒｜VLM：${f.timing_seconds.vlm??'未執行'} 秒\\n\\n${f.display_text||'未執行或尚未完成 VLM。'}\\n${f.errors.join('\\n')}`;
const body=$('detections');body.replaceChildren();for(const d of f.detections||[]){const tr=document.createElement('tr');
for(const text of [d.class,d.confidence.toFixed(3),d.bbox_xyxy.map(x=>x.toFixed(1)).join(', ')]){const td=document.createElement('td');td.textContent=text;tr.append(td);}body.append(tr);}
const done=new Set(frames.slice(0,index+1).filter(x=>x.status==='completed').map(x=>x.view_id));
if(DATA.cameras.length)Plotly.restyle('room-scene',{'marker.color':[DATA.cameras.map(id=>id===f.view_id?'#f97316':done.has(id)?'#22c55e':'#94a3b8')]},[1]);}
$('timeline').oninput=e=>show(Number(e.target.value));$('previous').onclick=()=>show(index-1);$('next').onclick=()=>show(index+1);
$('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;$('play').textContent='播放';return;}
if(index===frames.length-1)show(0);$('play').textContent='暫停';timer=setInterval(()=>{if(index>=frames.length-1){clearInterval(timer);timer=null;$('play').textContent='播放';}else show(index+1);},1000);};
show(0);</script></html>'''
    (directory / 'scan_review.html').write_text(html.replace('__PLOT__', plot).replace('__DATA__', data), encoding='utf-8')
