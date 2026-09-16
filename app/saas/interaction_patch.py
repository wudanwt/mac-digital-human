from __future__ import annotations

from fastapi.responses import Response


JS = r'''
(() => {
  const style=document.createElement('style');
  style.textContent='@media(max-width:680px){.nav{grid-template-columns:repeat(auto-fit,minmax(42px,1fr))!important}} .job-card[data-job-card-id]{cursor:pointer;transition:border-color .18s ease,background .18s ease,transform .18s ease}.job-card[data-job-card-id]:hover{border-color:rgba(105,191,255,.34)!important;background:linear-gradient(180deg,rgba(17,28,41,.98),rgba(10,16,24,.98))!important}.job-card[data-job-card-id]:focus-visible{outline:2px solid rgba(105,191,255,.55);outline-offset:2px}.job-card .job-detail-btn{margin-left:auto;white-space:nowrap}';
  document.head.appendChild(style);

  function bindJobCards(){
    const items=Array.isArray(window.__lastJobs)?window.__lastJobs:[];
    const cards=[...document.querySelectorAll('#page .job-card')];
    cards.forEach((card,index)=>{
      const job=items[index];
      if(!job)return;
      card.dataset.jobCardId=job.id;
      card.tabIndex=0;
      card.title='点击查看任务详情';

      const actionRow=card.lastElementChild||card;
      let detailButton=card.querySelector('[data-job-detail]');
      if(!detailButton){
        detailButton=document.createElement('button');
        detailButton.type='button';
        detailButton.className='secondary job-detail-btn primary-entry';
        detailButton.dataset.jobDetail=job.id;
        detailButton.textContent='查看详情';
        actionRow.appendChild(detailButton);
      }else{
        detailButton.dataset.jobDetail=job.id;
      }

      card.onclick=e=>{
        if(e.target.closest('button,a,input,select,textarea,label'))return;
        detailButton.click();
      };
      card.onkeydown=e=>{
        if(e.target!==card)return;
        if(e.key==='Enter'||e.key===' '){
          e.preventDefault();
          detailButton.click();
        }
      };
    });
  }

  const baseDashboard=renderDashboard;
  renderDashboard=async function(){
    await baseDashboard();
    document.querySelectorAll('[data-modern-download]').forEach(b=>b.onclick=()=>downloadAsset(b.dataset.modernDownload,b.dataset.name));
    document.querySelectorAll('[data-modern-cancel]').forEach(b=>b.onclick=async()=>{try{await api('/jobs/'+b.dataset.modernCancel+'/cancel',{method:'POST'});renderDashboard()}catch(e){toast(e.message)}});
    bindJobCards();
  };

  const baseJobs=renderJobs;
  renderJobs=async function(){
    await baseJobs();
    bindJobCards();
  };

  // The base page starts its first async boot before enhancement scripts are loaded.
  // Re-render once after all enhancement layers are installed so the user never
  // gets stuck on the legacy markup on a very fast localhost connection.
  if(token){setTimeout(()=>showPage(current).catch(()=>{}),0)}
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
