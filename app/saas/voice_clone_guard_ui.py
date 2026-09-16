from __future__ import annotations

from fastapi.responses import Response


JS = r'''
(() => {
  const RECORDING_PROMPT = '大家好，欢迎来到今天的课程，很高兴和大家一起学习。';

  function applyRecordingPrompt() {
    const mode = document.getElementById('dhVoiceMode');
    const transcript = document.getElementById('dhTranscript');
    const status = document.getElementById('dhRecordStatus');
    if (!mode || !transcript) return;

    if (mode.value === 'record') {
      transcript.value = RECORDING_PROMPT;
      transcript.readOnly = true;
      transcript.setAttribute('aria-readonly', 'true');
      transcript.style.background = '#0a1119';
      transcript.style.color = '#dce8f7';
      if (status && !status.dataset.cloneGuard) {
        status.dataset.cloneGuard = '1';
        status.textContent = '请逐字朗读上方固定文本，建议 5–10 秒；不要增字、漏字或自行换句。';
      }
      if (!document.getElementById('dhCloneAccuracyHint')) {
        const hint = document.createElement('div');
        hint.id = 'dhCloneAccuracyHint';
        hint.className = 'muted';
        hint.style.cssText = 'margin-top:8px;line-height:1.65;color:#8fa6bf';
        hint.textContent = 'CosyVoice Zero-shot 要求参考录音与参考逐字稿准确对应。录错时请重新录制，不要只修改文字。';
        transcript.insertAdjacentElement('afterend', hint);
      }
    }
  }

  document.addEventListener('change', event => {
    if (event.target?.id === 'dhVoiceMode') setTimeout(applyRecordingPrompt, 0);
  }, true);

  const observer = new MutationObserver(() => applyRecordingPrompt());
  observer.observe(document.body, {childList: true, subtree: true});
  setTimeout(applyRecordingPrompt, 0);
})();
'''


def javascript_response() -> Response:
    return Response(JS, media_type="application/javascript; charset=utf-8")
