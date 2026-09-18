from __future__ import annotations

from fastapi.responses import Response


CSS = r'''
.avatar-mode-section .avatar-mode-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.avatar-mode-btn{border:1px solid rgba(151,176,214,.12);background:#0e141d;color:#91a4b8;border-radius:10px;padding:9px 7px;font-size:10px;cursor:pointer;min-height:48px}.avatar-mode-btn b{display:block;color:#cbd9e8;font-size:10px}.avatar-mode-btn small{display:block;color:#5f7288;font-size:8px;margin-top:2px}.avatar-mode-btn.active{border-color:#65b9f6;background:#102235;box-shadow:0 0 0 2px rgba(101,185,246,.07)}.avatar-mode-btn.active b{color:#e7f6ff}.avatar-mode-btn:disabled{opacity:.38;cursor:not-allowed}.avatar-mode-readiness{margin-top:8px;padding:8px 9px;border-radius:9px;border:1px solid rgba(151,176,214,.09);background:#0b1118;color:#6d8197;font-size:9px;line-height:1.55}.avatar-mode-readiness.ok{color:#79d9b8;border-color:rgba(74,185,143,.18);background:rgba(21,75,60,.12)}.avatar-mode-readiness.bad{color:#e6a2ad;border-color:rgba(207,92,114,.16);background:rgba(91,30,43,.10)}.avatar-mode-apply{width:100%;margin-top:8px!important;font-size:9px!important;padding:6px 8px!important}.avatar-mode-make{margin-top:7px!important;font-size:9px!important;padding:5px 8px!important}.layout-layer.avatar.avatar-mode-transparent{background:transparent!important}.layout-layer.avatar.avatar-mode-white{background:#fff!important}.layout-layer.avatar.avatar-mode-matted #studioAvatarMedia{opacity:0!important}.studio-avatar-matte-overlay{position:absolute;inset:0;z-index:3;display:grid;place-items:center;pointer-events:none;overflow:hidden}.studio-avatar-matte-overlay img{display:block;width:100%;height:100%;object-fit:contain;object-position:center bottom}.avatar-mode-pill{position:absolute;right:6px;top:6px;z-index:7;border-radius:999px;padding:3px 7px;font-size:8px;background:rgba(4,10,16,.78);border:1px solid rgba(255,255,255,.08);color:#9dc9ea;pointer-events:none}
'''


