from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .config import settings
from .jobs import manager
from .presets import (
    get_avatar_profile,
    get_prompt_preset,
    list_avatar_profiles,
    list_prompt_presets,
)


app = FastAPI(title="Mac Digital Human", version="0.3.0")


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Mac Digital Human</title>
<style>
:root{color-scheme:dark}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#090b10;color:#eef2ff;margin:0}
main{max-width:960px;margin:42px auto;padding:0 20px}.card{background:#141821;border:1px solid #293142;border-radius:20px;padding:30px;box-shadow:0 20px 60px #0005}
h1{font-size:30px;margin:0 0 8px}.muted{color:#9ba7bd;line-height:1.6}.grid{display:grid;gap:18px;margin-top:26px}.modes{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.mode{border:1px solid #374151;border-radius:14px;padding:16px;cursor:pointer;background:#0f131b}.mode.active{border-color:#8bb8ff;background:#132033}.mode b{display:block;margin-bottom:5px}
label{font-weight:650}input,select,textarea,button{width:100%;box-sizing:border-box;margin-top:8px;padding:13px;border-radius:10px;border:1px solid #384154;background:#0f131b;color:#fff}
textarea{min-height:120px;resize:vertical}button{background:#f8fafc;color:#111827;font-weight:780;cursor:pointer;border:0}.panel{display:none}.panel.active{display:grid;gap:18px}.status{white-space:pre-wrap;background:#0f131b;padding:15px;border-radius:10px;min-height:64px;line-height:1.55}
a{color:#9ec5ff}.tip{font-size:13px;color:#9ba7bd;margin-top:7px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.section{border-top:1px solid #2a3140;padding-top:18px}
@media(max-width:680px){.modes,.row{grid-template-columns:1fr}}
</style>
</head>
<body><main><div class="card">
<h1>Mac Digital Human</h1>
<div class="muted">Apple Silicon 本地数字人工作台：MuseTalk 快速口播 + LongCat Avatar 1.5 高质量生成。</div>
<form id="form" class="grid">
<input id="engine" name="engine" type="hidden" value="musetalk">
<div class="modes">
  <div class="mode active" data-engine="musetalk"><b>⚡ 极速数字人口播</b><span class="muted">母版视频 + 新音频，速度快、身份稳定，适合批量课程正文。</span></div>
  <div class="mode" data-engine="longcat"><b>🎬 高质量数字人</b><span class="muted">参考照片 + 音频 + Prompt，适合片头、章节引导和精品短段。</span></div>
</div>

<div class="section"><label>人物模板（可选）</label><select id="profileSelect" name="profile_id"><option value="">本次手工上传素材</option></select><div id="profileTip" class="tip">在 profiles/*.json 中注册人物后，可复用照片、母版和默认 Prompt。</div></div>
<div><label>驱动音频</label><input name="audio" type="file" accept="audio/*" required><div class="tip">单段模式仍由你上传音频；课程批量模式可自动通过 TTS 生成。</div></div>

<div id="musetalkPanel" class="panel active">
  <div><label>母版视频</label><input id="video" name="video" type="file" accept="video/*" required><div class="tip">如果人物模板已经配置 master_video，可不上传。</div></div>
  <div><label>MuseTalk 权重</label><select name="musetalk_variant"><option value="q8">Q8（推荐）</option><option value="q4">Q4</option><option value="fp16">FP16</option></select></div>
</div>

<div id="longcatPanel" class="panel">
  <div><label>参考人物照片</label><input id="image" name="image" type="file" accept="image/*"><div class="tip">如果人物模板已经配置 image，可不上传。</div></div>
  <div class="row">
    <div><label>场景 Prompt 预设</label><select id="promptPreset" name="prompt_preset"></select></div>
    <div><label>LongCat 权重</label><select name="longcat_variant"><option value="q4-merged">Q4 DMD merged（M5 Pro 48GB 推荐）</option><option value="q8-merged">Q8 DMD merged</option><option value="merged">BF16 DMD merged（不建议 48GB）</option></select></div>
  </div>
  <div><label>场景 / 动作 Prompt</label><textarea id="promptText" name="prompt"></textarea><div class="tip">可在预设基础上继续修改。人物模板中的自定义 Prompt 优先于预设。</div></div>
  <div class="row">
    <div><label>生成尺寸</label><select id="longcatSize" name="longcat_size"><option value="preset">跟随 Prompt 预设</option><option value="480x832">832×480</option><option value="432x768">768×432（更省内存）</option></select></div>
    <div><label>生成帧数</label><select id="numFrames" name="num_frames"><option value="0">跟随 Prompt 预设</option><option value="61">61 帧（快速测试）</option><option value="93">93 帧</option><option value="125">125 帧（更长、更吃内存）</option></select></div>
  </div>
</div>

<button id="submitBtn" type="submit">生成数字人口播</button>
</form>
<h3>任务状态</h3><div id="status" class="status">等待提交</div>
</div></main>
<script>
const form=document.getElementById('form'),statusEl=document.getElementById('status'),engineInput=document.getElementById('engine');
const videoInput=document.getElementById('video'),imageInput=document.getElementById('image'),submitBtn=document.getElementById('submitBtn');
const profileSelect=document.getElementById('profileSelect'),promptPreset=document.getElementById('promptPreset'),promptText=document.getElementById('promptText');
let catalog={prompts:[],profiles:[]};
function selectedProfile(){return catalog.profiles.find(x=>x.id===profileSelect.value)||null;}
function selectedPreset(){return catalog.prompts.find(x=>x.id===promptPreset.value)||null;}
function syncRequired(){const p=selectedProfile();videoInput.required=engineInput.value==='musetalk' && !(p&&p.has_master_video);imageInput.required=engineInput.value==='longcat' && !(p&&p.has_image);}
function applyPreset(){const p=selectedPreset();if(p)promptText.value=p.prompt;}
function applyProfile(){const p=selectedProfile();if(p){if(p.prompt_preset)promptPreset.value=p.prompt_preset;const preset=selectedPreset();promptText.value=p.prompt||(preset?preset.prompt:'');document.getElementById('profileTip').textContent=`已选择：${p.name}${p.clone_voice?'｜含声音克隆参考':''}`;}else{document.getElementById('profileTip').textContent='在 profiles/*.json 中注册人物后，可复用照片、母版和默认 Prompt。';applyPreset();}syncRequired();}
function chooseEngine(engine){engineInput.value=engine;document.querySelectorAll('.mode').forEach(x=>x.classList.toggle('active',x.dataset.engine===engine));document.getElementById('musetalkPanel').classList.toggle('active',engine==='musetalk');document.getElementById('longcatPanel').classList.toggle('active',engine==='longcat');submitBtn.textContent=engine==='musetalk'?'生成数字人口播':'生成高质量数字人';syncRequired();}
document.querySelectorAll('.mode').forEach(x=>x.onclick=()=>chooseEngine(x.dataset.engine));
promptPreset.onchange=applyPreset;profileSelect.onchange=applyProfile;
async function loadCatalog(){const r=await fetch('/api/catalog');catalog=await r.json();promptPreset.innerHTML='';catalog.prompts.forEach(p=>{const o=document.createElement('option');o.value=p.id;o.textContent=p.name;promptPreset.appendChild(o);});profileSelect.innerHTML='<option value="">本次手工上传素材</option>';catalog.profiles.forEach(p=>{const o=document.createElement('option');o.value=p.id;o.textContent=p.name;profileSelect.appendChild(o);});if(catalog.prompts.length){promptPreset.value='energy_training_studio';applyPreset();}syncRequired();}
form.onsubmit=async(e)=>{e.preventDefault();statusEl.textContent=engineInput.value==='longcat'?'正在上传并排队… LongCat 首次加载模型会比较慢。':'正在上传并排队…';const r=await fetch('/api/jobs',{method:'POST',body:new FormData(form)});const data=await r.json();if(!r.ok){statusEl.textContent=JSON.stringify(data,null,2);return;}poll(data.id);};
async function poll(id){const r=await fetch('/api/jobs/'+id),j=await r.json();statusEl.textContent='任务 '+id+'\n引擎：'+j.engine+'\n状态：'+j.status+(j.error?'\n'+j.error:'');if(j.status==='completed'){statusEl.innerHTML='任务 '+id+'<br>引擎：'+j.engine+'<br>状态：completed<br><a href="/api/jobs/'+id+'/video">打开生成视频</a>';return;}if(j.status!=='failed')setTimeout(()=>poll(id),2500);}
loadCatalog();
</script></body></html>'''


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return HTML


@app.get("/api/health")
def health() -> dict:
    return manager.readiness()


@app.get("/api/catalog")
def catalog() -> dict:
    profiles = []
    for item in list_avatar_profiles():
        profiles.append(
            {
                "id": item["id"],
                "name": item["name"],
                "prompt_preset": item.get("prompt_preset"),
                "prompt": item.get("prompt", ""),
                "has_image": bool(item.get("image") and Path(item["image"]).exists()),
                "has_master_video": bool(item.get("master_video") and Path(item["master_video"]).exists()),
                "clone_voice": bool((item.get("tts") or {}).get("ref_audio")),
            }
        )
    return {"prompts": list_prompt_presets(), "profiles": profiles}


def _save_upload(upload: UploadFile, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return target


def _profile_asset(profile: dict | None, key: str) -> Path | None:
    if not profile or not profile.get(key):
        return None
    path = Path(str(profile[key])).expanduser().resolve()
    return path if path.exists() else None


@app.post("/api/jobs")
def create_job(
    engine: str = Form("musetalk"),
    audio: UploadFile = File(...),
    video: UploadFile | None = File(None),
    image: UploadFile | None = File(None),
    profile_id: str = Form(""),
    prompt_preset: str = Form("energy_training_studio"),
    variant: str | None = Form(None),
    musetalk_variant: str = Form("q8"),
    longcat_variant: str = Form("q4-merged"),
    prompt: str = Form(""),
    longcat_size: str = Form("preset"),
    num_frames: int = Form(0),
    seed: int = Form(42),
) -> dict:
    if engine not in {"musetalk", "longcat"}:
        raise HTTPException(400, "engine must be musetalk or longcat")

    profile = get_avatar_profile(profile_id) if profile_id else None
    if profile_id and profile is None:
        raise HTTPException(400, f"avatar profile not found: {profile_id}")

    stage = settings.workspace_dir / "uploads" / uuid.uuid4().hex
    stage.mkdir(parents=True, exist_ok=True)
    audio_suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    audio_path = _save_upload(audio, stage / f"audio{audio_suffix}")

    if engine == "musetalk":
        resolved_variant = variant or musetalk_variant
        if resolved_variant not in {"q4", "q8", "fp16"}:
            raise HTTPException(400, "MuseTalk variant must be q4, q8 or fp16")
        if video is not None:
            video_suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
            video_path = _save_upload(video, stage / f"video{video_suffix}")
        else:
            video_path = _profile_asset(profile, "master_video")
        if video_path is None:
            raise HTTPException(400, "MuseTalk requires an uploaded video or a profile with master_video")
        job = manager.create("musetalk", video=video_path, audio=audio_path, variant=resolved_variant)
        return job.to_dict()

    resolved_variant = variant or longcat_variant
    if resolved_variant not in {"q4-merged", "q8-merged", "merged"}:
        raise HTTPException(400, "LongCat variant must be q4-merged, q8-merged or merged")
    if image is not None:
        image_suffix = Path(image.filename or "reference.png").suffix or ".png"
        image_path = _save_upload(image, stage / f"image{image_suffix}")
    else:
        image_path = _profile_asset(profile, "image")
    if image_path is None:
        raise HTTPException(400, "LongCat requires an uploaded image or a profile with image")

    preset_id = prompt_preset or (profile.get("prompt_preset") if profile else None)
    preset = get_prompt_preset(preset_id)
    resolved_prompt = prompt.strip() or (str(profile.get("prompt") or "").strip() if profile else "")
    if not resolved_prompt:
        resolved_prompt = preset.prompt if preset else settings.longcat_default_prompt

    if longcat_size == "preset":
        height = preset.height if preset else settings.longcat_height
        width = preset.width if preset else settings.longcat_width
    else:
        try:
            height_text, width_text = longcat_size.lower().split("x", 1)
            height, width = int(height_text), int(width_text)
        except ValueError as exc:
            raise HTTPException(400, "longcat_size must be preset or look like 480x832") from exc

    resolved_frames = num_frames or (preset.num_frames if preset else settings.longcat_num_frames)
    if (resolved_frames - 1) % 4 != 0:
        raise HTTPException(400, "LongCat num_frames must satisfy 4n+1, e.g. 61, 93, 125")

    job = manager.create(
        "longcat",
        image=image_path,
        audio=audio_path,
        prompt=resolved_prompt,
        variant=resolved_variant,
        height=height,
        width=width,
        num_frames=resolved_frames,
        seed=seed,
    )
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
