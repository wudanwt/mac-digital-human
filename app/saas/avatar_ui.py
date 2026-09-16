from __future__ import annotations

from fastapi.responses import Response


JS = r'''
(() => {
  const dhState = { recorder: null, stream: null, chunks: [], recordingFile: null, previewUrls: [] };

  function dhEsc(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function dhStatus(item) {
    if (item.readiness?.musetalk_ready) return '<span class="badge ready">可生成</span>';
    if (item.readiness?.master_video_ready) return '<span class="badge running">待配置声音</span>';
    return '<span class="badge failed">配置不完整</span>';
  }

  function dhTranscriptPanel(voice) {
    const transcript = String(voice?.transcript || '').trim();
    const verified = Boolean(voice?.settings?.transcript_verified);
    return `<div style="margin-top:12px;padding:12px;border:1px solid ${transcript ? '#29445a' : '#663744'};border-radius:11px;background:${transcript ? '#0a1620' : '#241117'}">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:7px">
        <b style="font-size:12px;color:#9fc9eb">参考录音逐字稿</b>
        <span class="badge ${verified ? 'ready' : transcript ? 'running' : 'failed'}">${verified ? '已人工核对' : transcript ? '已填写 · 待核对' : '缺失'}</span>
      </div>
      <div style="white-space:pre-wrap;word-break:break-word;line-height:1.75;color:${transcript ? '#edf6ff' : '#ff9bac'}">${transcript ? dhEsc(transcript) : '尚未填写逐字稿，当前声音不可用于可靠克隆。'}</div>
      <div class="muted" style="margin-top:7px;font-size:11px">这里必须完整记录参考录音实际说出的每一个字，不能填写讲稿或近似内容。</div>
    </div>`;
  }

  async function dhBlobUrl(assetId) {
    const r = await fetch(API + '/assets/' + assetId + '/download', {headers:{Authorization:'Bearer ' + token}});
    if (!r.ok) throw new Error('素材预览失败');
    const url = URL.createObjectURL(await r.blob());
    dhState.previewUrls.push(url);
    return url;
  }

  function dhCleanupUrls() {
    dhState.previewUrls.splice(0).forEach(url => URL.revokeObjectURL(url));
  }

  async function hydrateDigitalHumanPreviews() {
    const nodes = document.querySelectorAll('[data-dh-image-id]');
    for (const node of nodes) {
      const id = node.dataset.dhImageId;
      if (!id) continue;
      try {
        const url = await dhBlobUrl(id);
        node.innerHTML = `<img src="${url}" alt="数字人头像" style="width:100%;height:100%;object-fit:cover">`;
      } catch (_) {}
    }
  }

  function dhCard(item) {
    const imageId = item.image?.id || '';
    const voice = item.voice;
    return `<div class="card" style="padding:0;overflow:hidden">
      <div data-dh-image-id="${imageId}" style="height:190px;background:linear-gradient(145deg,#18243a,#0d131e);display:grid;place-items:center;color:#71809a;font-size:40px">${imageId ? '◉' : '👤'}</div>
      <div style="padding:16px">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">
          <div><h3 style="margin:0 0 4px">${dhEsc(item.name)}</h3><div class="muted">${item.master_video ? '母版视频已配置' : '未配置母版视频'}</div></div>
          ${dhStatus(item)}
        </div>
        <div style="margin-top:14px;padding:11px;border:1px solid #243249;border-radius:11px;background:#0d141f">
          <div style="font-weight:700">默认声音：${dhEsc(voice?.name || '未配置')}</div>
          <div class="muted">${voice ? 'CosyVoice 克隆声音' : '创建课程前需要配置声音'}</div>
        </div>
        ${voice ? dhTranscriptPanel(voice) : ''}
        <div class="actions" style="margin-top:14px">
          ${item.master_video?.id ? `<button class="secondary" data-dh-preview-video="${item.master_video.id}">预览母版</button>` : ''}
          ${voice?.reference_asset?.id ? `<button class="secondary" data-dh-preview-audio="${voice.reference_asset.id}">试听声音</button>` : ''}
          ${voice?.reference_asset?.id && ['owner','admin'].includes(me.workspace.role) ? `<button class="secondary" data-dh-review-transcript="${item.id}">核对 / 修正逐字稿</button>` : ''}
          <button class="secondary" data-dh-edit="${item.id}">编辑</button>
          ${['owner','admin'].includes(me.workspace.role) ? `<button class="danger" data-dh-delete="${item.id}">删除</button>` : ''}
        </div>
      </div>
    </div>`;
  }

  renderAvatars = async function() {
    dhCleanupUrls();
    const items = await api('/digital-humans');
    cache.avatars = items;
    $('page').innerHTML = `<div class="card" style="margin-bottom:16px">
      <div class="toolbar"><div><h2 style="margin-bottom:4px">数字人资产</h2><div class="muted">一个数字人包含人物形象、母版视频、默认克隆声音和授权记录。</div></div><button class="primary" id="newDigitalHuman">+ 创建数字人</button></div>
      <div class="muted">普通用户不需要先去“素材中心”分别上传人物、视频和声音；创建流程会自动完成素材入库和绑定。</div>
    </div>
    ${items.length ? `<div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px">${items.map(dhCard).join('')}</div>` : '<div class="empty">还没有数字人。点击“创建数字人”，一次完成头像、母版视频和克隆声音配置。</div>'}`;
    document.getElementById('newDigitalHuman')?.addEventListener('click', () => digitalHumanModal());
    document.querySelectorAll('[data-dh-edit]').forEach(b => b.addEventListener('click', () => digitalHumanModal(items.find(x => x.id === b.dataset.dhEdit))));
    document.querySelectorAll('[data-dh-delete]').forEach(b => b.addEventListener('click', async () => {
      if (!confirm('删除这个数字人？已被课程引用的数字人不能删除。')) return;
      try { await api('/digital-humans/' + b.dataset.dhDelete, {method:'DELETE'}); toast('数字人已删除'); renderAvatars(); } catch (e) { toast(e.message); }
    }));
    document.querySelectorAll('[data-dh-preview-audio]').forEach(b => b.addEventListener('click', () => previewRemoteMedia(b.dataset.dhPreviewAudio, 'audio')));
    document.querySelectorAll('[data-dh-preview-video]').forEach(b => b.addEventListener('click', () => previewRemoteMedia(b.dataset.dhPreviewVideo, 'video')));
    document.querySelectorAll('[data-dh-review-transcript]').forEach(b => b.addEventListener('click', () => reviewVoiceTranscript(items.find(x => x.id === b.dataset.dhReviewTranscript))));
    hydrateDigitalHumanPreviews();
  };

  async function previewRemoteMedia(assetId, type) {
    try {
      const url = await dhBlobUrl(assetId);
      openModal(`<div class="modal-head"><h2>${type === 'video' ? '母版视频预览' : '声音试听'}</h2><button class="iconbtn" data-close>×</button></div>
        ${type === 'video' ? `<video src="${url}" controls autoplay style="width:100%;max-height:60vh;background:#000;border-radius:12px"></video>` : `<audio src="${url}" controls autoplay style="width:100%;margin-top:18px"></audio>`}`);
      $('modalRoot').querySelector('[data-close]')?.addEventListener('click', closeModal);
    } catch (e) { toast(e.message); }
  }

  async function reviewVoiceTranscript(item) {
    const voice = item?.voice;
    const audioId = voice?.reference_asset?.id;
    if (!voice || !audioId) return toast('这个数字人没有可核对的参考录音');
    try {
      const url = await dhBlobUrl(audioId);
      openModal(`<div class="modal-head"><div><h2>核对参考录音逐字稿</h2><div class="muted">${dhEsc(item.name)} · ${dhEsc(voice.name)}</div></div><button class="iconbtn" data-close>×</button></div>
        <div style="margin:14px 0;padding:12px;border:1px solid #664b29;border-radius:11px;background:#21180d;color:#f5d49c;line-height:1.7">请播放参考录音，逐字核对下方文字。哪怕只有“我/我们”、词序或漏字不同，也应修正；不要根据意思概括。</div>
        <audio src="${url}" controls style="width:100%;margin:2px 0 12px"></audio>
        <form id="dhTranscriptReviewForm">
          <div class="field"><label>参考录音实际逐字稿</label><textarea id="dhTranscriptReviewText" required style="min-height:150px;line-height:1.8">${dhEsc(voice.transcript || '')}</textarea><div class="muted">保存后，新提交或尚未开始语音合成的任务会使用这份逐字稿；已生成的成片需要重新生成。</div></div>
          <button class="primary wide">确认核对并保存</button>
        </form>`);
      $('modalRoot').querySelector('[data-close]')?.addEventListener('click', closeModal);
      $('dhTranscriptReviewForm').addEventListener('submit', async event => {
        event.preventDefault();
        const transcript = $('dhTranscriptReviewText').value.trim();
        if (!transcript) return toast('逐字稿不能为空');
        await api('/voices/' + voice.id, {method:'PATCH', body:{transcript, transcript_verified:true}});
        await loadLookups();
        closeModal();
        toast('逐字稿已更新');
        renderAvatars();
      });
    } catch (e) { toast(e.message); }
  }

  function voiceOptions(selected) {
    return '<option value="">— 请选择已有声音 —</option>' + (cache.voices || []).map(v => `<option value="${v.id}" ${v.id===selected?'selected':''}>${dhEsc(v.name)}</option>`).join('');
  }

  function digitalHumanModal(item=null) {
    dhState.recordingFile = null;
    const editing = !!item;
    const recordingPrompt = '大家好，欢迎来到今天的课程，很高兴和大家一起学习。';
    const recordText = recordingPrompt;
    openModal(`<div class="modal-head"><div><h2>${editing ? '编辑数字人' : '创建数字人'}</h2><div class="muted">人物、母版视频和声音在这里一次完成</div></div><button class="iconbtn" data-close>×</button></div>
      <form id="digitalHumanForm" data-id="${item?.id || ''}">
        <div class="field"><label>数字人名称</label><input id="dhName" value="${dhEsc(item?.name || '')}" required placeholder="例如：丹哥讲师"></div>
        <div class="field"><label>人物头像 ${editing ? '（不更换可留空）' : '（建议上传）'}</label><input id="dhImage" type="file" accept="image/png,image/jpeg,image/webp"><div id="dhImagePreview" style="margin-top:8px"></div></div>
        <div class="field"><label>母版视频 ${editing ? '（不更换可留空）' : '（必填）'}</label><input id="dhVideo" type="file" accept="video/mp4,video/quicktime,video/x-m4v" ${editing ? '' : 'required'}><div class="muted">建议正面半身、光线稳定、背景干净、20–30 秒自然口播。</div><div id="dhVideoPreview" style="margin-top:8px"></div></div>
        <div class="field"><label>声音设置</label><select id="dhVoiceMode">
          <option value="record">现场录制克隆声音</option>
          <option value="upload">上传参考录音</option>
          <option value="existing" ${editing ? 'selected' : ''}>使用已有声音</option>
        </select></div>
        <div id="dhRecordBlock">
          <div class="field"><label>固定逐字稿（录音必须一字不差）</label><textarea id="dhTranscript">${dhEsc(recordText)}</textarea><div style="margin-top:8px;padding:10px 12px;border-radius:9px;background:#21180d;border:1px solid #5e4729;color:#f2d29d">请照着上方文字朗读，不要增字、漏字、换词或调整语序。录错时请重新录制，不要修改逐字稿去迁就录音。</div></div>
          <div class="actions"><button type="button" class="primary" id="dhStartRecord">● 开始录音</button><button type="button" class="secondary" id="dhStopRecord" disabled>■ 停止</button><span class="muted" id="dhRecordStatus">建议录制 5–10 秒</span></div>
          <audio id="dhRecordedAudio" controls class="hidden" style="width:100%;margin-top:12px"></audio>
        </div>
        <div id="dhUploadVoiceBlock" class="hidden">
          <div class="field"><label>步骤 1 · 上传参考录音</label><input id="dhVoiceFile" type="file" accept="audio/*,.m4a,.wav,.mp3,.aac,.flac,.webm"><div id="dhUploadAudioPreview" style="margin-top:10px"></div></div>
          <div class="field"><label>步骤 2 · 播放录音并填写实际逐字稿</label><textarea id="dhUploadTranscript" required placeholder="请逐字填写录音中实际说出的完整文字，不要填写准备稿或内容摘要"></textarea><div style="margin-top:8px;padding:10px 12px;border-radius:9px;background:#21180d;border:1px solid #5e4729;color:#f2d29d">必须边播放边核对，确保每个字和语序都一致。示例文字、近似内容和漏字都会导致合成语音错乱。</div></div>
        </div>
        <div id="dhExistingVoiceBlock" class="hidden">
          <div class="field"><label>已有声音</label><select id="dhExistingVoice">${voiceOptions(item?.voice_profile_id || '')}</select></div>
          <div id="dhExistingTranscript"></div>
        </div>
        <div class="field"><label>人物备注 / 提示词（可选）</label><textarea id="dhPrompt">${dhEsc(item?.prompt || '')}</textarea></div>
        <label class="check"><input id="dhPortraitConsent" type="checkbox" ${editing ? '' : 'required'}><span>我确认已取得该人物肖像和母版视频用于数字人合成的合法授权。</span></label>
        <label class="check" id="dhVoiceConsentRow"><input id="dhVoiceConsent" type="checkbox"><span>我确认已取得该声音用于合成/克隆的合法授权。</span></label>
        <button class="primary wide">${editing ? '保存数字人' : '创建数字人'}</button>
      </form>`);

    $('modalRoot').querySelector('[data-close]')?.addEventListener('click', () => { stopRecorderSilently(); closeModal(); });
    $('dhVoiceMode').addEventListener('change', syncVoiceMode);
    $('dhImage').addEventListener('change', () => localFilePreview($('dhImage').files[0], 'image', $('dhImagePreview')));
    $('dhVideo').addEventListener('change', () => localFilePreview($('dhVideo').files[0], 'video', $('dhVideoPreview')));
    $('dhVoiceFile').addEventListener('change', () => localFilePreview($('dhVoiceFile').files[0], 'audio', $('dhUploadAudioPreview')));
    $('dhExistingVoice').addEventListener('change', syncExistingVoiceTranscript);
    $('dhStartRecord').addEventListener('click', startRecording);
    $('dhStopRecord').addEventListener('click', stopRecording);
    $('digitalHumanForm').addEventListener('submit', submitDigitalHuman);
    syncVoiceMode();
  }

  function localFilePreview(file, type, host) {
    host.innerHTML = '';
    if (!file) return;
    const url = URL.createObjectURL(file);
    dhState.previewUrls.push(url);
    host.innerHTML = type === 'image'
      ? `<img src="${url}" style="max-width:180px;max-height:150px;object-fit:cover;border-radius:10px">`
      : type === 'audio'
        ? `<audio src="${url}" controls style="width:100%"></audio>`
        : `<video src="${url}" controls style="width:100%;max-height:260px;background:#000;border-radius:10px"></video>`;
  }

  function syncExistingVoiceTranscript() {
    const host = $('dhExistingTranscript');
    if (!host) return;
    const voice = (cache.voices || []).find(v => v.id === $('dhExistingVoice')?.value);
    host.innerHTML = voice ? dhTranscriptPanel(voice) : '<div class="muted">选择声音后，这里会显示该参考录音的完整逐字稿。</div>';
  }

  function syncVoiceMode() {
    const mode = $('dhVoiceMode').value;
    $('dhRecordBlock').classList.toggle('hidden', mode !== 'record');
    $('dhUploadVoiceBlock').classList.toggle('hidden', mode !== 'upload');
    $('dhExistingVoiceBlock').classList.toggle('hidden', mode !== 'existing');
    $('dhVoiceConsentRow').classList.toggle('hidden', mode === 'existing');
    if (mode === 'existing') syncExistingVoiceTranscript();
  }

  async function startRecording() {
    try {
      dhState.stream = await navigator.mediaDevices.getUserMedia({audio:true});
      let mime = '';
      for (const candidate of ['audio/mp4','audio/webm;codecs=opus','audio/webm']) {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported(candidate)) { mime = candidate; break; }
      }
      dhState.chunks = [];
      dhState.recorder = mime ? new MediaRecorder(dhState.stream, {mimeType:mime}) : new MediaRecorder(dhState.stream);
      dhState.recorder.ondataavailable = e => { if (e.data?.size) dhState.chunks.push(e.data); };
      dhState.recorder.onstop = () => {
        const actualMime = dhState.recorder.mimeType || mime || 'audio/webm';
        const blob = new Blob(dhState.chunks, {type:actualMime});
        const ext = actualMime.includes('mp4') ? 'm4a' : 'webm';
        dhState.recordingFile = new File([blob], 'voice-reference.' + ext, {type:actualMime});
        const url = URL.createObjectURL(blob); dhState.previewUrls.push(url);
        $('dhRecordedAudio').src = url; $('dhRecordedAudio').classList.remove('hidden');
        $('dhRecordStatus').textContent = '录音完成，可以试听或重新录制';
        stopStream();
      };
      dhState.recorder.start(250);
      $('dhStartRecord').disabled = true; $('dhStopRecord').disabled = false;
      $('dhRecordStatus').textContent = '正在录音…';
    } catch (e) { toast('无法使用麦克风：' + e.message); }
  }

  function stopRecording() {
    if (dhState.recorder && dhState.recorder.state !== 'inactive') dhState.recorder.stop();
    $('dhStartRecord').disabled = false; $('dhStopRecord').disabled = true;
  }
  function stopStream() { if (dhState.stream) dhState.stream.getTracks().forEach(t => t.stop()); dhState.stream = null; }
  function stopRecorderSilently() { try { if (dhState.recorder && dhState.recorder.state !== 'inactive') dhState.recorder.stop(); } catch (_) {} stopStream(); }

  async function submitDigitalHuman(e) {
    e.preventDefault();
    const form = e.currentTarget, editing = !!form.dataset.id, mode = $('dhVoiceMode').value;
    const fd = new FormData();
    fd.append('name', $('dhName').value.trim());
    fd.append('prompt', $('dhPrompt').value || '');
    fd.append('portrait_consent', $('dhPortraitConsent').checked ? 'true' : 'false');
    fd.append('voice_consent', $('dhVoiceConsent').checked ? 'true' : 'false');
    const image = $('dhImage').files[0], video = $('dhVideo').files[0];
    if (image) fd.append('image_file', image);
    if (video) fd.append('master_video_file', video);
    if (mode === 'existing') {
      if ($('dhExistingVoice').value) fd.append('existing_voice_profile_id', $('dhExistingVoice').value);
      else if (!editing) return toast('请选择已有声音');
    } else {
      const voiceFile = mode === 'record' ? dhState.recordingFile : $('dhVoiceFile').files[0];
      const transcript = mode === 'record' ? $('dhTranscript').value.trim() : $('dhUploadTranscript').value.trim();
      if (!voiceFile) return toast(mode === 'record' ? '请先完成录音' : '请选择参考录音');
      if (!transcript) return toast('请填写参考录音逐字稿');
      if (!$('dhVoiceConsent').checked) return toast('请确认声音克隆授权');
      fd.append('voice_file', voiceFile);
      fd.append('voice_transcript', transcript);
      fd.append('voice_name', $('dhName').value.trim() + '的声音');
    }
    if (!editing && !video) return toast('当前 MuseTalk 数字人必须上传母版视频');
    if (!editing && !$('dhPortraitConsent').checked) return toast('请确认人物肖像/视频授权');

    try {
      const path = editing ? '/digital-humans/' + form.dataset.id : '/digital-humans';
      await api(path, {method: editing ? 'PATCH' : 'POST', body: fd});
      stopRecorderSilently();
      await loadLookups();
      closeModal();
      toast(editing ? '数字人已更新' : '数字人创建成功');
      showPage('avatars');
    } catch (err) { toast(err.message); }
  }

  courseModal = function(c=null) {
    c = c || {title:'',ppt_asset_id:'',avatar_id:'',voice_profile_id:'',script:[]};
    const ppts = cache.assets.filter(a => a.kind === 'ppt' || a.name.toLowerCase().endsWith('.pptx'));
    const selectedAvatar = cache.avatars.find(a => a.id === c.avatar_id);
    const currentIsDefault = selectedAvatar && c.voice_profile_id === selectedAvatar.voice_profile_id;
    const overrideId = currentIsDefault ? '' : (c.voice_profile_id || '');
    openModal(`<div class="modal-head"><h2>${c.id?'编辑':'新建'}课程</h2><button class="iconbtn" data-close>×</button></div><form id="dhCourseForm" data-id="${c.id||''}">
      <div class="field"><label>课程名称</label><input id="cTitle" value="${dhEsc(c.title)}" required></div>
      <div class="field"><label>PPT</label><select id="cPpt">${opts(ppts,c.ppt_asset_id)}</select></div>
      <div class="field"><label>数字人</label><select id="cAvatar">${opts(cache.avatars,c.avatar_id)}</select><div class="muted" id="cDefaultVoice"></div></div>
      <details style="margin:12px 0"><summary style="cursor:pointer;color:#aebbd0">高级：覆盖数字人默认声音</summary><div class="field"><label>临时使用其他声音</label><select id="cVoiceOverride">${voiceOptions(overrideId)}</select><div class="muted">留空时自动使用数字人的默认克隆声音。</div></div></details>
      <div class="field"><label>按页讲稿 JSON</label><textarea id="cScript">${dhEsc(JSON.stringify(c.script||[],null,2))}</textarea></div>
      <button class="primary wide">保存</button></form>`);
    $('modalRoot').querySelector('[data-close]')?.addEventListener('click', closeModal);
    const updateVoiceText = () => {
      const avatar = cache.avatars.find(a => a.id === $('cAvatar').value);
      const voice = cache.voices.find(v => v.id === avatar?.voice_profile_id);
      $('cDefaultVoice').textContent = avatar ? ('默认声音：' + (voice?.name || avatar.voice?.name || '未配置')) : '请选择数字人';
    };
    $('cAvatar').addEventListener('change', updateVoiceText); updateVoiceText();
    $('dhCourseForm').addEventListener('submit', async e => {
      e.preventDefault();
      try {
        const script = JSON.parse($('cScript').value || '[]'), id = e.currentTarget.dataset.id;
        const avatar = cache.avatars.find(a => a.id === $('cAvatar').value);
        const effectiveVoice = $('cVoiceOverride').value || avatar?.voice_profile_id || null;
        if (avatar && !effectiveVoice) return toast('这个数字人还没有可用的默认声音');
        await api('/courses' + (id ? '/' + id : ''), {method:id?'PATCH':'POST', body:{title:$('cTitle').value,ppt_asset_id:$('cPpt').value||null,avatar_id:$('cAvatar').value||null,voice_profile_id:effectiveVoice,script}});
        await loadLookups(); closeModal(); showPage('courses');
      } catch (err) { toast(err.message); }
    });
  };

  renderModal = function(id) {
    openModal(`<div class="modal-head"><h2>提交生成</h2><button class="iconbtn" data-close>×</button></div><form id="dhRenderForm" data-id="${id}">
      <div class="field"><label>预计时长（秒）</label><input id="renderSecs" type="number" min="1" max="21600" value="60"><div class="muted">服务端会重新估算，并按实际成片时长结算。</div></div>
      <div class="field"><label>引擎</label><select id="renderEngine"><option value="musetalk">MuseTalk</option><option value="mock">Mock 联调</option></select></div>
      <div class="field"><label>已有配音素材（可选）</label><select id="renderAudio">${opts(cache.assets.filter(a=>a.kind==='audio'),'')}</select></div>
      <button class="primary wide">加入队列</button></form>`);
    $('modalRoot').querySelector('[data-close]')?.addEventListener('click', closeModal);
    $('dhRenderForm').addEventListener('submit', async e => {
      e.preventDefault();
      try {
        let course = await api('/courses/' + id);
        if (!course.voice_profile_id && course.avatar_id) {
          const avatar = cache.avatars.find(a => a.id === course.avatar_id) || await api('/digital-humans/' + course.avatar_id);
          if (avatar?.voice_profile_id) {
            course = await api('/courses/' + id, {method:'PATCH', body:{voice_profile_id:avatar.voice_profile_id}});
          }
        }
        await api('/courses/' + id + '/render', {method:'POST', body:{engine:$('renderEngine').value,estimated_seconds:Number($('renderSecs').value),audio_asset_id:$('renderAudio').value||null}});
        closeModal(); showPage('jobs');
      } catch (err) { toast(err.message); }
    });
  };

  const oldLoadLookups = loadLookups;
  loadLookups = async function() {
    await oldLoadLookups();
    try { cache.avatars = await api('/digital-humans'); } catch (_) {}
  };
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
