from __future__ import annotations

from fastapi.responses import Response


JS = r'''
(() => {
  if (typeof titles !== 'undefined') {
    titles.dashboard=['创作总览','数字人课程生产与运营状态'];
    titles.courses=['课程工作室','PPT 解析、逐页讲稿与数字人生成'];
    titles.avatars=['数字人资产','人物、母版视频、克隆声音与授权'];
    titles.assets=['素材中心','课件、媒体素材与成片归档'];
    titles.jobs=['生成任务','异步队列、进度与交付结果'];
    titles.billing=['套餐与额度','生成分钟、存储与团队容量'];
    titles.settings=['工作区设置','账号、成员与授权记录'];
    titles.admin=['运营控制台','平台运营、合规与审计'];
  }
  const hero=document.querySelector('.hero');
  if(hero){
    const h=hero.querySelector('h1');if(h)h.innerHTML='AI 数字人课程<br>创作工作室';
    const ps=hero.querySelectorAll('p');if(ps[0])ps[0].textContent='把课件、讲稿、数字人和声音组织成一条专业的内容生产链。';if(ps[1])ps[1].textContent='多租户 SaaS · 异步生成 · 私有素材 · AI 内容标识';
  }

  async function previewOutput(assetId,title){
    try{
      const r=await fetch(API+'/assets/'+assetId+'/download',{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('成片预览失败');
      const url=URL.createObjectURL(await r.blob());
      openModal(`<div class="modal-head"><div><div class="eyebrow">OUTPUT PREVIEW</div><h2>${esc(title||'成片预览')}</h2></div><button class="iconbtn" data-close>×</button></div><video src="${url}" controls autoplay style="width:100%;max-height:70vh;background:#000;border-radius:14px"></video>`);
      $('modalRoot').querySelector('[data-close]').onclick=()=>{URL.revokeObjectURL(url);closeModal()};
    }catch(e){toast(e.message)}
  }

  const baseCourses=renderCourses;
  renderCourses=async function(){
    await baseCourses();
    document.querySelectorAll('[data-course-download]').forEach(b=>{
      if(b.parentElement.querySelector('[data-course-preview]'))return;
      const p=document.createElement('button');p.className='secondary';p.textContent='预览';p.dataset.coursePreview=b.dataset.courseDownload;
      p.onclick=()=>previewOutput(p.dataset.coursePreview,b.dataset.name?.replace(/\.mp4$/,'')||'成片预览');b.before(p);
    });
  };

  const baseAvatars=renderAvatars;
  renderAvatars=async function(){
    await baseAvatars();
    document.querySelectorAll('[data-dh-preview-audio]').forEach(b=>b.textContent='试听参考录音');
  };

  const baseAdmin=renderAdmin;
  renderAdmin=async function(){
    await baseAdmin();
    if(!me?.user?.is_superuser)return;
    try{
      const [users,audits]=await Promise.all([api('/admin/users'),api('/admin/audit?limit=80')]);
      $('page').insertAdjacentHTML('beforeend',`<div class="split" style="margin-top:16px"><div class="card"><div class="toolbar"><div><h2>用户管理</h2><div class="muted">账号启用状态与平台管理员标识</div></div></div><div class="table-wrap"><table class="table"><tbody>${users.slice(0,40).map(u=>`<tr><td><b>${esc(u.display_name)}</b><div class="muted">${esc(u.email)}</div></td><td>${u.is_superuser?'<span class="badge running">平台管理员</span>':''}</td><td><span class="badge ${u.is_active?'active':'failed'}">${u.is_active?'启用':'停用'}</span></td><td>${!u.is_superuser?`<button class="secondary" data-user-toggle="${u.id}" data-active="${u.is_active?'1':'0'}">${u.is_active?'停用':'启用'}</button>`:''}</td></tr>`).join('')}</tbody></table></div></div><div class="card"><div class="toolbar"><div><h2>最近审计</h2><div class="muted">关键操作追踪</div></div></div><div class="table-wrap"><table class="table"><tbody>${audits.slice(0,40).map(a=>`<tr><td><b>${esc(a.action)}</b><div class="code">${esc((a.target_type||'')+' '+(a.target_id||'').slice(0,8))}</div></td><td>${fmtDateLocal(a.created_at)}</td></tr>`).join('')}</tbody></table></div></div></div>`);
      document.querySelectorAll('[data-user-toggle]').forEach(b=>b.onclick=async()=>{try{const next=b.dataset.active!=='1';await api('/admin/users/'+b.dataset.userToggle,{method:'PATCH',body:{is_active:next}});renderAdmin()}catch(e){toast(e.message)}});
    }catch(e){toast('运营附加数据加载失败：'+e.message)}
  };
  function fmtDateLocal(v){try{return new Date(v).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}catch(_){return '—'}}
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
