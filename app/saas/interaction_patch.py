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

  // A pronunciation correction is course-wide, but the studio's original
  // "保存并试听" flow only synthesized the selected token. That made it look as
  // though later occurrences on the same page were not corrected. Keep the
  // quick token check, then automatically synthesize the whole page so every
  // occurrence is verified through the exact production TTS path.
  let pronunciationReview=null;
  function patchPronunciationReview(){
    const save=document.getElementById('savePronunciation');
    if(save&&!save.dataset.fullPageReview){
      save.dataset.fullPageReview='1';
      save.textContent='保存并试听本页';
      save.title='保存读音规则后，自动试听整页并验证所有相同词语';
    }
  }
  function stopPronunciationReview(){
    if(!pronunciationReview)return;
    pronunciationReview.observer?.disconnect();
    clearTimeout(pronunciationReview.timeout);
    pronunciationReview=null;
  }
  function armPronunciationReview(source){
    stopPronunciationReview();
    const textarea=document.getElementById('studioNarration');
    const pageText=textarea?.value||'';
    const hits=source?pageText.split(source).length-1:0;
    pronunciationReview={source,hits,observer:null,timeout:null};
    pronunciationReview.observer=new MutationObserver(()=>{
      patchPronunciationReview();
      if(!pronunciationReview)return;
      const state=document.getElementById('speechPreviewState');
      const pageButton=document.getElementById('previewPage');
      // The selected-word preview has completed. Start a fresh full-page
      // preview; its fingerprint includes the just-saved pronunciation rules.
      if(state?.querySelector('audio')&&pageButton&&!pageButton.disabled){
        const count=pronunciationReview.hits;
        stopPronunciationReview();
        pageButton.click();
        if(typeof toast==='function'&&count>1)toast(`读音规则已命中本页 ${count} 处，正在试听整页`);
      }
    });
    pronunciationReview.observer.observe(document.documentElement,{childList:true,subtree:true});
    pronunciationReview.timeout=setTimeout(stopPronunciationReview,180000);
  }
  document.addEventListener('click',e=>{
    const button=e.target.closest?.('#savePronunciation');
    if(!button)return;
    const source=document.getElementById('pronunciationSource')?.value?.trim()||'';
    if(source)armPronunciationReview(source);
  },true);
  const pronunciationUiObserver=new MutationObserver(patchPronunciationReview);
  pronunciationUiObserver.observe(document.documentElement,{childList:true,subtree:true});
  patchPronunciationReview();

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
