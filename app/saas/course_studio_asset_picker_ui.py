from __future__ import annotations

from fastapi.responses import Response


CSS = r'''
/* Rich digital-human picker for course setup. */
.studio-avatar-choice{grid-template-columns:repeat(auto-fill,minmax(250px,1fr))!important;gap:12px!important;max-height:440px!important}
.studio-avatar-option{display:grid!important;grid-template-columns:82px minmax(0,1fr);gap:12px;align-items:stretch;padding:10px!important;min-height:116px!important;position:relative;overflow:hidden;transition:border-color .16s ease,background .16s ease,transform .16s ease}
.studio-avatar-option:hover{transform:translateY(-1px);border-color:rgba(113,183,255,.32)!important}
.studio-avatar-option.active{border-color:rgba(113,183,255,.72)!important;background:linear-gradient(145deg,#101d2b,#0c151f)!important}
.studio-avatar-thumb{width:82px;height:98px;border-radius:10px;overflow:hidden;background:linear-gradient(145deg,#162231,#0b1119);border:1px solid rgba(151,176,214,.12);display:grid;place-items:center;color:#53667c;font-size:24px}
.studio-avatar-thumb img,.studio-avatar-thumb video{width:100%;height:100%;object-fit:cover;object-position:center top;display:block}
.studio-avatar-copy{min-width:0;display:flex;flex-direction:column;gap:6px;padding:2px 0}
.studio-avatar-name{display:flex;align-items:center;justify-content:space-between;gap:8px}.studio-avatar-name b{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px}.studio-avatar-selected{font-size:9px;color:#80c8ff;opacity:0}.studio-avatar-option.active .studio-avatar-selected{opacity:1}
.studio-avatar-voice{display:grid;grid-template-columns:auto minmax(0,1fr);gap:3px 7px;align-items:center;padding:7px 8px;border-radius:9px;background:rgba(4,9,15,.48);border:1px solid rgba(151,176,214,.08)}
.studio-avatar-voice span{font-size:9px;color:#63758b}.studio-avatar-voice strong{font-size:10px;color:#dcecff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.studio-avatar-voice small{grid-column:2;color:#687d94!important;font-size:9px}
.studio-avatar-flags{display:flex;gap:5px;flex-wrap:wrap}.studio-avatar-flag{font-size:8px!important;padding:2px 6px;border-radius:999px;background:#111c28;color:#71859a!important;border:1px solid rgba(151,176,214,.08)}.studio-avatar-flag.ok{color:#74d9b4!important;background:rgba(35,111,86,.16)}.studio-avatar-flag.bad{color:#e99aaa!important;background:rgba(142,50,71,.12)}
.studio-avatar-audio{justify-self:start;padding:4px 8px!important;font-size:9px!important;border-radius:7px!important;min-height:26px}.studio-avatar-audio.playing{border-color:#72e6ff!important;color:#dff9ff!important}
.studio-avatar-picker-note{margin:-4px 0 10px;color:#64768c;font-size:10px}
@media(max-width:700px){.studio-avatar-choice{grid-template-columns:1fr!important}.studio-avatar-option{grid-template-columns:72px minmax(0,1fr)}.studio-avatar-thumb{width:72px;height:88px}}
'''


