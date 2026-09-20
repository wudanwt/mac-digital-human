from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app.saas.course_avatar_mode_ui import JS
from app.saas.course_studio_ui import JS as STUDIO_JS


def test_course_avatar_mode_ui_persists_and_previews_modes(tmp_path: Path) -> None:
    assert "avatar_mode" in JS
    assert "transparent" in JS
    assert "white" in JS
    assert "original" in JS
    assert "alph" not in JS.lower()  # browser preview consumes the cutout poster, not mask processing
    assert "/avatar-matting/" in JS
    assert "将当前模式应用到全部页面" in JS
    assert "Number(active.dataset.layoutSlide)+1" in JS
    assert "document.addEventListener('click'" in JS
    assert "section.dataset.avatarModeState===renderKey" in JS
    assert "r.addedNodes" in JS
    assert "section.querySelectorAll('[data-avatar-mode]').forEach" not in JS
    assert "window.__courseStudioSlides" in JS
    assert "slide.avatar_mode=mode" in JS
    assert "avatar_mode:s.avatar_mode||'original'" in STUDIO_JS
    assert "s.layout=src.layout" in STUDIO_JS
    assert "window.__courseAvatarModeCurrent?.()" in STUDIO_JS
    assert "window.__courseAvatarModeApplyAll?.(mode)" in STUDIO_JS
    assert "window.__courseAvatarModeCurrent=()=>currentMode()" in JS
    assert "window.__courseAvatarModeApplyAll=mode=>applyModeAll(mode)" in JS
    assert "for(let i=1;i<=totalSlides();i++)setMode(i,resolved)" in JS

    node = shutil.which("node")
    if node:
        script = tmp_path / "course-avatar-mode.js"
        script.write_text(JS, encoding="utf-8")
        proc = subprocess.run([node, "--check", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        studio_script = tmp_path / "course-studio.js"
        studio_script.write_text(STUDIO_JS, encoding="utf-8")
        studio_proc = subprocess.run([node, "--check", str(studio_script)], capture_output=True, text=True)
        assert studio_proc.returncode == 0, studio_proc.stderr


def test_apply_all_updates_the_mode_map_used_by_the_save_wrapper(tmp_path: Path) -> None:
    node = shutil.which("node")
    if not node:
        return
    harness = tmp_path / "apply-all-avatar-mode.js"
    harness.write_text(
        f"""
global.window = {{
  fetch: async (input, init={{}}) => {{
    if (String(init.method||'GET').toUpperCase() === 'PATCH') global.savedBody = init.body;
    return {{ok:true, clone:()=>({{json:async()=>course}})}};
  }},
  openCourseStudio: course => {{ window.__courseStudioSlides = course.script; }}
}};
global.document = {{
  documentElement: {{}},
  addEventListener: () => {{}},
  querySelector: selector => selector === '[data-layout-slide].active' ? {{dataset:{{layoutSlide:'1'}}}} : null,
  querySelectorAll: selector => selector === '[data-layout-slide]' ? [{{}}, {{}}] : [],
  getElementById: id => id === 'courseStudioShell' ? {{}} : null
}};
global.MutationObserver = class {{ observe() {{}} }};
global.setTimeout = () => 1;
global.clearTimeout = () => {{}};
eval({json.dumps(JS)});
const course = {{id:'course-1', avatar_id:'avatar-1', script:[
  {{index:1, avatar_mode:'original'}},
  {{index:2, avatar_mode:'transparent'}}
]}};
window.openCourseStudio(course);
const mode = window.__courseAvatarModeCurrent();
window.__courseAvatarModeApplyAll(mode);
if (course.script.some(slide => slide.avatar_mode !== 'transparent')) throw new Error('slide state was not updated');
(async () => {{
  // The background editor performs this GET before its PATCH. It must not
  // reseed the live mode map from the stale server snapshot.
  await window.fetch('/api/saas/courses/course-1');
  await Promise.resolve();
  await window.fetch('/api/saas/courses/course-1', {{method:'PATCH', body:JSON.stringify({{script:course.script}})}});
  const saved = JSON.parse(global.savedBody);
  if (saved.script.some(slide => slide.avatar_mode !== 'transparent')) throw new Error('save wrapper restored stale modes');
}})().catch(error => {{ console.error(error); process.exit(1); }});
""",
        encoding="utf-8",
    )
    proc = subprocess.run([node, str(harness)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
