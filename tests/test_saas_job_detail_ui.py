from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _job_detail_js() -> str:
    text = (ROOT / "app" / "saas" / "job_detail_ui.py").read_text(encoding="utf-8")
    match = re.search(r"JS = r'''(.*?)'''", text, re.S)
    assert match is not None, "job_detail_ui.py is missing the JS payload"
    return match.group(1)


JS = _job_detail_js()


def test_job_detail_javascript_syntax(tmp_path: Path) -> None:
    if shutil.which("node") is None:
        pytest.skip("node required for browser JavaScript syntax check")
    script = tmp_path / "job-detail.js"
    script.write_text(JS, encoding="utf-8")
    proc = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_job_detail_javascript_consumes_distributed_tasks() -> None:
    assert "pageTasks(d)" in JS
    assert "d.distributed" in JS
    assert "d.tasks" in JS
    assert "slideMatrix(d)" in JS
    assert "pages_running" in JS
    assert "clearTimeout(detailTimer)" in JS
    assert "未分配节点" in JS
    assert "elapsedSeconds(d)" in JS
    assert "etaSeconds(d,elapsed)" in JS
    assert "data-job-video-preview" in JS
    assert "hydrateResultVideo" in JS
    assert "Authorization:'Bearer '+token" in JS
    assert "预计剩余时间" in JS


