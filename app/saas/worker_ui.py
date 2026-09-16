from __future__ import annotations

from fastapi.responses import Response


JS = r'''
(() => {
  let checking=false;

  async function patchWorkerOptions(){
    if(checking||!token)return;
    const radios=[...document.querySelectorAll('input[name="studioEngine"]')];
    if(!radios.length)return;
    checking=true;
    try{
      const status=await api('/workers/status');
      for(const radio of radios){
        const engine=radio.value==='musetalk'?'musetalk':'mock';
        const info=status.engines?.[engine]||{online:false,count:0};
        const option=radio.closest('.engine-option');
        if(!option)continue;
        let badge=option.querySelector('.worker-live-badge');
        if(!badge){
          badge=document.createElement('div');
          badge.className='worker-live-badge';
          option.appendChild(badge);
        }
        badge.textContent=info.online?`● Worker 在线 · ${info.count}`:'○ Worker 未启动';
        badge.style.cssText=`margin-top:7px;font-size:10px;color:${info.online?'#69ddb4':'#ff9d9d'}`;
        radio.disabled=!info.online;
        option.style.opacity=info.online?'1':'.55';
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

  const observer=new MutationObserver(()=>{
    if(document.querySelector('input[name="studioEngine"]'))setTimeout(patchWorkerOptions,0);
  });
  observer.observe(document.body,{childList:true,subtree:true});
  setInterval(()=>{if(document.querySelector('input[name="studioEngine"]'))patchWorkerOptions()},5000);
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