JS = r'''
(() => {
  const state={activeKey:'__new__',activeAvatar:null,modes:new Map(),matting:new Map(),urls:new Map(),loading:new Map(),patchTimer:null};
  const nativeFetch=window.fetch.bind(window);
  const courseSave=/\/api\/saas\/courses(?:\/([^/?]+))?$/;
  const validModes=new Set(['original','transparent','white']);
  const html=s=>typeof esc==='function'?esc(s):String(s??'');

  function key(){return state.activeKey||'__new__'}
  function modeMap(){if(!state.modes.has(key()))state.modes.set(key(),new Map());return state.modes.get(key())}
  function slideIndex(){
    const active=document.querySelector('[data-layout-slide].active');if(active?.dataset?.layoutSlide!==undefined)return Number(active.dataset.layoutSlide)+1;
    const text=document.querySelector('#courseStudioPane .course-pane-head>.muted')?.textContent||'';const m=text.match(/第\s*(\d+)/);return Number(m?.[1]||1);
  }
  function totalSlides(){
    const count=document.querySelectorAll('[data-layout-slide]').length;if(count)return count;
    const text=document.querySelector('#courseStudioPane .course-pane-head>.muted')?.textContent||'';const m=text.match(/\/\s*(\d+)/);return Number(m?.[1]||1);
  }
  function currentMode(){return modeMap().get(slideIndex())||'original'}
  function setMode(index,mode){
    if(!validModes.has(mode))return;
    modeMap().set(Number(index),mode);
    const slides=window.__courseStudioSlides;
    if(Array.isArray(slides)){
      const slide=slides.find((item,i)=>Number(item?.index||i+1)===Number(index));
      if(slide)slide.avatar_mode=mode;
    }
  }
  function dirty(){const e=document.getElementById('studioSaveState');if(e)e.textContent='有未保存更改'}

  function seedCourse(course){
    state.activeKey=course?.id||'__new__';state.activeAvatar=course?.avatar_id||null;
    const map=new Map(),global=validModes.has(String(course?.settings?.avatar_mode||''))?String(course.settings.avatar_mode):'original';
    (course?.script||[]).forEach((item,i)=>{const idx=Number(item?.index||i+1),mode=String(item?.avatar_mode||global);map.set(idx,validModes.has(mode)?mode:'original')});
    state.modes.set(state.activeKey,map);schedulePatch();
  }

  const oldCourseModal=window.courseModal;if(typeof oldCourseModal==='function')window.courseModal=function(c=null){seedCourse(c);return oldCourseModal(c)};
  const oldOpen=window.openCourseStudio;if(typeof oldOpen==='function')window.openCourseStudio=function(c=null,step){seedCourse(c);return oldOpen(c,step)};
  const oldRenderModal=window.renderModal;if(typeof oldRenderModal==='function')window.renderModal=function(id){state.activeKey=id||'__new__';return oldRenderModal(id)};

  window.fetch=async function(input,init={}){
    const url=typeof input==='string'?input:(input?.url||'');const method=String(init.method||'GET').toUpperCase();const match=url.match(courseSave);let parsed=null;
    if(match&&['POST','PATCH'].includes(method)&&typeof init.body==='string'){
      try{parsed=JSON.parse(init.body)}catch(_){}
      if(parsed){
        if(parsed.avatar_id)state.activeAvatar=parsed.avatar_id;
        const map=modeMap();
        if(Array.isArray(parsed.script))parsed.script=parsed.script.map((item,i)=>{const idx=Number(item?.index||i+1);return {...item,avatar_mode:map.get(idx)||item.avatar_mode||'original'}});
        const activeModes=[...map.values()];const defaultMode=activeModes.length&&activeModes.every(m=>m===activeModes[0])?activeModes[0]:'original';
        parsed.settings={...(parsed.settings||{}),avatar_mode:defaultMode};init={...init,body:JSON.stringify(parsed)};
      }
    }
    const response=await nativeFetch(input,init);
    if(match&&method==='GET'&&match[1]&&response.ok&&document.getElementById('courseStudioShell'))response.clone().json().then(seedCourse).catch(()=>{});
    if(match&&method==='POST'&&!match[1]&&response.ok)response.clone().json().then(c=>{if(!c?.id)return;const old=state.modes.get('__new__');state.activeKey=c.id;if(old){state.modes.set(c.id,old);state.modes.delete('__new__')}if(c.avatar_id)state.activeAvatar=c.avatar_id}).catch(()=>{});
    return response;
  };

  async function matting(avatarId,force=false){
    if(!avatarId)return null;if(!force&&state.matting.has(avatarId))return state.matting.get(avatarId);if(state.loading.has(avatarId))return state.loading.get(avatarId);
    const task=api('/avatar-matting/'+avatarId).then(s=>{state.matting.set(avatarId,s);return s}).catch(()=>null).finally(()=>state.loading.delete(avatarId));state.loading.set(avatarId,task);return task;
  }
  async function blob(path,key2){if(state.urls.has(key2))return state.urls.get(key2);const r=await nativeFetch(path.startsWith('/api/')?path:(API+path),{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('透明讲师预览加载失败');const u=URL.createObjectURL(await r.blob());state.urls.set(key2,u);return u}
  function selectedAvatarId(){const select=document.getElementById('studioAvatarSelect');if(select?.value)state.activeAvatar=select.value;return state.activeAvatar}

  async function applyPreview(){
    const layer=document.getElementById('studioAvatarLayer'),host=document.getElementById('studioAvatarMedia');if(!layer||!host)return;
    const mode=currentMode(),avatarId=selectedAvatarId();layer.classList.remove('avatar-mode-transparent','avatar-mode-white','avatar-mode-matted');layer.querySelector('.studio-avatar-matte-overlay')?.remove();layer.querySelector('.avatar-mode-pill')?.remove();
    if(mode==='original'){return}
    const s=await matting(avatarId);if(!s?.transparent_ready||!s.poster_asset)return;
    try{const url=await blob(s.poster_asset.download_url,'poster:'+avatarId+':'+s.source_asset_id);if(!document.body.contains(layer)||selectedAvatarId()!==avatarId||currentMode()!==mode)return;const overlay=document.createElement('div');overlay.className='studio-avatar-matte-overlay';overlay.innerHTML=`<img src="${url}" alt="透明讲师">`;layer.appendChild(overlay);const pill=document.createElement('span');pill.className='avatar-mode-pill';pill.textContent=mode==='white'?'白底讲师':'透明讲师';layer.appendChild(pill);layer.classList.add('avatar-mode-matted',mode==='white'?'avatar-mode-white':'avatar-mode-transparent')}catch(_){}
  }

  async function choose(mode,all=false){
    const avatarId=selectedAvatarId();if(mode!=='original'){
      const s=await matting(avatarId,true);if(!s?.transparent_ready){if(s?.status==='queued'||s?.status==='running')toast('透明资产正在处理中，完成后即可使用');else toast('请先生成这个数字人的透明资产');await patchControls();return}
    }
    if(all){for(let i=1;i<=totalSlides();i++)setMode(i,mode)}else setMode(slideIndex(),mode);dirty();await patchControls();await applyPreview();
  }

  async function ensureMatting(){const avatarId=selectedAvatarId();if(!avatarId)return toast('请先选择数字人');try{const s=await api('/avatar-matting/'+avatarId+'/ensure',{method:'POST'});state.matting.set(avatarId,s);toast('透明资产已加入处理队列');pollMatting(avatarId);await patchControls()}catch(e){toast(e.message)}}
  async function pollMatting(avatarId){for(let i=0;i<120;i++){await new Promise(r=>setTimeout(r,2200));const s=await matting(avatarId,true);if(!s)continue;await patchControls();if(s.status==='succeeded'){toast('透明讲师资产已就绪');await applyPreview();return}if(['failed','canceled'].includes(s.status)){toast(s.error||'透明资产处理失败');return}}}

  async function patchControls(){
    const controls=document.querySelector('#courseStudioPane .layout-controls');if(!controls)return;const avatarId=selectedAvatarId(),courseKey=key(),slide=slideIndex(),s=await matting(avatarId);if(!document.body.contains(controls)||selectedAvatarId()!==avatarId||key()!==courseKey||slideIndex()!==slide)return;const ready=Boolean(s?.transparent_ready),mode=currentMode();
    let section=controls.querySelector('.avatar-mode-section');if(!section){section=document.createElement('section');section.className='layout-section avatar-mode-section';controls.prepend(section)}
    const status=ready?'透明资产已就绪':s?.status==='running'?`正在抠像 ${Number(s.progress||0)}%`:s?.status==='queued'?'等待抠像处理':s?.status==='failed'?'上次抠像失败':'尚未生成透明资产';
    const renderKey=JSON.stringify([courseKey,avatarId,slide,mode,ready,s?.status||'',Number(s?.progress||0),s?.error||'']);if(section.dataset.avatarModeState===renderKey){await applyPreview();return}section.dataset.avatarModeState=renderKey;
    section.innerHTML=`<h3>讲师背景模式</h3><div class="avatar-mode-grid">
      <button type="button" class="avatar-mode-btn ${mode==='transparent'?'active':''}" data-avatar-mode="transparent" ${ready?'':'disabled'}><b>透明叠加</b><small>推荐</small></button>
      <button type="button" class="avatar-mode-btn ${mode==='white'?'active':''}" data-avatar-mode="white" ${ready?'':'disabled'}><b>纯白背景</b><small>独立白底</small></button>
      <button type="button" class="avatar-mode-btn ${mode==='original'?'active':''}" data-avatar-mode="original"><b>原始背景</b><small>保留母版</small></button>
    </div><div class="avatar-mode-readiness ${ready?'ok':s?.status==='failed'?'bad':''}">${html(status)}${s?.error?` · ${html(s.error)}`:''}</div>
    ${!ready&&!['queued','running'].includes(s?.status)?'<button type="button" class="secondary avatar-mode-make">生成透明讲师资产</button>':''}
    <button type="button" class="secondary avatar-mode-apply">将当前模式应用到全部页面</button>`;
    await applyPreview();
  }

  document.addEventListener('click',e=>{const target=e.target.closest?.('[data-avatar-mode],.avatar-mode-apply,.avatar-mode-make');if(!target||!target.closest('.avatar-mode-section')||target.disabled)return;e.preventDefault();e.stopPropagation();if(target.matches('[data-avatar-mode]'))choose(target.dataset.avatarMode,false);else if(target.matches('.avatar-mode-apply'))choose(currentMode(),true);else ensureMatting()},true);
  function schedulePatch(){clearTimeout(state.patchTimer);state.patchTimer=setTimeout(()=>{state.patchTimer=null;patchControls();const select=document.getElementById('studioAvatarSelect');if(select&&!select.dataset.avatarModeBound){select.dataset.avatarModeBound='1';select.addEventListener('change',()=>{state.activeAvatar=select.value;state.matting.delete(select.value);patchControls()})}},80)}
  const observer=new MutationObserver(records=>{if(records.some(r=>[...r.addedNodes].some(n=>n.nodeType===1&&(n.matches?.('#courseStudioPane .layout-controls')||n.querySelector?.('#courseStudioPane .layout-controls')))))schedulePatch()});observer.observe(document.documentElement,{childList:true,subtree:true});
})();
'''


def css_response() -> Response:
    return Response(CSS, media_type="text/css; charset=utf-8")


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
