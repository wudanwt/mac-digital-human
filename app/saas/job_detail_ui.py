from __future__ import annotations

from fastapi.responses import Response


CSS = r'''
.job-detail-shell{position:fixed;inset:0;z-index:760;background:#070a0f;color:#edf5ff;display:grid;grid-template-rows:72px minmax(0,1fr);overflow:hidden}.job-detail-top{display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid rgba(151,176,214,.12);background:rgba(8,12,18,.96);backdrop-filter:blur(20px)}.job-detail-title{display:flex;align-items:center;gap:13px}.job-detail-mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(145deg,#8edcff,#4389e9);box-shadow:0 0 28px rgba(82,164,255,.2)}.job-detail-title h2{margin:0;font-size:16px}.job-detail-title small{display:block;color:#67778c;margin-top:2px}.job-detail-body{overflow:auto;padding:26px 30px 50px}.job-detail-pane{max-width:1440px;margin:0 auto}.job-detail-hero{display:grid;grid-template-columns:minmax(0,1.3fr) repeat(3,minmax(150px,.55fr));gap:12px;margin-bottom:16px}.job-detail-card{background:linear-gradient(180deg,rgba(17,23,32,.94),rgba(10,14,20,.94));border:1px solid rgba(151,176,214,.12);border-radius:17px;padding:18px;box-shadow:0 18px 52px rgba(0,0,0,.18)}.job-detail-card h1{font-size:22px;margin:0 0 6px}.job-detail-card .metric{font-size:25px;font-weight:780;letter-spacing:-.03em}.job-detail-card .label{font-size:10px;color:#6d7c90;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px}.job-detail-progress{height:8px;border-radius:999px;background:#172130;overflow:hidden;margin-top:14px}.job-detail-progress i{display:block;height:100%;background:linear-gradient(90deg,#357fcb,#70ddff);box-shadow:0 0 18px rgba(91,190,255,.28)}.job-phase-row{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:16px}.job-phase{position:relative;padding:12px 13px;border:1px solid rgba(151,176,214,.1);border-radius:13px;background:#0c1118;color:#617086}.job-phase b{display:block;font-size:11px;color:#8697aa}.job-phase span{font-size:10px}.job-phase.done{border-color:rgba(80,197,157,.18);background:#0c1817}.job-phase.done b{color:#6fd7b2}.job-phase.active{border-color:rgba(99,181,245,.42);background:#0f1d2c;box-shadow:0 0 0 2px rgba(99,181,245,.055)}.job-phase.active b{color:#85cfff}.job-detail-layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:16px}.slide-progress-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(245px,1fr));gap:10px}.slide-progress-card{background:#0b1017;border:1px solid rgba(151,176,214,.10);border-radius:14px;padding:14px}.slide-progress-card.current{border-color:rgba(105,191,255,.42);box-shadow:0 0 0 2px rgba(105,191,255,.05)}.slide-progress-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px}.slide-progress-head b{font-size:12px}.slide-progress-head small{display:block;color:#637389;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:170px}.slide-pipeline{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.slide-stage{padding:7px 6px;border-radius:8px;background:#121923;text-align:center;font-size:9px;color:#65758a;border:1px solid transparent}.slide-stage.running{color:#86cbff;border-color:rgba(94,177,239,.26);background:#102033;animation:jobPulse 1.4s infinite}.slide-stage.done{color:#75d9b5;background:#0d211d}.slide-stage.skipped{color:#8895a5;background:#15191f}.slide-stage.failed{color:#ff97a7;background:#2a151b}.slide-meta-row{display:flex;justify-content:space-between;gap:10px;margin-top:9px;color:#607086;font-size:9px}.job-runtime-side{display:flex;flex-direction:column;gap:10px}.job-runtime-line{display:flex;justify-content:space-between;gap:14px;padding:9px 0;border-bottom:1px solid rgba(151,176,214,.08);font-size:11px}.job-runtime-line span:first-child{color:#69798e}.job-runtime-detail{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;line-height:1.7;color:#8ca9c4;word-break:break-word}.job-error{margin-top:12px;padding:12px;border-radius:10px;background:#29151b;border:1px solid rgba(255,111,133,.2);color:#ff9cad;white-space:pre-wrap}.job-detail-empty{padding:44px;text-align:center;color:#64748b}.job-detail-btn{margin-left:6px}@keyframes jobPulse{0%,100%{opacity:1}50%{opacity:.62}}@media(max-width:980px){.job-detail-hero{grid-template-columns:1fr 1fr}.job-detail-layout{grid-template-columns:1fr}.job-phase-row{grid-template-columns:1fr 1fr}.job-detail-body{padding:18px 14px 40px}}@media(max-width:600px){.job-detail-hero{grid-template-columns:1fr}.job-phase-row{grid-template-columns:1fr}.slide-progress-grid{grid-template-columns:1fr}}
'''


