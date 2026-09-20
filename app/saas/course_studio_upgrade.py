from __future__ import annotations

from fastapi.responses import Response


CSS = r'''
/* Premium narration editor */
.script-editor.premium-narration{position:relative;overflow:hidden;padding:0!important;background:linear-gradient(155deg,rgba(18,25,35,.98),rgba(9,13,19,.98))!important;border-color:rgba(128,180,226,.18)!important;box-shadow:0 24px 70px rgba(0,0,0,.26),inset 0 1px 0 rgba(255,255,255,.025)!important}
.script-editor.premium-narration:before{content:"";position:absolute;inset:0 auto auto 0;width:100%;height:1px;background:linear-gradient(90deg,transparent,rgba(113,183,255,.7),rgba(114,230,255,.45),transparent)}
.premium-narration .narration-head{padding:22px 23px 16px;border-bottom:1px solid rgba(151,176,214,.09);background:linear-gradient(180deg,rgba(36,56,78,.18),transparent)}
.premium-narration .narration-kicker{display:flex;align-items:center;gap:8px;color:#75b8f0;font-size:10px;font-weight:760;letter-spacing:.16em;text-transform:uppercase}.premium-narration .narration-kicker:before{content:"";width:18px;height:1px;background:#72e6ff;box-shadow:0 0 12px rgba(114,230,255,.45)}
.premium-narration .narration-title-row{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-top:8px}.premium-narration .narration-title-row h2{font-size:21px;letter-spacing:-.025em;margin:0}.premium-narration .narration-status{font-size:10px;color:#6d7d91;white-space:nowrap}.premium-narration .narration-status:before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:#63d6ad;margin-right:6px;box-shadow:0 0 10px rgba(99,214,173,.4)}
.premium-narration .narration-surface{padding:18px 20px 16px;display:flex;flex:1;min-height:0;flex-direction:column}.premium-narration textarea{flex:1;min-height:390px!important;border:1px solid rgba(128,170,215,.10)!important;border-radius:15px!important;background:linear-gradient(180deg,rgba(5,9,14,.86),rgba(8,13,20,.96))!important;color:#edf5ff!important;padding:22px 22px!important;font-size:15px!important;line-height:1.9!important;letter-spacing:.012em;resize:none!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.02),0 16px 50px rgba(0,0,0,.13)!important}
.premium-narration textarea:focus{outline:none!important;border-color:rgba(113,183,255,.38)!important;box-shadow:0 0 0 3px rgba(113,183,255,.055),inset 0 1px 0 rgba(255,255,255,.025)!important}.premium-narration textarea::placeholder{color:#435164}
.premium-narration .script-stats{display:flex;gap:8px!important;margin:12px 0 0!important}.premium-narration .script-stats span{display:inline-flex;align-items:center;gap:6px;border:1px solid rgba(130,168,208,.10);background:#0c121a;border-radius:999px;padding:5px 10px;color:#8193a9!important;font-size:10px!important}.premium-narration .script-stats span:first-child:before{content:"Aa";font-size:9px;color:#6db8f2}.premium-narration .script-stats span:last-child:before{content:"◷";font-size:11px;color:#6db8f2}
.premium-narration .script-nav{padding:0 20px 18px;margin-top:14px!important}.premium-narration .script-nav button{min-width:112px}

/* Digital-human preview: always use the master video and keep the whole lecturer visible. */
#studioAvatarLayer{isolation:isolate}.layout-layer.avatar #studioAvatarMedia{position:absolute;inset:0;width:100%;height:100%;display:grid;place-items:center;overflow:hidden;background:transparent}.layout-layer.avatar #studioAvatarMedia>img,.layout-layer.avatar #studioAvatarMedia>video{display:block;width:100%!important;height:100%!important;max-width:none!important;max-height:none!important;object-fit:contain!important;object-position:center bottom!important;background:transparent!important}.layout-layer.avatar.full-avatar-preview #studioAvatarMedia>img,.layout-layer.avatar.full-avatar-preview #studioAvatarMedia>video{object-fit:contain!important;object-position:center center!important}.layout-layer.avatar .layout-label{z-index:7}.layout-layer.avatar .resize-dot{z-index:8}

/* Studio background catalog */
.layout-canvas.has-studio-background{background-position:center!important;background-size:cover!important;background-repeat:no-repeat!important}.studio-bg-specials{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:10px}.studio-bg-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;max-height:270px;overflow:auto;padding-right:2px}.studio-bg-card{position:relative;aspect-ratio:16/9;border:1px solid rgba(151,176,214,.12);border-radius:10px;overflow:hidden;background:#090e15 center/cover no-repeat;cursor:pointer;transition:border-color .16s,transform .16s,box-shadow .16s}.studio-bg-card:hover{transform:translateY(-1px);border-color:rgba(113,183,255,.35)}.studio-bg-card.active{border-color:#6bb8f8;box-shadow:0 0 0 2px rgba(107,184,248,.10),0 10px 30px rgba(0,0,0,.2)}.studio-bg-card:after{content:"";position:absolute;inset:48% 0 0;background:linear-gradient(transparent,rgba(2,5,9,.9))}.studio-bg-card span{position:absolute;z-index:2;left:8px;right:6px;bottom:6px;font-size:9px;color:#dcecff;font-weight:680;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.studio-bg-upload{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:10px;padding:10px 11px;border:1px dashed rgba(113,183,255,.24);border-radius:11px;background:rgba(74,139,205,.035);cursor:pointer}.studio-bg-upload:hover{border-color:rgba(113,183,255,.42);background:rgba(74,139,205,.06)}.studio-bg-upload b{font-size:11px}.studio-bg-upload small{display:block;color:#66778b;font-size:9px}.studio-bg-upload input{display:none}.studio-bg-current{margin-top:8px;color:#6f8299;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.studio-bg-mode.active{border-color:#5ca9ed!important;color:#e6f5ff!important;background:#102033!important}
'''


