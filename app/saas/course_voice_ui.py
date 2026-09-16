from __future__ import annotations

from fastapi.responses import Response


CSS = r'''
.voice-package-panel{margin-top:14px;padding:15px 16px;border:1px solid rgba(151,176,214,.10);border-radius:14px;background:linear-gradient(180deg,rgba(11,18,27,.92),rgba(8,13,20,.92))}.voice-package-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}.voice-package-head b{font-size:12px}.voice-package-head small{display:block;color:#64758a;margin-top:2px}.voice-emotions{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.voice-emotion{border:1px solid rgba(151,176,214,.11);background:#0c121a;color:#8798aa;border-radius:10px;padding:9px 7px;text-align:center;font-size:10px;cursor:pointer}.voice-emotion.active{border-color:rgba(102,187,249,.48);background:#102033;color:#e1f3ff;box-shadow:0 0 0 2px rgba(93,179,244,.05)}.voice-speed-row{display:grid;grid-template-columns:90px 1fr 48px;gap:10px;align-items:center;margin-top:13px}.voice-speed-row label{font-size:10px;color:#728398}.voice-speed-row input{width:100%;accent-color:#64b8f5}.voice-speed-value{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#8dd7ff;text-align:right}.voice-package-note{margin-top:10px;font-size:9px;color:#56677b;line-height:1.6}@media(max-width:700px){.voice-emotions{grid-template-columns:1fr 1fr}}
'''


JS = r'''
(() => {
  let activeCourseId=null;
  let voiceState={speed:1.0,emotion:'professional',subtitle_mode:'burn'};
  const originalFetch=window.fetch.bind(window);
  const courseRe=/\/api\/saas\/courses(?:\/([^/?]+))?$/;

  function absorbSettings(settings){
    if(!settings||typeof settings!=='object')return;
    const speed=Number(settings.speed||1.0);voiceState.speed=Math.max(.75,Math.min(1.35,Number.isFinite(speed)?speed:1));
    voiceState.emotion=String(settings.emotion||'professional');
    voiceState.subtitle_mode=String(settings.subtitle_mode||'burn');
  }

  window.fetch=async function(input,init={}){
    const url=typeof input==='string'?input:(input?.url||'');const method=String(init.method||'GET').toUpperCase();const m=url.match(courseRe);
    let outgoing=init;
    if(m&&['POST','PATCH'].includes(method)&&typeof init.body==='string'){
      try{
        const body=JSON.parse(init.body);if(body.settings&&typeof body.settings==='object'){
          absorbSettings(body.settings);
          body.settings={...body.settings,speed:voiceState.speed,emotion:voiceState.emotion,subtitle_mode:voiceState.subtitle_mode};
          outgoing={...init,body:JSON.stringify(body)};
        }
        if(m[1])activeCourseId=m[1];
      }catch(_){}
    }
    const response=await originalFetch(input,outgoing);
    if(m&&response.ok){
      try{
        const data=await response.clone().json();
        if(method==='POST'&&data?.id)activeCourseId=data.id;
        if(data?.settings)absorbSettings(data.settings);
      }catch(_){}
    }
    return response;
  };

  function refreshControls(){
    document.querySelectorAll('[data-voice-emotion]').forEach(btn=>btn.classList.toggle('active',btn.dataset.voiceEmotion===voiceState.emotion));
    const range=document.getElementById('studioVoiceSpeed');if(range)range.value=String(voiceState.speed);
    const value=document.getElementById('studioVoiceSpeedValue');if(value)value.textContent=`${voiceState.speed.toFixed(2)}×`;
  }

  function mount(){
    const produce=document.getElementById('studioProduce');if(!produce||document.getElementById('studioVoicePackage'))return;
    const left=produce.closest('.package-grid')?.querySelector('section.studio-panel');if(!left)return;
    const readiness=left.querySelector('.readiness-list');
    const host=document.createElement('div');host.id='studioVoicePackage';host.className='voice-package-panel';host.innerHTML=`<div class="voice-package-head"><div><b>讲解声音</b><small>与本地生产版保持一致的语气与语速控制</small></div><span class="badge">CosyVoice</span></div><div class="voice-emotions"><button type="button" class="voice-emotion" data-voice-emotion="professional">标准专业</button><button type="button" class="voice-emotion" data-voice-emotion="passionate">激昂有力</button><button type="button" class="voice-emotion" data-voice-emotion="warm">亲切温和</button><button type="button" class="voice-emotion" data-voice-emotion="calm">从容淡雅</button></div><div class="voice-speed-row"><label for="studioVoiceSpeed">讲解语速</label><input id="studioVoiceSpeed" type="range" min="0.75" max="1.35" step="0.05"><span id="studioVoiceSpeedValue" class="voice-speed-value"></span></div><div class="voice-package-note">标准专业模式保持纯 zero-shot 克隆，不注入风格提示词；成片字幕默认采用画面硬字幕，避免播放器不显示软字幕。</div>`;
    if(readiness)left.insertBefore(host,readiness);else left.appendChild(host);
    host.querySelectorAll('[data-voice-emotion]').forEach(btn=>btn.onclick=()=>{voiceState.emotion=btn.dataset.voiceEmotion;refreshControls();const s=document.getElementById('studioSaveState');if(s)s.textContent='有未保存修改'});
    const range=host.querySelector('#studioVoiceSpeed');range.oninput=()=>{voiceState.speed=Number(range.value);refreshControls();const s=document.getElementById('studioSaveState');if(s)s.textContent='有未保存修改'};
    refreshControls();
  }

  const observer=new MutationObserver(()=>setTimeout(mount,0));observer.observe(document.body,{childList:true,subtree:true});
})();
'''


def css_response() -> Response:
    return Response(CSS, media_type="text/css; charset=utf-8")


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
