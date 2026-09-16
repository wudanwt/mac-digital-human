from __future__ import annotations

from fastapi.responses import Response


JS = r'''
(() => {
  const icons = {
    dashboard:'<svg viewBox="0 0 24 24" fill="none"><path d="M4 4h6v6H4zM14 4h6v10h-6zM4 14h6v6H4zM14 18h6v2h-6z" stroke-width="1.6"/></svg>',
    courses:'<svg viewBox="0 0 24 24" fill="none"><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" stroke-width="1.6" stroke-linecap="round"/></svg>',
    avatars:'<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="3.2" stroke-width="1.6"/><path d="M5 20c.6-4 3-6 7-6s6.4 2 7 6" stroke-width="1.6" stroke-linecap="round"/></svg>',
    assets:'<svg viewBox="0 0 24 24" fill="none"><path d="M4 7.5h6l1.8 2H20v9.5H4zM4 7.5V5h6l1.5 2.5" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    jobs:'<svg viewBox="0 0 24 24" fill="none"><path d="M12 3a9 9 0 1 1-7.4 3.9M4 3v4h4" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 7v5l3 2" stroke-width="1.6" stroke-linecap="round"/></svg>',
    billing:'<svg viewBox="0 0 24 24" fill="none"><path d="M4 7h16v11H4zM4 10h16M8 15h3" stroke-width="1.6" stroke-linecap="round"/></svg>',
    settings:'<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="3" stroke-width="1.6"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" stroke-width="1.6" stroke-linecap="round"/></svg>',
    admin:'<svg viewBox="0 0 24 24" fill="none"><path d="m12 3 8 4v5c0 4.7-3.2 7.6-8 9-4.8-1.4-8-4.3-8-9V7z" stroke-width="1.6"/><path d="m9 12 2 2 4-4" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
  };
  const navLabels={dashboard:'总览',courses:'课程',avatars:'数字人',assets:'素材',jobs:'任务',billing:'套餐',settings:'设置',admin:'运营'};
  const stageLabels={queued:'等待调度',starting:'准备中',running:'生成中',mock_render:'模拟生成',mock_complete:'模拟完成',ppt_parse:'解析课件',uploading:'上传成片',succeeded:'生成完成',failed:'生成失败',canceled:'已取消',queue_failed:'队列异常'};
  const kindLabels={ppt:'课件',document:'文档',image:'图片',video:'视频',audio:'音频',background:'背景',output:'成片',other:'其他'};

  function decorateChrome(){
    document.querySelectorAll('#nav button[data-page]').forEach(b=>{
      const p=b.dataset.page;if(!p)return;
      b.innerHTML=(icons[p]||'')+`<span>${navLabels[p]||p}</span>`;
    });
    const logo=document.querySelector('.logo');if(logo)logo.textContent='NEO HUMAN';
    const refresh=$('refreshBtn');if(refresh)refresh.textContent='刷新';
  }
  decorateChrome();

  function fmtDate(v){try{return new Date(v).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}catch(_){return '—'}}
  function statusText(v){return ({draft:'草稿',queued:'排队中',running:'生成中',succeeded:'已完成',completed:'已完成',failed:'失败',canceled:'已取消',ready:'可用',active:'有效',pending:'待确认',paid:'已支付',expired:'已到期'})[v]||v||'—'}
  function pct(value,total){if(!total)return 0;return Math.max(0,Math.min(100,Math.round(value/total*100)))}
  function getAvatarName(id){return cache.avatars.find(x=>x.id===id)?.name||'未选择数字人'}
  function courseByJob(id){const j=(window.__lastJobs||[]).find(x=>x.id===id);return cache.courses.find(c=>c.id===j?.course_id)}

  renderDashboard=async function(){
    const [d,sub,jobs,plans]=await Promise.all([api('/dashboard'),api('/billing/subscription'),api('/jobs'),api('/billing/plans')]);
    window.__lastJobs=jobs;
    const plan=plans.find(p=>p.code===sub.plan_code)||{monthly_minutes:Math.max(sub.remaining_minutes,1)};
    const used=Math.max(0,plan.monthly_minutes-sub.remaining_minutes),usedPct=pct(used,plan.monthly_minutes);
    $('page').innerHTML=`
      <section class="tech-hero">
        <div class="eyebrow">AI COURSE PRODUCTION</div>
        <h2>把课件变成可交付的数字人课程</h2>
        <p>课程、数字人、声音与异步生成统一在一个工作区。当前处于 SaaS 功能验收阶段，CUDA 暂不参与。</p>
        <div class="hero-actions"><button class="primary" id="dashNewCourse">新建课程</button><button class="secondary" id="dashDigitalHuman">管理数字人</button></div>
      </section>
      <div class="section-title"><div><h2>工作区状态</h2><p>核心资产与生成情况</p></div></div>
      <div class="grid stats">
        <div class="stat"><div class="muted">课程项目</div><div class="num">${d.courses}</div></div>
        <div class="stat"><div class="muted">数字人资产</div><div class="num">${d.avatars}</div></div>
        <div class="stat"><div class="muted">素材文件</div><div class="num">${d.assets}</div></div>
        <div class="stat"><div class="muted">进行中任务</div><div class="num">${d.active_jobs}</div></div>
        <div class="stat"><div class="muted">已交付成片</div><div class="num">${d.completed_jobs}</div></div>
      </div>
      <div class="split" style="margin-top:16px">
        <div class="card"><div class="eyebrow">CURRENT PLAN</div><div class="metric-line"><div class="quota-ring" style="--p:${usedPct}"><div><b>${sub.remaining_minutes}</b><small>剩余分钟</small></div></div><div><h2>${esc(sub.plan_name)}</h2><div class="muted">本周期已使用 ${sub.consumed_minutes} 分钟</div><div class="muted">${sub.storage_gb}GB 存储 · ${sub.max_avatars} 个数字人 · ${sub.max_members} 位成员</div></div></div></div>
        <div class="card"><div class="toolbar"><div><h2>最近任务</h2><div class="muted">最新 5 条生成记录</div></div><button class="secondary" id="dashJobs">查看全部</button></div>${modernJobList(jobs.slice(0,5),true)}</div>
      </div>`;
    $('dashNewCourse').onclick=()=>courseModal();$('dashDigitalHuman').onclick=()=>showPage('avatars');$('dashJobs').onclick=()=>showPage('jobs');
  };

  function modernJobList(items,compact=false){
    if(!items.length)return '<div class="empty">还没有生成任务</div>';
    return `<div style="display:grid;gap:8px">${items.map(j=>{const c=cache.courses.find(x=>x.id===j.course_id);return `<div class="job-card" style="padding:${compact?'12px':'16px'}"><div style="display:flex;justify-content:space-between;gap:12px;align-items:center"><div><h3>${esc(c?.title||'课程生成任务')}</h3><div class="job-meta"><span>${fmtDate(j.created_at)}</span><span>${esc(j.engine)}</span><span>${esc(stageLabels[j.stage]||j.stage||'')}</span></div></div><span class="badge ${j.status}">${statusText(j.status)}</span></div><div style="display:flex;align-items:center;gap:12px;margin-top:10px"><div class="progress" style="flex:1;width:auto"><i style="width:${j.progress||0}%"></i></div><span class="code">${j.progress||0}%</span>${j.output_asset_id?`<button class="secondary" data-modern-download="${j.output_asset_id}" data-name="${esc(c?.title||'result')}.mp4">下载</button>`:''}${j.status==='queued'?`<button class="danger" data-modern-cancel="${j.id}">取消</button>`:''}</div></div>`}).join('')}</div>`;
  }
  function wireModernJobs(){
    document.querySelectorAll('[data-modern-download]').forEach(b=>b.onclick=()=>downloadAsset(b.dataset.modernDownload,b.dataset.name));
    document.querySelectorAll('[data-modern-cancel]').forEach(b=>b.onclick=async()=>{try{await api('/jobs/'+b.dataset.modernCancel+'/cancel',{method:'POST'});showPage('jobs')}catch(e){toast(e.message)}});
  }

  renderCourses=async function(){
    cache.courses=await api('/courses');
    $('page').innerHTML=`<div class="section-title"><div><h2>课程项目</h2><p>从 PPT、讲稿到数字人成片</p></div><button class="primary" id="newCourseModern">+ 新建课程</button></div>
      ${cache.courses.length?`<div class="course-grid">${cache.courses.map(c=>`<article class="course-card"><div style="display:flex;justify-content:space-between;gap:12px"><div><div class="eyebrow">COURSE</div><h3>${esc(c.title)}</h3></div><span class="badge ${c.status}">${statusText(c.status)}</span></div><div class="course-meta"><span>${getAvatarName(c.avatar_id)}</span><span>${Array.isArray(c.script)?c.script.length:0} 页讲稿</span><span>${fmtDate(c.updated_at)}</span></div><div class="course-actions"><button class="secondary" data-course-edit="${c.id}">编辑</button><button class="primary" data-course-render="${c.id}">生成</button>${c.output_asset_id?`<button class="secondary" data-course-download="${c.output_asset_id}" data-name="${esc(c.title)}.mp4">成片</button>`:''}<button class="danger" data-course-delete="${c.id}">删除</button></div></article>`).join('')}</div>`:'<div class="empty">还没有课程。新建课程后可直接上传 PPT 并逐页编辑讲稿。</div>'}`;
    $('newCourseModern').onclick=()=>courseModal();
    document.querySelectorAll('[data-course-edit]').forEach(b=>b.onclick=async()=>courseModal(await api('/courses/'+b.dataset.courseEdit)));
    document.querySelectorAll('[data-course-render]').forEach(b=>b.onclick=()=>renderModal(b.dataset.courseRender));
    document.querySelectorAll('[data-course-download]').forEach(b=>b.onclick=()=>downloadAsset(b.dataset.courseDownload,b.dataset.name));
    document.querySelectorAll('[data-course-delete]').forEach(b=>b.onclick=async()=>{if(!confirm('删除这个课程？已生成成片素材不会自动删除。'))return;try{await api('/courses/'+b.dataset.courseDelete,{method:'DELETE'});await loadLookups();renderCourses()}catch(e){toast(e.message)}});
  };

  let courseStudio={pptId:null,outline:null,existingScript:[]};
  function layoutOptions(value){return [['pip','画中画'],['split','左右分屏'],['full_slide','全屏课件'],['full_avatar','全屏讲师']].map(([v,n])=>`<option value="${v}" ${value===v?'selected':''}>${n}</option>`).join('')}
  function renderSlideEditor(outline,existing=[]){
    courseStudio.outline=outline;courseStudio.existingScript=existing||[];
    const map=Object.fromEntries((existing||[]).map((x,i)=>[Number(x.index||i+1),x]));
    const host=$('courseSlides');if(!host)return;
    host.innerHTML=`<div class="toolbar" style="margin:16px 0 10px"><div><b>${outline.total_slides} 页课件</b><div class="muted">已自动读取标题、备注与讲解文本，可逐页调整</div></div></div><div class="slide-editor">${outline.slides.map(s=>{const old=map[s.index]||{};const narration=old.narration||old.script||s.narration||'';return `<div class="slide-edit-card" data-slide-index="${s.index}"><div class="slide-head"><div><span class="slide-no">SLIDE ${String(s.index).padStart(2,'0')}</span><div style="font-weight:680">${esc(s.title||'未命名页面')}</div></div><select class="slide-layout">${layoutOptions(old.layout||s.layout||'pip')}</select></div><textarea class="slide-narration" placeholder="这一页的讲解内容">${esc(narration)}</textarea></div>`}).join('')}</div>`;
  }
  async function inspectSelectedPpt(existingScript=[]){
    let id=$('coursePptSelect')?.value||courseStudio.pptId;const file=$('coursePptFile')?.files?.[0];
    if(file){
      const fd=new FormData();fd.append('file',file);fd.append('kind','ppt');
      const uploaded=await api('/assets',{method:'POST',body:fd});id=uploaded.id;courseStudio.pptId=id;await loadLookups();
      if($('coursePptSelect')){$('coursePptSelect').innerHTML=opts(cache.assets.filter(a=>a.kind==='ppt'),id);$('coursePptSelect').value=id;}
    }
    if(!id)throw Error('请先上传或选择 PPT/PDF 课件');
    courseStudio.pptId=id;const outline=await api('/course-tools/ppt/'+id+'/outline');
    if(!$('courseTitle').value.trim())$('courseTitle').value=outline.title||'';
    renderSlideEditor(outline,existingScript);
  }

  courseModal=function(c=null){
    c=c||{title:'',ppt_asset_id:'',avatar_id:'',voice_profile_id:'',script:[]};courseStudio={pptId:c.ppt_asset_id||null,outline:null,existingScript:c.script||[]};
    const ppts=cache.assets.filter(a=>a.kind==='ppt'||/\.(pptx|ppt|pdf)$/i.test(a.name));
    const selectedAvatar=cache.avatars.find(a=>a.id===c.avatar_id);const override=(selectedAvatar&&c.voice_profile_id===selectedAvatar.voice_profile_id)?'':(c.voice_profile_id||'');
    openModal(`<div class="modal-head"><div><div class="eyebrow">COURSE STUDIO</div><h2>${c.id?'编辑课程':'新建课程'}</h2><div class="muted">上传课件后自动生成逐页讲稿编辑区</div></div><button class="iconbtn" data-close>×</button></div><form id="modernCourseForm" data-id="${c.id||''}">
      <div class="field"><label>课程名称</label><input id="courseTitle" value="${esc(c.title||'')}" required placeholder="例如：从项目交付到业务经营"></div>
      <div class="field"><label>PPT / PDF 课件</label><div class="upload-zone"><input id="coursePptFile" type="file" accept=".pptx,.ppt,.pdf"><div class="muted">可以直接上传新课件，或从已有课件中选择</div></div><select id="coursePptSelect" style="margin-top:9px">${opts(ppts,c.ppt_asset_id)}</select><button type="button" class="secondary" id="inspectCoursePpt" style="margin-top:9px">解析课件并生成讲稿</button></div>
      <div class="field"><label>数字人</label><select id="courseAvatar" required>${opts(cache.avatars,c.avatar_id)}</select><div class="muted" id="courseVoiceHint"></div></div>
      <details class="details-box"><summary>高级设置 · 覆盖默认声音</summary><div class="field"><label>临时使用其他声音</label><select id="courseVoiceOverride">${(typeof voiceOptions==='function'?voiceOptions(override):opts(cache.voices,override))}</select><div class="muted">一般无需设置，课程会自动跟随数字人的默认声音。</div></div></details>
      <div id="courseSlides"></div>
      <button class="primary wide" style="margin-top:18px">保存课程</button></form>`);
    $('modalRoot').querySelector('[data-close]').onclick=closeModal;
    const voiceHint=()=>{const a=cache.avatars.find(x=>x.id===$('courseAvatar').value);const v=cache.voices.find(x=>x.id===a?.voice_profile_id);$('courseVoiceHint').textContent=a?`默认声音：${v?.name||a.voice?.name||'未配置'}`:'请选择数字人'};voiceHint();$('courseAvatar').onchange=voiceHint;
    $('inspectCoursePpt').onclick=async()=>{try{await inspectSelectedPpt(c.script||[])}catch(e){toast(e.message)}};
    $('modernCourseForm').onsubmit=async e=>{e.preventDefault();try{
      if(!courseStudio.outline){await inspectSelectedPpt(c.script||[])}
      const avatar=cache.avatars.find(a=>a.id===$('courseAvatar').value);if(!avatar)throw Error('请选择数字人');
      const effectiveVoice=$('courseVoiceOverride').value||avatar.voice_profile_id||null;if(!effectiveVoice)throw Error('这个数字人还没有可用声音');
      const script=[...document.querySelectorAll('.slide-edit-card')].map(card=>({index:Number(card.dataset.slideIndex),narration:card.querySelector('.slide-narration').value.trim(),layout:card.querySelector('.slide-layout').value}));
      const id=e.currentTarget.dataset.id;await api('/courses'+(id?'/'+id:''),{method:id?'PATCH':'POST',body:{title:$('courseTitle').value.trim(),ppt_asset_id:courseStudio.pptId,avatar_id:avatar.id,voice_profile_id:effectiveVoice,script}});
      await loadLookups();closeModal();renderCourses();toast(id?'课程已更新':'课程已创建');
    }catch(err){toast(err.message)}};
    if(c.ppt_asset_id)setTimeout(()=>inspectSelectedPpt(c.script||[]).catch(()=>{}),20);
  };

  renderModal=async function(id){
    try{await api('/course-tools/courses/'+id+'/normalize',{method:'POST'})}catch(_){}
    let ready={ready:false,issues:['正在检查课程配置…']};try{ready=await api('/course-tools/courses/'+id+'/readiness')}catch(e){ready={ready:false,issues:[e.message]}}
    openModal(`<div class="modal-head"><div><div class="eyebrow">RENDER JOB</div><h2>提交生成</h2><div class="muted">生成前检查数字人、声音、授权和讲稿完整性</div></div><button class="iconbtn" data-close>×</button></div>
      <div class="details-box" style="margin-bottom:14px"><div style="display:flex;align-items:center;gap:8px"><span class="status-dot ${ready.ready?'good':'warn'}"></span><b>${ready.ready?'课程配置完整':'需要注意'}</b></div>${ready.issues?.length?`<div class="muted" style="margin-top:8px">${ready.issues.map(x=>'• '+esc(x)).join('<br>')}</div>`:'<div class="muted" style="margin-top:6px">可以提交真实生成任务。</div>'}</div>
      <form id="modernRenderForm" data-id="${id}"><div class="field"><label>生成模式</label><select id="modernRenderEngine"><option value="mock">Mock · SaaS 功能验收</option><option value="musetalk">MuseTalk · M5/MLX Worker</option></select><div class="muted">目前默认使用 Mock 验收 SaaS 流程；选择 MuseTalk 需要启动本地 MLX Worker。</div></div><div class="field"><label>预计时长（秒）</label><input id="modernRenderSecs" type="number" min="1" max="21600" value="60"><div class="muted">服务端会重新估算，并按实际成片时长结算。</div></div><button class="primary wide">加入生成队列</button></form>`);
    $('modalRoot').querySelector('[data-close]').onclick=closeModal;
    $('modernRenderForm').onsubmit=async e=>{e.preventDefault();try{const engine=$('modernRenderEngine').value;if(engine==='musetalk'&&!ready.ready)throw Error('课程配置未通过真实生成检查');await api('/courses/'+id+'/render',{method:'POST',body:{engine,estimated_seconds:Number($('modernRenderSecs').value),audio_asset_id:null}});closeModal();showPage('jobs')}catch(err){toast(err.message)}};
  };

  renderAssets=async function(){
    cache.assets=await api('/assets');const groups=['ppt','video','audio','image','background','output','document','other'];
    $('page').innerHTML=`<div class="section-title"><div><h2>素材中心</h2><p>底层素材统一归档，创建数字人和课程时也会自动入库</p></div><button class="primary" id="modernUploadAsset">+ 上传素材</button></div>
      <div class="asset-grid">${cache.assets.map(a=>`<article class="asset-card"><div style="display:flex;justify-content:space-between;gap:10px"><div><div class="eyebrow">${kindLabels[a.kind]||a.kind}</div><h3>${esc(a.name)}</h3></div><span class="badge">${(a.size_bytes/1024/1024).toFixed(1)} MB</span></div><div class="asset-meta"><span>${fmtDate(a.created_at)}</span><span>${esc(a.content_type||'')}</span></div><div class="course-actions"><button class="secondary" data-asset-download="${a.id}" data-name="${esc(a.name)}">下载</button>${['owner','admin'].includes(me.workspace.role)&&a.kind!=='output'?`<button class="danger" data-asset-delete="${a.id}">删除</button>`:''}</div></article>`).join('')||'<div class="empty">暂无素材</div>'}</div>`;
    $('modernUploadAsset').onclick=modernAssetModal;document.querySelectorAll('[data-asset-download]').forEach(b=>b.onclick=()=>downloadAsset(b.dataset.assetDownload,b.dataset.name));document.querySelectorAll('[data-asset-delete]').forEach(b=>b.onclick=async()=>{if(!confirm('删除素材？被数字人或课程引用的素材不能删除。'))return;try{await api('/assets/'+b.dataset.assetDelete,{method:'DELETE'});await loadLookups();renderAssets()}catch(e){toast(e.message)}});
  };
  function inferKind(name){const ext=(name.split('.').pop()||'').toLowerCase();if(['pptx','ppt'].includes(ext))return'ppt';if(ext==='pdf')return'document';if(['png','jpg','jpeg','webp'].includes(ext))return'image';if(['mp4','mov','m4v'].includes(ext))return'video';if(['wav','mp3','m4a','aac','flac'].includes(ext))return'audio';return'other'}
  function modernAssetModal(){openModal(`<div class="modal-head"><div><h2>上传素材</h2><div class="muted">系统会根据文件格式自动识别类型</div></div><button class="iconbtn" data-close>×</button></div><form id="modernAssetForm"><div class="upload-zone"><input id="modernAssetFile" type="file" required><div class="muted" id="assetKindHint">选择文件后自动识别</div></div><button class="primary wide" style="margin-top:16px">上传</button></form>`);$('modalRoot').querySelector('[data-close]').onclick=closeModal;$('modernAssetFile').onchange=()=>{$('assetKindHint').textContent='识别类型：'+(kindLabels[inferKind($('modernAssetFile').files[0]?.name||'')]||'其他')};$('modernAssetForm').onsubmit=async e=>{e.preventDefault();try{const f=$('modernAssetFile').files[0],fd=new FormData();fd.append('file',f);fd.append('kind',inferKind(f.name));await api('/assets',{method:'POST',body:fd});await loadLookups();closeModal();renderAssets();toast('素材已上传')}catch(err){toast(err.message)}}}

  renderJobs=async function(){const jobs=await api('/jobs');window.__lastJobs=jobs;$('page').innerHTML=`<div class="section-title"><div><h2>生成任务</h2><p>异步队列、进度与成片交付</p></div></div>${modernJobList(jobs)}`;wireModernJobs()};

  renderBilling=async function(){const [plans,sub,orders]=await Promise.all([api('/billing/plans'),api('/billing/subscription'),api('/billing/orders')]);$('page').innerHTML=`<div class="section-title"><div><h2>套餐与额度</h2><p>当前为人工确认订单模式，正式支付待商户资质接入</p></div></div><div class="plan-grid">${plans.map(p=>`<div class="plan ${p.code===sub.plan_code?'current':''}"><div class="eyebrow">${p.code===sub.plan_code?'CURRENT PLAN':'PLAN'}</div><h3>${esc(p.name)}</h3><div class="price">¥${p.price_cny}<small class="muted"> / 30天</small></div><p class="muted">${p.monthly_minutes} 分钟生成额度</p><div class="details-box"><div>${p.storage_gb}GB 存储</div><div>${p.max_avatars} 个数字人</div><div>${p.max_members} 位成员</div></div>${['owner','admin'].includes(me.workspace.role)&&p.code!==sub.plan_code?`<button class="primary wide" style="margin-top:16px" data-plan-order="${p.code}">选择此套餐</button>`:''}</div>`).join('')}</div><div class="card" style="margin-top:16px"><div class="metric-line"><div><div class="muted">剩余生成额度</div><b>${sub.remaining_minutes} 分钟</b></div><div><div class="muted">已使用</div><b>${sub.consumed_minutes} 分钟</b></div><div><div class="muted">订阅状态</div><b>${statusText(sub.status)}</b></div></div></div>${orders.length?`<div class="card" style="margin-top:16px"><h2>最近订单</h2><div class="table-wrap"><table class="table"><tbody>${orders.slice(0,10).map(o=>`<tr><td>${esc(o.plan_code)}</td><td>¥${o.amount_cny}</td><td><span class="badge ${o.status}">${statusText(o.status)}</span></td><td>${fmtDate(o.created_at)}</td></tr>`).join('')}</tbody></table></div></div>`:''}`;document.querySelectorAll('[data-plan-order]').forEach(b=>b.onclick=async()=>{try{await api('/billing/orders',{method:'POST',body:{plan_code:b.dataset.planOrder,provider:'manual'}});toast('订单已创建，等待平台管理员确认');renderBilling()}catch(e){toast(e.message)}})};

  renderSettings=async function(){const [members,account,consents]=await Promise.all([api('/workspaces/members'),api('/account'),api('/compliance/consents')]);$('page').innerHTML=`<div class="section-title"><div><h2>设置</h2><p>账号、工作区、成员与授权记录</p></div></div><div class="split"><div class="card"><div class="eyebrow">ACCOUNT</div><h2>账号资料</h2><div class="field"><label>显示名称</label><input id="settingsDisplayName" value="${esc(account.display_name)}"></div><div class="muted">${esc(account.email)}</div><div class="actions" style="margin-top:16px"><button class="primary" id="saveProfile">保存资料</button><button class="secondary" id="changePassword">修改密码</button></div></div><div class="card"><div class="eyebrow">WORKSPACE</div><h2>工作区</h2><div class="field"><label>当前工作区</label><select id="workspaceSwitch">${me.workspaces.map(w=>`<option value="${w.id}" ${w.id===me.workspace.id?'selected':''}>${esc(w.name)} · ${esc(w.role)}</option>`).join('')}</select></div><button class="secondary" id="newWorkspaceModern">+ 新建工作区</button></div></div><div class="card" style="margin-top:16px"><div class="toolbar"><div><h2>成员</h2><div class="muted">团队成员共享当前工作区资产</div></div>${me.workspace.role==='owner'?'<button class="primary" id="newMemberModern">+ 添加成员</button>':''}</div><div class="table-wrap"><table class="table"><tbody>${members.map(m=>`<tr><td><b>${esc(m.display_name)}</b><div class="muted">${esc(m.email)}</div></td><td>${esc(m.role)}</td><td>${me.workspace.role==='owner'&&m.role!=='owner'?`<button class="danger" data-remove-member-modern="${m.id}">移除</button>`:''}</td></tr>`).join('')}</tbody></table></div></div><div class="card" style="margin-top:16px"><div class="toolbar"><div><h2>授权记录</h2><div class="muted">数字人肖像与克隆声音的授权状态</div></div></div>${consents.length?`<div class="table-wrap"><table class="table"><thead><tr><th>类型</th><th>对象</th><th>状态</th><th>时间</th><th></th></tr></thead><tbody>${consents.slice(0,50).map(c=>`<tr><td>${esc(c.consent_type)}</td><td class="code">${esc(c.subject_id.slice(0,10))}</td><td><span class="badge ${c.revoked_at?'canceled':'active'}">${c.revoked_at?'已撤销':'有效'}</span></td><td>${fmtDate(c.created_at)}</td><td>${!c.revoked_at&&['owner','admin'].includes(me.workspace.role)?`<button class="danger" data-revoke-consent="${c.id}">撤销</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">暂无授权记录</div>'}</div>`;
    $('workspaceSwitch').onchange=switchWorkspace;$('saveProfile').onclick=async()=>{try{await api('/account',{method:'PATCH',body:{display_name:$('settingsDisplayName').value}});me.user.display_name=$('settingsDisplayName').value;$('userName').textContent=me.user.display_name;toast('资料已保存')}catch(e){toast(e.message)}};$('changePassword').onclick=passwordModal;$('newWorkspaceModern').onclick=workspaceModal;$('newMemberModern')?.addEventListener('click',memberModal);document.querySelectorAll('[data-remove-member-modern]').forEach(b=>b.onclick=async()=>{if(!confirm('移除成员？'))return;try{await api('/workspaces/members/'+b.dataset.removeMemberModern,{method:'DELETE'});renderSettings()}catch(e){toast(e.message)}});document.querySelectorAll('[data-revoke-consent]').forEach(b=>b.onclick=async()=>{if(!confirm('撤销后，相关数字人/声音将不能继续用于生成。确定？'))return;try{await api('/compliance/consents/'+b.dataset.revokeConsent+'/revoke',{method:'POST'});await loadLookups();renderSettings()}catch(e){toast(e.message)}});
  };
  function passwordModal(){openModal(`<div class="modal-head"><h2>修改密码</h2><button class="iconbtn" data-close>×</button></div><form id="passwordForm"><div class="field"><label>当前密码</label><input id="currentPassword" type="password" required minlength="8"></div><div class="field"><label>新密码</label><input id="newPassword" type="password" required minlength="8"></div><button class="primary wide">更新密码</button></form>`);$('modalRoot').querySelector('[data-close]').onclick=closeModal;$('passwordForm').onsubmit=async e=>{e.preventDefault();try{await api('/account/change-password',{method:'POST',body:{current_password:$('currentPassword').value,new_password:$('newPassword').value}});closeModal();toast('密码已更新')}catch(err){toast(err.message)}}}

  renderAdmin=async function(){if(!me.user.is_superuser){$('page').innerHTML='<div class="empty">无平台运营权限</div>';return}const [o,tenants,orders,reports]=await Promise.all([api('/admin/overview'),api('/admin/tenants'),api('/admin/orders'),api('/admin/compliance/reports')]);window.__tenants=Object.fromEntries(tenants.map(t=>[t.id,t]));$('page').innerHTML=`<div class="section-title"><div><h2>运营控制台</h2><p>平台级用户、工作区、订单与内容合规</p></div></div><div class="grid stats"><div class="stat"><div class="muted">用户</div><div class="num">${o.users}</div></div><div class="stat"><div class="muted">工作区</div><div class="num">${o.tenants}</div></div><div class="stat"><div class="muted">排队任务</div><div class="num">${o.queued_jobs}</div></div><div class="stat"><div class="muted">运行任务</div><div class="num">${o.running_jobs}</div></div><div class="stat"><div class="muted">待确认订单</div><div class="num">${o.pending_orders}</div></div></div><div class="split" style="margin-top:16px"><div class="card"><h2>工作区</h2><div class="table-wrap"><table class="table"><tbody>${tenants.slice(0,30).map(t=>`<tr><td>${esc(t.name)}<div class="code">${t.id.slice(0,8)}</div></td><td>${esc(t.plan_code||'-')}</td><td>${t.remaining_minutes} 分钟</td><td><button class="secondary" data-admin-credit="${t.id}">额度</button></td></tr>`).join('')}</tbody></table></div></div><div class="card"><h2>待确认订单</h2><div class="table-wrap"><table class="table"><tbody>${orders.filter(x=>x.status==='pending').map(o=>`<tr><td>${o.id.slice(0,9)}</td><td>${esc(o.plan_code)}</td><td>¥${o.amount_cny}</td><td><button class="primary" data-admin-paid="${o.id}">确认</button></td></tr>`).join('')||'<tr><td class="muted">暂无</td></tr>'}</tbody></table></div></div></div><div class="card" style="margin-top:16px"><div class="toolbar"><div><h2>内容合规队列</h2><div class="muted">用户举报与处理状态</div></div></div>${reports.length?`<div class="table-wrap"><table class="table"><thead><tr><th>原因</th><th>对象</th><th>状态</th><th>时间</th><th></th></tr></thead><tbody>${reports.slice(0,50).map(r=>`<tr><td>${esc(r.reason)}</td><td>${esc(r.target_type)} · <span class="code">${r.target_id.slice(0,8)}</span></td><td><span class="badge ${r.status}">${esc(r.status)}</span></td><td>${fmtDate(r.created_at)}</td><td>${r.status!=='resolved'?`<button class="secondary" data-report-review="${r.id}">处理中</button> <button class="primary" data-report-resolve="${r.id}">完成</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">暂无举报</div>'}</div>`;document.querySelectorAll('[data-admin-credit]').forEach(b=>b.onclick=()=>creditModal(b.dataset.adminCredit));document.querySelectorAll('[data-admin-paid]').forEach(b=>b.onclick=async()=>{try{await api('/admin/orders/'+b.dataset.adminPaid+'/mark-paid',{method:'POST'});renderAdmin()}catch(e){toast(e.message)}});document.querySelectorAll('[data-report-review]').forEach(b=>b.onclick=()=>updateReport(b.dataset.reportReview,'reviewing'));document.querySelectorAll('[data-report-resolve]').forEach(b=>b.onclick=()=>updateReport(b.dataset.reportResolve,'resolved'))};
  async function updateReport(id,status){try{await api('/admin/compliance/reports/'+id,{method:'PATCH',body:{status,resolution:status==='resolved'?'已处理':'进入人工审核'}});renderAdmin()}catch(e){toast(e.message)}}

  const oldShowPage=showPage;showPage=async function(name){decorateChrome();return oldShowPage(name)};
  setTimeout(decorateChrome,80);
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