JS = r'''
(() => {
  const upgrade={courseId:null,avatarId:null,backgrounds:new Map(),themes:null,blobUrls:new Map(),scheduled:false};
  const nativeFetch=window.fetch.bind(window);
  const courseSaveRe=/\/api\/saas\/courses(?:\/([^/]+))?$/;

  function slideIndex(){const text=document.querySelector('#courseStudioPane .course-pane-head>.muted')?.textContent||'';const m=text.match(/第\s*(\d+)/);return Number(m?.[1]||1)}
  function totalSlides(){const text=document.querySelector('#courseStudioPane .course-pane-head>.muted')?.textContent||'';const m=text.match(/\/\s*(\d+)/);return Number(m?.[1]||document.querySelectorAll('[data-layout-slide]').length||1)}
  function mapKey(){return upgrade.courseId||'__new__'}
  function bgMap(){if(!upgrade.backgrounds.has(mapKey()))upgrade.backgrounds.set(mapKey(),new Map());return upgrade.backgrounds.get(mapKey())}
  function bgState(index=slideIndex()){return bgMap().get(Number(index))||{mode:'dark',custom_bg:null,background_asset_id:null,bg_blur:false}}
  function setBgState(index,state){bgMap().set(Number(index),{...state})}
  function cloneState(state){return JSON.parse(JSON.stringify(state))}

  function seed(course){
    upgrade.courseId=course?.id||null;upgrade.avatarId=course?.avatar_id||null;
    const map=new Map();
    (course?.script||[]).forEach((item,i)=>{
      const index=Number(item.index||i+1),custom=item.custom_bg||null,assetId=item.background_asset_id||null,blur=Boolean(item.bg_blur)||custom==='blur';
      let mode='dark',themeId=null;
      if(blur)mode='blur';else if(assetId)mode='asset';else if(custom&&String(custom).startsWith('builtin-'))mode='builtin';
      if(mode==='builtin')themeId=String(custom).replace(/^builtin-/,'').replace(/\.png$/,'');
      map.set(index,{mode,theme_id:themeId,custom_bg:custom,background_asset_id:assetId,bg_blur:blur});
    });
    upgrade.backgrounds.set(mapKey(),map);schedulePatch();
  }

  window.fetch=async function(input,init={}){
    const url=typeof input==='string'?input:(input?.url||'');const method=String(init.method||'GET').toUpperCase();const match=url.match(courseSaveRe);
    let bodyObj=null;
    if(match&&['POST','PATCH'].includes(method)&&typeof init.body==='string'){
      try{bodyObj=JSON.parse(init.body)}catch(_){}
      if(bodyObj){
        if(bodyObj.avatar_id)upgrade.avatarId=bodyObj.avatar_id;
        if(Array.isArray(bodyObj.script)){
          const map=bgMap();
          bodyObj.script=bodyObj.script.map((item,i)=>{const state=map.get(Number(item.index||i+1));return state?{...item,custom_bg:state.custom_bg||null,background_asset_id:state.background_asset_id||null,bg_blur:Boolean(state.bg_blur)}:item});
          init={...init,body:JSON.stringify(bodyObj)};
        }
      }
    }
    const response=await nativeFetch(input,init);
    if(match&&method==='POST'&&!match[1]&&response.ok){
      try{const data=await response.clone().json();if(data?.id){const old=upgrade.backgrounds.get('__new__');upgrade.courseId=data.id;if(old){upgrade.backgrounds.set(data.id,old);upgrade.backgrounds.delete('__new__')}}}catch(_){}
    }
    return response;
  };

  async function privateBlob(path,key){
    if(upgrade.blobUrls.has(key))return upgrade.blobUrls.get(key);
    const objectUrl=await assetMediaUrl(path);upgrade.blobUrls.set(key,objectUrl);return objectUrl;
  }
  async function themes(){if(!upgrade.themes)upgrade.themes=await api('/course-tools/backgrounds');return upgrade.themes}

  async function persistBackgrounds(){
    if(!upgrade.courseId)return;
    try{
      const course=await api('/courses/'+upgrade.courseId),map=bgMap();
      const script=(course.script||[]).map((item,i)=>{const state=map.get(Number(item.index||i+1));return state?{...item,custom_bg:state.custom_bg||null,background_asset_id:state.background_asset_id||null,bg_blur:Boolean(state.bg_blur)}:item});
      await api('/courses/'+upgrade.courseId,{method:'PATCH',body:{script}});
      const label=document.getElementById('studioSaveState');if(label)label.textContent='已保存';
    }catch(e){if(typeof toast==='function')toast(e.message)}
  }

  async function ensureAvatarPreview(){
    const host=document.getElementById('studioAvatarMedia'),layer=document.getElementById('studioAvatarLayer'),ppt=document.getElementById('studioPptLayer');if(!host||!layer)return;
    const isFull=ppt&&ppt.style.display==='none'&&parseFloat(layer.style.width||'0')>=99;layer.classList.toggle('full-avatar-preview',Boolean(isFull));
    const avatar=cache.avatars.find(a=>a.id===upgrade.avatarId);if(!avatar)return;
    const videoId=avatar.master_video_asset_id, imageId=avatar.image_asset_id||avatar.image?.id;
    const mediaKey=videoId?'video:'+videoId:imageId?'image:'+imageId:'';if(!mediaKey||host.dataset.upgradeMedia===mediaKey)return;
    try{
      if(videoId){
        const v=document.createElement('video');v.muted=true;v.loop=true;v.autoplay=true;v.playsInline=true;v.preload='metadata';v.src=await privateBlob('/assets/'+videoId+'/download',mediaKey);host.replaceChildren(v);v.play().catch(()=>{});
      }else if(imageId){
        const img=document.createElement('img');img.src=await privateBlob('/assets/'+imageId+'/download',mediaKey);host.replaceChildren(img);
      }
      host.dataset.upgradeMedia=mediaKey;
    }catch(_){}
  }

  function patchNarration(){
    const editor=document.querySelector('#courseStudioPane .script-editor');if(!editor||editor.dataset.premiumNarration)return;editor.dataset.premiumNarration='1';editor.classList.add('premium-narration');
    const eyebrow=editor.querySelector('.eyebrow'),title=editor.querySelector('h2'),ta=editor.querySelector('#studioNarration'),stats=editor.querySelector('.script-stats'),nav=editor.querySelector('.script-nav');if(!ta)return;
    const head=document.createElement('div');head.className='narration-head';head.innerHTML=`<div class="narration-kicker">VOICE SCRIPT</div><div class="narration-title-row"><h2>本页讲解词</h2><span class="narration-status">草稿自动保存</span></div>`;
    eyebrow?.remove();title?.remove();editor.insertBefore(head,ta);const surface=document.createElement('div');surface.className='narration-surface';editor.insertBefore(surface,ta);surface.appendChild(ta);if(stats)surface.appendChild(stats);if(nav)editor.appendChild(nav);
  }

  async function applyBackgroundPreview(){
    const canvas=document.getElementById('studioLayoutCanvas');if(!canvas)return;const state=bgState(),pptImg=document.getElementById('studioCanvasPpt');
    canvas.classList.remove('has-studio-background');canvas.style.backgroundImage='';
    if(state.mode==='blur'){
      canvas.classList.add('blur-bg');canvas.classList.remove('dark-bg');if(pptImg?.src)canvas.style.setProperty('--slide-bg',`url(${pptImg.src})`);return;
    }
    canvas.classList.remove('blur-bg');
    if(state.mode==='dark'){canvas.classList.add('dark-bg');return}
    canvas.classList.remove('dark-bg');
    try{
      let url='';
      if(state.mode==='asset'&&state.background_asset_id)url=await privateBlob('/assets/'+state.background_asset_id+'/download','bg-asset:'+state.background_asset_id);
      else if(state.mode==='builtin'){
        const theme=(await themes()).find(t=>t.id===state.theme_id||t.filename===state.custom_bg);if(theme)url=await privateBlob(theme.preview_url,'bg-theme:'+theme.id);
      }
      if(url){canvas.style.backgroundImage=`url(${url})`;canvas.classList.add('has-studio-background')}
    }catch(_){}
  }

  function setActiveBackgroundControls(){
    const state=bgState();document.querySelectorAll('[data-upgrade-bg-mode]').forEach(x=>x.classList.toggle('active',x.dataset.upgradeBgMode===state.mode));document.querySelectorAll('[data-upgrade-bg-theme]').forEach(x=>x.classList.toggle('active',state.mode==='builtin'&&(x.dataset.upgradeBgTheme===state.theme_id||x.dataset.filename===state.custom_bg)));document.querySelectorAll('[data-upgrade-bg-asset]').forEach(x=>x.classList.toggle('active',state.mode==='asset'&&x.dataset.upgradeBgAsset===state.background_asset_id));
    const current=document.getElementById('studioBgCurrent');if(current){if(state.mode==='dark')current.textContent='当前：深色科技背景';else if(state.mode==='blur')current.textContent='当前：PPT 模糊延展';else if(state.mode==='builtin')current.textContent='当前：'+(document.querySelector('[data-upgrade-bg-theme].active span')?.textContent||'内置背景');else{const a=cache.assets.find(x=>x.id===state.background_asset_id);current.textContent='当前：'+(a?.name||'自定义背景')}}
  }

  async function chooseBackground(state){setBgState(slideIndex(),state);await applyBackgroundPreview();setActiveBackgroundControls();await persistBackgrounds()}

  async function patchBackgroundPanel(){
    const select=document.getElementById('studioBgMode');if(!select)return;const section=select.closest('.layout-section');if(!section)return;const page=slideIndex(),marker=mapKey()+':'+page;
    if(section.dataset.upgradeBg===marker){applyBackgroundPreview();setActiveBackgroundControls();return}
    section.dataset.upgradeBg=marker;const catalog=await themes();
    section.innerHTML=`<h3>演播厅背景</h3><div class="studio-bg-specials"><button class="layout-chip studio-bg-mode" data-upgrade-bg-mode="dark">深色科技</button><button class="layout-chip studio-bg-mode" data-upgrade-bg-mode="blur">PPT 模糊延展</button></div><div class="studio-bg-grid">${catalog.map(t=>`<button type="button" class="studio-bg-card" data-upgrade-bg-theme="${t.id}" data-filename="${t.filename}" id="studioBgTheme-${t.id}"><span>${t.name}</span></button>`).join('')}</div><label class="studio-bg-upload"><div><b>上传自定义背景</b><small>PNG / JPG / WEBP，自动作为工作区私有素材保存</small></div><span>选择图片</span><input id="studioCustomBgFile" type="file" accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"></label><div class="studio-bg-current" id="studioBgCurrent"></div>`;
    for(const t of catalog){try{document.getElementById('studioBgTheme-'+t.id).style.backgroundImage=`url(${await privateBlob(t.preview_url,'bg-theme:'+t.id)})`}catch(_){}}
    const ownedBackgrounds=(cache.assets||[]).filter(a=>a.kind==='background');
    if(ownedBackgrounds.length){
      const heading=document.createElement('h3');heading.textContent='工作区背景（含已导入的平台素材）';
      const grid=document.createElement('div');grid.className='studio-bg-grid';
      for(const asset of ownedBackgrounds){
        const button=document.createElement('button');button.type='button';button.className='studio-bg-card';
        button.dataset.upgradeBgAsset=asset.id;
        const label=document.createElement('span');label.textContent=asset.name;button.appendChild(label);
        button.onclick=()=>{const ext=(asset.name.match(/\.[^.]+$/)||['.png'])[0].toLowerCase();chooseBackground({mode:'asset',custom_bg:`asset-${asset.id}${ext}`,background_asset_id:asset.id,bg_blur:false})};
        grid.appendChild(button);
        try{button.style.backgroundImage=`url(${await privateBlob('/assets/'+asset.id+'/download','bg-asset:'+asset.id)})`}catch(_){}
      }
      const upload=section.querySelector('.studio-bg-upload');section.insertBefore(heading,upload);section.insertBefore(grid,upload);
    }
    section.querySelector('[data-upgrade-bg-mode="dark"]').onclick=()=>chooseBackground({mode:'dark',custom_bg:null,background_asset_id:null,bg_blur:false});
    section.querySelector('[data-upgrade-bg-mode="blur"]').onclick=()=>chooseBackground({mode:'blur',custom_bg:'blur',background_asset_id:null,bg_blur:true});
    section.querySelectorAll('[data-upgrade-bg-theme]').forEach(btn=>btn.onclick=()=>chooseBackground({mode:'builtin',theme_id:btn.dataset.upgradeBgTheme,custom_bg:btn.dataset.filename,background_asset_id:null,bg_blur:false}));
    document.getElementById('studioCustomBgFile').onchange=async e=>{
      const file=e.target.files?.[0];if(!file)return;try{const fd=new FormData();fd.append('file',file);fd.append('kind','background');const asset=await api('/assets',{method:'POST',body:fd});await loadLookups();const ext=(asset.name.match(/\.[^.]+$/)||['.png'])[0].toLowerCase();await chooseBackground({mode:'asset',custom_bg:`asset-${asset.id}${ext}`,background_asset_id:asset.id,bg_blur:false});if(typeof toast==='function')toast('背景已上传并应用到当前页面')}catch(err){if(typeof toast==='function')toast(err.message)}finally{e.target.value=''}
    };
    const applyAll=document.getElementById('applyAllLayout');if(applyAll&&!applyAll.dataset.upgradeBgAll){applyAll.dataset.upgradeBgAll='1';applyAll.addEventListener('click',()=>{const state=cloneState(bgState());for(let i=1;i<=totalSlides();i++)setBgState(i,state);persistBackgrounds()})}
    setActiveBackgroundControls();applyBackgroundPreview();
  }

  function patchStep1(){const select=document.getElementById('studioAvatarSelect');if(select&&!select.dataset.upgradeWatch){select.dataset.upgradeWatch='1';select.addEventListener('change',()=>{upgrade.avatarId=select.value})}}
  async function patchStudio(){if(!document.getElementById('courseStudioShell'))return;patchStep1();patchNarration();await patchBackgroundPanel();await ensureAvatarPreview();setTimeout(()=>{applyBackgroundPreview();ensureAvatarPreview()},180)}
  function schedulePatch(){if(upgrade.scheduled)return;upgrade.scheduled=true;requestAnimationFrame(()=>{upgrade.scheduled=false;patchStudio().catch(()=>{})})}
  new MutationObserver(schedulePatch).observe(document.body,{childList:true,subtree:true});

  const baseCourseModal=window.courseModal;
  window.courseModal=function(course=null){seed(course);return baseCourseModal(course)};
  const baseRenderModal=window.renderModal;
  window.renderModal=async function(id){try{seed(await api('/courses/'+id))}catch(_){upgrade.courseId=id}return baseRenderModal(id)};
  const baseOpen=window.openCourseStudio;
  if(baseOpen)window.openCourseStudio=function(course,forcedStep){seed(course);return baseOpen(course,forcedStep)};
  schedulePatch();
})();
'''


def css_response() -> Response:
    return Response(CSS, media_type="text/css; charset=utf-8")


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