JS = r'''
(() => {
  let detailTimer=null;
  let jobsCache={at:0,items:[]};
  const safe=s=>typeof esc==='function'?esc(s):String(s??'');
  const fmtSec=v=>v==null?'—':`${Number(v).toFixed(Number(v)>=10?0:1)}s`;
  const statusName=s=>({queued:'排队中',running:'生成中',succeeded:'已完成',failed:'失败',canceled:'已取消',pending:'等待',done:'完成',skipped:'跳过'}[s]||s||'—');

  async function jobs(force=false){
    if(!force&&Date.now()-jobsCache.at<2500)return jobsCache.items;
    try{jobsCache={at:Date.now(),items:await api('/jobs')}}catch(_){return jobsCache.items}
    return jobsCache.items;
  }

  async function decorate(){
    if(typeof token==='undefined'||!token)return;
    const rows=[...document.querySelectorAll('#page table tr')].filter(r=>r.querySelector('td.code'));
    if(!rows.length)return;
    const items=await jobs();
    rows.forEach(row=>{
      if(row.querySelector('[data-job-detail]'))return;
      const prefix=(row.querySelector('td.code')?.textContent||'').trim();
      const job=items.find(j=>String(j.id).startsWith(prefix));if(!job)return;
      const last=row.lastElementChild;if(!last)return;
      const btn=document.createElement('button');btn.className='secondary job-detail-btn';btn.dataset.jobDetail=job.id;btn.textContent='详情';last.appendChild(btn);
    });
  }

  function closeDetail(){if(detailTimer){clearTimeout(detailTimer);detailTimer=null}document.getElementById('jobDetailShell')?.remove()}

  function stageClass(stage,n,status){if(status==='succeeded')return'done';if(stage>n)return'done';if(stage===n&&status==='running')return'active';return''}
  function stageBox(n,name,sub,stage,status){return `<div class="job-phase ${stageClass(stage,n,status)}"><b>0${n} · ${safe(name)}</b><span>${safe(sub)}</span></div>`}
  function slideStage(label,value){return `<div class="slide-stage ${safe(value||'pending')}">${safe(label)} · ${safe(statusName(value||'pending'))}</div>`}

  function renderShell(d){
    const runtime=d.runtime||{},slides=Object.values(runtime.slides||{}),stage=Number(runtime.stage||0);
    const elapsed=runtime.elapsed_seconds??(d.gpu_seconds||null),eta=runtime.eta_seconds;
    const course=safe(d.course_title||'数字人课程');
    const current=Number(runtime.current_slide||0);
    const matrix=slides.length?slides.map(s=>`<div class="slide-progress-card ${Number(s.index)===current?'current':''}"><div class="slide-progress-head"><div><b>SLIDE ${String(s.index).padStart(2,'0')}</b><small>${safe(s.title||'')}</small></div><span class="badge">${s.audio_seconds?`${Number(s.audio_seconds).toFixed(1)}s`:'—'}</span></div><div class="slide-pipeline">${slideStage('语音',s.audio)}${slideStage('口型',s.video)}${slideStage('合成',s.compose)}</div><div class="slide-meta-row"><span>TTS ${fmtSec(s.tts_elapsed_seconds)}</span><span>MuseTalk ${fmtSec(s.render_seconds)}</span>${s.musetalk?.batch_size?`<span>Batch ${safe(s.musetalk.batch_size)}</span>`:''}</div></div>`).join(''):'<div class="job-detail-empty">任务尚未进入逐页生产阶段</div>';
    return `<section id="jobDetailShell" class="job-detail-shell"><header class="job-detail-top"><div class="job-detail-title"><div class="job-detail-mark"></div><div><h2>生成任务详情</h2><small>${course} · ${safe(d.id.slice(0,16))}</small></div></div><div class="actions">${d.output_asset_id?`<button class="primary" data-job-download="${safe(d.output_asset_id)}">预览 / 下载成片</button>`:''}<button class="secondary" data-job-detail-close>返回任务中心</button></div></header><main class="job-detail-body"><div class="job-detail-pane"><div class="job-detail-hero"><div class="job-detail-card"><div class="label">CURRENT STAGE</div><h1>${safe(runtime.stage_name||d.stage||statusName(d.status))}</h1><div class="muted">${safe(runtime.step_detail||'任务正在等待 Worker 更新详细状态')}</div><div class="job-detail-progress"><i style="width:${Math.max(0,Math.min(100,Number(d.progress||0)))}%"></i></div></div><div class="job-detail-card"><div class="label">PROGRESS</div><div class="metric">${Number(d.progress||0)}%</div><div class="muted">${safe(statusName(d.status))}</div></div><div class="job-detail-card"><div class="label">ELAPSED</div><div class="metric">${fmtSec(elapsed)}</div><div class="muted">已耗时</div></div><div class="job-detail-card"><div class="label">ETA</div><div class="metric">${eta==null?'—':fmtSec(eta)}</div><div class="muted">动态估算</div></div></div><div class="job-phase-row">${stageBox(1,'课件解析','PPT 高清底板',stage,d.status)}${stageBox(2,'语音合成','CosyVoice 高保真',stage,d.status)}${stageBox(3,'数字人驱动','MuseTalk MLX',stage,d.status)}${stageBox(4,'排版压制','画面 / 字幕 / 标识',stage,d.status)}${stageBox(5,'完成','上传 SaaS 成片',stage,d.status)}</div><div class="job-detail-layout"><section class="job-detail-card"><div class="toolbar"><div><div class="label">SLIDE MATRIX</div><h2 style="margin:0">逐页生成进度</h2></div><span class="muted">当前第 ${current||'—'} / ${runtime.total_slides||slides.length||'—'} 页</span></div><div class="slide-progress-grid">${matrix}</div></section><aside class="job-runtime-side"><div class="job-detail-card"><div class="label">RUNTIME</div><div class="job-runtime-line"><span>生成引擎</span><b>${safe(d.engine)}</b></div><div class="job-runtime-line"><span>队列等待</span><b>${fmtSec(d.queue_wait_seconds)}</b></div><div class="job-runtime-line"><span>成片时长</span><b>${fmtSec(d.video_seconds)}</b></div><div class="job-runtime-line"><span>TTS 流水线预取</span><b>${runtime.tts_prefetch===true?'开启':runtime.tts_prefetch===false?'关闭':'—'}</b></div></div><div class="job-detail-card"><div class="label">LIVE LOGIC</div><div class="job-runtime-detail">${safe(runtime.step_detail||d.stage||'等待任务状态')}</div>${d.error?`<div class="job-error">${safe(d.error)}</div>`:''}</div></aside></div></div></main></section>`;
  }

  async function refreshDetail(id){
    try{
      const d=await api('/jobs/'+id+'/detail');
      const old=document.getElementById('jobDetailShell');
      const holder=document.createElement('div');holder.innerHTML=renderShell(d);const fresh=holder.firstElementChild;
      if(old)old.replaceWith(fresh);else document.body.appendChild(fresh);
      if(['queued','running'].includes(d.status))detailTimer=setTimeout(()=>refreshDetail(id),1500);
    }catch(e){if(typeof toast==='function')toast(e.message)}
  }

  document.addEventListener('click',e=>{
    const btn=e.target.closest('[data-job-detail]');if(btn){e.preventDefault();closeDetail();refreshDetail(btn.dataset.jobDetail);return}
    if(e.target.closest('[data-job-detail-close]')){closeDetail();return}
    const dl=e.target.closest('[data-job-download]');if(dl&&typeof downloadAsset==='function')downloadAsset(dl.dataset.jobDownload,'result.mp4').catch(err=>toast(err.message));
  },true);

  const observer=new MutationObserver(()=>setTimeout(decorate,0));observer.observe(document.body,{childList:true,subtree:true});
  setInterval(()=>{if(typeof current!=='undefined'&&(current==='jobs'||current==='dashboard'))decorate()},3500);
})();
'''


def css_response() -> Response:
    return Response(CSS, media_type="text/css; charset=utf-8")


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