@pytest.mark.skipif(shutil.which("node") is None, reason="node required to execute job-detail helpers")
def test_job_detail_javascript_renders_parallel_page_progress(tmp_path: Path) -> None:
    harness = tmp_path / "job-detail-harness.js"
    payload = {
        "id": "job-distributed-progress-1",
        "course_title": "并行分页课程",
        "engine": "musetalk",
        "status": "running",
        "progress": 14,
        "stage": "distributed_pages",
        "runtime": {},
        "distributed": {
            "enabled_for_job": True,
            "page_count": 19,
            "pages_succeeded": 0,
            "pages_running": 3,
            "pages_queued": 16,
            "pages_failed": 0,
        },
        "tasks": [
            {"type": "prepare", "status": "succeeded", "progress": 100, "stage": "completed", "slide_index": 0, "node": None},
            {
                "type": "page",
                "slide_index": 10,
                "status": "running",
                "progress": 40,
                "stage": "video_start",
                "node": {"name": "mini-64", "host": "192.168.1.64", "machine": "M4"},
            },
            {
                "type": "page",
                "slide_index": 14,
                "status": "running",
                "progress": 20,
                "stage": "audio_start",
                "node": {"name": "local", "host": "127.0.0.1", "machine": "M5"},
            },
            {
                "type": "page",
                "slide_index": 17,
                "status": "running",
                "progress": 40,
                "stage": "video_start",
                "node": {"name": "mini-89", "host": "192.168.1.89", "machine": "M4"},
            },
            {"type": "page", "slide_index": 1, "status": "queued", "progress": 0, "stage": "queued", "node": None},
            {"type": "finalize", "status": "blocked", "progress": 0, "stage": "blocked", "slide_index": 0, "node": None},
        ],
    }
    harness.write_text(
        "\n".join(
            [
                "global.document = {",
                "  createElement: () => ({ innerHTML: '', querySelectorAll: () => [], querySelector: () => null, appendChild() {}, dataset: {} }),",
                "  getElementById: () => null,",
                "  querySelectorAll: () => [],",
                "  addEventListener() {},",
                "  body: { appendChild() {}, querySelector: () => null },",
                "};",
                "global.window = global;",
                "global.MutationObserver = class { observe() {} disconnect() {} };",
                "global.setInterval = () => 0;",
                "global.setTimeout = () => 0;",
                "const src = " + json.dumps(JS) + ";",
                "const rewritten = src",
                "  .replace('(() => {', 'global.__jobDetail = (() => {')",
                "  .replace(/\\}\\)\\(\\);\\s*$/, 'return {renderShell, slideMatrix, liveLogic, distributedPhase};\\n})();');",
                "eval(rewritten);",
                "const d = " + json.dumps(payload) + ";",
                "const html = global.__jobDetail.renderShell(d);",
                "if (!html.includes('3 页并行生成')) throw new Error('missing parallel headline');",
                "if (!html.includes('SLIDE 10')) throw new Error('missing slide 10');",
                "if (!html.includes('SLIDE 14')) throw new Error('missing slide 14');",
                "if (!html.includes('mini-64')) throw new Error('missing node name');",
                "if (!html.includes('14%')) throw new Error('missing parent progress');",
                "if (!html.includes('3 页生成中')) throw new Error('missing running summary');",
                "if (html.includes('任务尚未进入逐页生产阶段')) throw new Error('still showing empty matrix');",
                "const live = global.__jobDetail.liveLogic(d);",
                "if (!live.includes('第 10 页')) throw new Error('missing live page 10');",
                "if (!live.includes('数字人驱动')) throw new Error('missing video stage label');",
                "console.log('ok');",
                "process.exit(0);",
            ]
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(["node", str(harness)], capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node required to execute job-detail helpers")
def test_job_detail_javascript_fills_elapsed_and_eta_without_runtime(tmp_path: Path) -> None:
    now_ms = 1_700_000_000_000
    payload = {
        "id": "job-distributed-timing-1",
        "status": "running",
        "progress": 40,
        "stage": "distributed_pages",
        "runtime": {},
        "gpu_seconds": None,
        "estimated_seconds": 900,
        "started_at": "2023-11-14T22:12:50.000Z",
        "created_at": "2023-11-14T22:12:40.000Z",
        "completed_at": None,
        "distributed": {
            "enabled_for_job": True,
            "page_count": 4,
            "pages_succeeded": 1,
            "pages_running": 2,
            "pages_queued": 1,
            "pages_failed": 0,
        },
        "tasks": [
            {
                "type": "page",
                "slide_index": 1,
                "status": "succeeded",
                "progress": 100,
                "started_at": "2023-11-14T22:12:50.000Z",
                "completed_at": "2023-11-14T22:13:20.000Z",
            },
            {"type": "page", "slide_index": 2, "status": "running", "progress": 50, "stage": "video_start"},
            {"type": "page", "slide_index": 3, "status": "running", "progress": 20, "stage": "audio_start"},
            {"type": "page", "slide_index": 4, "status": "queued", "progress": 0, "stage": "queued"},
            {"type": "finalize", "status": "blocked", "progress": 0, "estimated_seconds": 25},
        ],
    }
    done = {
        **payload,
        "id": "job-distributed-timing-done",
        "status": "succeeded",
        "progress": 100,
        "completed_at": "2023-11-14T22:15:20.000Z",
        "tasks": [
            {
                "type": "page",
                "slide_index": 1,
                "status": "succeeded",
                "progress": 100,
                "started_at": "2023-11-14T22:12:50.000Z",
                "completed_at": "2023-11-14T22:15:20.000Z",
            }
        ],
    }
    harness = tmp_path / "job-detail-timing.js"
    harness.write_text(
        "\n".join(
            [
                "global.document = {createElement: () => ({ innerHTML: '', querySelectorAll: () => [], querySelector: () => null, appendChild() {}, dataset: {} }), getElementById: () => null, querySelectorAll: () => [], addEventListener() {}, body: { appendChild() {}, querySelector: () => null }};",
                "global.window = global;",
                "global.MutationObserver = class { observe() {} disconnect() {} };",
                "global.setInterval = () => 0;",
                "global.setTimeout = () => 0;",
                f"Date.now = () => {now_ms};",
                "const src = " + json.dumps(JS) + ";",
                "const rewritten = src.replace('(() => {', 'global.__jobDetail = (() => {').replace(/\\}\\)\\(\\);\\s*$/, 'return {renderShell, elapsedSeconds, etaSeconds};\\n})();');",
                "eval(rewritten);",
                "const running = " + json.dumps(payload) + ";",
                "const done = " + json.dumps(done) + ";",
                "const elapsed = global.__jobDetail.elapsedSeconds(running);",
                "const eta = global.__jobDetail.etaSeconds(running, elapsed);",
                "if (Math.abs(elapsed - 30) > 0.01) throw new Error('expected 30s elapsed, got ' + elapsed);",
                "if (!(eta > 0)) throw new Error('expected positive eta, got ' + eta);",
                "const html = global.__jobDetail.renderShell(running);",
                "const elapsedHtml = (html.match(/ELAPSED<\\/div><div class=\\\"metric\\\">([^<]+)/) || [])[1];",
                "const etaHtml = (html.match(/ETA<\\/div><div class=\\\"metric\\\">([^<]+)/) || [])[1];",
                "if (elapsedHtml !== '30秒') throw new Error('missing elapsed 30秒, got ' + elapsedHtml);",
                "if (!etaHtml || etaHtml === '—') throw new Error('eta still empty: ' + etaHtml);",
                "const doneElapsed = global.__jobDetail.elapsedSeconds(done);",
                "if (Math.abs(doneElapsed - 150) > 0.01) throw new Error('expected 150s completed elapsed, got ' + doneElapsed);",
                "const doneHtml = global.__jobDetail.renderShell(done);",
                "if (!doneHtml.includes('2分30秒')) throw new Error('completed elapsed should use minutes and seconds');",
                "if (global.__jobDetail.etaSeconds(done, doneElapsed) != null) throw new Error('completed jobs should not show eta');",
                "console.log('ok');",
                "process.exit(0);",
            ]
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(["node", str(harness)], capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout
