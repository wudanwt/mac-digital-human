from __future__ import annotations

from fastapi.responses import Response


CSS = r'''
.job-result-preview{margin-bottom:16px}.job-result-preview video{display:block;width:100%;max-height:min(62vh,720px);aspect-ratio:16/9;object-fit:contain;background:#020305;border:1px solid rgba(151,176,214,.12);border-radius:10px}.job-result-preview .toolbar{margin-bottom:10px}.job-preview-loading{display:grid;place-items:center;min-height:240px;color:#718197;background:#05080c;border-radius:10px}
.job-detail-shell{position:fixed;inset:0;z-index:760;background:#070a0f;color:#edf5ff;display:grid;grid-template-rows:72px minmax(0,1fr);overflow:hidden}.job-detail-top{display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid rgba(151,176,214,.12);background:rgba(8,12,18,.96);backdrop-filter:blur(20px)}.job-detail-title{display:flex;align-items:center;gap:13px}.job-detail-mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(145deg,#8edcff,#4389e9);box-shadow:0 0 28px rgba(82,164,255,.2)}.job-detail-title h2{margin:0;font-size:16px}.job-detail-title small{display:block;color:#67778c;margin-top:2px}.job-detail-body{overflow:auto;padding:26px 30px 50px}.job-detail-pane{max-width:1440px;margin:0 auto}.job-detail-hero{display:grid;grid-template-columns:minmax(0,1.3fr) repeat(3,minmax(150px,.55fr));gap:12px;margin-bottom:16px}.job-detail-card{background:linear-gradient(180deg,rgba(17,23,32,.94),rgba(10,14,20,.94));border:1px solid rgba(151,176,214,.12);border-radius:17px;padding:18px;box-shadow:0 18px 52px rgba(0,0,0,.18)}.job-detail-card h1{font-size:22px;margin:0 0 6px}.job-detail-card .metric{font-size:25px;font-weight:780;letter-spacing:-.03em}.job-detail-card .label{font-size:10px;color:#6d7c90;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px}.job-detail-progress{height:8px;border-radius:999px;background:#172130;overflow:hidden;margin-top:14px}.job-detail-progress i{display:block;height:100%;background:linear-gradient(90deg,#357fcb,#70ddff);box-shadow:0 0 18px rgba(91,190,255,.28)}.job-phase-row{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:16px}.job-phase{position:relative;padding:12px 13px;border:1px solid rgba(151,176,214,.1);border-radius:13px;background:#0c1118;color:#617086}.job-phase b{display:block;font-size:11px;color:#8697aa}.job-phase span{font-size:10px}.job-phase.done{border-color:rgba(80,197,157,.18);background:#0c1817}.job-phase.done b{color:#6fd7b2}.job-phase.active{border-color:rgba(99,181,245,.42);background:#0f1d2c;box-shadow:0 0 0 2px rgba(99,181,245,.055)}.job-phase.active b{color:#85cfff}.job-detail-layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:16px}.slide-progress-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(245px,1fr));gap:10px}.slide-progress-card{background:#0b1017;border:1px solid rgba(151,176,214,.10);border-radius:14px;padding:14px}.slide-progress-card.current,.slide-progress-card.running{border-color:rgba(105,191,255,.42);box-shadow:0 0 0 2px rgba(105,191,255,.05)}.slide-progress-card.failed{border-color:rgba(255,111,133,.28)}.slide-progress-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px}.slide-progress-head b{font-size:12px}.slide-progress-head small{display:block;color:#637389;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:170px}.slide-pipeline{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.slide-stage{padding:7px 6px;border-radius:8px;background:#121923;text-align:center;font-size:9px;color:#65758a;border:1px solid transparent}.slide-stage.running{color:#86cbff;border-color:rgba(94,177,239,.26);background:#102033;animation:jobPulse 1.4s infinite}.slide-stage.done{color:#75d9b5;background:#0d211d}.slide-stage.skipped{color:#8895a5;background:#15191f}.slide-stage.failed{color:#ff97a7;background:#2a151b}.slide-progress-bar{height:4px;border-radius:99px;background:#172130;overflow:hidden;margin-top:8px}.slide-progress-bar i{display:block;height:100%;background:linear-gradient(90deg,#357fcb,#70ddff)}.slide-meta-row{display:flex;justify-content:space-between;gap:10px;margin-top:9px;color:#607086;font-size:9px}.job-runtime-side{display:flex;flex-direction:column;gap:10px}.job-runtime-line{display:flex;justify-content:space-between;gap:14px;padding:9px 0;border-bottom:1px solid rgba(151,176,214,.08);font-size:11px}.job-runtime-line span:first-child{color:#69798e}.job-runtime-detail{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;line-height:1.7;color:#8ca9c4;word-break:break-word;white-space:pre-wrap}.job-error{margin-top:12px;padding:12px;border-radius:10px;background:#29151b;border:1px solid rgba(255,111,133,.2);color:#ff9cad;white-space:pre-wrap}.job-detail-empty{padding:44px;text-align:center;color:#64748b}.job-detail-btn{margin-left:6px;white-space:nowrap}.job-detail-btn.primary-entry{border-color:rgba(90,177,245,.45);background:#10283e;color:#aaddff}@keyframes jobPulse{0%,100%{opacity:1}50%{opacity:.62}}@media(max-width:980px){.job-detail-hero{grid-template-columns:1fr 1fr}.job-detail-layout{grid-template-columns:1fr}.job-phase-row{grid-template-columns:1fr 1fr}.job-detail-body{padding:18px 14px 40px}}@media(max-width:600px){.job-detail-hero{grid-template-columns:1fr}.job-phase-row{grid-template-columns:1fr}.slide-progress-grid{grid-template-columns:1fr}}
'''


