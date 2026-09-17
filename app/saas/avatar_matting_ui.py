from __future__ import annotations

from fastapi.responses import Response


CSS = r'''
.dh-matte-panel{margin-top:12px;padding:12px;border:1px solid rgba(110,177,233,.15);border-radius:12px;background:linear-gradient(145deg,rgba(12,23,34,.94),rgba(8,14,21,.96))}
.dh-matte-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.dh-matte-head b{font-size:12px;color:#dceeff}.dh-matte-head small{display:block;margin-top:2px;color:#6f8298;font-size:10px}.dh-matte-badge{font-size:9px;border:1px solid rgba(255,255,255,.08);border-radius:999px;padding:3px 7px;color:#8ea0b5;background:#111b27;white-space:nowrap}.dh-matte-badge.ready{color:#79ddb9;background:rgba(31,113,84,.18)}.dh-matte-badge.running{color:#8fc9ff;background:rgba(42,105,168,.18)}.dh-matte-badge.failed{color:#ff99aa;background:rgba(151,43,67,.15)}
.dh-matte-progress{height:5px;border-radius:99px;background:#1e2a38;overflow:hidden;margin-top:10px}.dh-matte-progress i{display:block;height:100%;background:linear-gradient(90deg,#4e91e8,#72e6ff);transition:width .2s}.dh-matte-meta{margin-top:7px;display:flex;justify-content:space-between;gap:8px;color:#667b91;font-size:9px}.dh-matte-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.dh-matte-actions button{font-size:9px!important;padding:5px 8px!important}.dh-matte-error{margin-top:8px;padding:8px;border-radius:8px;background:rgba(125,31,51,.14);color:#ff9daf;font-size:10px;line-height:1.55;word-break:break-word}
.dh-cutout-stage{min-height:420px;border-radius:14px;overflow:hidden;display:grid;place-items:center;background-color:#c7ccd1;background-image:linear-gradient(45deg,#e5e8eb 25%,transparent 25%),linear-gradient(-45deg,#e5e8eb 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#e5e8eb 75%),linear-gradient(-45deg,transparent 75%,#e5e8eb 75%);background-size:28px 28px;background-position:0 0,0 14px,14px -14px,-14px 0}.dh-cutout-stage img{max-width:100%;max-height:65vh;object-fit:contain}.dh-white-preview{width:100%;max-height:66vh;background:white;border-radius:12px}
'''