JS = r'''
(() => {
  const state={rich:null,loading:null,blobUrls:new Map(),audio:null,patchedHost:null};
  const nativeFetch=window.fetch.bind(window);
  const escHtml=s=>typeof esc==='function'?esc(s):String(s??'');

  async function richAvatars(){
    if(state.rich)return state.rich;
    if(state.loading)return state.loading;
    state.loading=api('/digital-humans').then(items=>{
      const legacy=new Map((cache.avatars||[]).map(a=>[a.id,a]));
      state.rich=(items||[]).map(a=>({...legacy.get(a.id),...a,ready:Boolean(a.readiness?.musetalk_ready)}));
      cache.avatars=state.rich;
      return state.rich;
    }).finally(()=>{state.loading=null});
    return state.loading;
  }

  async function privateBlob(path,key){
    if(!path)return '';
    if(state.blobUrls.has(key))return state.blobUrls.get(key);
    const url=await assetMediaUrl(path);state.blobUrls.set(key,url);return url;
  }

  function card(a,selected){
    const voice=a.voice||null,ready=a.readiness||{};
    const voiceName=voice?.name||'未绑定声音';
    const provider=voice?.provider?String(voice.provider).replace('cosyvoice','CosyVoice'):'—';
    const canPlay=Boolean(voice?.reference_asset?.download_url);
    return `<div class="studio-avatar-option ${a.id===selected?'active':''}" data-avatar="${a.id}" role="button" tabindex="0" aria-label="选择数字人 ${escHtml(a.name)}">
      <div class="studio-avatar-thumb" data-avatar-thumb="${a.id}"><span>◉</span></div>
      <div class="studio-avatar-copy">
        <div class="studio-avatar-name"><b>${escHtml(a.name)}</b><span class="studio-avatar-selected">已选择</span></div>
        <div class="studio-avatar-voice"><span>声音</span><strong>${escHtml(voiceName)}</strong><small>${escHtml(provider)}${voice?.transcript?' · 参考文本已绑定':''}</small></div>
        <div class="studio-avatar-flags"><small class="studio-avatar-flag ${ready.master_video_ready?'ok':'bad'}">${ready.master_video_ready?'母版就绪':'缺少母版'}</small><small class="studio-avatar-flag ${ready.voice_ready?'ok':'bad'}">${ready.voice_ready?'声音就绪':'声音未就绪'}</small></div>
        ${canPlay?`<button type="button" class="secondary studio-avatar-audio" data-avatar-voice-preview="${a.id}">▶ 试听声音</button>`:''}
      </div>
    </div>`;
  }

  async function loadThumb(a){
    const host=document.querySelector(`[data-avatar-thumb="${CSS.escape(a.id)}"]`);if(!host||host.dataset.loaded)return;
    host.dataset.loaded='1';
    try{
      if(a.image?.download_url){
        const img=document.createElement('img');img.alt=a.name||'数字人形象';img.src=await privateBlob(a.image.download_url,'portrait:'+a.id);host.replaceChildren(img);return;
      }
      if(a.master_video?.download_url){
        const video=document.createElement('video');video.muted=true;video.playsInline=true;video.preload='metadata';video.src=await privateBlob(a.master_video.download_url,'master:'+a.id);host.replaceChildren(video);
      }
    }catch(_){host.dataset.loaded=''}
  }

  async function previewVoice(a,button){
    const path=a.voice?.reference_asset?.download_url;if(!path)return;
    try{
      if(state.audio){state.audio.pause();state.audio=null;document.querySelectorAll('.studio-avatar-audio.playing').forEach(x=>{x.classList.remove('playing');x.textContent='▶ 试听声音'})}
      const url=await privateBlob(path,'voice:'+a.id);const audio=new Audio(url);state.audio=audio;button.classList.add('playing');button.textContent='■ 停止试听';
      const reset=()=>{if(state.audio===audio)state.audio=null;button.classList.remove('playing');button.textContent='▶ 试听声音'};
      audio.onended=reset;audio.onerror=reset;await audio.play();
    }catch(e){if(typeof toast==='function')toast(e.message||'声音试听失败')}
  }

  async function enhancePicker(){
    const host=document.getElementById('studioAvatarCards'),select=document.getElementById('studioAvatarSelect');
    if(!host||!select||host===state.patchedHost)return;
    state.patchedHost=host;
    try{
      const items=await richAvatars();
      if(!document.body.contains(host)){state.patchedHost=null;return}
      const selected=select.value;
      const panel=host.closest('.studio-panel');
      if(panel&&!panel.querySelector('.studio-avatar-picker-note')){
        const note=document.createElement('div');note.className='studio-avatar-picker-note';note.textContent='直接看形象、绑定音色和就绪状态；可先试听声音，再选择主讲数字人。';host.before(note);
      }
      host.innerHTML=items.length?items.map(a=>card(a,selected)).join(''):'<div class="empty">暂无数字人，请先到数字人资产中创建。</div>';
      host.querySelectorAll('.studio-avatar-option').forEach(el=>{
        const choose=()=>{select.value=el.dataset.avatar;select.dispatchEvent(new Event('change',{bubbles:true}));host.querySelectorAll('.studio-avatar-option').forEach(x=>x.classList.toggle('active',x.dataset.avatar===select.value))};
        el.addEventListener('click',e=>{if(e.target.closest('[data-avatar-voice-preview]'))return;choose()});
        el.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&!e.target.closest('button')){e.preventDefault();choose()}});
      });
      host.querySelectorAll('[data-avatar-voice-preview]').forEach(btn=>btn.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();const a=items.find(x=>x.id===btn.dataset.avatarVoicePreview);if(a)previewVoice(a,btn)}));
      items.forEach(loadThumb);
    }catch(e){state.patchedHost=null;if(typeof toast==='function')toast(e.message||'数字人信息加载失败')}
  }

  const observer=new MutationObserver(()=>{if(document.getElementById('studioAvatarCards'))enhancePicker()});
  observer.observe(document.documentElement,{childList:true,subtree:true});
  if(document.getElementById('studioAvatarCards'))enhancePicker();
})();
'''


def css_response() -> Response:
    return Response(CSS, media_type="text/css; charset=utf-8")


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