JS = r'''
(() => {
  let detailTimer=null;
  let resultVideoUrl=null;
  let jobsCache={at:0,items:[]};
  const safe=s=>typeof esc==='function'?esc(s):String(s??'');
  const fmtSec=v=>{
    if(v==null||v===''||Number.isNaN(Number(v)))return '—';
    const total=Math.max(0,Math.round(Number(v)));
    if(total<60)return `${total}秒`;
    const hours=Math.floor(total/3600),minutes=Math.floor((total%3600)/60),seconds=total%60;
    if(hours)return `${hours}小时${minutes}分${seconds}秒`;
    return `${minutes}分${seconds}秒`;
  };
  const parseTime=v=>{const ms=Date.parse(v||'');return Number.isFinite(ms)?ms:null};
  const statusName=s=>({queued:'排队中',running:'生成中',succeeded:'已完成',failed:'失败',canceled:'已取消',pending:'等待',done:'完成',skipped:'跳过',blocked:'等待前置',retry_wait:'等待重试',audio_start:'语音合成',audio_done:'语音完成',video_start:'数字人驱动',video_done:'口型完成',video_skipped:'跳过口型',compose_start:'排版压制',compose_done:'本页合成完成',distributed_prepare:'课件准备',distributed_pages:'多机分页生成',distributed_finalize:'成片封装',waiting_avatar_matting:'等待透明资产',waiting_matting:'等待抠像',ppt_prepare:'解析课件',publishing_pages:'分发页面',materializing_pages:'汇总页面',concat:'拼接成片',publishing:'上传成片',completed:'完成',center_starting:'中心启动',page_failed:'页面失败'}[s]||s||'—');

  function patchJobTable(){
    const original=window.jobTable;
    if(typeof original!=='function'||original.__jobDetailPatched)return;
    const wrapped=function(items){
      const html=original(items);
      if(!Array.isArray(items)||!items.length)return html;
      const host=document.createElement('div');host.innerHTML=html;
      const rows=[...host.querySelectorAll('tbody tr')];
      rows.forEach((row,index)=>{
        const job=items[index];if(!job)return;
        const last=row.lastElementChild;if(!last)return;
        if(!last.querySelector('[data-job-detail]')){
          const btn=document.createElement('button');
          btn.className='secondary job-detail-btn primary-entry';
          btn.dataset.jobDetail=job.id;
          btn.textContent='查看详情';
          last.appendChild(btn);
        }
      });
      return host.innerHTML;
    };
    wrapped.__jobDetailPatched=true;
    window.jobTable=wrapped;
  }

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
      const btn=document.createElement('button');btn.className='secondary job-detail-btn primary-entry';btn.dataset.jobDetail=job.id;btn.textContent='查看详情';last.appendChild(btn);
    });
  }

  function releaseResultVideo(){if(resultVideoUrl){URL.revokeObjectURL(resultVideoUrl);resultVideoUrl=null}}
  function closeDetail(){if(detailTimer){clearTimeout(detailTimer);detailTimer=null}releaseResultVideo();document.getElementById('jobDetailShell')?.remove()}

  async function hydrateResultVideo(assetId){
    const host=document.querySelector('[data-job-video-preview]');if(!host||!assetId)return;
    try{
      const r=await fetch(API+'/assets/'+assetId+'/download',{headers:{Authorization:'Bearer '+token}});
      if(!r.ok)throw Error('成片预览加载失败');
      releaseResultVideo();resultVideoUrl=URL.createObjectURL(await r.blob());
      if(!document.body.contains(host)){releaseResultVideo();return}
      host.innerHTML=`<video controls playsinline preload="metadata" src="${resultVideoUrl}"></video>`;
    }catch(e){host.innerHTML=`<div class="job-preview-loading">${safe(e.message)}</div>`}
  }

  function mountResultPreview(shell,assetId){
    if(!shell||!assetId)return;
    const section=document.createElement('section');section.className='job-detail-card job-result-preview';
    section.innerHTML=`<div class="toolbar"><div><div class="label">RESULT PREVIEW</div><h2 style="margin:0">成片预览</h2></div><button class="secondary" data-job-download="${safe(assetId)}">下载成片</button></div><div data-job-video-preview><div class="job-preview-loading">正在加载成片…</div></div>`;
    shell.querySelector('.job-detail-layout')?.before(section);
    const headerDownload=shell.querySelector('.job-detail-top [data-job-download]');if(headerDownload)headerDownload.textContent='下载成片';
  }

  function clarifyTimeLabels(shell){
    const label=[...shell.querySelectorAll('.job-detail-card .label')].find(item=>item.textContent.trim()==='ETA');
    if(!label)return;
    label.textContent='REMAINING';
    const note=label.parentElement?.querySelector('.muted');if(note)note.textContent='预计剩余时间';
  }

  function stageClass(stage,n,status,actives){
    if(status==='succeeded')return'done';
    if(Array.isArray(actives)&&actives.includes(n))return'active';
    if(stage>n)return'done';
    if(stage===n&&status==='running')return'active';
    return'';
  }
  function stageBox(n,name,sub,stage,status,actives){return `<div class="job-phase ${stageClass(stage,n,status,actives)}"><b>0${n} · ${safe(name)}</b><span>${safe(sub)}</span></div>`}
  function slideStage(label,value){return `<div class="slide-stage ${safe(value||'pending')}">${safe(label)} · ${safe(statusName(value||'pending'))}</div>`}

  function pageTasks(d){return (Array.isArray(d.tasks)?d.tasks:[]).filter(t=>t.type==='page').slice().sort((a,b)=>Number(a.slide_index||0)-Number(b.slide_index||0))}

  function pagePipeline(task){
    const stage=String(task?.stage||'');
    const status=String(task?.status||'');
    const succeeded=status==='succeeded';
    const failed=status==='failed'||status==='canceled';
    const running=status==='running';
    const audioDone=succeeded||/^(audio_done|video_|compose_)/.test(stage);
    const videoDone=succeeded||/^(video_done|video_skipped|compose_)/.test(stage);
    const composeDone=succeeded||stage==='compose_done';
    const audioRun=running&&(stage===''||stage==='running'||stage==='audio_start'||stage==='center_starting');
    const videoRun=running&&stage==='video_start';
    const composeRun=running&&stage==='compose_start';
    const state=(done,run,failNow)=>failNow?'failed':done?'done':run?'running':'pending';
    return {
      audio:state(audioDone,audioRun,failed&&!audioDone&&!videoRun&&!composeRun),
      video:state(videoDone,videoRun,failed&&audioDone&&!videoDone),
      compose:state(composeDone,composeRun,failed&&videoDone&&!composeDone)
    };
  }

  function distributedPhase(d){
    const tasks=Array.isArray(d.tasks)?d.tasks:[];
    const prepare=tasks.find(t=>t.type==='prepare');
    const finalize=tasks.find(t=>t.type==='finalize');
    const pages=pageTasks(d);
    const actives=[];
    let current=Number((d.runtime||{}).stage||0);
    if(d.status==='succeeded')return {current:5,actives:[]};
    if(prepare&&(prepare.status==='running'||prepare.status==='queued')){current=Math.max(current,1);actives.push(1)}
    else if(prepare&&prepare.status==='succeeded')current=Math.max(current,1);
    const runningPages=pages.filter(p=>p.status==='running');
    if(runningPages.some(p=>{const s=String(p.stage||'');return !s||s==='running'||s==='center_starting'||s.startsWith('audio')}))actives.push(2);
    if(runningPages.some(p=>String(p.stage||'').startsWith('video')))actives.push(3);
    if(runningPages.some(p=>String(p.stage||'').startsWith('compose')))actives.push(4);
    if(pages.some(p=>p.status==='running'||p.status==='succeeded'))current=Math.max(current,2);
    if(pages.some(p=>/^(video_|compose_)/.test(String(p.stage||''))||p.status==='succeeded'))current=Math.max(current,3);
    if(pages.some(p=>String(p.stage||'').startsWith('compose')||p.status==='succeeded'))current=Math.max(current,4);
    if(finalize&&finalize.status==='running'){current=5;actives.push(5)}
    if(finalize&&finalize.status==='succeeded')current=5;
    if(actives.length)current=Math.max(current,...actives);
    return {current,actives};
  }

  function slideMatrix(d){
    const runtime=d.runtime||{};
    const runtimeSlides=runtime.slides||{};
    const pages=pageTasks(d);
    if(pages.length){
      return pages.map(task=>{
        const meta=runtimeSlides[task.slide_index]||runtimeSlides[String(task.slide_index)]||{};
        const pipe=pagePipeline(task);
        const running=task.status==='running';
        const node=task.node?.name||task.node?.machine||task.node?.host||'';
        const pct=Math.max(0,Math.min(100,Number(task.progress||0)));
        return `<div class="slide-progress-card ${running?'current running':''}${task.status==='failed'?' failed':''}"><div class="slide-progress-head"><div><b>SLIDE ${String(task.slide_index).padStart(2,'0')}</b><small>${safe(meta.title||('第 '+task.slide_index+' 页'))}</small></div><span class="badge">${safe(statusName(task.status))}</span></div><div class="slide-pipeline">${slideStage('语音',pipe.audio)}${slideStage('口型',pipe.video)}${slideStage('合成',pipe.compose)}</div><div class="slide-progress-bar"><i style="width:${pct}%"></i></div><div class="slide-meta-row"><span>${pct}%</span><span>${safe(statusName(task.stage||task.status))}</span><span>${safe(node||'未分配节点')}</span></div></div>`;
      }).join('');
    }
    const slides=Object.values(runtimeSlides);
    if(!slides.length)return '<div class="job-detail-empty">任务尚未进入逐页生产阶段</div>';
    const current=Number(runtime.current_slide||0);
    return slides.map(s=>`<div class="slide-progress-card ${Number(s.index)===current?'current':''}"><div class="slide-progress-head"><div><b>SLIDE ${String(s.index).padStart(2,'0')}</b><small>${safe(s.title||'')}</small></div><span class="badge">${s.audio_seconds?`${Number(s.audio_seconds).toFixed(1)}s`:'—'}</span></div><div class="slide-pipeline">${slideStage('语音',s.audio)}${slideStage('口型',s.video)}${slideStage('合成',s.compose)}</div><div class="slide-meta-row"><span>TTS ${fmtSec(s.tts_elapsed_seconds)}</span><span>MuseTalk ${fmtSec(s.render_seconds)}</span>${s.musetalk?.batch_size?`<span>Batch ${safe(s.musetalk.batch_size)}</span>`:''}</div></div>`).join('');
  }

  function elapsedSeconds(d){
    const runtime=d.runtime||{};
    if(runtime.elapsed_seconds!=null&&runtime.elapsed_seconds!==''){
      const value=Number(runtime.elapsed_seconds);
      if(Number.isFinite(value)&&value>=0)return value;
    }
    const start=parseTime(d.started_at)||parseTime(d.created_at);
    if(start==null){
      const gpu=Number(d.gpu_seconds);
      return Number.isFinite(gpu)&&gpu>0?gpu:null;
    }
    const end=d.completed_at?parseTime(d.completed_at):Date.now();
    if(end==null||end<start)return 0;
    return (end-start)/1000;
  }

  function averagePageSeconds(d){
    const durations=pageTasks(d).map(task=>{
      if(task.status!=='succeeded')return null;
      const start=parseTime(task.started_at),end=parseTime(task.completed_at);
      if(start==null||end==null||end<=start)return Number(task.estimated_seconds)||null;
      return (end-start)/1000;
    }).filter(value=>Number.isFinite(value)&&value>0);
    if(durations.length)return durations.reduce((sum,value)=>sum+value,0)/durations.length;
    const pages=pageTasks(d);
    const estimate=Number(d.estimated_seconds);
    if(pages.length&&Number.isFinite(estimate)&&estimate>0)return estimate/pages.length;
    return null;
  }

  function etaSeconds(d,elapsed){
    const runtime=d.runtime||{};
    if(runtime.eta_seconds!=null&&runtime.eta_seconds!==''){
      const value=Number(runtime.eta_seconds);
      if(Number.isFinite(value)&&value>=0)return value;
    }
    if(!['queued','running'].includes(d.status))return null;
    const pages=pageTasks(d);
    const avg=averagePageSeconds(d);
    if(pages.length&&avg!=null){
      const unfinished=pages.filter(task=>!['succeeded','failed','canceled'].includes(task.status));
      const slots=Math.max(1,pages.filter(task=>task.status==='running').length);
      const pageWork=unfinished.reduce((sum,task)=>{
        const fraction=task.status==='running'?Math.max(0,1-Math.max(0,Math.min(100,Number(task.progress||0)))/100):1;
        return sum+avg*fraction;
      },0);
      const finalize=(Array.isArray(d.tasks)?d.tasks:[]).find(task=>task.type==='finalize');
      let extra=0;
      if(finalize&&!['succeeded','failed','canceled'].includes(finalize.status)){
        const finalizeEstimate=Number(finalize.estimated_seconds);
        extra=Number.isFinite(finalizeEstimate)&&finalizeEstimate>0?finalizeEstimate:Math.max(20,avg*0.25);
      }
      return (pageWork/slots)+extra;
    }
    const estimate=Number(d.estimated_seconds);
    if(Number.isFinite(estimate)&&estimate>0&&elapsed!=null)return Math.max(0,estimate-elapsed);
    return null;
  }

  function liveLogic(d){
    const running=(Array.isArray(d.tasks)?d.tasks:[]).filter(t=>t.status==='running');
    if(running.length){
      return running.map(t=>{
        const who=t.type==='page'?`第 ${t.slide_index} 页`:(t.type==='prepare'?'课件准备':'成片封装');
        const node=t.node?.name||t.node?.machine||t.node?.host||'';
        return `${who} · ${statusName(t.stage||t.status)} · ${Number(t.progress||0)}%${node?' · '+node:''}`;
      }).join('\n');
    }
    return (d.runtime||{}).step_detail||statusName(d.stage)||'等待任务状态';
  }

  function renderShell(d){
    const runtime=d.runtime||{},dist=d.distributed||null;
    const elapsed=elapsedSeconds(d),eta=etaSeconds(d,elapsed);
    const course=safe(d.course_title||'数字人课程');
    const pages=pageTasks(d);
    const runningPages=pages.filter(p=>p.status==='running');
    const phase=distributedPhase(d);
    const stage=phase.current;
    const total=dist?.page_count||runtime.total_slides||pages.length||Object.values(runtime.slides||{}).length||'—';
    const currentLabel=dist?`${Number(dist.pages_succeeded||0)} 完成 · ${Number(dist.pages_running||0)} 进行中`:(runtime.current_slide||'—');
    const headline=runningPages.length>1
      ? `${runningPages.length} 页并行生成`
      : (runningPages.length===1
          ? `第 ${runningPages[0].slide_index} 页 · ${statusName(runningPages[0].stage)}`
          : statusName(runtime.stage_name||d.stage||d.status));
    const subtitle=dist
      ? [`${Number(dist.pages_succeeded||0)} 页完成`,`${Number(dist.pages_running||0)} 页生成中`,`${Number(dist.pages_queued||0)} 页排队`,dist.pages_failed?`${dist.pages_failed} 页失败`:''].filter(Boolean).join(' · ')
      : (runtime.step_detail||'任务正在等待 Worker 更新详细状态');
    const matrix=slideMatrix(d);
    return `<section id="jobDetailShell" class="job-detail-shell"><header class="job-detail-top"><div class="job-detail-title"><div class="job-detail-mark"></div><div><h2>生成任务详情</h2><small>${course} · ${safe(d.id.slice(0,16))}</small></div></div><div class="actions">${d.output_asset_id?`<button class="primary" data-job-download="${safe(d.output_asset_id)}">预览 / 下载成片</button>`:''}<button class="secondary" data-job-detail-close>返回任务中心</button></div></header><main class="job-detail-body"><div class="job-detail-pane"><div class="job-detail-hero"><div class="job-detail-card"><div class="label">CURRENT STAGE</div><h1>${safe(headline)}</h1><div class="muted">${safe(subtitle)}</div><div class="job-detail-progress"><i style="width:${Math.max(0,Math.min(100,Number(d.progress||0)))}%"></i></div></div><div class="job-detail-card"><div class="label">PROGRESS</div><div class="metric">${Number(d.progress||0)}%</div><div class="muted">${safe(statusName(d.status))}</div></div><div class="job-detail-card"><div class="label">ELAPSED</div><div class="metric">${fmtSec(elapsed)}</div><div class="muted">已耗时</div></div><div class="job-detail-card"><div class="label">ETA</div><div class="metric">${eta==null?'—':fmtSec(eta)}</div><div class="muted">动态估算</div></div></div><div class="job-phase-row">${stageBox(1,'课件解析','PPT 高清底板',stage,d.status,phase.actives)}${stageBox(2,'语音合成','CosyVoice 高保真',stage,d.status,phase.actives)}${stageBox(3,'数字人驱动','MuseTalk MLX',stage,d.status,phase.actives)}${stageBox(4,'排版压制','画面 / 字幕 / 标识',stage,d.status,phase.actives)}${stageBox(5,'完成','上传 SaaS 成片',stage,d.status,phase.actives)}</div><div class="job-detail-layout"><section class="job-detail-card"><div class="toolbar"><div><div class="label">SLIDE MATRIX</div><h2 style="margin:0">逐页生成进度</h2></div><span class="muted">当前 ${safe(currentLabel)} / ${total} 页</span></div><div class="slide-progress-grid">${matrix}</div></section><aside class="job-runtime-side"><div class="job-detail-card"><div class="label">RUNTIME</div><div class="job-runtime-line"><span>生成引擎</span><b>${safe(d.engine)}</b></div><div class="job-runtime-line"><span>队列等待</span><b>${fmtSec(d.queue_wait_seconds)}</b></div><div class="job-runtime-line"><span>成片时长</span><b>${fmtSec(d.video_seconds)}</b></div><div class="job-runtime-line"><span>TTS 流水线预取</span><b>${runtime.tts_prefetch===true?'开启':runtime.tts_prefetch===false?'关闭':'—'}</b></div></div><div class="job-detail-card"><div class="label">LIVE LOGIC</div><div class="job-runtime-detail">${safe(liveLogic(d))}</div>${d.error?`<div class="job-error">${safe(d.error)}</div>`:''}</div></aside></div></div></main></section>`;
  }

  async function refreshDetail(id){
    try{
      if(detailTimer){clearTimeout(detailTimer);detailTimer=null}
      const d=await api('/jobs/'+id+'/detail');
      const old=document.getElementById('jobDetailShell');
      const scroll=old?.querySelector('.job-detail-body')?.scrollTop||0;
      const holder=document.createElement('div');holder.innerHTML=renderShell(d);const fresh=holder.firstElementChild;
      if(old)old.replaceWith(fresh);else document.body.appendChild(fresh);
      clarifyTimeLabels(fresh);
      if(d.output_asset_id){mountResultPreview(fresh,d.output_asset_id);hydrateResultVideo(d.output_asset_id)}
      const body=fresh.querySelector('.job-detail-body');if(body)body.scrollTop=scroll;
      if(['queued','running'].includes(d.status))detailTimer=setTimeout(()=>refreshDetail(id),1500);
    }catch(e){if(typeof toast==='function')toast(e.message)}
  }

  patchJobTable();
  if(typeof current!=='undefined'&&current==='jobs'&&typeof renderJobs==='function')renderJobs().catch(()=>{});

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
