from __future__ import annotations

from fastapi.responses import Response


CSS = r'''
.course-studio-shell{position:fixed;inset:0;z-index:600;background:#07090d;color:#eef5ff;display:grid;grid-template-rows:72px 76px minmax(0,1fr);overflow:hidden}
.course-studio-top{display:flex;align-items:center;justify-content:space-between;padding:0 26px;border-bottom:1px solid rgba(151,176,214,.12);background:rgba(8,11,16,.94);backdrop-filter:blur(20px)}
.course-studio-brand{display:flex;align-items:center;gap:13px}.course-studio-mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(145deg,#9bddff,#4b91e9);box-shadow:0 0 26px rgba(82,164,255,.22)}
.course-studio-brand h2{font-size:16px;margin:0}.course-studio-brand small{color:#66758a}.course-studio-top-actions{display:flex;gap:8px;align-items:center}
.course-studio-steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));padding:13px 26px;background:#0a0e14;border-bottom:1px solid rgba(151,176,214,.09)}
.course-step{display:flex;align-items:center;gap:11px;position:relative;opacity:.52;cursor:pointer;padding:7px 10px;border-radius:12px}.course-step:not(:last-child):after{content:"";position:absolute;height:1px;background:#202a39;left:calc(100% - 12px);right:-12px;top:50%}.course-step.active{opacity:1;background:rgba(113,183,255,.07)}.course-step.done{opacity:.84}
.course-step-num{width:30px;height:30px;display:grid;place-items:center;border-radius:50%;background:#18212d;border:1px solid rgba(255,255,255,.05);font-size:12px;font-weight:760}.course-step.active .course-step-num{background:#2674b8;border-color:#6bb8f8;color:#fff;box-shadow:0 0 24px rgba(74,159,235,.18)}.course-step.done .course-step-num{background:#155c4a;color:#77dfb8}
.course-step b{display:block;font-size:12px}.course-step small{display:block;color:#64748b;font-size:10px;margin-top:1px}
.course-studio-body{overflow:auto;padding:24px 28px 38px}.course-pane{max-width:1440px;margin:0 auto}.course-pane-head{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;margin-bottom:18px}.course-pane-head h2{font-size:24px;margin:0 0 3px;letter-spacing:-.025em}.course-pane-head p{margin:0;color:#718097}
.studio-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(340px,.85fr);gap:16px}.studio-panel{background:linear-gradient(180deg,rgba(17,22,30,.91),rgba(12,16,22,.9));border:1px solid rgba(151,176,214,.12);border-radius:18px;padding:20px;box-shadow:0 18px 52px rgba(0,0,0,.2)}
.studio-drop{border:1px dashed rgba(113,183,255,.28);border-radius:16px;padding:24px;background:rgba(73,133,197,.035)}.studio-drop input{margin-top:11px}.studio-avatar-choice{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;max-height:330px;overflow:auto}.studio-avatar-option{border:1px solid rgba(151,176,214,.11);border-radius:14px;background:#0c1118;padding:12px;cursor:pointer;min-height:92px}.studio-avatar-option.active{border-color:rgba(113,183,255,.58);box-shadow:0 0 0 2px rgba(113,183,255,.07);background:#101b29}.studio-avatar-option b{display:block}.studio-avatar-option small{color:#68778b}
.studio-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:18px;padding-top:16px;border-top:1px solid rgba(151,176,214,.09)}.studio-footer-right{display:flex;gap:9px;align-items:center}.studio-save-state{font-size:11px;color:#627187}
.script-workspace{display:grid;grid-template-columns:176px minmax(360px,1.05fr) minmax(380px,.95fr);gap:14px;min-height:610px}.script-rail{background:#0b0f15;border:1px solid rgba(151,176,214,.1);border-radius:16px;padding:10px;overflow:auto;max-height:calc(100vh - 250px)}.script-thumb{border:1px solid transparent;border-radius:10px;padding:7px;margin-bottom:7px;cursor:pointer;background:#0f141c}.script-thumb.active{border-color:#5faef1;background:#111e2c}.script-thumb-img{aspect-ratio:16/9;border-radius:6px;background:#05070a center/cover no-repeat;display:grid;place-items:center;color:#526174;font-size:10px;overflow:hidden}.script-thumb-img img{width:100%;height:100%;object-fit:cover}.script-thumb-meta{display:flex;justify-content:space-between;margin-top:5px;color:#718096;font-size:10px}
.script-preview{display:flex;flex-direction:column;gap:12px}.script-preview-frame{aspect-ratio:16/9;background:#020305;border:1px solid rgba(151,176,214,.13);border-radius:16px;overflow:hidden;display:grid;place-items:center}.script-preview-frame img{width:100%;height:100%;object-fit:contain}.script-preview-title{font-size:15px;font-weight:690}.script-editor{display:flex;flex-direction:column;min-height:0}.script-editor textarea{flex:1;min-height:360px;font-size:15px;line-height:1.75}.script-stats{display:flex;gap:16px;color:#6e7f95;font-size:11px;margin:8px 0 0}.script-nav{display:flex;justify-content:space-between;gap:8px;margin-top:12px}
.layout-workspace{display:grid;grid-template-columns:minmax(620px,1fr) 340px;gap:16px;align-items:start}.layout-main{display:flex;flex-direction:column;gap:11px}.layout-toolbar{display:flex;gap:8px;justify-content:space-between;align-items:center;flex-wrap:wrap}.layout-canvas{position:relative;aspect-ratio:16/9;background:#05070b;border:1px solid rgba(113,183,255,.27);border-radius:17px;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.42);user-select:none;touch-action:none}.layout-canvas.blur-bg:before{content:"";position:absolute;inset:-28px;background:var(--slide-bg) center/cover no-repeat;filter:blur(30px) brightness(.55);transform:scale(1.12)}.layout-canvas.dark-bg{background:radial-gradient(circle at 72% 18%,#172638 0,#0a111a 36%,#05070b 78%)}
.layout-layer{position:absolute;border:1.5px solid rgba(113,183,255,.65);box-shadow:0 12px 35px rgba(0,0,0,.32);cursor:grab;touch-action:none}.layout-layer.selected{border-color:#72e6ff;box-shadow:0 0 0 2px rgba(114,230,255,.18),0 16px 44px rgba(0,0,0,.42)}.layout-layer.ppt{background:#030407;overflow:hidden}.layout-layer.ppt img{width:100%;height:100%;object-fit:contain;pointer-events:none}.layout-layer.avatar{background:rgba(5,10,16,.28);overflow:hidden;display:grid;place-items:center;color:#87a5c2;font-size:12px}.layout-layer.avatar img,.layout-layer.avatar video{width:100%;height:100%;object-fit:contain;pointer-events:none}.layout-label{position:absolute;left:6px;top:6px;background:rgba(4,8,13,.72);border:1px solid rgba(255,255,255,.08);padding:3px 7px;border-radius:6px;font-size:9px;z-index:4}.resize-dot{position:absolute;right:-5px;bottom:-5px;width:14px;height:14px;background:#72e6ff;border:2px solid #071018;border-radius:50%;cursor:nwse-resize;z-index:5}.layout-controls{position:sticky;top:0;background:linear-gradient(180deg,rgba(17,22,30,.94),rgba(12,16,22,.94));border:1px solid rgba(151,176,214,.12);border-radius:18px;padding:17px}.layout-section{padding:0 0 15px;margin-bottom:15px;border-bottom:1px solid rgba(151,176,214,.09)}.layout-section:last-child{border:0;margin-bottom:0}.layout-section h3{font-size:12px;margin:0 0 9px;color:#a9b6c8}.layout-presets{display:grid;grid-template-columns:1fr 1fr;gap:7px}.layout-chip{border:1px solid rgba(151,176,214,.12);background:#0e141d;color:#aab9ca;border-radius:10px;padding:9px;font-size:11px;cursor:pointer}.layout-chip:hover,.layout-chip.active{border-color:#5ca9ed;color:#e6f5ff;background:#102033}.layout-layer-tabs{display:grid;grid-template-columns:1fr 1fr;gap:7px}.layout-coords{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;color:#6ca7da;line-height:1.6}.slide-strip{display:flex;gap:8px;overflow:auto;padding:9px 2px}.slide-strip button{width:76px;min-width:76px;padding:5px;border:1px solid rgba(151,176,214,.1);background:#0d1219;border-radius:9px;color:#728298;cursor:pointer}.slide-strip button.active{border-color:#5aa9ed;color:#dff2ff}.slide-strip-thumb{aspect-ratio:16/9;background:#030508 center/cover no-repeat;border-radius:5px;margin-bottom:4px;overflow:hidden}.slide-strip-thumb img{width:100%;height:100%;object-fit:cover}
.package-grid{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:16px}.package-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}.package-metric{padding:15px;border:1px solid rgba(151,176,214,.1);border-radius:13px;background:#0d1219}.package-metric b{font-size:22px;display:block}.readiness-list{display:grid;gap:8px;margin-top:12px}.readiness-row{display:flex;gap:9px;align-items:flex-start;padding:10px;border-radius:10px;background:#0d1219;color:#8d9cae}.readiness-row.ok{color:#78dcb8}.readiness-row.bad{color:#ff889c}.engine-choice{display:grid;gap:8px}.engine-option{border:1px solid rgba(151,176,214,.12);border-radius:12px;padding:12px;cursor:pointer;background:#0d1219}.engine-option.active{border-color:#62b2f3;background:#102034}.engine-option b{display:block}.engine-option small{color:#6e7c90}
@media(max-width:1050px){.course-studio-shell{grid-template-rows:64px 66px minmax(0,1fr)}.course-studio-steps{padding:9px 14px}.course-step small{display:none}.course-studio-body{padding:18px 14px}.studio-grid,.package-grid{grid-template-columns:1fr}.script-workspace{grid-template-columns:116px 1fr}.script-editor{grid-column:1/-1}.layout-workspace{grid-template-columns:1fr}.layout-controls{position:static}.layout-main{min-width:0}}
@media(max-width:700px){.course-step{justify-content:center}.course-step div:last-child{display:none}.course-studio-brand small{display:none}.script-workspace{display:block}.script-rail{display:flex;max-height:none;margin-bottom:10px}.script-thumb{min-width:100px}.script-editor{margin-top:12px}.layout-workspace{display:block}.layout-controls{margin-top:12px}.package-summary{grid-template-columns:1fr}.studio-footer{align-items:stretch;flex-direction:column}.studio-footer-right{display:grid;grid-template-columns:1fr 1fr}}
'''


