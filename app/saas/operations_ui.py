from __future__ import annotations

from fastapi.responses import Response


JS = r'''
(() => {
  const style=document.createElement('style');
  style.textContent=`
    .ops-kpis{grid-template-columns:repeat(6,minmax(120px,1fr))}
    .ops-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 16px}
    .ops-chip{padding:5px 9px;border-radius:999px;background:#172235;color:#a9bad2;font-size:12px}
    .ops-customer-name{font-weight:800}
    .ops-meter{height:7px;background:#202c40;border-radius:999px;overflow:hidden;min-width:120px}
    .ops-meter>i{display:block;height:100%;background:#4f8cff}
    .ops-detail-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0}
    .ops-mini{padding:12px;border:1px solid #25334a;border-radius:12px;background:#0e1520}
    .ops-mini b{display:block;font-size:20px;margin-top:3px}
    .ops-section{margin-top:18px}
    .ops-search{display:flex;gap:8px;min-width:min(420px,100%)}
    .ops-search input{flex:1;border:1px solid #2a3953;background:#0a0f18;color:#fff;padding:10px 12px;border-radius:10px}
    @media(max-width:1100px){.ops-kpis{grid-template-columns:repeat(3,1fr)}}
    @media(max-width:700px){
      .ops-kpis,.ops-detail-grid{grid-template-columns:1fr 1fr}
      .ops-search{width:100%;min-width:0}
      .ops-search input{min-width:0;font-size:16px}
      .ops-search button{min-height:42px;flex:0 0 auto}
      .ops-tabs{flex-wrap:nowrap;overflow-x:auto;padding-bottom:4px;-webkit-overflow-scrolling:touch;scrollbar-width:none}
      .ops-tabs::-webkit-scrollbar{display:none}
      .ops-tabs button{flex:0 0 auto;min-height:40px}
      .ops-meter{min-width:88px}
    }
    @media(max-width:460px){
      .ops-kpis,.ops-detail-grid{grid-template-columns:1fr}
      .ops-search{display:grid;grid-template-columns:minmax(0,1fr) auto}
      .ops-mini b{font-size:18px}
    }
  `;
  document.head.appendChild(style);

  let opsSearch='';
  let opsPlans=[];

  const opsMoney=v=>'¥'+Number(v||0).toLocaleString('zh-CN',{maximumFractionDigits:2});
  const opsDate=v=>v?new Date(v).toLocaleString('zh-CN',{hour12:false}):'—';
  const opsStatus=s=>`<span class="badge ${esc(s||'')}">${esc(s||'—')}</span>`;

  async function opsLoadCustomers(q=''){
    return api('/admin/ops/customers'+(q?('?q='+encodeURIComponent(q)):''));
  }

  function opsCustomerRows(customers){
    if(!customers.length)return '<tr><td colspan="6" class="muted">没有匹配客户</td></tr>';
    return customers.map(c=>`<tr>
      <td><div class="ops-customer-name">${esc(c.name)}</div><div class="muted">${esc(c.owner?.email||'')}</div><div class="code">${c.id.slice(0,8)}</div></td>
      <td><b>${esc(c.plan_name||c.plan_code)}</b><div class="muted">${esc(c.plan_code)}</div></td>
      <td>${opsStatus(c.subscription_status)}</td>
      <td><b>${c.remaining_minutes}</b> 分钟</td>
      <td>${opsDate(c.period_ends_at)}</td>
      <td><div class="actions"><button class="secondary" data-ops-detail="${c.id}">详情</button><button class="primary" data-ops-activate="${c.id}">开通/续费</button><button class="secondary" data-ops-credit="${c.id}">额度</button></div></td>
    </tr>`).join('');
  }

  function opsPlanRows(plans){
    return plans.map(p=>`<tr>
      <td><b>${esc(p.name)}</b><div class="code">${esc(p.code)}</div></td>
      <td>${p.monthly_minutes} 分钟/月</td>
      <td>${p.storage_gb} GB</td>
      <td>${p.max_avatars} 个数字人</td>
      <td>${p.max_members} 人</td>
      <td>${opsMoney(p.price_cny)}</td>
      <td>${p.is_active?'<span class="badge active">上架</span>':'<span class="badge canceled">下架</span>'}</td>
      <td><button class="secondary" data-ops-edit-plan="${esc(p.code)}">编辑</button></td>
    </tr>`).join('');
  }

  async function opsCustomerDetail(id){
    const d=await api('/admin/ops/customers/'+id);
    const s=d.subscription,r=d.resources,c=d.customer;
    const periods=d.periods||[], orders=d.orders||[], ledger=d.usage_ledger||[];
    openModal(`<div class="modal-head"><div><h2>${esc(c.name)}</h2><div class="muted">${esc(c.owner.display_name||'')} · ${esc(c.owner.email||'')}</div></div><button class="iconbtn" data-close>×</button></div>
      <div class="ops-detail-grid">
        <div class="ops-mini"><span class="muted">当前套餐</span><b>${esc(s.plan_name||s.plan_code)}</b><small>${opsStatus(s.status)}</small></div>
        <div class="ops-mini"><span class="muted">剩余生成额度</span><b>${s.remaining_minutes} min</b><small>已消耗 ${s.consumed_minutes} min</small></div>
        <div class="ops-mini"><span class="muted">有效期至</span><b style="font-size:15px">${opsDate(s.period_ends_at)}</b><small>开始 ${opsDate(s.period_started_at)}</small></div>
        <div class="ops-mini"><span class="muted">数字人</span><b>${r.avatars} / ${s.max_avatars}</b></div>
        <div class="ops-mini"><span class="muted">成员</span><b>${r.members} / ${s.max_members}</b></div>
        <div class="ops-mini"><span class="muted">存储</span><b>${r.storage_gb_used} / ${s.storage_gb} GB</b></div>
      </div>
      <div class="actions"><button class="primary" data-detail-activate="${id}">开通 / 续费</button><button class="secondary" data-detail-credit="${id}">调整额度</button></div>
      <div class="ops-section"><h3>订阅周期历史</h3><div class="table-wrap"><table class="table"><thead><tr><th>套餐</th><th>方式</th><th>额度</th><th>金额</th><th>起止时间</th><th>备注</th></tr></thead><tbody>${periods.map(x=>`<tr><td>${esc(x.plan_code)}</td><td>${x.activation_mode==='renew'?'续费':'开通/替换'}</td><td>${x.granted_minutes} min</td><td>${opsMoney(x.amount_cny)}</td><td>${opsDate(x.started_at)}<br><span class="muted">→ ${opsDate(x.ends_at)}</span></td><td>${esc(x.note||'—')}</td></tr>`).join('')||'<tr><td colspan="6" class="muted">暂无历史周期（旧数据不会伪造历史）</td></tr>'}</tbody></table></div></div>
      <div class="ops-section"><h3>最近订单</h3><div class="table-wrap"><table class="table"><thead><tr><th>订单</th><th>套餐</th><th>金额</th><th>状态</th><th>时间</th></tr></thead><tbody>${orders.slice(0,20).map(x=>`<tr><td class="code">${x.id.slice(0,10)}</td><td>${esc(x.plan_code)}</td><td>${opsMoney(x.amount_cny)}</td><td>${opsStatus(x.status)}</td><td>${opsDate(x.paid_at||x.created_at)}</td></tr>`).join('')||'<tr><td colspan="5" class="muted">暂无订单</td></tr>'}</tbody></table></div></div>
      <div class="ops-section"><h3>最近额度流水</h3><div class="table-wrap"><table class="table"><thead><tr><th>类型</th><th>数值</th><th>时间</th></tr></thead><tbody>${ledger.slice(0,20).map(x=>`<tr><td>${esc(x.kind)}</td><td>${Number(x.units).toFixed(1)}</td><td>${opsDate(x.created_at)}</td></tr>`).join('')||'<tr><td colspan="3" class="muted">暂无流水</td></tr>'}</tbody></table></div></div>`);
    $('modalRoot').querySelector('[data-close]').onclick=closeModal;
    $('modalRoot').querySelector('[data-detail-activate]').onclick=()=>{closeModal();opsActivateModal(id,c.name)};
    $('modalRoot').querySelector('[data-detail-credit]').onclick=()=>{closeModal();opsCreditModal(id,c.name)};
  }

  function opsActivateModal(id,name){
    const options=opsPlans.filter(p=>p.is_active).map(p=>`<option value="${esc(p.code)}">${esc(p.name)} · ${p.monthly_minutes}min/月 · ${opsMoney(p.price_cny)}/月</option>`).join('');
    openModal(`<div class="modal-head"><div><h2>开通 / 续费套餐</h2><div class="muted">${esc(name||'客户')}</div></div><button class="iconbtn" data-close>×</button></div>
      <form id="opsActivateForm" data-id="${id}">
        <div class="field"><label>套餐</label><select id="opsPlanCode">${options}</select></div>
        <div class="row"><div class="field"><label>时长（月）</label><input id="opsMonths" type="number" min="1" max="36" value="1" required></div><div class="field"><label>操作方式</label><select id="opsActivationMode"><option value="replace">开通 / 升级（替换当前套餐）</option><option value="renew">续费（同套餐延长并追加额度）</option></select></div></div>
        <div class="field"><label>实收金额（留空按套餐价自动计算）</label><input id="opsAmount" type="number" min="0" step="0.01" placeholder="自动计算"></div>
        <div class="field"><label>备注 / 合同编号</label><input id="opsNote" maxlength="500" placeholder="例如：合同 HT-2026-0919，线下转账"></div>
        <div class="muted" style="margin:8px 0 14px">确认后会自动生成已付款人工订单、更新当前订阅、发放额度并写入订阅周期历史与审计日志。</div>
        <button class="primary wide">确认开通</button>
      </form>`);
    $('modalRoot').querySelector('[data-close]').onclick=closeModal;
    $('opsActivateForm').onsubmit=async e=>{e.preventDefault();try{
      const raw=$('opsAmount').value.trim();
      await api('/admin/ops/customers/'+id+'/activate',{method:'POST',body:{
        plan_code:$('opsPlanCode').value,
        months:Number($('opsMonths').value),
        activation_mode:$('opsActivationMode').value,
        amount_cny:raw===''?null:Number(raw),
        note:$('opsNote').value
      }});
      closeModal();toast('套餐已开通并完成权益发放');renderAdmin();
    }catch(err){toast(err.message)}};
  }

  function opsCreditModal(id,name){
    openModal(`<div class="modal-head"><div><h2>调整生成额度</h2><div class="muted">${esc(name||'客户')}</div></div><button class="iconbtn" data-close>×</button></div>
      <form id="opsCreditForm" data-id="${id}">
        <div class="field"><label>分钟数</label><input id="opsCreditMinutes" type="number" value="60" min="-100000" max="100000" required><div class="muted">正数赠送，负数扣减；系统不会允许扣成负数。</div></div>
        <div class="field"><label>原因</label><input id="opsCreditReason" value="运营调整" required maxlength="240"></div>
        <button class="primary wide">确认调整</button>
      </form>`);
    $('modalRoot').querySelector('[data-close]').onclick=closeModal;
    $('opsCreditForm').onsubmit=async e=>{e.preventDefault();try{
      await api('/admin/ops/customers/'+id+'/credits',{method:'POST',body:{minutes:Number($('opsCreditMinutes').value),reason:$('opsCreditReason').value}});
      closeModal();toast('额度已调整');renderAdmin();
    }catch(err){toast(err.message)}};
  }

  function opsPlanModal(plan=null){
    const p=plan||{code:'',name:'',monthly_minutes:60,storage_gb:10,max_avatars:1,max_members:1,priority:0,price_cny:99,is_active:true};
    const editing=!!plan;
    openModal(`<div class="modal-head"><h2>${editing?'编辑套餐':'新建套餐'}</h2><button class="iconbtn" data-close>×</button></div>
      <form id="opsPlanForm" data-code="${esc(p.code)}" data-editing="${editing?'1':'0'}">
        <div class="row"><div class="field"><label>套餐代码</label><input id="opsPlanEditCode" value="${esc(p.code)}" ${editing?'disabled':''} required pattern="[a-z0-9][a-z0-9_-]*"></div><div class="field"><label>套餐名称</label><input id="opsPlanName" value="${esc(p.name)}" required></div></div>
        <div class="row"><div class="field"><label>每月生成分钟</label><input id="opsPlanMinutes" type="number" min="0" value="${p.monthly_minutes}" required></div><div class="field"><label>存储 GB</label><input id="opsPlanStorage" type="number" min="0" value="${p.storage_gb}" required></div></div>
        <div class="row"><div class="field"><label>数字人上限</label><input id="opsPlanAvatars" type="number" min="0" value="${p.max_avatars}" required></div><div class="field"><label>成员上限</label><input id="opsPlanMembers" type="number" min="1" value="${p.max_members}" required></div></div>
        <div class="row"><div class="field"><label>任务优先级</label><input id="opsPlanPriority" type="number" min="0" value="${p.priority}" required></div><div class="field"><label>月价格（元）</label><input id="opsPlanPrice" type="number" min="0" step="0.01" value="${p.price_cny}" required></div></div>
        <label class="check"><input id="opsPlanActive" type="checkbox" ${p.is_active?'checked':''}> 套餐上架，可被客户购买/运营开通</label>
        <button class="primary wide">${editing?'保存套餐':'创建套餐'}</button>
      </form>`);
    $('modalRoot').querySelector('[data-close]').onclick=closeModal;
    $('opsPlanForm').onsubmit=async e=>{e.preventDefault();try{
      const body={name:$('opsPlanName').value,monthly_minutes:Number($('opsPlanMinutes').value),storage_gb:Number($('opsPlanStorage').value),max_avatars:Number($('opsPlanAvatars').value),max_members:Number($('opsPlanMembers').value),priority:Number($('opsPlanPriority').value),price_cny:Number($('opsPlanPrice').value),is_active:$('opsPlanActive').checked};
      if(editing) await api('/admin/ops/plans/'+encodeURIComponent(p.code),{method:'PATCH',body});
      else {body.code=$('opsPlanEditCode').value;await api('/admin/ops/plans',{method:'POST',body});}
      closeModal();toast(editing?'套餐已更新':'套餐已创建');renderAdmin();
    }catch(err){toast(err.message)}};
  }

  async function opsUpdateReport(id,status){
    try{await api('/admin/compliance/reports/'+id,{method:'PATCH',body:{status,resolution:status==='resolved'?'已处理':'进入人工审核'}});renderAdmin()}catch(e){toast(e.message)}
  }

  renderAdmin=async function(){
    if(!me.user.is_superuser){$('page').innerHTML='<div class="empty">无平台运营权限</div>';return}
    const [o,customers,plans,orders,reports]=await Promise.all([
      api('/admin/ops/overview'),
      opsLoadCustomers(opsSearch),
      api('/admin/ops/plans'),
      api('/admin/orders'),
      api('/admin/compliance/reports')
    ]);
    opsPlans=plans;
    window.__tenants=Object.fromEntries(customers.map(t=>[t.id,t]));
    $('page').innerHTML=`
      <div class="section-title"><div><h2>SaaS 运营管理中心</h2><p>客户 → 套餐 → 订单 → 订阅 → 权益 → 用量 → 续费的运营闭环</p></div></div>
      <div class="grid stats ops-kpis">
        <div class="stat"><div class="muted">客户工作区</div><div class="num">${o.customers}</div></div>
        <div class="stat"><div class="muted">付费客户</div><div class="num">${o.paid_customers}</div></div>
        <div class="stat"><div class="muted">有效订阅</div><div class="num">${o.active_subscriptions}</div></div>
        <div class="stat"><div class="muted">累计已收款</div><div class="num" style="font-size:22px">${opsMoney(o.paid_revenue_cny)}</div></div>
        <div class="stat"><div class="muted">7天内到期</div><div class="num">${o.expiring_7d}</div></div>
        <div class="stat"><div class="muted">待确认订单</div><div class="num">${o.pending_orders}</div></div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="toolbar"><div><h2>客户管理</h2><div class="muted">以客户详情为中心完成开通、续费、额度和历史追溯</div></div>
          <div class="ops-search"><input id="opsCustomerSearch" value="${esc(opsSearch)}" placeholder="搜索客户名称、工作区、Owner邮箱"><button class="secondary" id="opsSearchBtn">搜索</button></div>
        </div>
        <div class="table-wrap"><table class="table"><thead><tr><th>客户</th><th>套餐</th><th>状态</th><th>剩余额度</th><th>到期时间</th><th>操作</th></tr></thead><tbody>${opsCustomerRows(customers)}</tbody></table></div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="toolbar"><div><h2>套餐管理</h2><div class="muted">统一管理销售套餐、额度、资源限制、价格与上下架</div></div><button class="primary" id="opsNewPlan">+ 新建套餐</button></div>
        <div class="table-wrap"><table class="table"><thead><tr><th>套餐</th><th>额度</th><th>存储</th><th>数字人</th><th>成员</th><th>价格</th><th>状态</th><th></th></tr></thead><tbody>${opsPlanRows(plans)}</tbody></table></div>
      </div>
      <div class="split" style="margin-top:16px">
        <div class="card"><h2>待确认订单</h2><div class="table-wrap"><table class="table"><tbody>${orders.filter(x=>x.status==='pending').slice(0,30).map(x=>`<tr><td><span class="code">${x.id.slice(0,9)}</span><div class="muted">${esc(x.plan_code)}</div></td><td>${opsMoney(x.amount_cny)}</td><td><button class="primary" data-ops-paid="${x.id}">确认收款</button></td></tr>`).join('')||'<tr><td class="muted">暂无待确认订单</td></tr>'}</tbody></table></div></div>
        <div class="card"><h2>经营提示</h2><div class="ops-detail-grid" style="grid-template-columns:1fr 1fr"><div class="ops-mini"><span class="muted">累计生成</span><b>${o.rendered_minutes} min</b></div><div class="ops-mini"><span class="muted">平台注册用户</span><b>${o.users}</b></div></div><div class="muted">当前为人工运营闭环：先把线下成交、套餐发放、续费和售后跑顺；微信/支付宝自动支付、退款、发票和通知可在下一阶段接入。</div></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="toolbar"><div><h2>内容合规队列</h2><div class="muted">保留原有举报与人工审核入口</div></div></div>${reports.length?`<div class="table-wrap"><table class="table"><thead><tr><th>原因</th><th>对象</th><th>状态</th><th>时间</th><th></th></tr></thead><tbody>${reports.slice(0,50).map(r=>`<tr><td>${esc(r.reason)}</td><td>${esc(r.target_type)} · <span class="code">${r.target_id.slice(0,8)}</span></td><td>${opsStatus(r.status)}</td><td>${opsDate(r.created_at)}</td><td>${r.status!=='resolved'?`<button class="secondary" data-ops-report-review="${r.id}">处理中</button> <button class="primary" data-ops-report-resolve="${r.id}">完成</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">暂无举报</div>'}</div>
    `;

    $('opsSearchBtn').onclick=()=>{opsSearch=$('opsCustomerSearch').value.trim();renderAdmin()};
    $('opsCustomerSearch').onkeydown=e=>{if(e.key==='Enter'){opsSearch=e.target.value.trim();renderAdmin()}};
    $('opsNewPlan').onclick=()=>opsPlanModal();
    document.querySelectorAll('[data-ops-detail]').forEach(b=>b.onclick=()=>opsCustomerDetail(b.dataset.opsDetail));
    document.querySelectorAll('[data-ops-activate]').forEach(b=>b.onclick=()=>opsActivateModal(b.dataset.opsActivate,window.__tenants[b.dataset.opsActivate]?.name));
    document.querySelectorAll('[data-ops-credit]').forEach(b=>b.onclick=()=>opsCreditModal(b.dataset.opsCredit,window.__tenants[b.dataset.opsCredit]?.name));
    document.querySelectorAll('[data-ops-edit-plan]').forEach(b=>b.onclick=()=>opsPlanModal(opsPlans.find(p=>p.code===b.dataset.opsEditPlan)));
    document.querySelectorAll('[data-ops-paid]').forEach(b=>b.onclick=async()=>{try{await api('/admin/orders/'+b.dataset.opsPaid+'/mark-paid',{method:'POST'});toast('订单已确认并开通套餐');renderAdmin()}catch(e){toast(e.message)}});
    document.querySelectorAll('[data-ops-report-review]').forEach(b=>b.onclick=()=>opsUpdateReport(b.dataset.opsReportReview,'reviewing'));
    document.querySelectorAll('[data-ops-report-resolve]').forEach(b=>b.onclick=()=>opsUpdateReport(b.dataset.opsReportResolve,'resolved'));
  };
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
