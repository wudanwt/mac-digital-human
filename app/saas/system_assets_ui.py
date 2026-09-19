from fastapi.responses import Response


JS = r'''
(() => {
  const previews = new Map();
  async function preview(item) {
    if (previews.has(item.id)) return previews.get(item.id);
    const response = await fetch(item.preview_url, {headers:{Authorization:'Bearer '+token}});
    if (!response.ok) return '';
    const url = URL.createObjectURL(await response.blob());
    previews.set(item.id, url);
    return url;
  }
  async function decorateAssets() {
    const page = document.getElementById('page');
    if (!page || current !== 'assets' || page.querySelector('#systemAssetCatalog')) return;
    const host = document.createElement('div');
    host.id = 'systemAssetCatalog';
    host.className = 'card';
    host.style.marginTop = '16px';
    host.innerHTML = '<div class="toolbar"><div><h2>平台默认素材</h2><div class="muted">选用后会导入当前工作区，不会共享你的私人文件。</div></div></div><div id="systemAssetItems" class="grid" style="grid-template-columns:repeat(auto-fill,minmax(170px,1fr))"></div>';
    page.appendChild(host);
    try {
      const items = await api('/system-assets');
      if (!host.isConnected) return;
      const list = host.querySelector('#systemAssetItems');
      if (!items.length) { list.innerHTML = '<div class="muted">平台素材尚未发布。</div>'; return; }
      list.innerHTML = items.map(item => `<div class="card" style="padding:10px"><div data-system-preview="${item.id}" style="height:92px;background:#0a111b center/contain no-repeat;border-radius:8px"></div><b>${esc(item.name)}</b><div class="muted">${item.kind==='avatar'?'数字人':'背景图'}</div><button class="secondary" data-system-import="${item.id}" style="margin-top:8px">导入工作区</button></div>`).join('');
      for (const item of items) {
        const image = list.querySelector(`[data-system-preview="${item.id}"]`);
        const url = await preview(item).catch(() => '');
        if (image && url) image.style.backgroundImage = `url("${url}")`;
      }
      list.querySelectorAll('[data-system-import]').forEach(button => button.onclick = async () => {
        button.disabled = true;
        try {
          const result = await api('/system-assets/'+button.dataset.systemImport+'/import',{method:'POST'});
          await loadLookups();
          toast(result.imported ? '已导入当前工作区' : '当前工作区已导入过该素材');
          await showPage('assets');
        } catch (error) { toast(error.message); button.disabled = false; }
      });
    } catch (error) { if (host.isConnected) host.querySelector('#systemAssetItems').textContent = error.message; }
  }
  new MutationObserver(() => queueMicrotask(decorateAssets)).observe(document.body,{childList:true,subtree:true});
  queueMicrotask(decorateAssets);
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