JS = r'''
(() => {
  let studio=null;
  let studioBlobUrls=[];
  const defaultPpt={x:.04,y:.10,w:.65,h:.76};
  const defaultAvatar={x:.71,y:.25,w:.25,h:.70};
  const deep=v=>JSON.parse(JSON.stringify(v));
  const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
  const ehtml=s=>typeof esc==='function'?esc(s):String(s??'');
  const ppts=()=>cache.assets.filter(a=>a.kind==='ppt'||/\.(pptx|ppt|pdf)$/i.test(a.name||''));

  function cleanupBlobUrls(){studioBlobUrls.forEach(u=>URL.revokeObjectURL(u));studioBlobUrls=[]}
  async function authBlobUrl(path){
    const url=path.startsWith('/api/')?path:(API+path);
    const r=await fetch(url,{headers:{Authorization:'Bearer '+token}});
    if(!r.ok)throw Error('预览素材加载失败');
    const u=URL.createObjectURL(await r.blob());studioBlobUrls.push(u);return u;
  }
  async function loadAuthImg(el,path){if(!el||!path)return;try{el.src=await authBlobUrl(path)}catch(_){}}

  function emptySlide(source){return {
    index:Number(source.index),title:source.title||`第 ${source.index} 页`,narration:source.narration||'',layout:source.layout||'pip',
    ppt_box:deep(source.ppt_box||defaultPpt),pip_box:deep(source.pip_box||defaultAvatar),bg_blur:Boolean(source.bg_blur),thumbnail_url:source.thumbnail_url||null
  }}
  function mergeSlides(outline,existing=[]){
    const map=Object.fromEntries((existing||[]).filter(x=>x&&typeof x==='object').map((x,i)=>[Number(x.index||i+1),x]));
    return outline.slides.map(s=>emptySlide({...s,...(map[s.index]||{}),thumbnail_url:s.thumbnail_url}));
  }
  function selectedAvatar(){return cache.avatars.find(a=>a.id===studio.avatarId)||null}
  function effectiveVoice(){const a=selectedAvatar();return studio.voiceOverrideId||a?.voice_profile_id||null}
  function settingsPayload(step=studio.step){return {...(studio.baseSettings||{}),wizard_step:step,bg_blur:studio.globalBlur,embed_subtitles:studio.embedSubtitles,studio_version:1}}
  function scriptPayload(){return studio.slides.map(s=>({index:s.index,title:s.title,narration:s.narration,layout:s.layout,ppt_box:s.ppt_box,pip_box:s.pip_box,bg_blur:s.bg_blur}))}

  async function uploadPptIfNeeded(){
    const input=document.getElementById('studioPptFile');const file=input?.files?.[0];
    if(file){const fd=new FormData();fd.append('file',file);fd.append('kind','ppt');const a=await api('/assets',{method:'POST',body:fd});studio.pptId=a.id;await loadLookups()}
    const sel=document.getElementById('studioPptSelect');if(sel?.value)studio.pptId=sel.value;
    if(!studio.pptId)throw Error('请先上传或选择 PPT / PDF 课件');
  }
  async function parseDeck(){
    await uploadPptIfNeeded();
    const old=studio.slides||[];studio.outline=await api('/course-tools/ppt/'+studio.pptId+'/outline');studio.slides=mergeSlides(studio.outline,old);
    if(!studio.title)studio.title=studio.outline.title||'';
  }
  async function saveDraft(step=studio.step,quiet=false){
    if(!studio)return null;
    const title=(document.getElementById('studioCourseTitle')?.value||studio.title||'未命名课程').trim();studio.title=title;
    const avatarSelect=document.getElementById('studioAvatarSelect');if(avatarSelect?.value)studio.avatarId=avatarSelect.value;
    const body={title:studio.title,ppt_asset_id:studio.pptId||null,avatar_id:studio.avatarId||null,voice_profile_id:effectiveVoice(),script:scriptPayload(),settings:settingsPayload(step)};
    let saved;
    if(studio.courseId)saved=await api('/courses/'+studio.courseId,{method:'PATCH',body});
    else{saved=await api('/courses',{method:'POST',body});studio.courseId=saved.id}
    studio.baseSettings=saved.settings||body.settings;studio.dirty=false;
    const label=document.getElementById('studioSaveState');if(label)label.textContent='已保存';
    if(!quiet)toast('课程草稿已保存');
    return saved;
  }
  function markDirty(){if(!studio)return;studio.dirty=true;const e=document.getElementById('studioSaveState');if(e)e.textContent='有未保存修改'}
  async function changeStep(step){
    if(!studio)return;
    if(step>1){
      if(studio.step===1){
        studio.title=(document.getElementById('studioCourseTitle')?.value||studio.title||'').trim();
        const av=document.getElementById('studioAvatarSelect')?.value||studio.avatarId;studio.avatarId=av;
        if(!studio.title)throw Error('请输入课程名称');if(!studio.avatarId)throw Error('请选择数字人');
        if(!studio.outline)await parseDeck();
      }
      syncStepState();await saveDraft(step,true);
    }
    studio.step=step;renderStudio();
  }
  function syncStepState(){
    if(!studio)return;
    if(studio.step===2){const ta=document.getElementById('studioNarration');if(ta){studio.slides[studio.currentSlide].narration=ta.value;markDirty()}}
    if(studio.step===3)syncCanvasFromDom();
  }
  async function closeStudio(){
    if(!studio)return;
    try{syncStepState();if(studio.courseId&&studio.dirty)await saveDraft(studio.step,true)}catch(_){}
    cleanupBlobUrls();document.getElementById('courseStudioShell')?.remove();document.body.style.overflow='';studio=null;await loadLookups();if(current==='courses')renderCourses();
  }

  function stepBar(){const names=[['课件与数字人','上传、解析、选择讲师'],['文稿确认','逐页审校讲解词'],['画面排版','所见即所得自由布局'],['包装与生成','检查配置并提交任务']];return names.map((x,i)=>{const n=i+1,c=n===studio.step?'active':n<studio.step?'done':'';return `<div class="course-step ${c}" data-step="${n}"><div class="course-step-num">${n<studio.step?'✓':n}</div><div><b>${x[0]}</b><small>${x[1]}</small></div></div>`}).join('')}
  function shell(){
    document.getElementById('courseStudioShell')?.remove();document.body.style.overflow='hidden';
    document.body.insertAdjacentHTML('beforeend',`<section class="course-studio-shell" id="courseStudioShell"><header class="course-studio-top"><div class="course-studio-brand"><div class="course-studio-mark"></div><div><h2>课程制作工作室</h2><small>${ehtml(studio.title||'新课程')} · 自动保存草稿</small></div></div><div class="course-studio-top-actions"><span class="studio-save-state" id="studioSaveState">已保存</span><button class="secondary" id="studioSaveBtn">保存草稿</button><button class="secondary" id="studioCloseBtn">退出工作室</button></div></header><nav class="course-studio-steps">${stepBar()}</nav><main class="course-studio-body"><div class="course-pane" id="courseStudioPane"></div></main></section>`);
    document.querySelectorAll('.course-step').forEach(n=>n.onclick=()=>changeStep(Number(n.dataset.step)).catch(e=>toast(e.message)));
    document.getElementById('studioSaveBtn').onclick=()=>{syncStepState();saveDraft(studio.step).catch(e=>toast(e.message))};document.getElementById('studioCloseBtn').onclick=closeStudio;
  }
  function footer(back,next,nextLabel='下一步'){return `<div class="studio-footer"><div><span class="studio-save-state">步骤 ${studio.step} / 4</span></div><div class="studio-footer-right">${back?`<button class="secondary" id="studioBack">← 上一步</button>`:''}<button class="secondary" id="studioSaveInner">保存草稿</button>${next?`<button class="primary" id="studioNext">${nextLabel} →</button>`:''}</div></div>`}
  function wireFooter(back,next){const b=document.getElementById('studioBack'),n=document.getElementById('studioNext'),s=document.getElementById('studioSaveInner');if(b)b.onclick=()=>changeStep(back).catch(e=>toast(e.message));if(n)n.onclick=()=>changeStep(next).catch(e=>toast(e.message));if(s)s.onclick=()=>{syncStepState();saveDraft(studio.step).catch(e=>toast(e.message))}}

  function renderStep1(){
    const pane=document.getElementById('courseStudioPane');
    pane.innerHTML=`<div class="course-pane-head"><div><div class="eyebrow">STEP 01 · COURSE SETUP</div><h2>课件与数字人</h2><p>上传教学课件，选择一个已经配置完整的数字人。</p></div></div><div class="studio-grid"><section class="studio-panel"><h2>教学课件</h2><div class="studio-drop"><b>上传 PPT / PDF</b><div class="muted">系统会解析标题、正文、备注，并生成每页真实缩略图。</div><input id="studioPptFile" type="file" accept=".pptx,.ppt,.pdf"></div><div class="field"><label>或选择已有课件</label><select id="studioPptSelect">${opts(ppts(),studio.pptId)}</select></div><div class="field"><label>课程名称</label><input id="studioCourseTitle" value="${ehtml(studio.title||'')}" placeholder="例如：从项目交付到业务经营"></div><button class="secondary" id="studioParseBtn">解析课件并预览</button><div id="studioParseState" class="muted" style="margin-top:9px">${studio.outline?`已解析 ${studio.outline.total_slides} 页`:'尚未解析'}</div></section><section class="studio-panel"><h2>主讲数字人</h2><div class="field"><label>选择数字人</label><select id="studioAvatarSelect">${opts(cache.avatars,studio.avatarId)}</select></div><div class="studio-avatar-choice" id="studioAvatarCards">${cache.avatars.map(a=>`<div class="studio-avatar-option ${a.id===studio.avatarId?'active':''}" data-avatar="${a.id}"><b>${ehtml(a.name)}</b><small>${a.ready===false?'配置不完整':'母版与声音已绑定'}</small></div>`).join('')||'<div class="empty">暂无数字人，请先到数字人资产中创建。</div>'}</div></section></div>${footer(null,2,'进入文稿确认')}`;
    const select=document.getElementById('studioAvatarSelect');select.onchange=()=>{studio.avatarId=select.value;document.querySelectorAll('.studio-avatar-option').forEach(x=>x.classList.toggle('active',x.dataset.avatar===studio.avatarId));markDirty()};
    document.querySelectorAll('.studio-avatar-option').forEach(x=>x.onclick=()=>{studio.avatarId=x.dataset.avatar;select.value=studio.avatarId;document.querySelectorAll('.studio-avatar-option').forEach(y=>y.classList.toggle('active',y===x));markDirty()});
    document.getElementById('studioCourseTitle').oninput=e=>{studio.title=e.target.value;markDirty()};document.getElementById('studioPptSelect').onchange=e=>{studio.pptId=e.target.value||null;studio.outline=null;studio.slides=[];markDirty()};
    document.getElementById('studioParseBtn').onclick=async()=>{const state=document.getElementById('studioParseState');state.textContent='正在解析并生成缩略图…';try{await parseDeck();document.getElementById('studioCourseTitle').value=studio.title;state.textContent=`解析完成 · ${studio.outline.total_slides} 页课件`;markDirty()}catch(e){state.textContent=e.message;toast(e.message)}};wireFooter(null,2)
  }

  function current(){return studio.slides[studio.currentSlide]}
  function scriptThumbs(){return studio.slides.map((s,i)=>`<div class="script-thumb ${i===studio.currentSlide?'active':''}" data-slide="${i}"><div class="script-thumb-img" id="scriptThumb${i}">加载中</div><div class="script-thumb-meta"><span>${String(s.index).padStart(2,'0')}</span><span>${(s.narration||'').length}字</span></div></div>`).join('')}
  async function loadThumbInto(hostId,slide){const host=document.getElementById(hostId);if(!host||!slide?.thumbnail_url)return;const img=document.createElement('img');host.textContent='';host.appendChild(img);await loadAuthImg(img,slide.thumbnail_url)}
  function updateScriptStats(){const ta=document.getElementById('studioNarration');if(!ta)return;const n=ta.value.trim().length;document.getElementById('studioWordCount').textContent=n+' 字';document.getElementById('studioDuration').textContent='约 '+Math.max(1,Math.round(n/4))+' 秒'}
  function selectScriptSlide(i){const ta=document.getElementById('studioNarration');if(ta)studio.slides[studio.currentSlide].narration=ta.value;studio.currentSlide=clamp(i,0,studio.slides.length-1);renderStep2()}
  function renderStep2(){
    if(!studio.slides.length){changeStep(1);return}const s=current(),pane=document.getElementById('courseStudioPane');
    pane.innerHTML=`<div class="course-pane-head"><div><div class="eyebrow">STEP 02 · SCRIPT REVIEW</div><h2>确认逐页讲稿</h2><p>对着真实 PPT 页面审校讲解词，不再面对一串抽象 JSON。</p></div><div class="muted">第 ${s.index} / ${studio.slides.length} 页</div></div><div class="script-workspace"><aside class="script-rail">${scriptThumbs()}</aside><section class="script-preview"><div class="script-preview-frame" id="studioLargePreview"><span class="muted">正在加载课件画面…</span></div><div><div class="script-preview-title">${ehtml(s.title)}</div><div class="muted">页面标题来自课件解析，可结合画面调整右侧讲稿。</div></div></section><section class="studio-panel script-editor"><div class="eyebrow">NARRATION</div><h2 style="margin-top:0">本页讲解词</h2><textarea id="studioNarration" placeholder="输入本页讲解内容…">${ehtml(s.narration)}</textarea><div class="script-stats"><span id="studioWordCount"></span><span id="studioDuration"></span></div><div class="script-nav"><button class="secondary" id="scriptPrev" ${studio.currentSlide===0?'disabled':''}>← 上一页</button><button class="secondary" id="scriptNext" ${studio.currentSlide===studio.slides.length-1?'disabled':''}>下一页 →</button></div></section></div>${footer(1,3,'进入画面排版')}`;
    document.querySelectorAll('.script-thumb').forEach(x=>x.onclick=()=>selectScriptSlide(Number(x.dataset.slide)));studio.slides.forEach((x,i)=>loadThumbInto('scriptThumb'+i,x));loadThumbInto('studioLargePreview',s);
    const ta=document.getElementById('studioNarration');ta.oninput=()=>{studio.slides[studio.currentSlide].narration=ta.value;updateScriptStats();markDirty()};updateScriptStats();document.getElementById('scriptPrev').onclick=()=>selectScriptSlide(studio.currentSlide-1);document.getElementById('scriptNext').onclick=()=>selectScriptSlide(studio.currentSlide+1);wireFooter(1,3)
  }

  function applyPreset(name){const s=current();if(!s)return;if(name==='studio'){s.layout='pip';s.ppt_box={x:.04,y:.10,w:.65,h:.76};s.pip_box={x:.71,y:.25,w:.25,h:.70}}else if(name==='ppt_full'){s.layout='full_slide';s.ppt_box={x:0,y:0,w:1,h:1}}else if(name==='avatar_full'){s.layout='full_avatar';s.pip_box={x:0,y:0,w:1,h:1}}else if(name==='left'){s.layout='pip';s.ppt_box={x:.34,y:.10,w:.62,h:.78};s.pip_box={x:.04,y:.23,w:.27,h:.72}}else if(name==='split'){s.layout='split'}renderCanvas();markDirty()}
  function syncCanvasFromDom(){if(!studio||studio.step!==3)return;const s=current(),ppt=document.getElementById('studioPptLayer'),av=document.getElementById('studioAvatarLayer'),c=document.getElementById('studioLayoutCanvas');if(!s||!ppt||!av||!c)return;const box=el=>({x:parseFloat(el.style.left)/100,y:parseFloat(el.style.top)/100,w:parseFloat(el.style.width)/100,h:parseFloat(el.style.height)/100});if(s.layout==='pip'){s.ppt_box=box(ppt);s.pip_box=box(av)}}
  function styleBox(el,b){el.style.left=(b.x*100)+'%';el.style.top=(b.y*100)+'%';el.style.width=(b.w*100)+'%';el.style.height=(b.h*100)+'%'}
  function selectLayer(which){studio.activeLayer=which;document.querySelectorAll('.layout-layer').forEach(x=>x.classList.toggle('selected',x.dataset.layer===which));document.querySelectorAll('[data-layer-tab]').forEach(x=>x.classList.toggle('active',x.dataset.layerTab===which));updateCoords()}
  function updateCoords(){const s=current(),b=studio.activeLayer==='ppt'?s.ppt_box:s.pip_box,e=document.getElementById('studioCoords');if(e)e.textContent=`X ${(b.x*100).toFixed(1)}% · Y ${(b.y*100).toFixed(1)}%\n宽 ${(b.w*100).toFixed(1)}% · 高 ${(b.h*100).toFixed(1)}%`}
  function makeInteractive(el,key){
    el.onpointerdown=e=>{if(current().layout!=='pip')return;selectLayer(key);e.preventDefault();el.setPointerCapture(e.pointerId);const canvas=document.getElementById('studioLayoutCanvas'),rect=canvas.getBoundingClientRect(),box=deep(key==='ppt'?current().ppt_box:current().pip_box),resize=e.target.classList.contains('resize-dot'),sx=e.clientX,sy=e.clientY;
      const move=ev=>{const dx=(ev.clientX-sx)/rect.width,dy=(ev.clientY-sy)/rect.height,b=key==='ppt'?current().ppt_box:current().pip_box;if(resize){b.w=clamp(box.w+dx,key==='ppt'?.20:.12,1-b.x);b.h=clamp(box.h+dy,key==='ppt'?.18:.20,1-b.y)}else{b.x=clamp(box.x+dx,0,1-b.w);b.y=clamp(box.y+dy,0,1-b.h)}styleBox(el,b);updateCoords();markDirty()};
      const up=()=>{el.removeEventListener('pointermove',move);el.removeEventListener('pointerup',up);el.removeEventListener('pointercancel',up)};el.addEventListener('pointermove',move);el.addEventListener('pointerup',up);el.addEventListener('pointercancel',up)}
  }
  async function renderCanvas(){
    const s=current(),canvas=document.getElementById('studioLayoutCanvas');if(!canvas)return;canvas.classList.toggle('blur-bg',studio.globalBlur);canvas.classList.toggle('dark-bg',!studio.globalBlur);const ppt=document.getElementById('studioPptLayer'),av=document.getElementById('studioAvatarLayer');
    if(s.layout==='full_slide'){styleBox(ppt,{x:0,y:0,w:1,h:1});av.style.display='none';ppt.style.display='block'}else if(s.layout==='full_avatar'){ppt.style.display='none';av.style.display='grid';styleBox(av,{x:0,y:0,w:1,h:1})}else if(s.layout==='split'){ppt.style.display='block';av.style.display='grid';styleBox(ppt,{x:0,y:0,w:.7,h:1});styleBox(av,{x:.7,y:0,w:.3,h:1})}else{ppt.style.display='block';av.style.display='grid';styleBox(ppt,s.ppt_box);styleBox(av,s.pip_box)}
    const img=document.getElementById('studioCanvasPpt');if(img&&s.thumbnail_url)await loadAuthImg(img,s.thumbnail_url);canvas.style.setProperty('--slide-bg',img?.src?`url(${img.src})`:'none');
    document.querySelectorAll('[data-layout-preset]').forEach(x=>x.classList.toggle('active',(x.dataset.layoutPreset==='studio'&&s.layout==='pip')||(x.dataset.layoutPreset==='split'&&s.layout==='split')||(x.dataset.layoutPreset==='ppt_full'&&s.layout==='full_slide')||(x.dataset.layoutPreset==='avatar_full'&&s.layout==='full_avatar')));selectLayer(studio.activeLayer||'avatar');
  }
  async function loadAvatarMedia(){const a=selectedAvatar(),host=document.getElementById('studioAvatarMedia');if(!a||!host)return;const imageId=a.image_asset_id||a.image?.id,videoId=a.master_video_asset_id;if(imageId){const img=document.createElement('img');host.textContent='';host.appendChild(img);await loadAuthImg(img,'/assets/'+imageId+'/download')}else if(videoId){try{const v=document.createElement('video');v.muted=true;v.loop=true;v.autoplay=true;v.playsInline=true;v.src=await authBlobUrl('/api/saas/assets/'+videoId+'/download');host.textContent='';host.appendChild(v)}catch(_){}}}
  function changeLayoutSlide(i){syncCanvasFromDom();studio.currentSlide=clamp(i,0,studio.slides.length-1);renderStep3()}
  function applyLayoutAll(){syncCanvasFromDom();const src=current();studio.slides.forEach(s=>{s.layout=src.layout;s.ppt_box=deep(src.ppt_box);s.pip_box=deep(src.pip_box);s.bg_blur=studio.globalBlur});markDirty();toast('当前排版已应用到全部页面')}
  function renderStep3(){
    const s=current(),pane=document.getElementById('courseStudioPane');pane.innerHTML=`<div class="course-pane-head"><div><div class="eyebrow">STEP 03 · LAYOUT STUDIO</div><h2>所见即所得画面排版</h2><p>直接拖动 PPT 与数字人，拖右下角圆点缩放；坐标会进入真实合成参数。</p></div><div class="muted">第 ${s.index} / ${studio.slides.length} 页</div></div><div class="layout-workspace"><section class="layout-main"><div class="layout-toolbar"><div class="actions"><button class="secondary" id="layoutPrev">← 上一页</button><button class="secondary" id="layoutNext">下一页 →</button></div><button class="secondary" id="applyAllLayout">应用当前排版到全部页面</button></div><div class="layout-canvas dark-bg" id="studioLayoutCanvas"><div class="layout-layer ppt" id="studioPptLayer" data-layer="ppt"><div class="layout-label">PPT</div><img id="studioCanvasPpt"><span class="resize-dot"></span></div><div class="layout-layer avatar selected" id="studioAvatarLayer" data-layer="avatar"><div class="layout-label">数字人</div><div id="studioAvatarMedia">数字人预览</div><span class="resize-dot"></span></div></div><div class="slide-strip">${studio.slides.map((x,i)=>`<button class="${i===studio.currentSlide?'active':''}" data-layout-slide="${i}"><div class="slide-strip-thumb" id="layoutThumb${i}"></div>${String(x.index).padStart(2,'0')}</button>`).join('')}</div></section><aside class="layout-controls"><div class="layout-section"><h3>布局模板</h3><div class="layout-presets"><button class="layout-chip" data-layout-preset="studio">经典演播厅</button><button class="layout-chip" data-layout-preset="left">左讲师右课件</button><button class="layout-chip" data-layout-preset="split">左右分屏</button><button class="layout-chip" data-layout-preset="ppt_full">课件全屏</button><button class="layout-chip" data-layout-preset="avatar_full">讲师全屏</button></div></div><div class="layout-section"><h3>当前编辑图层</h3><div class="layout-layer-tabs"><button class="layout-chip" data-layer-tab="ppt">PPT</button><button class="layout-chip active" data-layer-tab="avatar">数字人</button></div><div class="layout-coords" id="studioCoords" style="margin-top:9px"></div></div><div class="layout-section"><h3>画面背景</h3><select id="studioBgMode"><option value="dark" ${studio.globalBlur?'':'selected'}>深色科技背景</option><option value="blur" ${studio.globalBlur?'selected':''}>PPT 模糊延展背景</option></select></div><div class="muted">自由坐标目前用于画中画模式；左右分屏、课件全屏、讲师全屏使用固定模板。</div></aside></div>${footer(2,4,'进入包装与生成')}`;
    makeInteractive(document.getElementById('studioPptLayer'),'ppt');makeInteractive(document.getElementById('studioAvatarLayer'),'avatar');renderCanvas();loadAvatarMedia();studio.slides.forEach((x,i)=>loadThumbInto('layoutThumb'+i,x));document.querySelectorAll('[data-layout-slide]').forEach(x=>x.onclick=()=>changeLayoutSlide(Number(x.dataset.layoutSlide)));document.querySelectorAll('[data-layout-preset]').forEach(x=>x.onclick=()=>applyPreset(x.dataset.layoutPreset));document.querySelectorAll('[data-layer-tab]').forEach(x=>x.onclick=()=>selectLayer(x.dataset.layerTab));document.getElementById('layoutPrev').onclick=()=>changeLayoutSlide(studio.currentSlide-1);document.getElementById('layoutNext').onclick=()=>changeLayoutSlide(studio.currentSlide+1);document.getElementById('applyAllLayout').onclick=applyLayoutAll;document.getElementById('studioBgMode').onchange=e=>{studio.globalBlur=e.target.value==='blur';studio.slides.forEach(x=>x.bg_blur=studio.globalBlur);renderCanvas();markDirty()};wireFooter(2,4)
  }

  function estimateSeconds(){return Math.max(10,Math.round(studio.slides.reduce((n,s)=>n+(s.narration||'').trim().length,0)/4))}
  async function submitRender(){
    try{syncStepState();await saveDraft(4,true);await api('/course-tools/courses/'+studio.courseId+'/normalize',{method:'POST'});const ready=await api('/course-tools/courses/'+studio.courseId+'/readiness');if(!ready.ready){studio.readiness=ready;renderStep4();toast('还有项目需要确认');return}const engine=document.querySelector('[name="studioEngine"]:checked')?.value||'mock';await api('/courses/'+studio.courseId+'/render',{method:'POST',body:{engine,estimated_seconds:estimateSeconds(),audio_asset_id:null}});toast('已加入生成队列');await closeStudio();showPage('jobs')}catch(e){toast(e.message)}
  }
  async function renderStep4(){
    const pane=document.getElementById('courseStudioPane');let readiness=studio.readiness;if(studio.courseId){try{readiness=await api('/course-tools/courses/'+studio.courseId+'/readiness')}catch(_){}}studio.readiness=readiness;const sec=estimateSeconds(),mins=(sec/60).toFixed(1),chars=studio.slides.reduce((n,s)=>n+(s.narration||'').trim().length,0),avatar=selectedAvatar();
    pane.innerHTML=`<div class="course-pane-head"><div><div class="eyebrow">STEP 04 · PACKAGE & RENDER</div><h2>包装与生成确认</h2><p>确认课程、数字人、字幕和生成引擎，然后提交异步任务。</p></div></div><div class="package-grid"><section class="studio-panel"><h2>${ehtml(studio.title)}</h2><div class="package-summary"><div class="package-metric"><span class="muted">课件页数</span><b>${studio.slides.length}</b></div><div class="package-metric"><span class="muted">讲稿字数</span><b>${chars}</b></div><div class="package-metric"><span class="muted">预计时长</span><b>${mins} min</b></div></div><div class="field"><label>主讲数字人</label><div>${ehtml(avatar?.name||'未选择')}</div></div><label class="check"><input id="studioSubtitle" type="checkbox" ${studio.embedSubtitles?'checked':''}><span>生成并烧录字幕</span></label><div class="readiness-list">${readiness?.ready?'<div class="readiness-row ok">✓ 课程素材、数字人、声音、授权和讲稿均已就绪</div>':(readiness?.issues||['保存课程后进行完整性检查']).map(x=>`<div class="readiness-row bad">! ${ehtml(x)}</div>`).join('')}</div></section><aside class="studio-panel"><h2>生成引擎</h2><div class="engine-choice"><label class="engine-option active"><input type="radio" name="studioEngine" value="mock" checked> <b>Mock 验收</b><small>不需要 GPU，用于验证 SaaS 全流程、成片交付和额度结算。</small></label><label class="engine-option"><input type="radio" name="studioEngine" value="musetalk"> <b>Mac MLX · MuseTalk</b><small>使用 Apple Silicon 本地 Worker 生成真实数字人课程。</small></label></div><div class="studio-panel" style="margin-top:14px;padding:14px"><div class="eyebrow">COMPLIANCE</div><b>AI 生成标识自动开启</b><div class="muted">成片会执行平台统一的 AI 内容标识策略。</div></div><button class="primary wide" id="studioProduce" style="margin-top:16px;padding:13px">开始生成数字人课程</button></aside></div>${footer(3,null)}`;
    document.getElementById('studioSubtitle').onchange=e=>{studio.embedSubtitles=e.target.checked;markDirty()};document.querySelectorAll('.engine-option input').forEach(r=>r.onchange=()=>document.querySelectorAll('.engine-option').forEach(x=>x.classList.toggle('active',x.querySelector('input').checked)));document.getElementById('studioProduce').onclick=submitRender;wireFooter(3,null)
  }
  function renderStudio(){cleanupBlobUrls();shell();if(studio.step===1)renderStep1();else if(studio.step===2)renderStep2();else if(studio.step===3)renderStep3();else renderStep4()}

  async function openStudio(course=null,forcedStep=null){
    cleanupBlobUrls();
    if(!cache.avatars?.length||!cache.assets)await loadLookups();
    const settings=course?.settings||{};studio={courseId:course?.id||null,title:course?.title||'',pptId:course?.ppt_asset_id||null,avatarId:course?.avatar_id||'',voiceOverrideId:'',baseSettings:settings,outline:null,slides:[],currentSlide:0,step:forcedStep||Number(settings.wizard_step||1),activeLayer:'avatar',globalBlur:Boolean(settings.bg_blur),embedSubtitles:settings.embed_subtitles!==false,dirty:false,readiness:null};
    if(course?.avatar_id){const a=cache.avatars.find(x=>x.id===course.avatar_id);studio.voiceOverrideId=course.voice_profile_id&&course.voice_profile_id!==a?.voice_profile_id?course.voice_profile_id:''}
    if(studio.pptId){try{studio.outline=await api('/course-tools/ppt/'+studio.pptId+'/outline');studio.slides=mergeSlides(studio.outline,course?.script||[])}catch(e){studio.step=1;toast(e.message)}}
    if(!studio.slides.length&&course?.script?.length)studio.slides=course.script.map((x,i)=>emptySlide({index:x.index||i+1,...x}));
    renderStudio();
  }

  courseModal=function(c=null){openStudio(c).catch(e=>toast(e.message))};
  renderModal=function(id){api('/courses/'+id).then(c=>openStudio(c,4)).catch(e=>toast(e.message))};
  window.openCourseStudio=openStudio;
})();
'''


def css_response() -> Response:
    return Response(CSS, media_type="text/css; charset=utf-8")


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
