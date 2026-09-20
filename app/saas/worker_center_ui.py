from __future__ import annotations

from fastapi.responses import Response


JS = r'''
(() => {
  const style=document.createElement('style');
  style.textContent=`
    .worker-kpis{grid-template-columns:repeat(6,minmax(120px,1fr))}
    .worker-layout{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(300px,.45fr);gap:16px}
    .worker-name{font-weight:780;color:#eef6ff}
    .worker-sub{font-size:11px;color:var(--muted);margin-top:3px}
    .worker-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;vertical-align:1px;background:#667085}
    .worker-dot.online,.worker-dot.busy{background:#63d6ad;box-shadow:0 0 10px rgba(99,214,173,.45)}
    .worker-dot.draining,.worker-dot.disk_low{background:#efc06e;box-shadow:0 0 10px rgba(239,192,110,.35)}
    .worker-dot.offline,.worker-dot.revoked,.worker-dot.incompatible{background:#ff738c}
    .worker-dot.pending{background:#71b7ff}
    .worker-status{display:inline-flex;align-items:center;padding:4px 9px;border-radius:999px;border:1px solid rgba(255,255,255,.06);font-size:11px;font-weight:720;background:#171f2a;color:#a9b5c6}
    .worker-capabilities{display:flex;gap:5px;flex-wrap:wrap;max-width:330px}
    .worker-chip{padding:3px 7px;border-radius:999px;background:rgba(113,183,255,.07);border:1px solid rgba(113,183,255,.12);color:#9ecfff;font-size:10px}
    .worker-health{display:grid;gap:5px;min-width:170px}
    .worker-health-line{display:flex;justify-content:space-between;gap:12px;color:#c6d2e3;font-size:11px}
    .worker-health-line span:first-child{color:var(--muted)}
    .worker-warning{padding:10px 12px;border-radius:11px;background:rgba(239,192,110,.07);border:1px solid rgba(239,192,110,.16);color:#efcf8f;font-size:12px}
    .worker-error{padding:10px 12px;border-radius:11px;background:rgba(255,115,140,.07);border:1px solid rgba(255,115,140,.14);color:#ff9aae;white-space:pre-wrap;word-break:break-word}
    .worker-detail-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}
    .worker-detail-grid .ops-mini{min-width:0}
    .worker-detail-section{margin-top:18px}
    .worker-section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px}
    .worker-version-ok{color:#63d6ad}.worker-version-bad{color:#efc06e}
    .worker-empty-mini{padding:18px;color:var(--muted);border:1px dashed rgba(151,176,214,.14);border-radius:12px;text-align:center}
    @media(max-width:1200px){.worker-kpis{grid-template-columns:repeat(3,1fr)}.worker-layout{grid-template-columns:1fr}}
    @media(max-width:760px){.worker-kpis,.worker-detail-grid{grid-template-columns:1fr 1fr}}
  `;
  document.head.appendChild(style);

  const statusLabels={
    online:'空闲',busy:'工作中',draining:'排空中',offline:'离线',pending:'等待注册',
    disk_low:'磁盘不足',incompatible:'版本不兼容',revoked:'已吊销'
  };

  const fmtBytes=value=>{
    const n=Number(value||0);
    if(!n)return '—';
    if(n>=1024**3)return (n/1024**3).toFixed(1)+' GB';
    if(n>=1024**2)return (n/1024**2).toFixed(1)+' MB';
    return Math.round(n/1024)+' KB';
  };
  const fmtMemory=value=>value==null?'—':(Number(value)>=1024?(Number(value)/1024).toFixed(1)+' GB':Number(value)+' MB');
  const fmtTime=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'—';
  const fmtAgo=value=>{
    if(value==null)return '从未连接';
    const s=Math.max(0,Number(value));
    if(s<10)return '刚刚';
    if(s<60)return Math.round(s)+' 秒前';
    if(s<3600)return Math.round(s/60)+' 分钟前';
    return Math.round(s/3600)+' 小时前';
  };
  const statusHtml=w=>`<span class="worker-status"><i class="worker-dot ${esc(w.effective_status||w.status||'offline')}"></i>${esc(statusLabels[w.effective_status]||w.effective_status||w.status||'—')}</span>`;
  const capsHtml=w=>{
    const caps=Array.isArray(w.capabilities)?w.capabilities:[];
    return caps.length?`<div class="worker-capabilities">${caps.slice(0,6).map(x=>`<span class="worker-chip">${esc(x)}</span>`).join('')}${caps.length>6?`<span class="worker-chip">+${caps.length-6}</span>`:''}</div>`:'<span class="muted">尚未上报</span>';
  };

  function syncWorkerNav(){
    const admin=document.getElementById('adminNav');
    if(!admin)return;
    let nav=document.getElementById('workerCenterNav');
    if(!nav){
      nav=document.createElement('button');
      nav.id='workerCenterNav';
      nav.dataset.page='workers';
      nav.className='hidden';
      nav.innerHTML='<svg viewBox="0 0 24 24" fill="none"><rect x="4" y="5" width="16" height="5" rx="1.5" stroke="currentColor" stroke-width="1.6"/><rect x="4" y="14" width="16" height="5" rx="1.5" stroke="currentColor" stroke-width="1.6"/><circle cx="8" cy="7.5" r="1" fill="currentColor"/><circle cx="8" cy="16.5" r="1" fill="currentColor"/></svg><span>算力</span>';
      admin.insertAdjacentElement('beforebegin',nav);
    }
    nav.classList.toggle('hidden',!me?.user?.is_superuser);
  }

  const chromeObserver=new MutationObserver(syncWorkerNav);
  const adminNav=document.getElementById('adminNav');
  if(adminNav)chromeObserver.observe(adminNav,{attributes:true,attributeFilter:['class']});
  syncWorkerNav();

  if(typeof titles!=='undefined')titles.workers=['算力中心','Worker 节点、运行状态、资源与任务追踪'];

  const baseShowPage=showPage;
  showPage=async function(name){
    if(name!=='workers')return baseShowPage(name);
    current=name;
    syncWorkerNav();
    document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.page===name));
    $('pageTitle').textContent='算力中心';
    $('pageSubtitle').textContent='Worker 节点、运行状态、资源与任务追踪';
    $('page').innerHTML='<div class="card">加载中…</div>';
    if(!me?.user?.is_superuser){$('page').innerHTML='<div class="empty">无平台算力管理权限</div>';return}
    try{await renderWorkerCenter()}catch(e){$('page').innerHTML='<div class="card">'+esc(e.message)+'</div>'}
  };

  function workerRows(items,contractVersion){
    if(!items.length)return '<tr><td colspan="7" class="muted">暂无 Worker。点击右上角“新增 Worker”生成注册码。</td></tr>';
    return items.map(w=>{
      const mismatch=w.render_contract_version&&contractVersion&&w.render_contract_version!==contractVersion;
      const canToggle=!['revoked','pending','incompatible'].includes(w.effective_status);
      const canRevoke=w.effective_status!=='revoked'&&!w.slots_busy;
      return `<tr>
        <td><div class="worker-name">${esc(w.name)}</div><div class="worker-sub">${esc(w.host||'未连接')} · <span class="code">${w.id.slice(0,10)}</span></div></td>
        <td>${statusHtml(w)}<div class="worker-sub">${w.slots_busy||0} / ${w.slots_total||1} 槽位 · ${fmtAgo(w.heartbeat_age_seconds)}</div></td>
        <td>${capsHtml(w)}</td>
        <td><div class="worker-health"><div class="worker-health-line"><span>可用内存</span><b>${fmtMemory(w.memory_available_mb)}</b></div><div class="worker-health-line"><span>磁盘可用</span><b>${fmtBytes(w.disk_free_bytes)}</b></div></div></td>
        <td><div class="${mismatch?'worker-version-bad':'worker-version-ok'}">${esc(w.code_version||'—')}</div><div class="worker-sub">${esc(w.model_version||'')}</div>${mismatch?'<div class="worker-sub worker-version-bad">Contract 不一致</div>':''}</td>
        <td>${w.current_task_id?`<span class="code">${esc(w.current_task_id.slice(0,12))}</span>`:'<span class="muted">—</span>'}</td>
        <td><div class="actions">
          <button class="secondary" data-worker-detail="${w.id}">详情</button>
          ${canToggle?`<button class="secondary" data-worker-toggle="${w.id}" data-accepting="${w.accepting_tasks?'1':'0'}">${w.accepting_tasks?'停止接新任务':'恢复接任务'}</button>`:''}
          ${canRevoke?`<button class="danger" data-worker-revoke="${w.id}">吊销</button>`:''}
        </div></td>
      </tr>`;
    }).join('');
  }

  async function renderWorkerCenter(){
    const data=await api('/admin/workers/overview');
    const s=data.summary||{};
    const workers=data.workers||[];
    $('page').innerHTML=`
      <div class="section-title"><div><h2>Worker 控制中心</h2><p>统一管理本地、局域网和远程算力节点；查看在线、任务、资源和版本状态</p></div><button class="primary" id="workerAdd">+ 新增 Worker</button></div>
      <div class="grid stats worker-kpis">
        <div class="stat"><div class="muted">Worker 总数</div><div class="num">${s.total||0}</div><div class="worker-sub">在线 ${s.online||0}</div></div>
        <div class="stat"><div class="muted">工作中</div><div class="num">${s.busy||0}</div><div class="worker-sub">运行尝试 ${s.running_attempts||0}</div></div>
        <div class="stat"><div class="muted">排空 / 告警</div><div class="num">${(s.draining||0)+(s.warning||0)}</div><div class="worker-sub">Drain ${s.draining||0} · 告警 ${s.warning||0}</div></div>
        <div class="stat"><div class="muted">离线</div><div class="num">${s.offline||0}</div><div class="worker-sub">待注册 ${s.pending||0}</div></div>
        <div class="stat"><div class="muted">槽位占用</div><div class="num">${s.slots_busy||0}/${s.slots_total||0}</div><div class="worker-sub">队列 ${s.queued_tasks||0} 个分页任务</div></div>
        <div class="stat"><div class="muted">24h 完成 / 失败</div><div class="num" style="font-size:25px">${s.completed_24h||0} / ${s.failed_24h||0}</div><div class="worker-sub">Render Attempts</div></div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="toolbar"><div><h2>Worker 节点</h2><div class="muted">心跳超过控制面在线窗口后自动显示为离线；停止接新任务会进入 Drain</div></div><div class="code">Contract ${esc(data.render_contract_version||'—')}</div></div>
        <div class="table-wrap"><table class="table"><thead><tr><th>节点</th><th>状态 / 槽位</th><th>能力</th><th>资源</th><th>版本</th><th>当前任务</th><th>操作</th></tr></thead><tbody>${workerRows(workers,data.render_contract_version)}</tbody></table></div>
      </div>
      <div class="split" style="margin-top:16px">
        <div class="card"><h2>调度规则</h2><div class="muted">仅在线、兼容、允许接任务且有空闲槽位的 Worker 才会参与 claim。Worker 仍按已有 lease / heartbeat 机制工作，本页面只提供控制与可观测能力。</div></div>
        <div class="card"><h2>维护建议</h2><div class="muted">维护节点时优先使用“停止接新任务”，等待当前槽位清空后再停机；“吊销”仅用于永久废弃或凭据泄露的节点。</div></div>
      </div>
    `;
    $('workerAdd').onclick=()=>{
      if(typeof workerEnrollmentModal==='function')workerEnrollmentModal();
      else toast('Worker 注册功能未加载');
    };
    document.querySelectorAll('[data-worker-detail]').forEach(b=>b.onclick=()=>openWorkerDetail(b.dataset.workerDetail,data.render_contract_version));
    document.querySelectorAll('[data-worker-toggle]').forEach(b=>b.onclick=async()=>{
      try{
        await api('/distributed/workers/'+b.dataset.workerToggle+'/accepting',{method:'PATCH',body:{accepting_tasks:b.dataset.accepting!=='1'}});
        toast(b.dataset.accepting==='1'?'节点已停止接收新任务':'节点已恢复接收任务');
        await renderWorkerCenter();
      }catch(e){toast(e.message)}
    });
    document.querySelectorAll('[data-worker-revoke]').forEach(b=>b.onclick=async()=>{
      if(!confirm('吊销后该 Worker 的现有凭据立即失效，且不能继续接任务。确定继续？'))return;
      try{await api('/distributed/workers/'+b.dataset.workerRevoke+'/revoke',{method:'POST'});toast('Worker 已吊销');await renderWorkerCenter()}catch(e){toast(e.message)}
    });
  }

  function attemptRows(items){
    if(!items.length)return '<tr><td colspan="7" class="muted">暂无任务记录</td></tr>';
    return items.map(x=>`<tr>
      <td><span class="code">${esc((x.task?.parent_job_id||'').slice(0,10))}</span><div class="worker-sub">Attempt #${x.attempt_no}</div></td>
      <td>${x.task?.slide_index?('第 '+x.task.slide_index+' 页'):esc(x.task?.task_type||'—')}</td>
      <td><span class="badge ${esc(x.status||'')}">${esc(x.status||'—')}</span><div class="worker-sub">${esc(x.stage||'')}</div></td>
      <td>${x.progress||0}%</td>
      <td>${x.duration_seconds==null?'—':x.duration_seconds+'s'}</td>
      <td>${fmtTime(x.claimed_at)}</td>
      <td>${x.error?`<span style="color:#ff8ca0">${esc(String(x.error).slice(0,80))}</span>`:'—'}</td>
    </tr>`).join('');
  }

  async function openWorkerDetail(id,contractVersion){
    try{
      const d=await api('/admin/workers/'+id),w=d.worker||{},sum=d.summary||{},aux=d.active_auxiliary_tasks||[];
      const mismatch=w.render_contract_version&&contractVersion&&w.render_contract_version!==contractVersion;
      openModal(`<div class="modal-head"><div><div class="eyebrow">WORKER NODE</div><h2 style="margin:3px 0 0">${esc(w.name||'Worker')}</h2><div class="muted">${esc(w.host||'未连接')} · <span class="code">${esc(w.id||'')}</span></div></div><button class="iconbtn" data-close>×</button></div>
        <div class="worker-detail-grid">
          <div class="ops-mini"><span class="muted">当前状态</span><b style="font-size:16px">${statusHtml(w)}</b><small>${fmtAgo(w.heartbeat_age_seconds)}</small></div>
          <div class="ops-mini"><span class="muted">并发槽位</span><b>${w.slots_busy||0} / ${w.slots_total||1}</b><small>${w.accepting_tasks?'允许接新任务':'已停止接新任务'}</small></div>
          <div class="ops-mini"><span class="muted">最近成功率</span><b>${sum.success_rate||0}%</b><small>${sum.recent_succeeded||0} 成功 / ${sum.recent_failed||0} 失败</small></div>
          <div class="ops-mini"><span class="muted">平均成功耗时</span><b>${sum.average_success_seconds==null?'—':sum.average_success_seconds+'s'}</b><small>最近 50 次尝试</small></div>
        </div>
        <div class="worker-layout">
          <div>
            <div class="worker-detail-section"><div class="worker-section-head"><div><h3 style="margin:0">运行信息</h3><div class="muted">Worker 最近一次注册与心跳上报</div></div></div>
              <div class="table-wrap"><table class="table"><tbody>
                <tr><td class="muted">平台</td><td>${esc(w.platform||'—')}</td><td class="muted">架构</td><td>${esc(w.machine||'—')}</td></tr>
                <tr><td class="muted">可用内存</td><td>${fmtMemory(w.memory_available_mb)}</td><td class="muted">磁盘可用</td><td>${fmtBytes(w.disk_free_bytes)}</td></tr>
                <tr><td class="muted">代码版本</td><td>${esc(w.code_version||'—')}</td><td class="muted">模型版本</td><td>${esc(w.model_version||'—')}</td></tr>
                <tr><td class="muted">Render Contract</td><td colspan="3" class="${mismatch?'worker-version-bad':'worker-version-ok'}">${esc(w.render_contract_version||'—')}${mismatch?' · 与控制面不一致':''}</td></tr>
                <tr><td class="muted">最近心跳</td><td>${fmtTime(w.last_seen_at)}</td><td class="muted">当前任务</td><td class="code">${esc(w.current_task_id||'—')}</td></tr>
              </tbody></table></div>
            </div>
            <div class="worker-detail-section"><h3>最近任务</h3><div class="table-wrap"><table class="table"><thead><tr><th>父任务</th><th>页/类型</th><th>状态</th><th>进度</th><th>耗时</th><th>开始</th><th>错误</th></tr></thead><tbody>${attemptRows(d.recent_attempts||[])}</tbody></table></div></div>
          </div>
          <div>
            <div class="worker-detail-section"><h3>能力标签</h3>${capsHtml(w)}</div>
            <div class="worker-detail-section"><h3>版本明细</h3><div class="table-wrap"><table class="table"><tbody>${Object.entries(w.versions||{}).map(([k,v])=>`<tr><td class="muted">${esc(k)}</td><td class="code">${esc(v)}</td></tr>`).join('')||'<tr><td class="muted">暂无版本明细</td></tr>'}</tbody></table></div></div>
            <div class="worker-detail-section"><h3>辅助任务</h3>${aux.length?aux.map(x=>`<div class="ops-mini" style="margin-bottom:8px"><span class="muted">${esc(x.kind)}</span><b style="font-size:13px" class="code">${esc(x.job_id.slice(0,12))}</b><small>Lease 至 ${fmtTime(x.expires_at)}</small></div>`).join(''):'<div class="worker-empty-mini">当前无辅助任务</div>'}</div>
            ${w.last_error?`<div class="worker-detail-section"><h3>最近错误</h3><div class="worker-error">${esc(w.last_error)}</div></div>`:''}
          </div>
        </div>`);
      const modal=$('modalRoot').querySelector('.modal');if(modal)modal.style.width='min(1180px,100%)';
      $('modalRoot').querySelectorAll('[data-close]').forEach(b=>b.onclick=closeModal);
    }catch(e){toast(e.message)}
  }

  setInterval(()=>{
    if(typeof current!=='undefined'&&current==='workers'&&!document.querySelector('#modalRoot .modal-backdrop')){
      renderWorkerCenter().catch(()=>{});
    }
  },8000);
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
