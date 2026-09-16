from __future__ import annotations

from fastapi.responses import Response


JS = r'''
(() => {
  const style=document.createElement('style');
  style.textContent='@media(max-width:680px){.nav{grid-template-columns:repeat(auto-fit,minmax(42px,1fr))!important}}';
  document.head.appendChild(style);

  const baseDashboard=renderDashboard;
  renderDashboard=async function(){
    await baseDashboard();
    document.querySelectorAll('[data-modern-download]').forEach(b=>b.onclick=()=>downloadAsset(b.dataset.modernDownload,b.dataset.name));
    document.querySelectorAll('[data-modern-cancel]').forEach(b=>b.onclick=async()=>{try{await api('/jobs/'+b.dataset.modernCancel+'/cancel',{method:'POST'});renderDashboard()}catch(e){toast(e.message)}});
  };

  // The base page starts its first async boot before enhancement scripts are loaded.
  // Re-render once after all enhancement layers are installed so the user never
  // gets stuck on the legacy markup on a very fast localhost connection.
  if(token){setTimeout(()=>showPage(current).catch(()=>{}),0)}
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