JS = r'''
(() => {
  const state={statuses:new Map(),loading:false,timer:null,urls:[]};
  const nativeFetch=window.fetch.bind(window);
  const digitalHumanSave=/\/api\/saas\/digital-humans(?:\/([^/?]+))?$/;

  function esc2(v){return typeof esc==='function'?esc(v):String(v??'')}
  function roleCanAdmin(){return Boolean(me?.user?.is_superuser)||['owner','admin'].includes(me?.workspace?.role)}
  function cleanupUrls(){state.urls.splice(0).forEach(u=>URL.revokeObjectURL(u))}
  async function blobUrl(path){
    const url=path.startsWith('/api/')?path:(API+path);const r=await nativeFetch(url,{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('透明资产预览加载失败');
    const u=URL.createObjectURL(await r.blob());state.urls.push(u);return u;
  }

  window.fetch=async function(input,init={}){
    const url=typeof input==='string'?input:(input?.url||'');const method=String(init.method||'GET').toUpperCase();
    const response=await nativeFetch(input,init);
    if(response.ok&&['POST','PATCH'].includes(method)&&digitalHumanSave.test(url)){
      response.clone().json().then(item=>{
        if(!item?.id)return;
        api('/avatar-matting/'+item.id+'/ensure',{method:'POST'}).then(s=>{state.statuses.set(item.id,s);scheduleRefresh(350)}).catch(()=>{});
      }).catch(()=>{});
    }
    return response;
  };

  function statusLabel(s){
    if(!s||s.status==='unprocessed')return ['未处理',''];
    if(s.status==='succeeded'&&s.transparent_ready)return ['透明资产就绪','ready'];
    if(s.status==='queued')return ['等待处理','running'];
    if(s.status==='running')return ['正在抠像','running'];
    if(s.status==='failed')return ['处理失败','failed'];
    if(s.status==='canceled')return ['已取消','failed'];
    return [String(s.status||'未知'),''];
  }
  function stateKey(s){return encodeURIComponent(JSON.stringify([s?.status,s?.progress,s?.stage,s?.error,s?.transparent_ready,s?.model,s?.metadata?.frames,s?.poster_asset?.id||s?.poster_asset?.download_url,s?.white_preview_asset?.id||s?.white_preview_asset?.download_url]))}
  function panelHtml(id,s,key=stateKey(s)){
    const [label,cls]=statusLabel(s),progress=Math.max(0,Math.min(100,Number(s?.progress||0))),ready=Boolean(s?.transparent_ready);
    const meta=s?.metadata||{},frames=meta.frames?`${meta.frames} 帧`:'';
    return `<div class="dh-matte-panel" data-dh-matte-panel="${id}" data-dh-matte-state="${key}">
      <div class="dh-matte-head"><div><b>透明讲师资产</b><small>母版只抠像一次，课程生成直接复用 Alpha，不会重复做人像分割。</small></div><span class="dh-matte-badge ${cls}">${esc2(label)}</span></div>
      ${(s?.status==='queued'||s?.status==='running')?`<div class="dh-matte-progress"><i style="width:${progress}%"></i></div><div class="dh-matte-meta"><span>${esc2(s.stage||'处理中')}</span><span>${progress}%</span></div>`:''}
      ${ready?`<div class="dh-matte-meta"><span>${esc2(s.model||'')}</span><span>${frames}</span></div>`:''}
      ${s?.error?`<div class="dh-matte-error">${esc2(s.error)}</div>`:''}
      <div class="dh-matte-actions">
        ${!ready&&s?.status!=='queued'&&s?.status!=='running'?`<button type="button" class="secondary" data-dh-matte-start="${id}">生成透明资产</button>`:''}
        ${ready&&s.poster_asset?`<button type="button" class="secondary" data-dh-matte-cutout="${id}">透明预览</button>`:''}
        ${ready&&s.white_preview_asset?`<button type="button" class="secondary" data-dh-matte-white="${id}">白底预览</button>`:''}
        ${ready&&roleCanAdmin()?`<button type="button" class="secondary" data-dh-matte-rebuild="${id}">重新抠像</button>`:''}
      </div>
    </div>`;
  }

  function findCard(id){return document.querySelector(`[data-dh-edit="${CSS.escape(id)}"]`)?.closest('.card')||null}

  function patchCards(){
    for(const [id,s] of state.statuses){const card=findCard(id);if(!card)continue;const existing=card.querySelector('[data-dh-matte-panel]'),key=stateKey(s);if(existing?.dataset.dhMatteState===key)continue;const actions=card.querySelector('.actions');const html=panelHtml(id,s,key);if(existing){const holder=document.createElement('div');holder.innerHTML=html;existing.replaceWith(holder.firstElementChild)}else if(actions){actions.insertAdjacentHTML('beforebegin',html)}else{card.lastElementChild?.insertAdjacentHTML('beforeend',html)}}
  }

  document.addEventListener('click',async e=>{
    const button=e.target.closest?.('[data-dh-matte-start],[data-dh-matte-rebuild],[data-dh-matte-cutout],[data-dh-matte-white]');if(!button||button.dataset.dhBusy==='1')return;
    e.preventDefault();e.stopPropagation();
    const originalText=button.textContent,id=button.dataset.dhMatteStart||button.dataset.dhMatteRebuild||button.dataset.dhMatteCutout||button.dataset.dhMatteWhite,s=state.statuses.get(id);
    try{
      if(button.dataset.dhMatteStart!==undefined||button.dataset.dhMatteRebuild!==undefined){
        const rebuild=button.dataset.dhMatteRebuild!==undefined;if(rebuild&&!confirm('重新生成透明资产？旧成片不受影响。'))return;
        button.dataset.dhBusy='1';button.disabled=true;button.textContent='正在提交...';
        const out=await api('/avatar-matting/'+id+(rebuild?'/rebuild':'/ensure'),{method:'POST'});state.statuses.set(id,out);patchCards();startPolling();toast(rebuild?'已重新加入抠像队列':'透明资产已加入处理队列');return;
      }
      button.dataset.dhBusy='1';button.disabled=true;cleanupUrls();
      if(button.dataset.dhMatteCutout!==undefined){const url=await blobUrl(s.poster_asset.download_url);openModal(`<div class="modal-head"><div><h2>透明讲师预览</h2><div class="muted">棋盘格区域表示真正透明，课程里会直接叠加到 PPT / 背景上。</div></div><button class="iconbtn" data-close>×</button></div><div class="dh-cutout-stage" style="margin-top:14px"><img src="${url}" alt="透明讲师预览"></div>`)}
      else{const url=await blobUrl(s.white_preview_asset.download_url);openModal(`<div class="modal-head"><div><h2>白底讲师预览</h2><div class="muted">这是同一套 Alpha 在纯白背景上的质检效果。</div></div><button class="iconbtn" data-close>×</button></div><video class="dh-white-preview" src="${url}" controls autoplay loop muted style="margin-top:14px"></video>`)}
      document.querySelector('#modalRoot [data-close]')?.addEventListener('click',()=>{cleanupUrls();closeModal()});
    }catch(err){toast(err.message)}finally{if(button.isConnected){button.disabled=false;button.textContent=originalText;delete button.dataset.dhBusy}}
  },true);

  async function refreshStatuses(){
    if(state.loading||!document.querySelector('[data-dh-edit]'))return;state.loading=true;
    try{const items=await api('/avatar-matting');state.statuses=new Map((items||[]).map(s=>[s.avatar_id,s]));patchCards();if(items.some(s=>['queued','running'].includes(s.status)))startPolling();else stopPolling()}catch(_){}finally{state.loading=false}
  }
  function stopPolling(){if(state.timer){clearTimeout(state.timer);state.timer=null}}
  function scheduleRefresh(ms=120){stopPolling();state.timer=setTimeout(()=>{state.timer=null;refreshStatuses()},ms)}
  function startPolling(){if(state.timer)return;state.timer=setTimeout(async()=>{state.timer=null;await refreshStatuses();if([...state.statuses.values()].some(s=>['queued','running'].includes(s.status)))startPolling()},1200)}

  function containsEditor(node){return node.nodeType===1&&(node.matches?.('[data-dh-edit]')||node.querySelector?.('[data-dh-edit]'))}
  const observer=new MutationObserver(records=>{if(records.some(record=>[...record.addedNodes].some(containsEditor)))scheduleRefresh(80)});observer.observe(document.documentElement,{childList:true,subtree:true});
  if(document.querySelector('[data-dh-edit]'))refreshStatuses();
})();
'''


def css_response() -> Response:
    return Response(CSS, media_type="text/css; charset=utf-8")


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
