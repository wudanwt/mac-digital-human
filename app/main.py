from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .config import settings
from .jobs import manager


app = FastAPI(title="Mac Digital Human", version="0.1.0")


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Mac Digital Human</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0b0d12;color:#eef2ff;margin:0}
main{max-width:860px;margin:48px auto;padding:0 20px}.card{background:#151923;border:1px solid #2a3140;border-radius:18px;padding:28px}
h1{font-size:30px;margin:0 0 8px}.muted{color:#9ba7bd}.grid{display:grid;gap:18px;margin-top:28px}label{font-weight:650}
input,select,button{width:100%;box-sizing:border-box;margin-top:8px;padding:13px;border-radius:10px;border:1px solid #384154;background:#0f131b;color:#fff}
button{background:#fff;color:#111827;font-weight:750;cursor:pointer}.status{white-space:pre-wrap;background:#0f131b;padding:15px;border-radius:10px;min-height:62px}
a{color:#9ec5ff}</style>
</head>
<body><main><div class="card">
<h1>Mac Digital Human</h1><div class="muted">M5 Pro / Apple Silicon 本地数字人口播 MVP</div>
<form id="form" class="grid">
<div><label>母版视频</label><input name="video" type="file" accept="video/*" required></div>
<div><label>新音频</label><input name="audio" type="file" accept="audio/*" required></div>
<div><label>MLX 权重</label><select name="variant"><option value="q8">Q8（M5 Pro 48GB 推荐）</option><option value="fp16">FP16</option><option value="q4">Q4</option></select></div>
<button type="submit">生成数字人口播</button></form>
<h3>任务状态</h3><div id="status" class="status">等待提交</div>
</div></main>
<script>
const form=document.getElementById('form'), statusEl=document.getElementById('status');
form.onsubmit=async(e)=>{e.preventDefault();statusEl.textContent='正在上传…';
 const r=await fetch('/api/jobs',{method:'POST',body:new FormData(form)});const data=await r.json();
 if(!r.ok){statusEl.textContent=JSON.stringify(data,null,2);return;} poll(data.id);};
async function poll(id){const r=await fetch('/api/jobs/'+id),j=await r.json();
 statusEl.textContent='任务 '+id+'\n状态：'+j.status+(j.error?'\n'+j.error:'');
 if(j.status==='completed'){statusEl.innerHTML='任务 '+id+'<br>状态：completed<br><a href="/api/jobs/'+id+'/video">打开生成视频</a>';return;}
 if(j.status!=='failed')setTimeout(()=>poll(id),2000);}
</script></body></html>'''


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return HTML


@app.get("/api/health")
def health() -> dict:
    return manager.engine.readiness()


@app.post("/api/jobs")
def create_job(
    video: UploadFile = File(...),
    audio: UploadFile = File(...),
    variant: str = Form("q8"),
) -> dict:
    if variant not in {"q4", "q8", "fp16"}:
        raise HTTPException(400, "variant must be q4, q8 or fp16")
    stage = settings.workspace_dir / "uploads" / uuid.uuid4().hex
    stage.mkdir(parents=True, exist_ok=True)
    video_suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
    audio_suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    video_path = stage / f"video{video_suffix}"
    audio_path = stage / f"audio{audio_suffix}"
    with video_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)
    with audio_path.open("wb") as f:
        shutil.copyfileobj(audio.file, f)
    job = manager.create(video_path, audio_path, variant)
    return job.to_dict()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/video")
def get_video(job_id: str):
    job = manager.get(job_id)
    if not job or job.status != "completed" or not job.output:
        raise HTTPException(404, "completed video not found")
    output = Path(job.output).resolve()
    root = settings.outputs_dir.resolve()
    if root not in output.parents:
        raise HTTPException(403, "invalid output path")
    return FileResponse(output, media_type="video/mp4", filename=f"{job_id}.mp4")
