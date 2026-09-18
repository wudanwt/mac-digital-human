from __future__ import annotations

from fastapi.responses import Response


JS = r'''
(() => {
  let checking=false;
  let mountedRadio=null;

  function engineInfo(status,radioValue){
    const dist=status.distributed||{};
    if(radioValue==='musetalk'&&dist.enabled){
      const online=Number(dist.online_count||0);
      const registered=Number(dist.registered_count||(Array.isArray(dist.nodes)?dist.nodes.length:0)||0);
      if(registered>0||online>0){
        return {online:online>0,count:online,registered};
      }
    }
    const engine=radioValue==='musetalk'?'musetalk':'mock';
    const info=status.engines?.[engine]||{online:false,count:0};
    return {online:Boolean(info.online),count:Number(info.count||0),registered:Number(info.registered||info.count||0)};
  }

  function workerBadgeText(radioValue,info){
    if(radioValue==='musetalk'&&Number(info.registered||0)>0){
      return info.online
        ?`● Worker 在线 · ${info.count}/${info.registered} 台`
        :`○ Worker 未启动 · 已登记 ${info.registered} 台`;
    }
    return info.online?`● Worker 在线 · ${info.count}`:'○ Worker 未启动';
  }

  async function patchWorkerOptions(){
    if(checking||!token)return;
    const radios=[...document.querySelectorAll('input[name="studioEngine"]')];
    if(!radios.length)return;
    checking=true;
    try{
      const status=await api('/workers/status');
      for(const radio of radios){
        const info=engineInfo(status,radio.value);
        const option=radio.closest('.engine-option');
        if(!option)continue;
        let badge=option.querySelector('.worker-live-badge');
        if(!badge){
          badge=document.createElement('div');
          badge.className='worker-live-badge';
          option.appendChild(badge);
        }
        const badgeText=workerBadgeText(radio.value,info);
        const badgeStyle=`margin-top:7px;font-size:10px;color:${info.online?'#69ddb4':'#ff9d9d'}`;
        if(badge.textContent!==badgeText)badge.textContent=badgeText;
        if(badge.style.cssText!==badgeStyle)badge.style.cssText=badgeStyle;
        if(radio.disabled===info.online)radio.disabled=!info.online;
        const opacity=info.online?'1':'.55';
        if(option.style.opacity!==opacity)option.style.opacity=opacity;
        if(!info.online&&radio.checked){
          radio.checked=false;
          const fallback=radios.find(x=>!x.disabled);
          if(fallback){fallback.checked=true;fallback.dispatchEvent(new Event('change',{bubbles:true}))}
        }
      }
    }catch(_){
      // Status is advisory. A temporary lookup failure must not break the studio.
    }finally{checking=false}
  }

  document.addEventListener('click',event=>{
    const button=event.target.closest?.('#studioProduce');
    if(!button)return;
    const chosen=document.querySelector('input[name="studioEngine"]:checked');
    if(!chosen||chosen.disabled){
      event.preventDefault();
      event.stopImmediatePropagation();
      if(typeof toast==='function')toast('请先启动一个可用的生成 Worker');
    }
  },true);

  function patchNewWorkerPanel(){
    const radio=document.querySelector('input[name="studioEngine"]');
    if(!radio){mountedRadio=null;return}
    if(radio===mountedRadio)return;
    mountedRadio=radio;
    patchWorkerOptions();
  }

  const observer=new MutationObserver(()=>{
    patchNewWorkerPanel();
  });
  observer.observe(document.body,{childList:true,subtree:true});
  patchNewWorkerPanel();
  setInterval(()=>{
    if(!document.hidden&&document.querySelector('input[name="studioEngine"]'))patchWorkerOptions();
  },15000);
  document.addEventListener('visibilitychange',()=>{
    if(!document.hidden)patchNewWorkerPanel();
  });
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
