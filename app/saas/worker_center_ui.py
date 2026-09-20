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
    .worker-group-chip{padding:3px 7px;border-radius:8px;background:rgba(99,214,173,.07);border:1px solid rgba(99,214,173,.12);color:#8ee0bf;font-size:10px}
    .worker-health{display:grid;gap:5px;min-width:175px}
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
    .worker-filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
    .worker-filters input,.worker-filters select{border:1px solid var(--line);background:#0a0e14;color:#eef5ff;padding:9px 11px;border-radius:10px}
    .worker-filters input{min-width:220px}
    .worker-meter{height:5px;background:#1d2735;border-radius:999px;overflow:hidden;margin-top:3px}
    .worker-meter>i{display:block;height:100%;background:currentColor}
    .worker-trends{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    .worker-chart{padding:12px;border:1px solid rgba(151,176,214,.10);border-radius:13px;background:rgba(10,14,20,.6)}
    .worker-chart-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:8px}
    .worker-chart svg{display:block;width:100%;height:92px;color:#71b7ff}
    .worker-chart.memory svg{color:#63d6ad}
    .worker-group-summary{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
    .worker-group-summary button{padding:7px 10px;border-radius:10px;border:1px solid var(--line);background:#101721;color:#b9c7d9;cursor:pointer}
    .worker-group-summary button.active{border-color:var(--line-strong);color:#fff;background:#162235}
    @media(max-width:1200px){.worker-kpis{grid-template-columns:repeat(3,1fr)}.worker-layout{grid-template-columns:1fr}}
    @media(max-width:760px){.worker-kpis,.worker-detail-grid,.worker-trends{grid-template-columns:1fr 1fr}.worker-filters input{min-width:0;width:100%}}
    @media(max-width:560px){.worker-detail-grid,.worker-trends{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  const statusLabels={
    online:'空闲',busy:'工作中',draining:'排空中',offline:'离线',pending:'等待注册',
    disk_low:'磁盘不足',incompatible:'版本不兼容',revoked:'已吊销'
  };
  let workerView={search:'',group:'all',status:'all'};

  const fmtBytes=value=>{
    const n=Number(value||0);
    if(!n)return '—';
    if(n>=1024**3)return (n/1024**3).toFixed(1)+' GB';
    if(n>=1024**2)return (n/1024**2).toFixed(1)+' MB';
    return Math.round(n/1024)+' KB';
  };
  const fmtMemory=value=>value==null?'—':(Number(value)>=1024?(Number(value)/1024).toFixed(1)+' GB':Number(value)+' MB');
  const fmtPct=value=>value==null?'—':Number(value).toFixed(0)+'%';
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
  const meter=value=>{
    if(value==null)return '';
    const v=Math.max(0,Math.min(100,Number(value)));
    return `<div class="worker-meter"><i style="width:${v}%"></i></div>`;
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
    if(!items.length)return '<tr><td colspan="8" class="muted">当前筛选条件下没有 Worker。</td></tr>';
    return items.map(w=>{
      const mismatch=w.render_contract_version&&contractVersion&&w.render_contract_version!==contractVersion;
      const canToggle=!['revoked','pending','incompatible'].includes(w.effective_status);
      const canRevoke=w.effective_status!=='revoked'&&!w.slots_busy;
      return `<tr>
        <td><div class="worker-name">${esc(w.name)}</div><div class="worker-sub">${esc(w.host||'未连接')} · <span class="code">${w.id.slice(0,10)}</span></div></td>
        <td><span class="worker-group-chip">${esc(w.group_name||'default')}</span></td>
        <td>${statusHtml(w)}<div class="worker-sub">${w.slots_busy||0} / ${w.slots_total||1} 槽位 · ${fmtAgo(w.heartbeat_age_seconds)}</div></td>
        <td>${capsHtml(w)}</td>
        <td><div class="worker-health">
          <div><div class="worker-health-line"><span>CPU</span><b>${fmtPct(w.cpu_percent)}</b></div>${meter(w.cpu_percent)}</div>
          <div><div class="worker-health-line"><span>内存</span><b>${fmtPct(w.memory_percent)}</b></div>${meter(w.memory_percent)}</div>
          <div class="worker-health-line"><span>可用 / 磁盘</span><b>${fmtMemory(w.memory_available_mb)} / ${fmtBytes(w.disk_free_bytes)}</b></div>
        </div></td>
        <td><div class="${mismatch?'worker-version-bad':'worker-version-ok'}">${esc(w.code_version||'—')}</div><div class="worker-sub">${esc(w.model_version||'')}</div>${mismatch?'<div class="worker-sub worker-version-bad">Contract 不一致</div>':''}</td>
        <td>${w.current_task_id?`<span class="code">${esc(w.current_task_id.slice(0,12))}</span>`:'<span class="muted">—</span>'}</td>
        <td><div class="actions">
          <button class="secondary" data-worker-detail="${w.id}">详情</button>
          <button class="secondary" data-worker-edit="${w.id}">编辑</button>
          ${canToggle?`<button class="secondary" data-worker-toggle="${w.id}" data-accepting="${w.accepting_tasks?'1':'0'}">${w.accepting_tasks?'停止接新任务':'恢复接任务'}</button>`:''}
          ${canRevoke?`<button class="danger" data-worker-revoke="${w.id}">吊销</button>`:''}
        </div></td>
      </tr>`;
    }).join('');
  }

  function filterWorkers(workers){
    const q=workerView.search.trim().toLowerCase();
    return workers.filter(w=>{
      if(workerView.group!=='all'&&(w.group_name||'default')!==workerView.group)return false;
      if(workerView.status!=='all'&&(w.effective_status||w.status)!==workerView.status)return false;
      if(q){
        const hay=[w.name,w.host,w.id,w.group_name,...(w.capabilities||[])].join(' ').toLowerCase();
        if(!hay.includes(q))return false;
      }
      return true;
    });
  }

  async function renderWorkerCenter(){
    const data=await api('/admin/workers/overview');
    const s=data.summary||{};
    const workers=data.workers||[];
    const groups=Object.keys(data.groups||{}).sort();
    if(workerView.group!=='all'&&!groups.includes(workerView.group))workerView.group='all';
    const visible=filterWorkers(workers);
    $('page').innerHTML=`
      <div class="section-title"><div><h2>Worker 控制中心</h2><p>统一管理本地、局域网和远程算力节点；查看在线、任务、资源和版本状态</p></div><button class="primary" id="workerAdd">+ 新增 Worker</button></div>
      <div class="grid stats worker-kpis">
        <div class="stat"><div class="muted">Worker 总数</div><div class="num">${s.visible_total??s.total??0}</div><div class="worker-sub">受管节点在线 ${s.online||0} · 本地兼容 ${s.legacy_online||0}</div></div>
        <div class="stat"><div class="muted">工作中</div><div class="num">${s.busy||0}</div><div class="worker-sub">运行尝试 ${s.running_attempts||0}</div></div>
        <div class="stat"><div class="muted">排空 / 告警</div><div class="num">${(s.draining||0)+(s.warning||0)}</div><div class="worker-sub">Drain ${s.draining||0} · 告警 ${s.warning||0}</div></div>
        <div class="stat"><div class="muted">离线</div><div class="num">${s.offline||0}</div><div class="worker-sub">待注册 ${s.pending||0}</div></div>
        <div class="stat"><div class="muted">槽位占用</div><div class="num">${s.slots_busy||0}/${s.slots_total||0}</div><div class="worker-sub">队列 ${s.queued_tasks||0} 个分页任务</div></div>
        <div class="stat"><div class="muted">24h 完成 / 失败</div><div class="num" style="font-size:25px">${s.completed_24h||0} / ${s.failed_24h||0}</div><div class="worker-sub">Render Attempts</div></div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="toolbar"><div><h2>Worker 节点</h2><div class="muted">心跳超过控制面在线窗口后自动显示为离线；停止接新任务会进入 Drain</div></div><div class="code">Contract ${esc(data.render_contract_version||'—')}</div></div>
        <div class="worker-filters" style="margin-bottom:12px">
          <input id="workerSearch" value="${esc(workerView.search)}" placeholder="搜索名称、主机、ID、能力">
          <select id="workerGroupFilter"><option value="all">全部分组</option>${groups.map(g=>`<option value="${esc(g)}" ${workerView.group===g?'selected':''}>${esc(g)}</option>`).join('')}</select>
          <select id="workerStatusFilter"><option value="all">全部状态</option>${Object.entries(statusLabels).map(([k,v])=>`<option value="${k}" ${workerView.status===k?'selected':''}>${v}</option>`).join('')}</select>
          <span class="muted">显示 ${visible.length} / ${workers.length}</span>
        </div>
        <div class="worker-group-summary">${groups.map(g=>{const x=data.groups[g]||{};return `<button class="${workerView.group===g?'active':''}" data-worker-group-shortcut="${esc(g)}">${esc(g)} · ${x.online||0}/${x.total||0} 在线${x.warning?(' · '+x.warning+' 告警'):''}</button>`}).join('')}</div>
        <div class="table-wrap" style="margin-top:12px"><table class="table"><thead><tr><th>节点</th><th>分组</th><th>状态 / 槽位</th><th>能力</th><th>资源</th><th>版本</th><th>当前任务</th><th>操作</th></tr></thead><tbody>${workerRows(visible,data.render_contract_version)}</tbody></table></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="toolbar"><div><h2>本地队列 Worker（兼容模式）</h2><div class="muted">保留现有 Redis/本地 Worker 状态，只读展示；新节点建议统一走 Worker Enrollment 纳入受管节点。</div></div></div><div class="worker-capabilities">${Object.entries(data.legacy_engines||{}).map(([engine,info])=>`<span class="worker-chip">${esc(engine)} · ${info.online?("在线 "+Number(info.count||0)+" 台"):"离线"}</span>`).join("")||"<span class=\"muted\">未启用本地队列 Worker</span>"}</div></div>
      <div class="split" style="margin-top:16px">
        <div class="card"><h2>调度规则</h2><div class="muted">仅在线、兼容、允许接任务且有空闲槽位的 Worker 才会参与 claim。当前是 Worker 主动 claim 架构，因此没有加入“伪权重”配置；如后续需要权重调度，应改为控制面授予 claim 配额或任务定向。</div></div>
        <div class="card"><h2>维护建议</h2><div class="muted">维护节点时优先使用“停止接新任务”，等待当前槽位清空后再停机；“吊销”仅用于永久废弃或凭据泄露的节点。</div></div>
      </div>
    `;

    $('workerAdd').onclick=()=>{
      if(typeof workerEnrollmentModal==='function')workerEnrollmentModal();
      else toast('Worker 注册功能未加载');
    };
    $('workerSearch').oninput=e=>{workerView.search=e.target.value;clearTimeout(window.__workerSearchTimer);window.__workerSearchTimer=setTimeout(()=>renderWorkerCenter(),180)};
    $('workerGroupFilter').onchange=e=>{workerView.group=e.target.value;renderWorkerCenter()};
    $('workerStatusFilter').onchange=e=>{workerView.status=e.target.value;renderWorkerCenter()};
    document.querySelectorAll('[data-worker-group-shortcut]').forEach(b=>b.onclick=()=>{workerView.group=b.dataset.workerGroupShortcut;renderWorkerCenter()});
    document.querySelectorAll('[data-worker-detail]').forEach(b=>b.onclick=()=>openWorkerDetail(b.dataset.workerDetail,data.render_contract_version));
    document.querySelectorAll('[data-worker-edit]').forEach(b=>b.onclick=()=>openWorkerEdit(workers.find(w=>w.id===b.dataset.workerEdit)));
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

  function openWorkerEdit(w){
    if(!w)return;
    openModal(`<div class="modal-head"><div><h2 style="margin-bottom:4px">编辑 Worker</h2><div class="muted">${esc(w.host||w.id)}</div></div><button class="iconbtn" data-close>×</button></div>
      <form id="workerEditForm">
        <div class="row"><div class="field"><label>节点名称</label><input id="workerEditName" maxlength="120" value="${esc(w.name||'')}" required></div><div class="field"><label>分组</label><input id="workerEditGroup" maxlength="80" value="${esc(w.group_name||'default')}" placeholder="例如 production / mac-cluster"></div></div>
        <div class="field"><label>并发槽位</label><input id="workerEditSlots" type="number" min="1" max="4" value="${Number(w.slots_total||1)}" required><div class="muted">当前占用 ${Number(w.slots_busy||0)} 个槽位，不能调低到占用数以下。</div></div>
        <div class="field"><label>备注</label><textarea id="workerEditNotes" maxlength="2000" placeholder="机房、用途、维护说明等">${esc(w.notes||'')}</textarea></div>
        <button class="primary wide">保存 Worker 配置</button>
      </form>`);
    $('modalRoot').querySelectorAll('[data-close]').forEach(b=>b.onclick=closeModal);
    $('workerEditForm').onsubmit=async e=>{
      e.preventDefault();
      try{
        await api('/admin/workers/'+w.id,{method:'PATCH',body:{
          name:$('workerEditName').value,
          group_name:$('workerEditGroup').value,
          slots_total:Number($('workerEditSlots').value),
          notes:$('workerEditNotes').value
        }});
        closeModal();toast('Worker 配置已更新');renderWorkerCenter();
      }catch(err){toast(err.message)}
    };
  }

  function attemptRows(items){
    if(!items.length)return '<tr><td colspan="7" class="muted">当前筛选条件下暂无任务记录</td></tr>';
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

  function sparkline(samples,key,label,kind='cpu'){
    const values=(samples||[]).map(x=>({t:x.created_at,v:x[key]})).filter(x=>x.v!=null);
    if(values.length<2)return `<div class="worker-chart ${kind}"><div class="worker-chart-head"><b>${label}</b><span class="muted">等待更多心跳样本</span></div><div class="worker-empty-mini">暂无趋势数据</div></div>`;
    const width=420,height=92,pad=7;
    const pts=values.map((x,i)=>{
      const px=pad+(width-pad*2)*(i/Math.max(1,values.length-1));
      const py=height-pad-(height-pad*2)*(Math.max(0,Math.min(100,Number(x.v)))/100);
      return px.toFixed(1)+','+py.toFixed(1);
    }).join(' ');
    const last=Number(values[values.length-1].v);
    const max=Math.max(...values.map(x=>Number(x.v)));
    return `<div class="worker-chart ${kind}"><div class="worker-chart-head"><b>${label}</b><span class="muted">当前 ${last.toFixed(0)}% · 峰值 ${max.toFixed(0)}%</span></div><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"><path d="M${pad} ${height-pad} H${width-pad}" stroke="rgba(151,176,214,.16)" stroke-width="1"/><path d="M${pad} ${height/2} H${width-pad}" stroke="rgba(151,176,214,.10)" stroke-width="1"/><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2.2" vector-effect="non-scaling-stroke"/></svg></div>`;
  }

  async function openWorkerDetail(id,contractVersion){
    try{
      const d=await api('/admin/workers/'+id),w=d.worker||{},s24=d.stats_24h||{},s7=d.stats_7d||{},aux=d.active_auxiliary_tasks||[],attempts=d.recent_attempts||[],samples=d.health_series||[];
      const mismatch=w.render_contract_version&&contractVersion&&w.render_contract_version!==contractVersion;
      openModal(`<div class="modal-head"><div><div class="eyebrow">WORKER NODE</div><h2 style="margin:3px 0 0">${esc(w.name||'Worker')}</h2><div class="muted"><span class="worker-group-chip">${esc(w.group_name||'default')}</span> · ${esc(w.host||'未连接')} · <span class="code">${esc(w.id||'')}</span></div></div><div class="actions"><button class="secondary" id="workerDetailEdit">编辑</button><button class="iconbtn" data-close>×</button></div></div>
        <div class="worker-detail-grid">
          <div class="ops-mini"><span class="muted">当前状态</span><b style="font-size:16px">${statusHtml(w)}</b><small>${fmtAgo(w.heartbeat_age_seconds)}</small></div>
          <div class="ops-mini"><span class="muted">24h 成功率</span><b>${s24.success_rate||0}%</b><small>${s24.succeeded||0} 成功 / ${s24.failed||0} 失败</small></div>
          <div class="ops-mini"><span class="muted">7d 成功率</span><b>${s7.success_rate||0}%</b><small>${s7.attempts||0} 次尝试</small></div>
          <div class="ops-mini"><span class="muted">24h 平均耗时</span><b>${s24.average_success_seconds==null?'—':s24.average_success_seconds+'s'}</b><small>成功任务平均</small></div>
        </div>
        <div class="worker-trends">${sparkline(samples,'cpu_percent','CPU · 近 2 小时','cpu')}${sparkline(samples,'memory_percent','内存 · 近 2 小时','memory')}</div>
        <div class="worker-layout">
          <div>
            <div class="worker-detail-section"><div class="worker-section-head"><div><h3 style="margin:0">运行信息</h3><div class="muted">Worker 最近一次注册与心跳上报</div></div></div>
              <div class="table-wrap"><table class="table"><tbody>
                <tr><td class="muted">平台</td><td>${esc(w.platform||'—')}</td><td class="muted">架构</td><td>${esc(w.machine||'—')}</td></tr>
                <tr><td class="muted">CPU</td><td>${fmtPct(w.cpu_percent)}</td><td class="muted">内存使用率</td><td>${fmtPct(w.memory_percent)}</td></tr>
                <tr><td class="muted">可用内存</td><td>${fmtMemory(w.memory_available_mb)}</td><td class="muted">磁盘可用</td><td>${fmtBytes(w.disk_free_bytes)}</td></tr>
                <tr><td class="muted">并发槽位</td><td>${w.slots_busy||0} / ${w.slots_total||1}</td><td class="muted">接收任务</td><td>${w.accepting_tasks?'允许':'已停止'}</td></tr>
                <tr><td class="muted">代码版本</td><td>${esc(w.code_version||'—')}</td><td class="muted">模型版本</td><td>${esc(w.model_version||'—')}</td></tr>
                <tr><td class="muted">Render Contract</td><td colspan="3" class="${mismatch?'worker-version-bad':'worker-version-ok'}">${esc(w.render_contract_version||'—')}${mismatch?' · 与控制面不一致':''}</td></tr>
                <tr><td class="muted">最近心跳</td><td>${fmtTime(w.last_seen_at)}</td><td class="muted">当前任务</td><td class="code">${esc(w.current_task_id||'—')}</td></tr>
              </tbody></table></div>
              ${w.notes?`<div class="worker-warning" style="margin-top:10px">${esc(w.notes)}</div>`:''}
            </div>
            <div class="worker-detail-section">
              <div class="worker-section-head"><div><h3 style="margin:0">最近任务</h3><div class="muted">最多显示最近 100 次 RenderAttempt</div></div><select id="workerAttemptFilter"><option value="all">全部状态</option><option value="succeeded">成功</option><option value="failed">失败</option><option value="running">运行中</option></select></div>
              <div class="table-wrap"><table class="table"><thead><tr><th>父任务</th><th>页/类型</th><th>状态</th><th>进度</th><th>耗时</th><th>开始</th><th>错误</th></tr></thead><tbody id="workerAttemptRows">${attemptRows(attempts)}</tbody></table></div>
            </div>
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
      $('workerDetailEdit').onclick=()=>{closeModal();openWorkerEdit(w)};
      $('workerAttemptFilter').onchange=e=>{
        const value=e.target.value;
        $('workerAttemptRows').innerHTML=attemptRows(value==='all'?attempts:attempts.filter(x=>x.status===value));
      };
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
