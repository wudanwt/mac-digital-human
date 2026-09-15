from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .config import settings
from .jobs import manager
from .lecture import lecture_job_manager
from .ppt import CourseDeck, PresentationParser, PPTRenderer
from .presets import (
    create_avatar_profile,
    delete_avatar_profile,
    get_avatar_profile,
    get_prompt_preset,
    list_avatar_profiles,
    list_prompt_presets,
    update_avatar_profile,
)



app = FastAPI(title="Mac Digital Human - PPT Micro-Course Studio", version="0.4.0")

HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Mac Digital Human - PPT 授课数字人微课制作平台</title>
<style>
:root{color-scheme:dark}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;background:#090b10;color:#eef2ff;margin:0;padding-bottom:60px}
header{background:#11151f;border-bottom:1px solid #1f2737;padding:16px 24px;position:sticky;top:0;z-index:100;display:flex;align-items:center;justify-content:space-between}
.logo-title{font-size:18px;font-weight:700;display:flex;align-items:center;gap:10px}
.nav-tabs{display:flex;gap:8px}
.nav-tab{padding:8px 18px;border-radius:8px;cursor:pointer;font-size:14px;font-weight:600;background:transparent;border:1px solid transparent;color:#94a3b8;transition:all .15s}
.nav-tab:hover{color:#fff;background:#182030}
.nav-tab.active{background:#1e293b;border-color:#3b82f6;color:#60a5fa}
main{max-width:1120px;margin:32px auto;padding:0 20px}
.card{background:#131722;border:1px solid #232c3f;border-radius:18px;padding:28px;box-shadow:0 16px 48px #00000055}
h1{font-size:26px;margin:0 0 8px;font-weight:750}
.muted{color:#94a3b8;line-height:1.6;font-size:14px}
.grid{display:grid;gap:18px;margin-top:22px}
label{font-weight:600;font-size:14px;color:#cbd5e1;display:block;margin-bottom:6px}
input,select,textarea,button{width:100%;box-sizing:border-box;padding:12px 14px;border-radius:10px;border:1px solid #2d3748;background:#0c0f17;color:#fff;font-size:14px}
textarea{min-height:90px;resize:vertical;line-height:1.5}
button.primary-btn{background:linear-gradient(135deg,#2563eb,#3b82f6);color:#fff;font-weight:700;cursor:pointer;border:0;box-shadow:0 4px 14px #2563eb44;transition:opacity .2s}
button.primary-btn:hover{opacity:0.92}
button.primary-btn:disabled{opacity:0.5;cursor:not-allowed}
.modes{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.mode{border:1px solid #2d3748;border-radius:14px;padding:16px;cursor:pointer;background:#0c0f17}
.mode.active{border-color:#3b82f6;background:#111c30}
.mode b{display:block;margin-bottom:5px;font-size:15px}
.panel{display:none}.panel.active{display:grid;gap:18px}
.status-box{white-space:pre-wrap;background:#0a0d14;padding:18px;border-radius:12px;border:1px solid #1f2737;min-height:64px;line-height:1.6;font-size:14px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.tip{font-size:12px;color:#64748b;margin-top:5px}
.badge{display:inline-block;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700;background:#1e293b;color:#94a3b8}

/* PPT Micro-Course Studio Styles */
.step-banner{display:flex;align-items:center;gap:12px;padding:14px 18px;background:#161d2d;border:1px solid #28354d;border-radius:12px;margin-bottom:20px}
.step-num{background:#3b82f6;color:#fff;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:13px}
.step-title{font-weight:700;font-size:15px;color:#e2e8f0}
.slide-card{background:#0c0f17;border:1px solid #232c3f;border-radius:14px;padding:18px;display:grid;grid-template-columns:360px 1fr;gap:20px;align-items:start;margin-bottom:16px;transition:border-color .2s}
.slide-card:hover{border-color:#3b82f6}
.slide-thumb-container{width:100%;aspect-ratio:16/9;background:#06080d;border-radius:10px;overflow:hidden;border:1px solid #1e293b;position:relative}
.slide-thumb{width:100%;height:100%;object-fit:cover;display:block}
.slide-meta{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.slide-badge{background:#2563eb;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700}
.slide-layout-select{padding:8px 12px;font-size:13px;background:#141a27;border-color:#2a364d}
.progress-bar-bg{width:100%;height:10px;background:#1e293b;border-radius:6px;overflow:hidden;margin:12px 0}
.progress-bar-fill{height:100%;background:#3b82f6;width:0%;transition:width .3s}
.video-preview-box{margin-top:20px;background:#0a0d14;border:1px solid #232c3f;border-radius:14px;padding:20px;text-align:center}
video{max-width:100%;border-radius:10px;box-shadow:0 8px 32px #0008}
/* Profile Studio Styles */
.profile-card{background:#0c0f17;border:1px solid #232c3f;border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:12px;transition:all .2s;position:relative}
.profile-card:hover{border-color:#3b82f6;transform:translateY(-2px)}
.profile-avatar-wrap{width:100%;aspect-ratio:1/1;max-height:180px;background:#07090e;border-radius:10px;overflow:hidden;border:1px solid #1e293b;display:flex;align-items:center;justify-content:center}
.profile-avatar-img{width:100%;height:100%;object-fit:cover}
.profile-tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;background:#1e293b;color:#94a3b8}
.profile-tag.voice{background:#065f46;color:#a7f3d0}
.profile-tag.video{background:#1e40af;color:#bfdbfe}

/* 4-Phase Stepper */
.phase-stepper{display:flex;align-items:center;justify-content:space-between;background:#0d121c;border:1px solid #1f2a3e;border-radius:14px;padding:18px 24px;margin-bottom:18px}
.phase-step{display:flex;flex-direction:column;align-items:center;gap:6px;position:relative;z-index:2}
.phase-icon{width:36px;height:36px;border-radius:50%;background:#1e293b;color:#94a3b8;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;transition:all .3s}
.phase-step.active .phase-icon{background:linear-gradient(135deg,#2563eb,#3b82f6);color:#fff;box-shadow:0 0 16px #3b82f688;transform:scale(1.08)}
.phase-step.done .phase-icon{background:#059669;color:#fff}
.phase-label{font-size:12px;font-weight:600;color:#94a3b8}
.phase-step.active .phase-label{color:#60a5fa}
.phase-step.done .phase-label{color:#34d399}
.phase-line{flex:1;height:2px;background:#1e293b;margin:0 10px;margin-top:-18px;transition:background .3s}
.phase-line.done{background:#059669}

/* Real-time Status HUD */
.hud-card{background:#0c0f17;border:1px solid #232c3f;border-radius:14px;padding:18px;margin-bottom:18px}
.hud-grid{display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:14px;margin-top:12px}
.hud-item{background:#111622;border:1px solid #1e2638;border-radius:10px;padding:12px 14px}
.hud-title{font-size:12px;color:#94a3b8;margin-bottom:4px}
.hud-val{font-size:18px;font-weight:750;color:#f8fafc}
.hud-detail{font-size:13px;color:#38bdf8;margin-top:8px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}

/* Slide Progress Matrix */
.slide-matrix{display:grid;grid-template-columns:repeat(auto-fill, minmax(210px, 1fr));gap:10px;margin-top:14px}
.matrix-card{background:#111622;border:1px solid #1e2638;border-radius:8px;padding:12px;font-size:12px}
.matrix-badge{display:inline-block;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:700}
.matrix-badge.pending{background:#1e293b;color:#64748b}
.matrix-badge.running{background:#1d4ed8;color:#93c5fd;animation:pulse 1.5s infinite}
.matrix-badge.done{background:#065f46;color:#6ee7b7}
@keyframes pulse{0%{opacity:1}50%{opacity:0.6}100%{opacity:1}}

/* 4-Step Wizard Bar */
.wizard-bar{display:flex;align-items:center;justify-content:space-between;background:#0d121c;border:1px solid #1f2a3e;border-radius:14px;padding:12px 18px;margin-bottom:24px}
.wizard-node{display:flex;align-items:center;gap:10px;cursor:pointer;opacity:0.55;transition:all .2s;padding:6px 12px;border-radius:10px}
.wizard-node:hover{opacity:0.9;background:#141a27}
.wizard-node.active{opacity:1;background:#162032;border:1px solid #2563eb66}
.wizard-node.done .wizard-num{background:#059669;color:#fff}
.wizard-num{width:28px;height:28px;border-radius:50%;background:#1e293b;color:#94a3b8;display:flex;align-items:center;justify-content:center;font-weight:750;font-size:13px;flex-shrink:0}
.wizard-node.active .wizard-num{background:linear-gradient(135deg,#2563eb,#3b82f6);color:#fff;box-shadow:0 0 12px #3b82f688}
.wizard-step-name{font-weight:700;font-size:13px;color:#f1f5f9}
.wizard-step-sub{font-size:11px;color:#64748b}
.wizard-divider{flex:1;height:2px;background:#1e293b;margin:0 10px}

/* Step Panels */
.wizard-panel{display:none}
.wizard-panel.active{display:block}

/* Visual Drag-and-Drop Canvas Studio */
.canvas-studio-wrap{display:grid;grid-template-columns:minmax(0,1fr) 340px;align-items:start;gap:16px;margin-top:16px}
.canvas-main-col{display:flex;flex-direction:column;gap:14px;min-width:0}
.canvas-toolbar{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:12px;min-width:0;background:#0c0f17;border:1px solid #1f2737;border-radius:12px;padding:10px 12px}
.canvas-toolbar-nav{display:flex;align-items:center;gap:8px;white-space:nowrap}
.canvas-toolbar-action{width:auto;padding:6px 12px;font-size:12px;background:#1e3a8a;border-color:#3b82f6;color:#93c5fd;font-weight:600;white-space:nowrap}
.canvas-viewport{position:relative;width:min(100%,853.333px);aspect-ratio:16/9;background:#05070c;border-radius:14px;overflow:hidden;border:2px solid #2563eb66;box-shadow:0 16px 40px #0008;user-select:none;margin:0 auto}
.canvas-controls-col{position:sticky;top:88px;display:flex;flex-direction:column;gap:10px;max-height:calc(100vh - 112px);min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:0 4px 4px 0;scrollbar-width:thin;scrollbar-color:#334155 transparent}
.canvas-controls-col::-webkit-scrollbar{width:6px}
.canvas-controls-col::-webkit-scrollbar-thumb{background:#334155;border-radius:999px}
.canvas-controls-col .hud-item{padding:12px 14px}
.canvas-controls-col label{margin-bottom:6px}
.canvas-controls-actions{position:sticky;bottom:0;z-index:4;display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:2px;padding:10px 0 2px;background:linear-gradient(180deg,transparent 0,#131722 22px,#131722 100%)}
.canvas-controls-actions button{padding:9px 6px;font-size:12px;border-radius:8px}
.slide-ribbon-panel{min-width:0;margin-top:2px;padding:10px 12px 4px;background:#0c0f1788;border:1px solid #1f2737;border-radius:12px}
.canvas-bg-layer{position:absolute;inset:0;background-size:cover;background-position:center;transition:background-image .3s ease;pointer-events:none}
.canvas-blur-bg{position:absolute;inset:-25px;background-size:cover;background-position:center;filter:blur(32px) brightness(0.65);transform:scale(1.15);pointer-events:none;transition:all .3s}

/* Multi-layer Draggable Boxes */
.drag-layer-box{position:absolute;touch-action:none;cursor:grab;transition:border-color .15s, box-shadow .15s;overflow:hidden}
.drag-layer-box:active{cursor:grabbing}
.drag-layer-box.active{z-index:15 !important}

/* PPT Box Specific */
.drag-ppt-box{border:2px solid #3b82f6aa;border-radius:10px;background:#000000;box-shadow:0 12px 36px rgba(0,0,0,0.8), 0 0 16px #3b82f633;z-index:5}
.drag-ppt-box.active{border-color:#38bdf8;box-shadow:0 0 0 2px #38bdf8, 0 16px 44px #000e}
.drag-ppt-box.fullscreen{border-style:dashed;border-color:#38bdf844;border-radius:0;box-shadow:none}
.ppt-inner-img{width:100%;height:100%;background-size:contain;background-repeat:no-repeat;background-position:center;pointer-events:none}

/* Avatar Box Specific */
.drag-avatar-box{border:2px solid #38bdf8;border-radius:10px;background:#00000055;backdrop-filter:blur(6px);box-shadow:0 8px 24px #000a,0 0 14px #38bdf844;z-index:8}
.drag-avatar-box.active{border-color:#60a5fa;box-shadow:0 0 0 2px #60a5fa, 0 0 20px #38bdf8aa}
.drag-avatar-img{width:100%;height:100%;object-fit:contain;background-position:center bottom;pointer-events:none;display:block}

/* Global Toast */
.global-toast{position:fixed;top:28px;left:50%;transform:translateX(-50%);background:#0f172aee;backdrop-filter:blur(12px);border:1px solid #38bdf888;color:#f8fafc;padding:12px 24px;border-radius:30px;font-size:14px;font-weight:600;box-shadow:0 12px 32px #000a,0 0 16px #38bdf844;z-index:99999;display:none;align-items:center;gap:10px;animation:toastFadeIn .25s cubic-bezier(0.16,1,0.3,1)}
@keyframes toastFadeIn{from{opacity:0;transform:translate(-50%,-10px)}to{opacity:1;transform:translate(-50%,0)}}

/* Tag Badges */
.drag-layer-tag{position:absolute;top:6px;left:6px;padding:3px 8px;border-radius:4px;font-size:10px;font-weight:700;pointer-events:none;display:flex;align-items:center;gap:4px;z-index:20}
.drag-layer-tag.ppt{background:#0f172acc;border:1px solid #3b82f6;color:#93c5fd}
.drag-layer-tag.avatar{background:#0f172acc;border:1px solid #38bdf8;color:#7dd3fc}

.resize-handle{position:absolute;right:0;bottom:0;width:22px;height:22px;background:#38bdf8;cursor:nwse-resize;border-top-left-radius:6px;border-bottom-right-radius:6px;box-shadow:0 0 8px #38bdf8;z-index:25;display:flex;align-items:center;justify-content:center;font-size:12px;color:#000;font-weight:900}
.canvas-sub-preview{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);max-width:85%;background:#090d16d0;border:1px solid #334155aa;color:#fff;padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:none;box-shadow:0 4px 14px #0009;z-index:30}
.canvas-hud-coord{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center;font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#94a3b8}

/* Layer Switch Tabs */
.layer-selector-bar{display:flex;gap:6px;background:#090d16;padding:4px;border-radius:8px;border:1px solid #1e2638;margin-bottom:12px}
.layer-tab-btn{flex:1;padding:8px 4px;font-size:12px;font-weight:700;border-radius:6px;border:none;background:transparent;color:#94a3b8;cursor:pointer;text-align:center;transition:all .15s}
.layer-tab-btn.active{background:#1e3a8a;color:#93c5fd;box-shadow:0 2px 8px #1e3a8a88}

/* Slide Thumbnail Ribbon */
.slide-ribbon{display:flex;align-items:flex-start;gap:10px;width:100%;min-width:0;max-width:100%;overflow-x:auto;overflow-y:hidden;padding:8px 2px 12px;box-sizing:border-box}
.ribbon-item{flex:0 0 130px;width:130px;height:73.125px;border-radius:8px;overflow:hidden;border:2px solid #1e293b;box-sizing:border-box;cursor:pointer;position:relative;background:#090b10;transition:all .2s}
.ribbon-item.active{border-color:#38bdf8;box-shadow:0 0 12px #38bdf866;transform:scale(1.03)}
.ribbon-thumb{display:block;width:100%;height:100%;object-fit:cover}
.ribbon-badge{position:absolute;bottom:4px;left:4px;background:#0f172acc;padding:1px 5px;border-radius:4px;font-size:10px;color:#cbd5e1}

.snap-btn-group{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.snap-btn{padding:8px 4px;font-size:12px;font-weight:600;background:#111622;border:1px solid #232c3f;border-radius:6px;color:#cbd5e1;cursor:pointer;text-align:center;transition:all .15s}
.snap-btn:hover{background:#1e293b;color:#fff;border-color:#38bdf8}
.action-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:18px;padding-top:16px;border-top:1px solid #1f2737}

/* Profile Edit Modal */
.modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(4,7,13,0.82);backdrop-filter:blur(8px);z-index:1000;display:flex;align-items:center;justify-content:center;padding:20px}
.modal-content{background:#111622;border:1px solid #232d42;border-radius:18px;width:100%;max-width:680px;max-height:90vh;overflow-y:auto;padding:24px;box-shadow:0 24px 60px rgba(0,0,0,0.7);animation:modalFadeIn .2s ease-out}
.modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;border-bottom:1px solid #232d42;padding-bottom:14px;width:100%;box-sizing:border-box}
.modal-title{font-size:18px;font-weight:700;color:#f8fafc;display:flex;align-items:center;gap:10px;white-space:nowrap;line-height:1.2}
.modal-close-btn{background:transparent;border:none;color:#94a3b8;font-size:22px;cursor:pointer;padding:4px 8px;border-radius:6px;line-height:1;transition:all .15s;width:auto}
.modal-close-btn:hover{color:#fff;background:#1e293b}
@keyframes modalFadeIn{from{opacity:0;transform:scale(0.96)}to{opacity:1;transform:scale(1)}}

@media(max-width:980px){.slide-card,.canvas-studio-wrap{grid-template-columns:1fr}.modes,.row{grid-template-columns:1fr}.canvas-controls-col{position:static;max-height:none;overflow:visible;padding-right:0}.canvas-toolbar{grid-template-columns:1fr auto}.canvas-hud-coord{grid-column:1/-1;grid-row:2;text-align:left}.canvas-controls-actions{position:static;background:none;padding-top:0}}
@media(max-width:620px){.canvas-toolbar{grid-template-columns:1fr}.canvas-toolbar-action{width:100%}.canvas-hud-coord{grid-column:1;grid-row:auto}.action-footer{align-items:stretch;flex-direction:column}.action-footer>button,.action-footer>div{width:100%!important}.action-footer>div{display:grid!important;grid-template-columns:1fr}.action-footer button{width:100%!important}}
</style>


</head>
<body>
<header>
  <div class="logo-title">
    <span>🎓</span>
    <span>Mac Digital Human</span>
    <span class="badge">Apple Silicon Native</span>
  </div>
  <div class="nav-tabs">
    <div id="tabBtnLecture" class="nav-tab active" onclick="switchMainTab('lecture')">🎓 PPT 授课微课工坊</div>
    <div id="tabBtnProfile" class="nav-tab" onclick="switchMainTab('profile')">🎭 数字人人设定制</div>
    <div id="tabBtnSingle" class="nav-tab" onclick="switchMainTab('single')">⚡ 基础数字人口播</div>
  </div>
</header>


<main>
  <!-- TAB 1: PPT LECTURE STUDIO -->
  <!-- TAB 1: PPT LECTURE STUDIO -->
  <div id="lectureView" class="card">
    <h1>PPT 授课数字人微课制作工坊</h1>
    <div class="muted">上传 PPTX 或 PDF 课件，系统将自动提取 1080P 高清讲义与逐页讲稿，支持自由拖拽数字人排版设计，一键生成超拟真微课视频。</div>

    <!-- Wizard Stepper Navigation Bar -->
    <div class="wizard-bar" style="margin-top:24px">
      <div class="wizard-node active" id="wnode-1" onclick="goToWizardStep(1)">
        <div class="wizard-num" id="wnum-1">1</div>
        <div class="wizard-info">
          <div class="wizard-step-name">上传课件</div>
          <div class="wizard-step-sub">课件解析与讲师选择</div>
        </div>
      </div>
      <div class="wizard-divider" id="wline-1"></div>
      <div class="wizard-node" id="wnode-2" onclick="goToWizardStep(2)">
        <div class="wizard-num" id="wnum-2">2</div>
        <div class="wizard-info">
          <div class="wizard-step-name">确认讲稿</div>
          <div class="wizard-step-sub">逐页审校讲解词</div>
        </div>
      </div>
      <div class="wizard-divider" id="wline-2"></div>
      <div class="wizard-node" id="wnode-3" onclick="goToWizardStep(3)">
        <div class="wizard-num" id="wnum-3">3</div>
        <div class="wizard-info">
          <div class="wizard-step-name">确认版面</div>
          <div class="wizard-step-sub">自由拖拽数字人</div>
        </div>
      </div>
      <div class="wizard-divider" id="wline-3"></div>
      <div class="wizard-node" id="wnode-4" onclick="goToWizardStep(4)">
        <div class="wizard-num" id="wnum-4">4</div>
        <div class="wizard-info">
          <div class="wizard-step-name">视听包装与生成</div>
          <div class="wizard-step-sub">人设/配乐/硬字幕</div>
        </div>
      </div>
    </div>

    <!-- ==================== WIZARD STEP 1: UPLOAD ==================== -->
    <div id="wizardStep1" class="wizard-panel active">
      <div class="step-banner">
        <div class="step-num">1</div>
        <div class="step-title">上传教学课件并选择主讲人设</div>
      </div>
      <div class="grid" style="margin-top:0">
        <div class="row">
          <div>
            <label>课件文件 (.pptx / .pdf)</label>
            <input id="pptFileInput" type="file" accept=".pptx,.pdf,.ppt">
            <div class="tip">推荐上传带有演讲者备注的 PPTX 课件或 16:9 教学 PDF。</div>
          </div>
          <div>
            <label>授课讲师 Profile</label>
            <select id="lectureProfileSelect" onchange="onLectureProfileChange()"></select>
            <div id="lectureProfileTip" class="tip">已配置专属声音与视频母版。</div>
          </div>
        </div>

        <!-- Quick Load Draft / History Session -->
        <div style="display:flex;align-items:center;gap:12px;margin:8px 0 4px 0;padding:12px 14px;background:#090d16;border:1px solid #1e293b;border-radius:8px">
          <span style="font-size:13px;font-weight:600;color:#94a3b8;white-space:nowrap">📂 或从最近课件草稿载入:</span>
          <select id="recentSessionSelect" style="flex:1;padding:7px 10px;background:#1e293b;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:13px">
            <option value="">-- 点击选择已解析课件草稿 --</option>
          </select>
          <button type="button" onclick="loadSelectedRecentSession()" style="width:auto;padding:7px 16px;font-size:13px;background:#0284c7;border:none;color:#fff;border-radius:6px;cursor:pointer;font-weight:600">⚡ 载入并进入向导</button>
        </div>

        <button id="parseBtn" class="primary-btn" type="button" onclick="handleParsePPT()" style="font-size:16px;padding:14px">🔍 解析课件并进入讲稿确认 ➔</button>
      </div>
    </div>

    <!-- ==================== WIZARD STEP 2: SCRIPT REVIEW ==================== -->
    <div id="wizardStep2" class="wizard-panel">
      <div class="step-banner">
        <div class="step-num">2</div>
        <div class="step-title">逐页讲稿审校与修润工坊</div>
      </div>
      <div class="muted" style="margin-bottom:18px">系统已自动识别幻灯片与演讲者备注。请检查或修润每页讲解词，完成后进入下一步确认版面。</div>
      
      <div id="slidesList"></div>

      <div class="action-footer">
        <button type="button" onclick="goToWizardStep(1)" style="width:auto;padding:10px 20px;background:#1e293b;border-color:#334155">⬅️ 上一步：重选课件</button>
        <button class="primary-btn" type="button" onclick="goToWizardStep(3)" style="width:auto;padding:12px 28px">下一步：确认版面排版 (自由拖拽) ➔</button>
      </div>
    </div>

    <!-- ==================== WIZARD STEP 3: VISUAL DRAG CANVAS STUDIO ==================== -->
    <div id="wizardStep3" class="wizard-panel">
      <div class="step-banner">
        <div class="step-num">3</div>
        <div class="step-title">所见即所得自由拖拽排版工作台</div>
      </div>
      <div class="muted">在下方 16:9 模拟视口中，您可以<b>自由拖拽并缩放 PPT 课件视窗</b>与<b>主讲数字人</b>，还可选择或<b>上传自定义演播厅背景图片</b>。</div>

      <div class="canvas-studio-wrap">
        <!-- Main Canvas Column -->
        <div class="canvas-main-col">
          <div class="canvas-toolbar">
            <div class="canvas-toolbar-nav">
              <button type="button" onclick="prevSlideCanvas()" style="width:auto;padding:6px 12px;font-size:12px">◀ 上一页</button>
              <span id="canvasSlideIndicator" style="font-weight:700;font-size:14px;color:#38bdf8">第 1 / 1 页</span>
              <button type="button" onclick="nextSlideCanvas()" style="width:auto;padding:6px 12px;font-size:12px">下一页 ▶</button>
            </div>
            <div class="canvas-hud-coord" id="canvasCoordHud">选中: 👤 主讲数字人 | X:68.0% Y:40.0% | 尺寸: 28.0% × 56.0%</div>
            <button type="button" class="canvas-toolbar-action" onclick="applyLayoutToAllSlides()">✨ 应用到全部页面</button>
          </div>

          <!-- 16:9 Interactive Viewport -->
          <div class="canvas-viewport" id="canvasViewport">
            <!-- Custom Background Image Layer -->
            <div class="canvas-bg-layer" id="canvasCustomBg" style="display:none"></div>
            <!-- Blur Background Layer -->
            <div class="canvas-blur-bg" id="canvasBlurBg"></div>

            <!-- Draggable PPT Box Layer -->
            <div class="drag-layer-box drag-ppt-box" id="dragPptBox" style="left:4%;top:10%;width:65%;height:76%;" onclick="selectActiveCanvasLayer('ppt', event)">
              <div class="drag-layer-tag ppt">
                <span>📑</span>
                <span>PPT 课件视窗 (按住拖拽)</span>
              </div>
              <div class="ppt-inner-img" id="pptInnerImg"></div>
              <div class="resize-handle" id="pptResizeHandle" title="拖拽拉伸缩放 PPT 窗口大小">⤡</div>
            </div>

            <!-- Draggable Avatar Box Layer -->
            <div class="drag-layer-box drag-avatar-box active" id="dragAvatarBox" style="left:71%;top:26%;width:25%;height:70%;" onclick="selectActiveCanvasLayer('avatar', event)">
              <div class="drag-layer-tag avatar">
                <span>👤</span>
                <span id="dragAvatarLabel">主讲数字人 (按住拖拽)</span>
              </div>
              <img id="dragAvatarImg" class="drag-avatar-img" src="" alt="Avatar">
              <div class="resize-handle" id="avatarResizeHandle" title="拖拽拉伸缩放数字人大小">⤡</div>
            </div>

            <!-- Subtitle Preview Bar -->
            <div class="canvas-sub-preview" id="canvasSubPreview">【字幕预览】今天我们一起学习全新微课生成引擎...</div>
          </div>

          <!-- Slide Ribbon Carousel -->
          <div class="slide-ribbon-panel">
            <div style="font-size:12px;color:#94a3b8;margin-bottom:2px">快速跳转幻灯片</div>
            <div class="slide-ribbon" id="slideRibbon"></div>
          </div>
        </div>

        <!-- Sidebar Controls Column -->
        <div class="canvas-controls-col">
          <!-- Presentation Layout Mode Selector -->
          <div class="hud-item">
            <label style="margin-bottom:8px">本页画面呈现模式</label>
            <select id="canvasLayoutModeSelect" onchange="onCanvasLayoutModeChange(this.value)" style="background:#1e293b;border:1px solid #38bdf8;color:#f8fafc;font-weight:600;padding:8px;border-radius:6px;width:100%">
              <option value="pip" selected>🎨 自由排版 / 演播厅 (默认，支持拖拽缩放与底板)</option>
              <option value="full_avatar">👤 讲师全屏特写 (开场/总结，隐藏PPT)</option>
              <option value="full_slide">📑 课件全屏 (纯画外音解说，隐藏讲师)</option>
              <option value="split">👥 固定左右分屏 (70% PPT + 30% 讲师)</option>
            </select>
            <div class="tip" id="canvasLayoutModeTip">当前采用自由多图层排版，所见即所得。</div>
          </div>

          <!-- Active Layer Switcher Tabs -->
          <div class="hud-item">
            <label style="margin-bottom:8px">选择当前排版编辑图层</label>
            <div class="layer-selector-bar">
              <button type="button" id="tabLayerPpt" class="layer-tab-btn" onclick="selectActiveCanvasLayer('ppt')">📑 PPT 课件视窗</button>
              <button type="button" id="tabLayerAvatar" class="layer-tab-btn active" onclick="selectActiveCanvasLayer('avatar')">👤 主讲数字人</button>
            </div>
            <div class="tip" id="activeLayerTip">当前可直接在视口中拖拽移动数字人，或拖拽右下角手柄缩放大小。</div>
          </div>

          <!-- PPT Snap Panel -->
          <div class="hud-item" id="pptSnapPanel" style="display:none">
            <label style="margin-bottom:8px">PPT 课件快捷吸附构图</label>
            <div class="snap-btn-group">
              <div class="snap-btn" style="grid-column:span 3;background:#1e3a8a;border-color:#3b82f6;color:#93c5fd;font-weight:700" onclick="snapPpt('studio_gold')">🌟 经典演播室黄金构图 (推荐 65%)</div>
              <div class="snap-btn" onclick="snapPpt('fullscreen')">🖥️ 全屏居中铺满 (100%)</div>
              <div class="snap-btn" onclick="snapPpt('left_main')">📑 经典左主屏 (65%)</div>
              <div class="snap-btn" onclick="snapPpt('right_main')">📑 经典右主屏 (65%)</div>
              <div class="snap-btn" onclick="snapPpt('center_box')">🎯 居中展台 (76%)</div>
            </div>
          </div>

          <!-- Avatar Snap Panel -->
          <div class="hud-item" id="avatarSnapPanel">
            <label style="margin-bottom:8px">数字人快捷吸附构图</label>
            <div class="snap-btn-group">
              <div class="snap-btn" onclick="snapAvatar('bottom_right')">↘️ 右下角</div>
              <div class="snap-btn" onclick="snapAvatar('bottom_left')">↙️ 左下角</div>
              <div class="snap-btn" onclick="snapAvatar('top_right')">↗️ 右上角</div>
              <div class="snap-btn" onclick="snapAvatar('top_left')">↖️ 左上角</div>
              <div class="snap-btn" onclick="snapAvatar('center_right')">➡️ 右中侧</div>
              <div class="snap-btn" onclick="snapAvatar('center_left')">⬅️ 左中侧</div>
              <div class="snap-btn" style="grid-column:span 3" onclick="snapAvatar('center_large')">🎯 居中半身特写</div>
            </div>
          </div>

          <div class="hud-item">
            <label id="scaleSliderTitle">当前选中图层宽度比例</label>
            <input type="range" id="activeScaleRange" min="18" max="100" value="28" oninput="onActiveLayerScaleSlider(this.value)">
            <div style="display:flex;justify-content:space-between;font-size:11px;color:#64748b;margin-top:2px">
              <span id="sliderMinLabel">18%</span>
              <span id="sliderValLabel">当前: 28%</span>
              <span id="sliderMaxLabel">100%</span>
            </div>
          </div>

          <div class="hud-item">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
              <label style="margin:0">虚拟演播厅背景底板</label>
              <button type="button" onclick="triggerBgUpload()" style="width:auto;padding:3px 8px;font-size:11px;background:#0284c7;border:none;color:#fff;border-radius:4px;cursor:pointer">➕ 上传背景</button>
              <input type="file" id="bgUploadInput" accept="image/*" style="display:none" onchange="handleBgUpload(event)">
            </div>
            <select id="canvasBgSelect" onchange="onCanvasBgSelectChange()">
              <option value="blur" selected>🌌 现代磨砂毛玻璃 (PPT自适应高斯虚化)</option>
              <option value="black">🎬 原版深黑演播室</option>
              <option value="studio_tech_blue.jpg">🏢 现代科技蓝演播室 (预设)</option>
              <option value="studio_executive_dark.jpg">🏛️ 高端商务暗黑发布会 (预设)</option>
              <option value="studio_academic_warm.jpg">📚 典雅学术暖调书房 (预设)</option>
              <option value="studio_cyber_neon.jpg">🔮 极简流光微课展台 (预设)</option>
            </select>
            <div class="tip" id="bgModeTip">实时在画布模拟真实成片虚拟演播厅底板效果。</div>
          </div>

          <div class="canvas-controls-actions">
            <button type="button" class="primary-btn" onclick="saveCurrentCanvasLayout()" style="background:#0284c7">💾 保存本页</button>
            <button type="button" class="secondary-btn" onclick="applyLayoutToAllSlides()">📌 同步全部</button>
          </div>
        </div>
      </div>

      <div class="action-footer">
        <button type="button" onclick="goToWizardStep(2)" style="width:auto;padding:10px 20px;background:#1e293b;border-color:#334155">⬅️ 上一步：修改讲稿</button>
        <div style="display:flex;gap:12px;align-items:center">
          <button type="button" class="primary-btn" onclick="saveCurrentCanvasLayout()" style="background:#0369a1;width:auto;padding:12px 22px;font-size:14px">💾 保存排版</button>
          <button class="primary-btn" type="button" onclick="goToWizardStep(4)" style="width:auto;padding:12px 28px">下一步：视听包装与一键生成 ➔</button>
        </div>
      </div>
    </div>


    <!-- ==================== WIZARD STEP 4: PACKAGING & PRODUCTION ==================== -->
    <div id="wizardStep4" class="wizard-panel">
      <div class="step-banner">
        <div class="step-num">4</div>
        <div class="step-title">视听包装与全自动微课渲染流水线</div>
      </div>

      <div class="grid" style="margin-top:0">
        <div class="row">
          <div>
            <label>演讲语速调节 (TTS Speed)</label>
            <select id="speedSelect">
              <option value="0.85">0.85x 沉稳微课（适合公式多、深度大课）</option>
              <option value="1.0" selected>1.0x 标准教学语速（推荐，自然清晰）</option>
              <option value="1.15">1.15x 紧凑高效（适合通识培训与快节奏讲解）</option>
              <option value="1.25">1.25x 快速口播（信息密集短视频）</option>
            </select>
            <div class="tip">高保真变音速不变调算法，杜绝小黄人变调失真。</div>
          </div>
          <div>
            <label>演讲情绪与语调风格 (Speech Emotion)</label>
            <select id="emotionSelect">
              <option value="professional" selected>🎓 沉稳严谨（专业学者讲师风格，标准自然）</option>
              <option value="warm">🌟 亲切温和（启发式教学，富有亲和力与交流感）</option>
              <option value="passionate">⚡ 激昂有力（热情洋溢，适合开场动员与重点强化）</option>
              <option value="calm">☕ 轻松从容（平缓自然，如好友娓娓道来）</option>
            </select>
            <div class="tip">智能调节声学表现力与起伏感染力。</div>
          </div>
        </div>

        <div class="row">
          <div>
            <label>背景音乐（BGM）</label>
            <select id="bgmSelect">
              <option value="">不添加背景音乐</option>
              <option value="samples/bgm.mp3">轻柔微课环境音 (Audio Ducking 自动下潜)</option>
            </select>
            <div class="tip">数字人开讲时背景音乐音量会自动平滑压低到 15%。</div>
          </div>
          <div>
            <label>微课字幕模式 (Subtitles & Hardcoding)</label>
            <select id="subtitlesSelect">
              <option value="burn" selected>🔥 烧录高清内嵌硬字幕 (黑底圆角药丸字幕条，任何设备开箱即显，推荐)</option>
              <option value="soft">📝 仅生成外挂软字幕 (.srt / .vtt)</option>
              <option value="none">❌ 不添加字幕</option>
            </select>
            <div class="tip">硬字幕采用高清抗锯齿渲染压制，无需播放器外挂即可直接显示。</div>
          </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px">
          <button type="button" onclick="goToWizardStep(3)" style="width:auto;padding:10px 20px;background:#1e293b;border-color:#334155">⬅️ 上一步：调整排版画布</button>
          <button id="produceBtn" class="primary-btn" type="button" onclick="handleProduceCourse()" style="font-size:16px;padding:15px 36px">🚀 开始制作数字人微课视频</button>
        </div>
      </div>

      <!-- Real-time Production Dashboard -->
      <div id="lectureJobBox" style="display:none;margin-top:30px">
        <div class="step-banner">
          <div class="step-num">✓</div>
          <div id="jobBannerTitle" class="step-title">微课生产线实时全流程看板</div>
        </div>

        <!-- 4-Phase Stepper -->
        <div class="phase-stepper">
          <div class="phase-step active" id="pstep-1">
            <div class="phase-icon" id="picon-1">1</div>
            <div class="phase-label">课件解析</div>
          </div>
          <div class="phase-line" id="pline-1"></div>
          <div class="phase-step" id="pstep-2">
            <div class="phase-icon" id="picon-2">2</div>
            <div class="phase-label">语音合成</div>
          </div>
          <div class="phase-line" id="pline-2"></div>
          <div class="phase-step" id="pstep-3">
            <div class="phase-icon" id="picon-3">3</div>
            <div class="phase-label">数字人生成</div>
          </div>
          <div class="phase-line" id="pline-3"></div>
          <div class="phase-step" id="pstep-4">
            <div class="phase-icon" id="picon-4">4</div>
            <div class="phase-label">排版字幕混流</div>
          </div>
        </div>

        <!-- Real-time HUD -->
        <div class="hud-card">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div style="font-weight:700;font-size:15px;color:#f1f5f9" id="hudStageTitle">阶段 1：课件解析与底板生成</div>
            <div style="font-weight:750;font-size:18px;color:#38bdf8" id="jobPctText">15%</div>
          </div>
          <div class="progress-bar-bg"><div id="jobProgressFill" class="progress-bar-fill"></div></div>

          <div class="hud-grid">
            <div class="hud-item" style="grid-column: span 2">
              <div class="hud-title">当前执行步骤 (细粒度实时进展)</div>
              <div class="hud-detail" id="currentStepDetail">初始化流水线环境...</div>
            </div>
            <div class="hud-item">
              <div class="hud-title">⏱️ 已用耗时</div>
              <div class="hud-val" id="elapsedTimeText">0.0s</div>
            </div>
            <div class="hud-item">
              <div class="hud-title">⏳ 预计剩余时间 (ETA)</div>
              <div class="hud-val" id="etaTimeText" style="color:#34d399">预估中...</div>
            </div>
          </div>

          <!-- Slide-by-slide progress matrix -->
          <div style="margin-top:16px;border-top:1px solid #1e2638;padding-top:14px">
            <div style="font-weight:600;font-size:13px;color:#94a3b8">逐页流水线状态矩阵 (Slide Status Matrix):</div>
            <div class="slide-matrix" id="slideMatrixContainer">
              <!-- JS rendered cards -->
            </div>
          </div>
        </div>

        <div id="jobStatusText" class="status-box" style="display:none">准备就绪</div>

        <div id="videoContainer" class="video-preview-box" style="display:none">
          <h3 style="margin-top:0;color:#38bdf8">🎉 微课视频制作成功！</h3>
          <video id="finalVideoPlayer" controls playsinline style="max-height:480px"></video>
          <div style="margin-top:16px;display:flex;gap:12px;justify-content:center">
            <a id="downloadVideoBtn" class="primary-btn" style="text-decoration:none;padding:10px 20px;border-radius:8px" download>⬇️ 下载高清成片 (MP4)</a>
            <a id="downloadSrtBtn" style="background:#1e293b;color:#94a3b8;text-decoration:none;padding:10px 20px;border-radius:8px;border:1px solid #334155" download>📝 下载外挂字幕 (SRT)</a>
          </div>
        </div>
      </div>
    </div>

        <div id="videoContainer" class="video-preview-box" style="display:none">
          <h3 style="margin-top:0;color:#38bdf8">🎉 微课视频制作成功！</h3>
          <video id="finalVideoPlayer" controls playsinline style="max-height:480px"></video>
          <div style="margin-top:16px;display:flex;gap:12px;justify-content:center">
            <a id="downloadVideoBtn" class="primary-btn" style="text-decoration:none;padding:10px 20px;border-radius:8px" download>⬇️ 下载高清成片 (MP4)</a>
            <a id="downloadSrtBtn" style="background:#1e293b;color:#94a3b8;text-decoration:none;padding:10px 20px;border-radius:8px;border:1px solid #334155" download>📝 下载外挂字幕 (SRT)</a>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- TAB 2: PROFILE CUSTOMIZATION STUDIO -->
  <div id="profileView" class="card" style="display:none">
    <h1>🎭 数字人形象与声音定制</h1>
    <div class="muted">自定义您的专属授课数字人：上传真人形象照片/立绘，直接使用麦克风录制示范声音，一键克隆音色并永久保存为您微课的主讲人。</div>

    <!-- Section 1: Existing Profiles Gallery -->
    <div style="margin-top:24px">
      <div class="step-banner">
        <div class="step-num">1</div>
        <div class="step-title">当前已有人设库</div>
      </div>
      <div id="profileGallery" style="display:grid;grid-template-columns:repeat(auto-fill, minmax(260px, 1fr));gap:16px;margin-top:16px">
        <!-- populated by JS -->
      </div>
    </div>

    <!-- Section 2: Create Custom Digital Human -->
    <div style="margin-top:36px">
      <div class="step-banner">
        <div class="step-num">2</div>
        <div class="step-title">定制并创建全新数字人</div>
      </div>

      <form id="createProfileForm" onsubmit="handleCreateProfile(event)" class="grid" style="margin-top:0">
        <div class="row">
          <div>
            <label>讲师人设名称 *</label>
            <input id="newProfileName" type="text" placeholder="例如：李老师、能源分析专家" required>
            <div class="tip">微课视频与系统列表显示的讲师称呼。</div>
          </div>
          <div>
            <label>专属唯一标识 (ID，可选)</label>
            <input id="newProfileId" type="text" placeholder="留空自动生成，如 teacher_li" pattern="[a-zA-Z0-9_-]*">
            <div class="tip">仅限字母、数字与下划线。</div>
          </div>
        </div>

        <div class="row">
          <!-- Image Upload & Preview -->
          <div>
            <label>数字人形象照片 * (.png / .jpg / .webp)</label>
            <input id="newProfileImage" type="file" accept="image/*" required onchange="previewProfileImage(event)">
            <div class="tip">推荐半身正视镜头、面部清晰、光照均匀的专业照片。</div>
            <div id="imagePreviewContainer" style="margin-top:12px;width:140px;height:140px;border-radius:12px;border:2px dashed #2a364d;overflow:hidden;display:none;background:#0c0f17;align-items:center;justify-content:center">
              <img id="imagePreviewImg" style="width:100%;height:100%;object-fit:cover">
            </div>
          </div>

          <!-- Video Master (Optional for MuseTalk) -->
          <div>
            <label>动态唇形母版视频 (可选，.mp4)</label>
            <input id="newProfileVideo" type="file" accept="video/mp4">
            <div class="tip">若提供母版视频，将直接支持 MuseTalk 极速高保真唇形对齐（若不提供则默认使用肖像图片驱动）。</div>
          </div>
        </div>

        <!-- Voice Recording & Cloning Section -->
        <div style="background:#0c0f17;border:1px solid #232c3f;border-radius:12px;padding:18px;margin-top:8px">
          <div style="font-weight:700;font-size:15px;color:#f8fafc;margin-bottom:6px">🎙️ 声音克隆与参考音频定制</div>
          <div class="tip" style="margin-bottom:14px">请选择【麦克风实时录音】或【上传本地录音】，用于克隆您的专属教学声音：</div>

          <div style="display:flex;gap:12px;margin-bottom:14px">
            <button id="btnVoiceModeMic" type="button" class="mode active" style="padding:6px 14px;font-size:13px" onclick="setVoiceInputMode('mic')">🎤 网页麦克风录制</button>
            <button id="btnVoiceModeUpload" type="button" class="mode" style="padding:6px 14px;font-size:13px" onclick="setVoiceInputMode('upload')">📁 上传音频文件</button>
          </div>

          <!-- Mic Recording Area -->
          <div id="voiceMicArea">
            <div style="background:#141a27;padding:12px 16px;border-radius:8px;border-left:4px solid #3b82f6;margin-bottom:12px">
              <div style="font-size:12px;color:#94a3b8;margin-bottom:4px">请朗读以下参考台词（约 5~10 秒）：</div>
              <div id="readSampleScript" style="color:#e2e8f0;font-size:14px;font-weight:500">“各位学员大家好，欢迎来到本期微课堂。今天我们一起来探讨核心知识点，希望大家学有所成。”</div>
            </div>

            <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
              <button id="recordBtn" type="button" class="primary-btn" style="background:#dc2626;padding:10px 20px" onclick="toggleRecording()">🔴 开始录音</button>
              <div id="recordTimer" style="font-size:14px;color:#94a3b8;font-family:monospace;display:none">⏱️ 00:00</div>
              <audio id="recordedAudioPreview" controls style="display:none;height:36px"></audio>
              <button id="rerecordBtn" type="button" style="display:none;padding:6px 12px;background:#1e293b;color:#cbd5e1;border:1px solid #334155;border-radius:6px;cursor:pointer" onclick="resetRecording()">🗑️ 重录</button>
            </div>
          </div>

          <!-- File Upload Area (Hidden by default) -->
          <div id="voiceUploadArea" style="display:none">
            <input id="newProfileAudio" type="file" accept="audio/*">
            <div class="tip">支持上传 5~30 秒清晰纯人声录音 (.wav / .mp3 / .m4a)。</div>
          </div>

          <div style="margin-top:14px">
            <label>录音对应文本（Reference Text，推荐填写以获得最佳克隆音质）</label>
            <input id="newProfileRefText" type="text" value="各位学员大家好，欢迎来到本期微课堂。今天我们一起来探讨核心知识点，希望大家学有所成。">
          </div>

          <div style="margin-top:14px">
            <label>TTS 语音驱动引擎 (TTS Engine)</label>
            <select id="newProfileProvider" style="width:100%">
              <option value="cosyvoice2" selected>✨ CosyVoice 2.0 (自然逼真高保真声音克隆)</option>
            </select>
          </div>
        </div>

        <!-- Submit Button -->
        <button id="saveProfileBtn" class="primary-btn" type="submit" style="font-size:16px;padding:14px;margin-top:12px">💾 保存并创建专属数字人</button>
      </form>
    </div>
  </div>

  <!-- TAB 3: ORIGINAL SINGLE TASK AVATAR (KEPT INTACT) -->
  <div id="singleView" class="card" style="display:none">

    <h1>单任务数字人口播</h1>
    <div class="muted">MuseTalk 极速口播单任务驱动（母版视频 + 音频）。</div>
    <form id="singleForm" class="grid">
      <input id="singleEngine" name="engine" type="hidden" value="musetalk">
      <div><label>人物模板（可选）</label><select id="singleProfileSelect" name="profile_id"><option value="">手工上传素材</option></select></div>
      <div><label>驱动音频</label><input name="audio" type="file" accept="audio/*" required></div>
      <div id="singleMusetalkPanel" class="panel active">
        <div><label>母版视频</label><input id="singleVideo" name="video" type="file" accept="video/*"><div class="tip">如果人物模板已配置 master_video，可不上传。</div></div>
        <div><label>MuseTalk 权重</label><select name="musetalk_variant"><option value="q8">Q8（推荐）</option><option value="q4">Q4</option><option value="fp16">FP16</option></select></div>
      </div>
      <button id="singleSubmitBtn" class="primary-btn" type="submit">生成极速数字人片段</button>
    </form>
    <h3 style="margin-top:24px">任务状态</h3>
    <div id="singleStatus" class="status-box">等待提交</div>
  </div>

  <!-- EDIT PROFILE MODAL (Online Edit & Master Video Update) -->
  <div id="editProfileModal" class="modal-overlay" style="display:none" onclick="if(event.target===this)closeEditProfileModal()">
    <div class="modal-content">
      <!-- Modal Header (Fixed Single-Line Layout) -->
      <div class="modal-header">
        <div class="modal-title">
          <span style="font-size:20px">✏️</span>
          <span>编辑数字人人设信息</span>
          <span id="editModalProfileIdBadge" class="profile-tag" style="font-family:monospace;font-size:12px;font-weight:normal">id</span>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeEditProfileModal()">✕</button>
      </div>

      <form id="editProfileForm" onsubmit="handleUpdateProfileSubmit(event)">
        <input type="hidden" id="editProfileId">

        <div class="grid" style="gap:16px;margin-top:0">
          <div>
            <label>讲师人设名称 *</label>
            <input id="editProfileName" type="text" required style="width:100%">
            <div class="tip">展示在微课成片与系统选择器中的讲师姓名。</div>
          </div>

          <!-- Master Video Section (Key Feature) -->
          <div style="background:#0c0f17;border:1px solid #232c3f;border-radius:12px;padding:16px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <label style="margin-bottom:0;color:#38bdf8;font-size:14px;font-weight:700">🎥 参考母版视频 (MuseTalk 极速高保真对齐)</label>
              <span id="editProfileVideoStatus" class="profile-tag">检测中...</span>
            </div>
            <div class="tip" style="margin-bottom:12px">
              母版视频用于 MuseTalk 毫秒级唇形音画对齐。替换后，后续生成的微课将以新母版的身姿与微动作渲染成片。
            </div>

            <div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
              <!-- Current Video Preview -->
              <div id="editCurrentVideoWrap" style="display:none;width:190px">
                <div style="font-size:12px;color:#94a3b8;margin-bottom:4px">当前母版视频预览：</div>
                <video id="editCurrentVideoPlayer" controls playsinline style="width:100%;max-height:140px;border-radius:8px;background:#000;border:1px solid #334155"></video>
              </div>

              <!-- Upload New Video -->
              <div style="flex:1;min-width:240px">
                <label style="font-size:13px">选择新母版视频 (.mp4 / .mov)</label>
                <input id="editProfileVideo" type="file" accept="video/mp4,video/*" onchange="previewEditVideo(event)">
                <div class="tip">建议时长 5~30 秒、正向面对镜头、光照清晰且头部稳定的半身视频。</div>
                <div id="editNewVideoNotice" style="display:none;margin-top:8px;font-size:12px;color:#34d399">
                  ✨ 已选定新母版文件，保存后将自动上传并替换！
                </div>
              </div>
            </div>
          </div>

          <!-- Portrait Image Section -->
          <div style="background:#0c0f17;border:1px solid #232c3f;border-radius:12px;padding:16px">
            <label style="color:#e2e8f0;margin-bottom:8px;font-size:14px;font-weight:700">🖼️ 数字人肖像照片</label>
            <div style="display:flex;gap:16px;align-items:center">
              <div style="width:80px;height:80px;border-radius:10px;overflow:hidden;border:1px solid #334155;background:#000;flex-shrink:0">
                <img id="editCurrentImagePreview" style="width:100%;height:100%;object-fit:cover">
              </div>
              <div style="flex:1">
                <label style="font-size:13px">更换形象图片 (.png / .jpg / .webp)</label>
                <input id="editProfileImage" type="file" accept="image/*" onchange="previewEditImage(event)">
                <div class="tip">若不选择文件则保留当前肖像照片。</div>
              </div>
            </div>
          </div>

          <!-- Voice & Clone Text Section (Support Re-recording) -->
          <div style="background:#0c0f17;border:1px solid #232c3f;border-radius:12px;padding:16px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <label style="color:#e2e8f0;margin-bottom:0;font-size:14px;font-weight:700">🎙️ 声音克隆与参考音频定制</label>
            </div>
            <div class="tip" style="margin-bottom:12px">支持保留当前已克隆音色，或使用麦克风重新录制、上传新音频文件更新声音：</div>

            <!-- Voice Mode Selector -->
            <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap">
              <button id="btnEditVoiceKeep" type="button" class="mode active" style="padding:6px 14px;font-size:13px;width:auto" onclick="setEditVoiceMode('keep')">🔒 保留现有声音</button>
              <button id="btnEditVoiceMic" type="button" class="mode" style="padding:6px 14px;font-size:13px;width:auto" onclick="setEditVoiceMode('mic')">🎤 麦克风重新录制</button>
              <button id="btnEditVoiceUpload" type="button" class="mode" style="padding:6px 14px;font-size:13px;width:auto" onclick="setEditVoiceMode('upload')">📁 上传新录音文件</button>
            </div>

            <!-- Mode 1: Keep Current Voice -->
            <div id="editVoiceKeepArea">
              <div id="editCurrentAudioWrap" style="display:none">
                <div style="font-size:12px;color:#94a3b8;margin-bottom:4px">当前已克隆音色试听：</div>
                <audio id="editCurrentAudioPlayer" controls style="height:32px;width:100%"></audio>
              </div>
              <div id="editNoAudioNotice" style="display:none;font-size:12px;color:#64748b">当前人设未绑定专属声音，使用系统默认音色。推荐切换至【麦克风重新录制】定制专属声音。</div>
            </div>

            <!-- Mode 2: Mic Re-recording -->
            <div id="editVoiceMicArea" style="display:none">
              <div style="background:#141a27;padding:12px 16px;border-radius:8px;border-left:4px solid #3b82f6;margin-bottom:12px">
                <div style="font-size:12px;color:#94a3b8;margin-bottom:4px">请朗读以下参考台词（约 5~10 秒）：</div>
                <div id="editReadSampleScript" style="color:#e2e8f0;font-size:14px;font-weight:500">“各位学员大家好，欢迎来到本期微课堂。今天我们一起来探讨核心知识点，希望大家学有所成。”</div>
              </div>

              <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
                <button id="editRecordBtn" type="button" class="primary-btn" style="background:#dc2626;padding:9px 18px;font-size:13px;width:auto" onclick="toggleEditRecording()">🔴 开始录音</button>
                <div id="editRecordTimer" style="font-size:14px;color:#94a3b8;font-family:monospace;display:none">⏱️ 00:00</div>
                <audio id="editRecordedAudioPreview" controls style="display:none;height:36px"></audio>
                <button id="editRerecordBtn" type="button" style="display:none;padding:6px 12px;background:#1e293b;color:#cbd5e1;border:1px solid #334155;border-radius:6px;cursor:pointer;width:auto;font-size:12px" onclick="resetEditRecording()">🗑️ 重录</button>
              </div>
            </div>

            <!-- Mode 3: File Upload -->
            <div id="editVoiceUploadArea" style="display:none">
              <label style="font-size:13px">选择音频文件 (.wav / .mp3 / .m4a)</label>
              <input id="editProfileAudio" type="file" accept="audio/*">
              <div class="tip">建议上传 5~30 秒无明显背景噪音的人声朗读录音。</div>
            </div>

            <div style="margin-top:14px">
              <label style="font-size:13px">参考朗读台词 (Reference Text，用于声音克隆音质对齐)</label>
              <input id="editProfileRefText" type="text" style="width:100%" oninput="document.getElementById('editReadSampleScript').textContent = this.value || '“各位学员大家好，欢迎来到本期微课堂。今天我们一起来探讨核心知识点，希望大家学有所成。”'">
            </div>

            <div style="margin-top:14px">
              <label style="font-size:13px">TTS 语音驱动引擎 (TTS Engine)</label>
              <select id="editProfileProvider" style="width:100%">
                <option value="cosyvoice2" selected>✨ CosyVoice 2.0 (自然逼真高保真声音克隆)</option>
              </select>
            </div>
          </div>
        </div>

        <div style="display:flex;justify-content:flex-end;gap:12px;margin-top:20px;border-top:1px solid #232d42;padding-top:16px">
          <button type="button" style="background:#1e293b;color:#cbd5e1;border:1px solid #334155;border-radius:8px;padding:9px 18px;font-size:14px;cursor:pointer;width:auto" onclick="closeEditProfileModal()">取消</button>
          <button id="saveEditProfileBtn" type="submit" class="primary-btn" style="padding:9px 24px;font-size:14px;width:auto">💾 保存修改</button>
        </div>
      </form>
    </div>
  </div>

</main>

<script>

let currentSession = null;
let catalog = {prompts:[], profiles:[]};

function switchMainTab(tab) {
  document.getElementById('tabBtnLecture').classList.toggle('active', tab==='lecture');
  document.getElementById('tabBtnProfile').classList.toggle('active', tab==='profile');
  document.getElementById('tabBtnSingle').classList.toggle('active', tab==='single');
  document.getElementById('lectureView').style.display = tab==='lecture'?'block':'none';
  document.getElementById('profileView').style.display = tab==='profile'?'block':'none';
  document.getElementById('singleView').style.display = tab==='single'?'block':'none';
  if (tab === 'profile') {
    loadProfilesGallery();
  }
}

// Profile Studio Variables & Handlers
let mediaRecorder = null;
let audioChunks = [];
let recordedVoiceBlob = null;
let recordTimerInterval = null;
let recordDurationSeconds = 0;
let voiceInputMode = 'mic';

function setVoiceInputMode(mode) {
  voiceInputMode = mode;
  document.getElementById('btnVoiceModeMic').classList.toggle('active', mode === 'mic');
  document.getElementById('btnVoiceModeUpload').classList.toggle('active', mode === 'upload');
  document.getElementById('voiceMicArea').style.display = mode === 'mic' ? 'block' : 'none';
  document.getElementById('voiceUploadArea').style.display = mode === 'upload' ? 'block' : 'none';
}

function previewProfileImage(e) {
  const file = e.target.files && e.target.files[0];
  const container = document.getElementById('imagePreviewContainer');
  const img = document.getElementById('imagePreviewImg');
  if (file) {
    const url = URL.createObjectURL(file);
    img.src = url;
    container.style.display = 'flex';
  } else {
    container.style.display = 'none';
  }
}

async function toggleRecording() {
  const btn = document.getElementById('recordBtn');
  const timer = document.getElementById('recordTimer');
  const audioPreview = document.getElementById('recordedAudioPreview');
  const rerecordBtn = document.getElementById('rerecordBtn');

  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
    clearInterval(recordTimerInterval);
    btn.textContent = '🔴 开始录音';
    btn.style.background = '#dc2626';
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    recordedVoiceBlob = null;
    mediaRecorder = new MediaRecorder(stream);

    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) audioChunks.push(event.data);
    };

    mediaRecorder.onstop = () => {
      recordedVoiceBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
      const audioUrl = URL.createObjectURL(recordedVoiceBlob);
      audioPreview.src = audioUrl;
      audioPreview.style.display = 'inline-block';
      rerecordBtn.style.display = 'inline-block';
      timer.textContent = `✅ 录音完成 (${recordDurationSeconds}s)`;
      stream.getTracks().forEach(track => track.stop());
    };

    mediaRecorder.start();
    recordDurationSeconds = 0;
    timer.style.display = 'inline-block';
    timer.textContent = '⏱️ 正在录音: 00:00';
    btn.textContent = '⏹️ 停止录制';
    btn.style.background = '#16a34a';

    recordTimerInterval = setInterval(() => {
      recordDurationSeconds++;
      const m = String(Math.floor(recordDurationSeconds / 60)).padStart(2, '0');
      const s = String(recordDurationSeconds % 60).padStart(2, '0');
      timer.textContent = `⏱️ 正在录音: ${m}:${s}`;
      if (recordDurationSeconds >= 30) {
        toggleRecording();
      }
    }, 1000);
  } catch (err) {
    alert('麦克风访问失败: ' + err.message + '\n请确认浏览器已授予麦克风权限，或切换至【上传音频文件】。');
  }
}

function resetRecording() {
  recordedVoiceBlob = null;
  audioChunks = [];
  document.getElementById('recordedAudioPreview').style.display = 'none';
  document.getElementById('rerecordBtn').style.display = 'none';
  document.getElementById('recordTimer').style.display = 'none';
  document.getElementById('recordBtn').textContent = '🔴 开始录音';
  document.getElementById('recordBtn').style.background = '#dc2626';
}

let allProfilesCache = [];

async function loadProfilesGallery() {
  const container = document.getElementById('profileGallery');
  if (!container) return;
  try {
    const res = await fetch('/api/profiles');
    if (!res.ok) return;
    const profiles = await res.json();
    allProfilesCache = profiles;
    container.innerHTML = '';

    profiles.forEach(p => {
      const card = document.createElement('div');
      card.className = 'profile-card';
      const imgSrc = p.image_url || '/samples/ref.png';
      const audioBtn = p.audio_url
        ? `<div style="margin-top:6px"><audio controls src="${p.audio_url}" style="height:32px;width:100%"></audio></div>`
        : `<div style="font-size:12px;color:#64748b">系统预置音色</div>`;

      const delBtn = p.is_builtin
        ? `<span class="profile-tag">内置默认</span>`
        : `<button type="button" style="background:#ef444422;color:#f87171;border:1px solid #ef444444;border-radius:6px;padding:3px 8px;font-size:11px;cursor:pointer" onclick="deleteProfile('${p.id}')">🗑️ 删除</button>`;

      const editBtn = `<button type="button" style="background:#0284c722;color:#38bdf8;border:1px solid #0284c755;border-radius:6px;padding:3px 8px;font-size:11px;cursor:pointer;font-weight:600" onclick="openEditProfileModal('${p.id}')">✏️ 编辑</button>`;

      card.innerHTML = `
        <div class="profile-avatar-wrap">
          <img class="profile-avatar-img" src="${imgSrc}" alt="${escapeHtml(p.name)}" onerror="this.src='/samples/ref.png'">
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div style="font-weight:700;font-size:15px;color:#f8fafc">${escapeHtml(p.name)}</div>
          <div style="display:flex;gap:6px;align-items:center">
            ${editBtn}
            ${delBtn}
          </div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <span class="profile-tag ${p.has_master_video?'video':''}">
            ${p.has_master_video ? '🎥 动态母版 (MuseTalk)' : '🖼️ 肖像图片'}
          </span>
          <span class="profile-tag ${p.clone_voice?'voice':''}">
            ${p.clone_voice ? '🎙️ 已克隆音色' : '🔈 系统默认音色'}
          </span>
          <span class="profile-tag voice" style="background:#1e1b4b;border-color:#6366f1;color:#a5b4fc">
            ✨ CosyVoice 2.0 高保真
          </span>
        </div>
        ${audioBtn}
      `;
      container.appendChild(card);
    });
  } catch (err) {
    console.error('Failed to load profiles gallery:', err);
  }
}

let editVoiceMode = 'keep';


let editMediaRecorder = null;
let editAudioChunks = [];
let editRecordedVoiceBlob = null;
let editRecordTimerInterval = null;
let editRecordDurationSeconds = 0;

function setEditVoiceMode(mode) {
  editVoiceMode = mode;
  document.getElementById('btnEditVoiceKeep').classList.toggle('active', mode === 'keep');
  document.getElementById('btnEditVoiceMic').classList.toggle('active', mode === 'mic');
  document.getElementById('btnEditVoiceUpload').classList.toggle('active', mode === 'upload');

  document.getElementById('editVoiceKeepArea').style.display = (mode === 'keep') ? 'block' : 'none';
  document.getElementById('editVoiceMicArea').style.display = (mode === 'mic') ? 'block' : 'none';
  document.getElementById('editVoiceUploadArea').style.display = (mode === 'upload') ? 'block' : 'none';
}

async function toggleEditRecording() {
  const btn = document.getElementById('editRecordBtn');
  const timer = document.getElementById('editRecordTimer');
  const audioPreview = document.getElementById('editRecordedAudioPreview');
  const rerecordBtn = document.getElementById('editRerecordBtn');

  if (editMediaRecorder && editMediaRecorder.state === 'recording') {
    editMediaRecorder.stop();
    clearInterval(editRecordTimerInterval);
    btn.textContent = '🔴 重新录制';
    btn.style.background = '#dc2626';
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    editMediaRecorder = new MediaRecorder(stream);
    editAudioChunks = [];

    editMediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) editAudioChunks.push(event.data);
    };

    editMediaRecorder.onstop = () => {
      editRecordedVoiceBlob = new Blob(editAudioChunks, { type: editMediaRecorder.mimeType || 'audio/webm' });
      const audioUrl = URL.createObjectURL(editRecordedVoiceBlob);
      audioPreview.src = audioUrl;
      audioPreview.style.display = 'inline-block';
      rerecordBtn.style.display = 'inline-block';
      timer.textContent = `✅ 录音完成 (${editRecordDurationSeconds}s)`;
      stream.getTracks().forEach(track => track.stop());
    };

    editMediaRecorder.start();
    editRecordDurationSeconds = 0;
    timer.style.display = 'inline-block';
    timer.textContent = '⏱️ 正在录音: 00:00';
    btn.textContent = '⏹️ 停止录制';
    btn.style.background = '#16a34a';

    editRecordTimerInterval = setInterval(() => {
      editRecordDurationSeconds++;
      const m = String(Math.floor(editRecordDurationSeconds / 60)).padStart(2, '0');
      const s = String(editRecordDurationSeconds % 60).padStart(2, '0');
      timer.textContent = `⏱️ 正在录音: ${m}:${s}`;
      if (editRecordDurationSeconds >= 30) {
        toggleEditRecording();
      }
    }, 1000);
  } catch (err) {
    alert('麦克风访问失败: ' + err.message + '\n请确认浏览器已授予麦克风权限，或切换至【上传音频文件】。');
  }
}

function resetEditRecording() {
  editRecordedVoiceBlob = null;
  editAudioChunks = [];
  const preview = document.getElementById('editRecordedAudioPreview');
  if (preview) {
    preview.pause();
    preview.style.display = 'none';
  }
  const rerecord = document.getElementById('editRerecordBtn');
  if (rerecord) rerecord.style.display = 'none';
  const timer = document.getElementById('editRecordTimer');
  if (timer) timer.style.display = 'none';
  const btn = document.getElementById('editRecordBtn');
  if (btn) {
    btn.textContent = '🔴 开始录音';
    btn.style.background = '#dc2626';
  }
}

function openEditProfileModal(profileId) {
  const p = allProfilesCache.find(item => item.id === profileId);
  if (!p) {
    alert('未找到人设信息: ' + profileId);
    return;
  }
  document.getElementById('editProfileId').value = p.id;
  document.getElementById('editModalProfileIdBadge').textContent = p.id;
  document.getElementById('editProfileName').value = p.name || '';
  const refText = p.ref_text || '各位学员大家好，欢迎来到本期微课堂。今天我们一起来探讨核心知识点，希望大家学有所成。';
  document.getElementById('editProfileRefText').value = refText;
  document.getElementById('editReadSampleScript').textContent = `“${refText}”`;
  document.getElementById('editProfileProvider').value = p.provider || 'cosyvoice2';

  // 肖像缩略图预览
  const imgPreview = document.getElementById('editCurrentImagePreview');
  imgPreview.src = (p.image_url ? (p.image_url + '?t=' + Date.now()) : '/samples/ref.png');
  document.getElementById('editProfileImage').value = '';

  // 母版视频预览与状态
  const videoStatus = document.getElementById('editProfileVideoStatus');
  const videoWrap = document.getElementById('editCurrentVideoWrap');
  const videoPlayer = document.getElementById('editCurrentVideoPlayer');
  document.getElementById('editProfileVideo').value = '';
  document.getElementById('editNewVideoNotice').style.display = 'none';

  if (p.has_master_video && p.video_url) {
    videoStatus.className = 'profile-tag video';
    videoStatus.textContent = '✅ 已绑定母版视频 (MuseTalk)';
    videoPlayer.src = p.video_url + '?t=' + Date.now();
    videoWrap.style.display = 'block';
  } else {
    videoStatus.className = 'profile-tag';
    videoStatus.textContent = '🖼️ 暂未绑定母版 (使用肖像)';
    videoPlayer.pause();
    videoPlayer.removeAttribute('src');
    videoPlayer.load();
    videoWrap.style.display = 'none';
  }

  // 音频预览与声音录制重置
  resetEditRecording();
  setEditVoiceMode('keep');
  const audioWrap = document.getElementById('editCurrentAudioWrap');
  const noAudioNotice = document.getElementById('editNoAudioNotice');
  const audioPlayer = document.getElementById('editCurrentAudioPlayer');
  document.getElementById('editProfileAudio').value = '';

  if (p.clone_voice && p.audio_url) {
    audioPlayer.src = p.audio_url + '?t=' + Date.now();
    audioWrap.style.display = 'block';
    noAudioNotice.style.display = 'none';
  } else {
    audioPlayer.pause();
    audioPlayer.removeAttribute('src');
    audioPlayer.load();
    audioWrap.style.display = 'none';
    noAudioNotice.style.display = 'block';
  }

  document.getElementById('editProfileModal').style.display = 'flex';
}

function closeEditProfileModal() {
  const modal = document.getElementById('editProfileModal');
  if (modal) modal.style.display = 'none';
  const videoPlayer = document.getElementById('editCurrentVideoPlayer');
  if (videoPlayer) {
    videoPlayer.pause();
    videoPlayer.removeAttribute('src');
    videoPlayer.load();
  }
  const audioPlayer = document.getElementById('editCurrentAudioPlayer');
  if (audioPlayer) {
    audioPlayer.pause();
    audioPlayer.removeAttribute('src');
    audioPlayer.load();
  }
  resetEditRecording();
}

function previewEditImage(e) {
  const file = e.target.files[0];
  if (file) {
    document.getElementById('editCurrentImagePreview').src = URL.createObjectURL(file);
  }
}

function previewEditVideo(e) {
  const file = e.target.files[0];
  const notice = document.getElementById('editNewVideoNotice');
  if (file) {
    notice.style.display = 'block';
    notice.textContent = `✨ 已选定新母版: ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`;
    const videoWrap = document.getElementById('editCurrentVideoWrap');
    const videoPlayer = document.getElementById('editCurrentVideoPlayer');
    videoPlayer.src = URL.createObjectURL(file);
    videoWrap.style.display = 'block';
  } else {
    notice.style.display = 'none';
  }
}

async function handleUpdateProfileSubmit(e) {
  e.preventDefault();
  const profileId = document.getElementById('editProfileId').value;
  if (!profileId) return;

  const saveBtn = document.getElementById('saveEditProfileBtn');
  saveBtn.disabled = true;
  saveBtn.textContent = '⏳ 正在更新人设与母版视频…';

  const formData = new FormData();
  formData.append('name', document.getElementById('editProfileName').value.trim());
  formData.append('ref_text', document.getElementById('editProfileRefText').value.trim());
  formData.append('provider', document.getElementById('editProfileProvider').value);

  const vidFile = document.getElementById('editProfileVideo').files[0];
  if (vidFile) {
    formData.append('master_video', vidFile);
  }

  const imgFile = document.getElementById('editProfileImage').files[0];
  if (imgFile) {
    formData.append('image', imgFile);
  }

  // 声音处理：麦克风重录 vs 文件上传 vs 保留现有
  if (editVoiceMode === 'mic' && editRecordedVoiceBlob) {
    formData.append('audio', editRecordedVoiceBlob, 'mic_rerecord.webm');
  } else if (editVoiceMode === 'upload') {
    const audFile = document.getElementById('editProfileAudio').files[0];
    if (audFile) {
      formData.append('audio', audFile);
    }
  }

  try {
    const res = await fetch(`/api/profiles/${encodeURIComponent(profileId)}`, {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
      alert('更新失败: ' + (data.detail || JSON.stringify(data)));
      return;
    }

    alert(`🎉 数字人人设【${data.profile ? data.profile.name : profileId}】已成功更新！`);
    closeEditProfileModal();
    await loadCatalog();
    await loadProfilesGallery();

    if (typeof updateAvatarPreviewFromCatalog === 'function') {
      updateAvatarPreviewFromCatalog();
    }
  } catch (err) {
    alert('提交异常: ' + err.message);
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 保存修改';
  }
}


async function deleteProfile(profileId) {
  if (!confirm(`确定要删除数字人人设【${profileId}】吗？`)) return;
  try {
    const res = await fetch(`/api/profiles/${profileId}`, { method: 'DELETE' });
    const json = await res.json();
    if (!res.ok) {
      alert('删除失败: ' + (json.detail || json.message));
      return;
    }
    await loadCatalog();
    await loadProfilesGallery();
  } catch (e) {
    alert('请求异常: ' + e.message);
  }
}

async function handleCreateProfile(e) {
  e.preventDefault();
  const saveBtn = document.getElementById('saveProfileBtn');
  saveBtn.disabled = true;
  saveBtn.textContent = '⏳ 正在保存人设与音频…';

  const formData = new FormData();
  formData.append('name', document.getElementById('newProfileName').value.trim());
  const customId = document.getElementById('newProfileId').value.trim();
  if (customId) formData.append('profile_id', customId);

  const imgFile = document.getElementById('newProfileImage').files[0];
  if (!imgFile) {
    alert('请选择数字人形象照片');
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 保存并创建专属数字人';
    return;
  }
  formData.append('image', imgFile);

  const videoFile = document.getElementById('newProfileVideo').files[0];
  if (videoFile) formData.append('master_video', videoFile);

  if (voiceInputMode === 'mic' && recordedVoiceBlob) {
    formData.append('audio', recordedVoiceBlob, 'mic_record.webm');
  } else if (voiceInputMode === 'upload') {
    const audioFile = document.getElementById('newProfileAudio').files[0];
    if (audioFile) formData.append('audio', audioFile);
  }

  formData.append('ref_text', document.getElementById('newProfileRefText').value.trim());
  formData.append('provider', document.getElementById('newProfileProvider').value);

  try {
    const res = await fetch('/api/profiles', {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
      alert('创建失败: ' + (data.detail || JSON.stringify(data)));
      return;
    }

    alert(`🎉 恭喜！数字人【${data.profile.name}】已定制成功！已为您自动添加到讲师库。`);
    document.getElementById('createProfileForm').reset();
    resetRecording();
    document.getElementById('imagePreviewContainer').style.display = 'none';

    await loadCatalog();
    await loadProfilesGallery();
    const lectureProfileSel = document.getElementById('lectureProfileSelect');
    lectureProfileSel.value = data.profile.id;
    switchMainTab('lecture');
  } catch (err) {
    alert('提交异常: ' + err.message);
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 保存并创建专属数字人';
  }
}

async function loadCatalog() {
  try {
    const r = await fetch('/api/catalog');
    catalog = await r.json();
    const lectureProfileSel = document.getElementById('lectureProfileSelect');
    lectureProfileSel.innerHTML = '';
    const singleProfileSel = document.getElementById('singleProfileSelect');
    singleProfileSel.innerHTML = '<option value="">手工上传素材</option>';

    catalog.profiles.forEach(p => {
      const o1 = document.createElement('option');
      o1.value = p.id;
      o1.textContent = p.name;
      lectureProfileSel.appendChild(o1);

      const o2 = document.createElement('option');
      o2.value = p.id;
      o2.textContent = p.name;
      singleProfileSel.appendChild(o2);
    });


    const singlePromptSel = document.getElementById('singlePromptPreset');
    singlePromptSel.innerHTML = '';
    catalog.prompts.forEach(p => {
      const o = document.createElement('option');
      o.value = p.id;
      o.textContent = p.name;
      singlePromptSel.appendChild(o);
    });
  } catch(e) { console.error(e); }
}

let currentWizardStep = 1;
let currentCanvasSlideIndex = 1;
let slidesLayoutMap = {};
let activeCanvasLayer = 'avatar'; // 'ppt' | 'avatar'
let isDraggingLayer = false;
let isResizingLayer = false;
let dragStartMouse = { x: 0, y: 0 };
let layerStartBox = { x: 0, y: 0, w: 0, h: 0 };
let canvasInitialized = false;

function goToWizardStep(step) {
  if (step > 1 && !currentSession) {
    alert('请先上传课件并完成解析');
    return;
  }
  currentWizardStep = step;

  for (let i = 1; i <= 4; i++) {
    const p = document.getElementById(`wizardStep${i}`);
    if (p) p.classList.toggle('active', i === step);

    const node = document.getElementById(`wnode-${i}`);
    const line = document.getElementById(`wline-${i}`);
    if (node) {
      node.classList.remove('active', 'done');
      if (i < step) node.classList.add('done');
      else if (i === step) node.classList.add('active');
    }
    if (line) {
      line.style.background = i < step ? '#059669' : '#1e293b';
    }
  }

  if (step === 3) {
    initOrUpdateCanvas();
  }

  document.getElementById('lectureView').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function onLectureProfileChange() {
  updateCanvasAvatarImage();
}

function updateCanvasAvatarImage() {
  const profileId = document.getElementById('lectureProfileSelect').value;
  const p = (catalog?.profiles || []).find(x => x.id === profileId);
  const imgEl = document.getElementById('dragAvatarImg');
  if (imgEl && p) {
    imgEl.src = p.image_url || '/samples/ref.png';
  }
}

async function loadRecentLectureSessions() {
  try {
    const res = await fetch('/api/lecture/sessions/recent');
    const data = await res.json();
    const sel = document.getElementById('recentSessionSelect');
    if (!sel) return;
    sel.innerHTML = '<option value="">-- 点击选择已解析课件草稿 --</option>';
    (data.sessions || []).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.session_id;
      opt.textContent = `📑 ${s.title || s.session_id} (${s.total_slides}页)`;
      sel.appendChild(opt);
    });
  } catch(e) {
    console.warn('Failed to load recent sessions', e);
  }
}

async function loadSelectedRecentSession() {
  const sel = document.getElementById('recentSessionSelect');
  const sid = sel ? sel.value : '';
  if (!sid) {
    alert('请先在下拉菜单中选择一个课件草稿');
    return;
  }
  await loadLectureSessionById(sid, 2);
}

async function loadLectureSessionById(sessionId, targetStep = 2) {
  try {
    const res = await fetch(`/api/lecture/sessions/${sessionId}`);
    if (!res.ok) {
      alert('无法读取该课件数据');
      return;
    }
    const data = await res.json();
    currentSession = data;
    slidesLayoutMap = {};
    data.slides.forEach(s => {
      slidesLayoutMap[s.index] = {
        layout: 'pip',
        ppt_box: { x: 0.04, y: 0.10, w: 0.65, h: 0.76 },
        pip_box: { x: 0.71, y: 0.26, w: 0.25, h: 0.70 },
        custom_bg: 'studio_tech_blue.jpg',
        bg_blur: false,
      };
    });
    // 自动恢复持久化保存的排版配置（优先从服务器读取，其次从本地缓存读取）
    if (data.slides_layout && Object.keys(data.slides_layout).length > 0) {
      for (const [k, v] of Object.entries(data.slides_layout)) {
        slidesLayoutMap[parseInt(k, 10)] = JSON.parse(JSON.stringify(v));
      }
    } else {
      try {
        const localCached = localStorage.getItem(`lecture_layout_${sessionId}`);
        if (localCached) {
          const parsed = JSON.parse(localCached);
          if (parsed && Object.keys(parsed).length > 0) {
            for (const [k, v] of Object.entries(parsed)) {
              slidesLayoutMap[parseInt(k, 10)] = JSON.parse(JSON.stringify(v));
            }
          }
        }
      } catch(e) {}
    }

    // 智能升级旧版满屏遗留配置：若 PPT 仍为满屏(1.0x1.0)且未配置背景，自动升级为演播厅黄金比例
    Object.values(slidesLayoutMap).forEach(cfg => {
      if (cfg.layout === 'pip' && (!cfg.ppt_box || (cfg.ppt_box.w >= 0.98 && cfg.ppt_box.h >= 0.98)) && (!cfg.custom_bg || cfg.custom_bg === 'blur')) {
        cfg.ppt_box = { x: 0.04, y: 0.10, w: 0.65, h: 0.76 };
        cfg.pip_box = { x: 0.71, y: 0.26, w: 0.25, h: 0.70 };
        cfg.custom_bg = 'studio_tech_blue.jpg';
        cfg.bg_blur = false;
      }
    });

    renderSlidesWorkshop(data);
    renderSlideRibbon(data);
    currentCanvasSlideIndex = 1;
    goToWizardStep(targetStep);
  } catch(err) {
    alert('载入课件草稿失败: ' + err.message);
  }
}

async function handleParsePPT() {
  const fileInput = document.getElementById('pptFileInput');
  if (!fileInput.files || !fileInput.files[0]) {
    alert('请先选择 PPTX 或 PDF 课件文件');
    return;
  }
  const btn = document.getElementById('parseBtn');
  btn.disabled = true;
  btn.textContent = '⏳ 正在解析课件与生成 1080P 幻灯片…';

  const fd = new FormData();
  fd.append('file', fileInput.files[0]);

  try {
    const res = await fetch('/api/lecture/parse', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) {
      alert('解析失败: ' + (data.detail || JSON.stringify(data)));
      return;
    }
    currentSession = data;
    slidesLayoutMap = {};
    data.slides.forEach(s => {
      slidesLayoutMap[s.index] = {
        layout: 'pip',
        ppt_box: { x: 0.04, y: 0.10, w: 0.65, h: 0.76 },
        pip_box: { x: 0.71, y: 0.26, w: 0.25, h: 0.70 },
        custom_bg: 'studio_tech_blue.jpg',
        bg_blur: false,
      };
    });
    if (data.slides_layout && Object.keys(data.slides_layout).length > 0) {
      for (const [k, v] of Object.entries(data.slides_layout)) {
        slidesLayoutMap[parseInt(k, 10)] = JSON.parse(JSON.stringify(v));
      }
    }
    Object.values(slidesLayoutMap).forEach(cfg => {
      if (cfg.layout === 'pip' && (!cfg.ppt_box || (cfg.ppt_box.w >= 0.98 && cfg.ppt_box.h >= 0.98)) && (!cfg.custom_bg || cfg.custom_bg === 'blur')) {
        cfg.ppt_box = { x: 0.04, y: 0.10, w: 0.65, h: 0.76 };
        cfg.pip_box = { x: 0.71, y: 0.26, w: 0.25, h: 0.70 };
        cfg.custom_bg = 'studio_tech_blue.jpg';
        cfg.bg_blur = false;
      }
    });


    renderSlidesWorkshop(data);
    renderSlideRibbon(data);
    currentCanvasSlideIndex = 1;
    await loadRecentLectureSessions();
    goToWizardStep(2); // 顺畅进入第 2 步：确认讲稿
  } catch (err) {
    alert('网络或服务异常: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 解析课件并进入讲稿确认 ➔';
  }
}

function insertScriptTag(slideIndex, tag) {
  const ta = document.getElementById(`narration-${slideIndex}`);
  if (!ta) return;
  const start = ta.selectionStart || 0;
  const end = ta.selectionEnd || 0;
  const text = ta.value;
  ta.value = text.substring(0, start) + tag + text.substring(end);
  ta.focus();
  ta.selectionStart = ta.selectionEnd = start + tag.length;
  updateScriptWordCount(slideIndex);
}

function updateScriptWordCount(slideIndex) {
  const ta = document.getElementById(`narration-${slideIndex}`);
  const counter = document.getElementById(`counter-${slideIndex}`);
  if (!ta || !counter) return;
  const len = ta.value.trim().length;
  const estSec = (len / 4.0).toFixed(1);
  counter.textContent = `字数: ${len} 字 | 预估朗读用时 ≈ ${estSec} 秒`;
}

function renderSlidesWorkshop(deckData) {
  const container = document.getElementById('slidesList');
  container.innerHTML = '';

  deckData.slides.forEach(s => {
    const card = document.createElement('div');
    card.className = 'slide-card';
    card.id = `slide-card-${s.index}`;
    const initialText = s.narration || '';
    const initialLen = initialText.trim().length;
    const initialSec = (initialLen / 4.0).toFixed(1);

    card.innerHTML = `
      <div>
        <div class="slide-thumb-container">
          <img class="slide-thumb" src="${s.thumbnail_url}" alt="Slide ${s.index}">
        </div>
      </div>
      <div>
        <div class="slide-meta">
          <span class="slide-badge">第 ${s.index} 页 / 共 ${deckData.total_slides} 页</span>
          <div style="display:flex;align-items:center;gap:6px">
            <span class="badge" style="background:#0f172a;border:1px solid #1e3a8a;color:#93c5fd;font-size:11px;font-weight:600">🎨 排版将在步骤 3 可视化自由设置</span>
          </div>
        </div>
        <div style="font-weight:700;font-size:16px;margin-bottom:8px;color:#f8fafc">${escapeHtml(s.title || '第 '+s.index+' 页')}</div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <label style="margin:0">本页讲解逐字稿（TTS 语音驱动音频）:</label>
          <div style="display:flex;gap:6px">
            <button type="button" onclick="insertScriptTag(${s.index}, '[pause:500ms]')" style="width:auto;padding:3px 8px;font-size:11px;background:#1e293b;border:1px solid #334155;color:#94a3b8;border-radius:4px" title="插入0.5秒语气停顿">⏸️ 停顿0.5s</button>
            <button type="button" onclick="insertScriptTag(${s.index}, '[pause:1s]')" style="width:auto;padding:3px 8px;font-size:11px;background:#1e293b;border:1px solid #334155;color:#94a3b8;border-radius:4px" title="插入1秒语气停顿">⏸️ 停顿1.0s</button>
          </div>
        </div>

        <textarea id="narration-${s.index}" oninput="updateScriptWordCount(${s.index})" placeholder="在此输入本页微课讲解词…">${escapeHtml(initialText)}</textarea>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px">
          <div class="tip">提示：支持标点符号断句与精准字幕烧录。</div>
          <div id="counter-${s.index}" style="font-size:12px;color:#38bdf8;font-weight:600">字数: ${initialLen} 字 | 预估朗读用时 ≈ ${initialSec} 秒</div>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

function renderSlideRibbon(deckData) {
  const ribbon = document.getElementById('slideRibbon');
  if (!ribbon) return;
  ribbon.innerHTML = '';

  deckData.slides.forEach(s => {
    const item = document.createElement('div');
    item.className = `ribbon-item ${s.index === currentCanvasSlideIndex ? 'active' : ''}`;
    item.id = `ribbon-item-${s.index}`;
    item.onclick = () => selectRibbonSlide(s.index);

    item.innerHTML = `
      <img class="ribbon-thumb" src="${s.thumbnail_url}" alt="Slide ${s.index}">
      <span class="ribbon-badge">第 ${s.index} 页</span>
    `;
    ribbon.appendChild(item);
  });
}

function selectRibbonSlide(index) {
  currentCanvasSlideIndex = index;
  document.querySelectorAll('.ribbon-item').forEach(x => x.classList.remove('active'));
  const target = document.getElementById(`ribbon-item-${index}`);
  if (target) {
    target.classList.add('active');
    target.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }
  initOrUpdateCanvas();
}

function prevSlideCanvas() {
  if (!currentSession) return;
  if (currentCanvasSlideIndex > 1) {
    selectRibbonSlide(currentCanvasSlideIndex - 1);
  }
}

function nextSlideCanvas() {
  if (!currentSession) return;
  if (currentCanvasSlideIndex < currentSession.total_slides) {
    selectRibbonSlide(currentCanvasSlideIndex + 1);
  }
}

function selectActiveCanvasLayer(layer, e) {
  if (e) e.stopPropagation();
  activeCanvasLayer = layer;

  // 更新 Tab 按钮
  document.getElementById('tabLayerPpt')?.classList.toggle('active', layer === 'ppt');
  document.getElementById('tabLayerAvatar')?.classList.toggle('active', layer === 'avatar');

  // 更新视口内边框高亮
  document.getElementById('dragPptBox')?.classList.toggle('active', layer === 'ppt');
  document.getElementById('dragAvatarBox')?.classList.toggle('active', layer === 'avatar');

  // 更新吸附面板与提示
  const pptSnap = document.getElementById('pptSnapPanel');
  const avatarSnap = document.getElementById('avatarSnapPanel');
  const tipEl = document.getElementById('activeLayerTip');
  const sliderTitle = document.getElementById('scaleSliderTitle');
  const slider = document.getElementById('activeScaleRange');
  const minLabel = document.getElementById('sliderMinLabel');
  const maxLabel = document.getElementById('sliderMaxLabel');
  const valLabel = document.getElementById('sliderValLabel');

  if (layer === 'ppt') {
    if (pptSnap) pptSnap.style.display = 'block';
    if (avatarSnap) avatarSnap.style.display = 'none';
    if (tipEl) tipEl.textContent = '当前激活 PPT 课件图层：可直接在视口中拖拽移动 PPT，拖动右下角手柄缩放大小。';
    if (sliderTitle) sliderTitle.textContent = 'PPT 课件视窗宽度比例 (30% ~ 100%)';
    if (slider) {
      slider.min = 30; slider.max = 100;
      const pb = (slidesLayoutMap[currentCanvasSlideIndex]?.ppt_box) || { w: 1.0 };
      const wPct = Math.round(pb.w * 100);
      slider.value = wPct;
      if (valLabel) valLabel.textContent = `当前: ${wPct}%`;
      if (minLabel) minLabel.textContent = '小窗 30%';
      if (maxLabel) maxLabel.textContent = '全屏 100%';
    }
  } else {
    if (pptSnap) pptSnap.style.display = 'none';
    if (avatarSnap) avatarSnap.style.display = 'block';
    if (tipEl) tipEl.textContent = '当前激活数字人图层：可直接在视口中拖拽移动数字人，拖动右下角手柄缩放大小。';
    if (sliderTitle) sliderTitle.textContent = '主讲数字人宽度比例 (16% ~ 55%)';
    if (slider) {
      slider.min = 16; slider.max = 55;
      const ab = (slidesLayoutMap[currentCanvasSlideIndex]?.pip_box) || { w: 0.28 };
      const wPct = Math.round(ab.w * 100);
      slider.value = wPct;
      if (valLabel) valLabel.textContent = `当前: ${wPct}%`;
      if (minLabel) minLabel.textContent = '小巧 16%';
      if (maxLabel) maxLabel.textContent = '特写 55%';
    }
  }

  updateCanvasHudCoord();
}

function updateCanvasHudCoord() {
  const hudCoord = document.getElementById('canvasCoordHud');
  if (!hudCoord || !slidesLayoutMap[currentCanvasSlideIndex]) return;
  const cfg = slidesLayoutMap[currentCanvasSlideIndex];
  if (activeCanvasLayer === 'ppt') {
    const pb = cfg.ppt_box || { x: 0.0, y: 0.0, w: 1.0, h: 1.0 };
    hudCoord.textContent = `选中: 📑 PPT课件 | X:${(pb.x*100).toFixed(1)}% Y:${(pb.y*100).toFixed(1)}% | 尺寸: ${(pb.w*100).toFixed(1)}% × ${(pb.h*100).toFixed(1)}%`;
  } else {
    const ab = cfg.pip_box || { x: 0.68, y: 0.40, w: 0.28, h: 0.56 };
    hudCoord.textContent = `选中: 👤 主讲数字人 | X:${(ab.x*100).toFixed(1)}% Y:${(ab.y*100).toFixed(1)}% | 尺寸: ${(ab.w*100).toFixed(1)}% × ${(ab.h*100).toFixed(1)}%`;
  }
}

async function loadAvailableBackgrounds(preferredSelectId = null) {
  try {
    const res = await fetch('/api/lecture/backgrounds');
    const data = await res.json();
    const sel = document.getElementById('canvasBgSelect');
    if (!sel || !data.backgrounds) return;
    
    let targetVal = preferredSelectId;
    if (!targetVal && slidesLayoutMap[currentCanvasSlideIndex]) {
      const cfg = slidesLayoutMap[currentCanvasSlideIndex];
      if (cfg.custom_bg) targetVal = cfg.custom_bg;
      else if (cfg.bg_blur) targetVal = 'blur';
      else targetVal = 'black';
    }
    if (!targetVal) targetVal = sel.value;

    sel.innerHTML = `
      <option value="blur">🌌 现代磨砂毛玻璃 (PPT自适应高斯虚化)</option>
      <option value="black">🎬 原版深黑演播室</option>
    `;
    data.backgrounds.forEach(bg => {
      const opt = document.createElement('option');
      opt.value = bg.id;
      opt.textContent = bg.name;
      sel.appendChild(opt);
    });
    if (targetVal) sel.value = targetVal;
  } catch(e) {
    console.warn('Failed to load backgrounds', e);
  }
}

function triggerBgUpload() {
  document.getElementById('bgUploadInput')?.click();
}

async function handleBgUpload(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);

  try {
    const res = await fetch('/api/lecture/backgrounds/upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) {
      alert('背景上传失败: ' + (data.detail || JSON.stringify(data)));
      return;
    }
    await loadAvailableBackgrounds(data.id);
    const sel = document.getElementById('canvasBgSelect');
    if (sel) {
      sel.value = data.id;
    }
    
    if (slidesLayoutMap[currentCanvasSlideIndex]) {
      const cfg = slidesLayoutMap[currentCanvasSlideIndex];
      cfg.bg_blur = false;
      cfg.custom_bg = data.id;
      
      // 如果 PPT 处于全屏，自动调整为经典左主屏，使背景底图即时可见
      const pb = cfg.ppt_box || { x: 0.0, y: 0.0, w: 1.0, h: 1.0 };
      if (pb.w >= 0.95 && pb.h >= 0.95) {
        cfg.ppt_box = { x: 0.03, y: 0.12, w: 0.66, h: 0.76 };
      }
      renderCanvasLayers(cfg);
    }
    
    alert(`🎉 背景图片【${file.name}】上传成功，已即时应用到底板！\n💡 提示：如需整套微课全部采用此背景，请点击右上角「✨ 应用当前版面到所有页面」。`);
  } catch(err) {
    alert('上传异常: ' + err.message);
  } finally {
    e.target.value = '';
  }
}

function onCanvasLayoutModeChange(mode) {
  if (!slidesLayoutMap[currentCanvasSlideIndex]) return;
  const cfg = slidesLayoutMap[currentCanvasSlideIndex];
  cfg.layout = mode;
  const tip = document.getElementById('canvasLayoutModeTip');
  if (tip) {
    if (mode === 'pip') tip.textContent = '当前采用自由多图层排版，可任意拖拽缩放与设置背景。';
    else if (mode === 'full_avatar') tip.textContent = '讲师全屏特写模式：画面纯数字人出镜，隐藏课件。';
    else if (mode === 'full_slide') tip.textContent = '课件全屏模式：画面纯课件展示，纯画外音讲解。';
    else if (mode === 'split') tip.textContent = '经典左右分屏模式：左侧70%课件，右侧30%讲师。';
  }
  renderCanvasLayers(cfg);
}

function onCanvasBgSelectChange() {
  const sel = document.getElementById('canvasBgSelect');
  if (!sel || !slidesLayoutMap[currentCanvasSlideIndex]) return;
  const val = sel.value;
  const cfg = slidesLayoutMap[currentCanvasSlideIndex];
  cfg.layout = 'pip';
  if (val === 'blur') {
    cfg.bg_blur = true;
    cfg.custom_bg = null;
  } else if (val === 'black') {
    cfg.bg_blur = false;
    cfg.custom_bg = 'black';
  } else {
    cfg.bg_blur = false;
    cfg.custom_bg = val;
    // 如果选择背景且 PPT 为全屏，自动切换为经典左主屏以便展示背景
    const pb = cfg.ppt_box || { x: 0.0, y: 0.0, w: 1.0, h: 1.0 };
    if (pb.w >= 0.95 && pb.h >= 0.95) {
      cfg.ppt_box = { x: 0.03, y: 0.12, w: 0.66, h: 0.76 };
    }
  }
  renderCanvasLayers(cfg);
}

function snapPpt(preset) {
  if (!slidesLayoutMap[currentCanvasSlideIndex]) return;
  const cfg = slidesLayoutMap[currentCanvasSlideIndex];
  cfg.layout = 'pip';
  const pptRatio = (currentSession && currentSession.aspect_ratio) ? currentSession.aspect_ratio : (16 / 9);

  if (preset === 'fullscreen') {
    cfg.ppt_box = { x: 0.0, y: 0.0, w: 1.0, h: 1.0 };
  } else if (preset === 'studio_gold' || preset === 'left_main') {
    cfg.ppt_box = { x: 0.04, y: 0.10, w: 0.65, h: 0.76 };
    if (!cfg.custom_bg || cfg.custom_bg === 'blur' || cfg.custom_bg === 'black') {
      cfg.custom_bg = 'studio_tech_blue.jpg';
      cfg.bg_blur = false;
    }
    cfg.pip_box = { x: 0.71, y: 0.26, w: 0.25, h: 0.70 };
  } else if (preset === 'right_main') {
    cfg.ppt_box = { x: 0.31, y: 0.10, w: 0.65, h: 0.76 };
    cfg.pip_box = { x: 0.04, y: 0.26, w: 0.25, h: 0.70 };
  } else if (preset === 'center_box') {
    cfg.ppt_box = { x: 0.12, y: 0.12, w: 0.76, h: 0.76 };
  }
  renderCanvasLayers(cfg);
  selectActiveCanvasLayer('ppt');
}

function snapAvatar(preset) {
  if (!slidesLayoutMap[currentCanvasSlideIndex]) return;
  const cfg = slidesLayoutMap[currentCanvasSlideIndex];
  cfg.layout = 'pip';
  const avatarRatio = 720 / 1264; // ~0.5696，母版原视频比例
  let w = 0.22;
  let h = w * (16 / 9) / avatarRatio; // ~0.686
  let x = 0.74, y = Math.max(0.04, 1.0 - h - 0.02);

  if (preset === 'bottom_right') { x = 0.74; y = Math.max(0.02, 1.0 - h - 0.02); }
  else if (preset === 'bottom_left') { x = 0.04; y = Math.max(0.02, 1.0 - h - 0.02); }
  else if (preset === 'top_right') { x = 0.74; y = 0.04; }
  else if (preset === 'top_left') { x = 0.04; y = 0.04; }
  else if (preset === 'center_right') { x = 0.74; y = Math.max(0.02, (1.0 - h) / 2); }
  else if (preset === 'center_left') { x = 0.04; y = Math.max(0.02, (1.0 - h) / 2); }
  else if (preset === 'center_large') {
    w = 0.30;
    h = Math.min(0.96, w * (16 / 9) / avatarRatio);
    x = (1.0 - w) / 2;
    y = Math.max(0.02, 1.0 - h);
  }

  cfg.pip_box = {
    x: Math.round(x * 1000) / 1000,
    y: Math.round(y * 1000) / 1000,
    w: Math.round(w * 1000) / 1000,
    h: Math.round(h * 1000) / 1000
  };
  renderCanvasLayers(cfg);
  selectActiveCanvasLayer('avatar');
}

function onActiveLayerScaleSlider(val) {
  if (!slidesLayoutMap[currentCanvasSlideIndex]) return;
  const cfg = slidesLayoutMap[currentCanvasSlideIndex];
  cfg.layout = 'pip';
  let w = parseFloat(val) / 100;
  const valLabel = document.getElementById('sliderValLabel');
  if (valLabel) valLabel.textContent = `当前: ${Math.round(w * 100)}%`;

  if (activeCanvasLayer === 'ppt') {
    const pptRatio = (currentSession && currentSession.aspect_ratio) ? currentSession.aspect_ratio : (16 / 9);
    let h = w * (16 / 9) / pptRatio;
    if (h > 1.0) {
      h = 1.0;
      w = h * pptRatio / (16 / 9);
    }
    const box = cfg.ppt_box || { x: 0.0, y: 0.0, w: 1.0, h: 1.0 };
    box.w = Math.round(w * 1000) / 1000;
    box.h = Math.round(h * 1000) / 1000;
    if (box.x + box.w > 1.0) box.x = Math.max(0, 1.0 - box.w);
    if (box.y + box.h > 1.0) box.y = Math.max(0, 1.0 - box.h);
    cfg.ppt_box = box;
  } else {
    const avatarRatio = 720 / 1264;
    let h = w * (16 / 9) / avatarRatio;
    if (h > 1.0) {
      h = 1.0;
      w = h * avatarRatio / (16 / 9);
    }
    const box = cfg.pip_box || { x: 0.74, y: 0.35, w: 0.22, h: 0.68 };
    box.w = Math.round(w * 1000) / 1000;
    box.h = Math.round(h * 1000) / 1000;
    if (box.x + box.w > 1.0) box.x = Math.max(0, 1.0 - box.w);
    if (box.y + box.h > 1.0) box.y = Math.max(0, 1.0 - box.h);
    cfg.pip_box = box;
  }
  renderCanvasLayers(cfg);
}

function initOrUpdateCanvas() {
  if (!currentSession || !currentSession.slides.length) return;
  const slide = currentSession.slides[currentCanvasSlideIndex - 1];
  if (!slide) return;

  document.getElementById('canvasSlideIndicator').textContent = `第 ${slide.index} / ${currentSession.total_slides} 页`;

  const scriptText = document.getElementById(`narration-${slide.index}`)?.value?.trim() || slide.title || '智能微课讲解词...';
  document.getElementById('canvasSubPreview').textContent = `【字幕预览】${scriptText.slice(0, 36)}${scriptText.length > 36 ? '...' : ''}`;

  updateCanvasAvatarImage();

  if (!slidesLayoutMap[slide.index]) {
    slidesLayoutMap[slide.index] = {
      layout: 'pip',
      ppt_box: { x: 0.04, y: 0.10, w: 0.65, h: 0.76 },
      pip_box: { x: 0.71, y: 0.26, w: 0.25, h: 0.70 },
      custom_bg: 'studio_tech_blue.jpg',
      bg_blur: false,
    };
  }
  const cfg = slidesLayoutMap[slide.index];
  if (!cfg.layout) cfg.layout = 'pip';
  if (cfg.layout === 'pip' && (!cfg.ppt_box || (cfg.ppt_box.w >= 0.98 && cfg.ppt_box.h >= 0.98)) && (!cfg.custom_bg || cfg.custom_bg === 'blur')) {
    cfg.ppt_box = { x: 0.04, y: 0.10, w: 0.65, h: 0.76 };
    cfg.pip_box = { x: 0.71, y: 0.26, w: 0.25, h: 0.70 };
    cfg.custom_bg = 'studio_tech_blue.jpg';
    cfg.bg_blur = false;
  }
  const modeSel = document.getElementById('canvasLayoutModeSelect');
  if (modeSel) modeSel.value = cfg.layout;

  // 同步背景下拉选单
  const bgSel = document.getElementById('canvasBgSelect');
  if (bgSel) {
    if (cfg.custom_bg) bgSel.value = cfg.custom_bg;
    else if (cfg.bg_blur) bgSel.value = 'blur';
    else bgSel.value = 'black';
  }

  renderCanvasLayers(cfg);

  if (!canvasInitialized) {
    setupCanvasDragAndResize();
    loadAvailableBackgrounds();
    canvasInitialized = true;
  }
}

function renderCanvasLayers(cfg) {
  const slide = currentSession.slides[currentCanvasSlideIndex - 1];
  if (!slide) return;

  const mode = cfg.layout || 'pip';
  const customBg = document.getElementById('canvasCustomBg');
  const blurBg = document.getElementById('canvasBlurBg');
  const pptBox = document.getElementById('dragPptBox');
  const pptInner = document.getElementById('pptInnerImg');
  const avatarBox = document.getElementById('dragAvatarBox');

  const modeSel = document.getElementById('canvasLayoutModeSelect');
  if (modeSel && modeSel.value !== mode) modeSel.value = mode;

  if (mode === 'full_avatar') {
    if (pptBox) pptBox.style.display = 'none';
    if (avatarBox) {
      avatarBox.style.display = 'block';
      avatarBox.style.left = '25%';
      avatarBox.style.top = '0%';
      avatarBox.style.width = '50%';
      avatarBox.style.height = '100%';
    }
    if (customBg) customBg.style.display = 'none';
    if (blurBg) blurBg.style.display = 'none';
    updateCanvasHudCoord();
    return;
  }

  if (mode === 'full_slide') {
    if (pptBox) {
      pptBox.style.display = 'block';
      pptBox.style.left = '0%';
      pptBox.style.top = '0%';
      pptBox.style.width = '100%';
      pptBox.style.height = '100%';
      pptBox.classList.add('fullscreen');
      if (pptInner) pptInner.style.backgroundImage = `url('${slide.thumbnail_url}')`;
    }
    if (avatarBox) avatarBox.style.display = 'none';
    if (customBg) customBg.style.display = 'none';
    if (blurBg) blurBg.style.display = 'none';
    updateCanvasHudCoord();
    return;
  }

  // 自由排版 / 演播厅模式 (pip) 或 固定左右分屏 (split)
  if (pptBox) pptBox.style.display = 'block';
  if (avatarBox) avatarBox.style.display = 'block';

  // 1. 背景层
  if (cfg.custom_bg && cfg.custom_bg !== 'blur' && cfg.custom_bg !== 'black') {
    customBg.style.display = 'block';
    customBg.style.backgroundImage = `url('/api/lecture/backgrounds/${encodeURIComponent(cfg.custom_bg)}')`;
    blurBg.style.display = 'none';
  } else if (cfg.bg_blur || cfg.custom_bg === 'blur') {
    customBg.style.display = 'none';
    blurBg.style.display = 'block';
    blurBg.style.backgroundImage = `url('${slide.thumbnail_url}')`;
  } else {
    customBg.style.display = 'none';
    blurBg.style.display = 'none';
  }

  // 2. PPT 课件层
  const pb = cfg.ppt_box || { x: 0.0, y: 0.0, w: 1.0, h: 1.0 };
  pptBox.style.left = `${pb.x * 100}%`;
  pptBox.style.top = `${pb.y * 100}%`;
  pptBox.style.width = `${pb.w * 100}%`;
  pptBox.style.height = `${pb.h * 100}%`;
  pptInner.style.backgroundImage = `url('${slide.thumbnail_url}')`;
  const isFullscreen = (pb.w >= 0.98 && pb.h >= 0.98 && pb.x <= 0.02 && pb.y <= 0.02);
  pptBox.classList.toggle('fullscreen', isFullscreen);

  // 3. 数字人层
  const ab = cfg.pip_box || { x: 0.68, y: 0.40, w: 0.28, h: 0.56 };
  avatarBox.style.left = `${ab.x * 100}%`;
  avatarBox.style.top = `${ab.y * 100}%`;
  avatarBox.style.width = `${ab.w * 100}%`;
  avatarBox.style.height = `${ab.h * 100}%`;

  updateCanvasHudCoord();
}

function showToast(msg, duration = 3000) {
  let toast = document.getElementById('globalToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'globalToast';
    toast.className = 'global-toast';
    document.body.appendChild(toast);
  }
  toast.innerHTML = msg;
  toast.style.display = 'flex';
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => {
    toast.style.display = 'none';
  }, duration);
}

async function saveCurrentCanvasLayout(silent = false) {
  if (!currentSession) {
    if (!silent) alert('请先载入课件');
    return;
  }
  const sessionId = currentSession.session_id;
  try {
    const res = await fetch(`/api/lecture/sessions/${sessionId}/layout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        slides_layout: slidesLayoutMap,
      }),
    });
    const data = await res.json();
    if (res.ok) {
      try {
        localStorage.setItem(`lecture_layout_${sessionId}`, JSON.stringify(slidesLayoutMap));
      } catch(e) {}
      if (!silent) {
        showToast('💾 当前排版方案已成功保存！');
      }
    } else {
      if (!silent) alert('保存排版失败: ' + (data.detail || JSON.stringify(data)));
    }
  } catch(err) {
    if (!silent) alert('保存排版请求异常: ' + err.message);
  }
}

async function applyLayoutToAllSlides() {
  if (!currentSession || !slidesLayoutMap[currentCanvasSlideIndex]) return;
  const currentCfg = JSON.parse(JSON.stringify(slidesLayoutMap[currentCanvasSlideIndex]));
  currentCfg.layout = currentCfg.layout || 'pip';
  currentSession.slides.forEach(s => {
    slidesLayoutMap[s.index] = JSON.parse(JSON.stringify(currentCfg));
  });
  await saveCurrentCanvasLayout(true);
  showToast(`✨ 已成功将当前版面排版保存并同步应用到全部 ${currentSession.total_slides} 页幻灯片！`);
}

function setupCanvasDragAndResize() {
  const viewport = document.getElementById('canvasViewport');
  const pptBox = document.getElementById('dragPptBox');
  const pptHandle = document.getElementById('pptResizeHandle');
  const avatarBox = document.getElementById('dragAvatarBox');
  const avatarHandle = document.getElementById('avatarResizeHandle');

  // PPT 拖拽与缩放事件
  pptBox.addEventListener('mousedown', e => {
    if (e.target === pptHandle) return;
    if (slidesLayoutMap[currentCanvasSlideIndex]) slidesLayoutMap[currentCanvasSlideIndex].layout = 'pip';
    selectActiveCanvasLayer('ppt');
    isDraggingLayer = true;
    dragStartMouse = { x: e.clientX, y: e.clientY };
    const rect = viewport.getBoundingClientRect();
    const boxRect = pptBox.getBoundingClientRect();
    layerStartBox = {
      x: (boxRect.left - rect.left) / rect.width,
      y: (boxRect.top - rect.top) / rect.height,
      w: boxRect.width / rect.width,
      h: boxRect.height / rect.height,
    };
    e.preventDefault();
  });

  pptHandle.addEventListener('mousedown', e => {
    if (slidesLayoutMap[currentCanvasSlideIndex]) slidesLayoutMap[currentCanvasSlideIndex].layout = 'pip';
    selectActiveCanvasLayer('ppt');
    isResizingLayer = true;
    dragStartMouse = { x: e.clientX, y: e.clientY };
    const rect = viewport.getBoundingClientRect();
    const boxRect = pptBox.getBoundingClientRect();
    layerStartBox = {
      x: (boxRect.left - rect.left) / rect.width,
      y: (boxRect.top - rect.top) / rect.height,
      w: boxRect.width / rect.width,
      h: boxRect.height / rect.height,
    };
    e.stopPropagation();
    e.preventDefault();
  });

  // Avatar 拖拽与缩放事件
  avatarBox.addEventListener('mousedown', e => {
    if (e.target === avatarHandle) return;
    if (slidesLayoutMap[currentCanvasSlideIndex]) slidesLayoutMap[currentCanvasSlideIndex].layout = 'pip';
    selectActiveCanvasLayer('avatar');
    isDraggingLayer = true;
    dragStartMouse = { x: e.clientX, y: e.clientY };
    const rect = viewport.getBoundingClientRect();
    const boxRect = avatarBox.getBoundingClientRect();
    layerStartBox = {
      x: (boxRect.left - rect.left) / rect.width,
      y: (boxRect.top - rect.top) / rect.height,
      w: boxRect.width / rect.width,
      h: boxRect.height / rect.height,
    };
    e.preventDefault();
  });

  avatarHandle.addEventListener('mousedown', e => {
    if (slidesLayoutMap[currentCanvasSlideIndex]) slidesLayoutMap[currentCanvasSlideIndex].layout = 'pip';
    selectActiveCanvasLayer('avatar');
    isResizingLayer = true;
    dragStartMouse = { x: e.clientX, y: e.clientY };
    const rect = viewport.getBoundingClientRect();
    const boxRect = avatarBox.getBoundingClientRect();
    layerStartBox = {
      x: (boxRect.left - rect.left) / rect.width,
      y: (boxRect.top - rect.top) / rect.height,
      w: boxRect.width / rect.width,
      h: boxRect.height / rect.height,
    };
    e.stopPropagation();
    e.preventDefault();
  });

  // 统一的平移与缩放监听
  window.addEventListener('mousemove', e => {
    if (!isDraggingLayer && !isResizingLayer) return;
    const rect = viewport.getBoundingClientRect();
    const cfg = slidesLayoutMap[currentCanvasSlideIndex];
    if (!cfg) return;

    if (isDraggingLayer) {
      const dx = (e.clientX - dragStartMouse.x) / rect.width;
      const dy = (e.clientY - dragStartMouse.y) / rect.height;

      let newX = layerStartBox.x + dx;
      let newY = layerStartBox.y + dy;

      newX = Math.max(0, Math.min(1 - layerStartBox.w, newX));
      newY = Math.max(0, Math.min(1 - layerStartBox.h, newY));

      const b = {
        x: Math.round(newX * 1000) / 1000,
        y: Math.round(newY * 1000) / 1000,
        w: Math.round(layerStartBox.w * 1000) / 1000,
        h: Math.round(layerStartBox.h * 1000) / 1000,
      };
      if (activeCanvasLayer === 'ppt') {
        cfg.ppt_box = b;
      } else {
        cfg.pip_box = b;
      }
      renderCanvasLayers(cfg);
    } else if (isResizingLayer) {
      const dx = (e.clientX - dragStartMouse.x) / rect.width;
      let newW = layerStartBox.w + dx;

      if (activeCanvasLayer === 'ppt') {
        const pptRatio = (currentSession && currentSession.aspect_ratio) ? currentSession.aspect_ratio : (16 / 9);
        newW = Math.max(0.20, Math.min(1.0, newW));
        let newH = newW * (16 / 9) / pptRatio;
        if (newH > 1.0) {
          newH = 1.0;
          newW = newH * pptRatio / (16 / 9);
        }
        let newX = layerStartBox.x;
        let newY = layerStartBox.y;
        if (newX + newW > 1.0) newX = 1.0 - newW;
        if (newY + newH > 1.0) newY = 1.0 - newH;
        cfg.ppt_box = {
          x: Math.round(newX * 1000) / 1000,
          y: Math.round(newY * 1000) / 1000,
          w: Math.round(newW * 1000) / 1000,
          h: Math.round(newH * 1000) / 1000,
        };
      } else {
        const avatarRatio = 720 / 1264;
        newW = Math.max(0.12, Math.min(0.60, newW));
        let newH = newW * (16 / 9) / avatarRatio;
        if (newH > 1.0) {
          newH = 1.0;
          newW = newH * avatarRatio / (16 / 9);
        }
        let newX = layerStartBox.x;
        let newY = layerStartBox.y;
        if (newX + newW > 1.0) newX = 1.0 - newW;
        if (newY + newH > 1.0) newY = 1.0 - newH;
        cfg.pip_box = {
          x: Math.round(newX * 1000) / 1000,
          y: Math.round(newY * 1000) / 1000,
          w: Math.round(newW * 1000) / 1000,
          h: Math.round(newH * 1000) / 1000,
        };
      }
      renderCanvasLayers(cfg);
    }
  });

  window.addEventListener('mouseup', () => {
    if (isDraggingLayer || isResizingLayer) {
      if (currentSession && slidesLayoutMap) {
        try {
          localStorage.setItem(`lecture_layout_${currentSession.session_id}`, JSON.stringify(slidesLayoutMap));
        } catch(e) {}
      }
    }
    isDraggingLayer = false;
    isResizingLayer = false;
  });
}

function updatePhaseStepper(stage) {
  const currentStage = Math.max(1, Math.min(5, stage || 1));
  const stagesTitles = {
    1: "阶段 1：课件解析与底板生成",
    2: "阶段 2：逐页语音高保真合成",
    3: "阶段 3：逐页数字人驱动与音唇同步",
    4: "阶段 4：排版混剪与内嵌字幕烧录",
    5: "微课全流程制作完成！",
  };
  const titleEl = document.getElementById('hudStageTitle');
  if (titleEl && stagesTitles[currentStage]) {
    titleEl.textContent = stagesTitles[currentStage];
  }

  for (let i = 1; i <= 4; i++) {
    const stepEl = document.getElementById(`pstep-${i}`);
    const lineEl = document.getElementById(`pline-${i}`);
    const iconEl = document.getElementById(`picon-${i}`);
    if (!stepEl) continue;

    stepEl.classList.remove('active', 'done');
    if (i < currentStage || currentStage === 5) {
      stepEl.classList.add('done');
      if (iconEl) iconEl.textContent = '✓';
      if (lineEl) lineEl.classList.add('done');
    } else if (i === currentStage) {
      stepEl.classList.add('active');
      if (iconEl) iconEl.textContent = i;
      if (lineEl) lineEl.classList.remove('done');
    } else {
      if (iconEl) iconEl.textContent = i;
      if (lineEl) lineEl.classList.remove('done');
    }
  }
}

function renderSlideMatrix(slideProg) {
  const container = document.getElementById('slideMatrixContainer');
  if (!container || !slideProg) return;

  const total = slideProg.total_slides || 0;
  const audioMap = slideProg.audio || {};
  const videoMap = slideProg.video || {};

  let html = '';
  for (let i = 1; i <= total; i++) {
    const aStat = audioMap[i] || 'pending';
    const vStat = videoMap[i] || 'pending';

    const aBadge = aStat === 'done'
      ? '<span class="matrix-badge done">✓ 音频完成</span>'
      : (aStat === 'synthesizing' ? '<span class="matrix-badge running">⏳ 正在合成</span>' : '<span class="matrix-badge pending">等待合成</span>');

    const vBadge = vStat === 'done'
      ? '<span class="matrix-badge done">✓ 视频完成</span>'
      : (vStat === 'rendering' ? '<span class="matrix-badge running">⏳ 正在渲染</span>' : '<span class="matrix-badge pending">等待渲染</span>');

    html += `
      <div class="matrix-card">
        <div style="font-weight:700;color:#cbd5e1;margin-bottom:6px">第 ${i} 页幻灯片</div>
        <div style="display:flex;flex-direction:column;gap:4px">
          <div>${aBadge}</div>
          <div>${vBadge}</div>
        </div>
      </div>
    `;
  }
  container.innerHTML = html;
}

async function handleProduceCourse() {
  if (!currentSession) {
    alert('请先完成课件解析');
    return;
  }
  const produceBtn = document.getElementById('produceBtn');
  produceBtn.disabled = true;
  produceBtn.textContent = '⏳ 正在提交微课生产流水线…';

  // 提交生成前自动持久化最新排版方案
  await saveCurrentCanvasLayout(true);

  const slidesPayload = currentSession.slides.map(s => {
    const narrationText = document.getElementById(`narration-${s.index}`).value;
    const cfg = slidesLayoutMap[s.index] || {
      layout: 'pip',
      ppt_box: { x: 0.04, y: 0.10, w: 0.65, h: 0.76 },
      pip_box: { x: 0.71, y: 0.26, w: 0.25, h: 0.70 },
      custom_bg: 'studio_tech_blue.jpg',
      bg_blur: false,
    };
    return {
      index: s.index,
      title: s.title,
      narration: narrationText,
      layout: cfg.layout || 'pip',
      pip_box: cfg.pip_box,
      ppt_box: cfg.ppt_box,
      custom_bg: cfg.custom_bg,
      bg_blur: cfg.bg_blur,
    };
  });

  const selectedProfile = document.getElementById('lectureProfileSelect').value;
  const speedVal = parseFloat(document.getElementById('speedSelect').value || '1.0');
  const emotionVal = document.getElementById('emotionSelect').value || 'professional';
  const subtitleMode = document.getElementById('subtitlesSelect').value;

  const payload = {
    session_id: currentSession.session_id,
    title: currentSession.title,
    profile_id: selectedProfile,
    profile: selectedProfile,
    speed: speedVal,
    emotion: emotionVal,
    burn_subtitles: subtitleMode === 'burn',
    bgm: document.getElementById('bgmSelect').value || null,
    subtitles: subtitleMode !== 'none',
    slides: slidesPayload,
  };

  try {
    const res = await fetch('/api/lecture/build', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const job = await res.json();
    if (!res.ok) {
      alert('任务创建失败: ' + (job.detail || JSON.stringify(job)));
      produceBtn.disabled = false;
      produceBtn.textContent = '🚀 开始制作数字人微课视频';
      return;
    }

    document.getElementById('lectureJobBox').style.display = 'block';
    document.getElementById('lectureJobBox').scrollIntoView({behavior:'smooth'});
    pollLectureJob(job.job_id);
  } catch(err) {
    alert('请求异常: ' + err.message);
    produceBtn.disabled = false;
    produceBtn.textContent = '🚀 开始制作数字人微课视频';
  }
}

async function pollLectureJob(jobId) {
  const progressFill = document.getElementById('jobProgressFill');
  const pctText = document.getElementById('jobPctText');
  const detailEl = document.getElementById('currentStepDetail');
  const elapsedEl = document.getElementById('elapsedTimeText');
  const etaEl = document.getElementById('etaTimeText');
  const videoContainer = document.getElementById('videoContainer');
  const produceBtn = document.getElementById('produceBtn');

  try {
    const res = await fetch(`/api/lecture/jobs/${jobId}`);
    const j = await res.json();

    // 更新 4 阶段进度条
    updatePhaseStepper(j.stage);

    // 更新百分比与流光进度条
    const pct = j.progress || 5;
    if (progressFill) progressFill.style.width = `${pct}%`;
    if (pctText) pctText.textContent = `${pct}%`;

    // 细粒度步骤详情
    if (detailEl) {
      if (j.error) {
        detailEl.innerHTML = `<span style="color:#f87171">制作失败: ${escapeHtml(j.message || j.error)}</span>`;
      } else {
        detailEl.textContent = j.step_detail || j.message || '正在处理微课生成任务...';
      }
    }

    // 耗时与预估时间
    if (elapsedEl) elapsedEl.textContent = `${j.elapsed_seconds || 0}s`;
    if (etaEl) {
      if (j.status === 'completed') {
        etaEl.textContent = '制作完毕';
      } else if (j.status === 'failed') {
        etaEl.textContent = '已中止';
      } else {
        etaEl.textContent = `约 ${Math.round(j.eta_seconds || 0)}s`;
      }
    }

    // 更新逐页流水线矩阵
    if (j.slide_progress) {
      renderSlideMatrix(j.slide_progress);
    }

    if (j.status === 'completed') {
      if (progressFill) progressFill.style.width = '100%';
      if (pctText) pctText.textContent = '100%';
      produceBtn.disabled = false;
      produceBtn.textContent = '🚀 再次制作数字人微课视频';

      const videoUrl = `/api/lecture/jobs/${jobId}/video`;
      const srtUrl = `/api/lecture/jobs/${jobId}/subtitles`;

      const player = document.getElementById('finalVideoPlayer');
      player.src = videoUrl;
      document.getElementById('downloadVideoBtn').href = videoUrl;
      document.getElementById('downloadSrtBtn').href = srtUrl;
      videoContainer.style.display = 'block';
      videoContainer.scrollIntoView({behavior:'smooth'});
      return;
    }

    if (j.status !== 'failed') {
      setTimeout(() => pollLectureJob(jobId), 2000);
    } else {
      produceBtn.disabled = false;
      produceBtn.textContent = '🚀 开始制作数字人微课视频';
    }
  } catch(e) {
    setTimeout(() => pollLectureJob(jobId), 3000);
  }
}

function escapeHtml(str) {
  return (str || '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

// Single task mode handlers
function chooseSingleEngine(engine) {
  document.getElementById('singleEngine').value = 'musetalk';
  document.getElementById('singleMusetalkPanel').classList.add('active');
  document.getElementById('singleSubmitBtn').textContent = '生成极速数字人片段';
}

document.getElementById('singleForm').onsubmit = async (e) => {
  e.preventDefault();
  const statusEl = document.getElementById('singleStatus');
  statusEl.textContent = '正在提交任务…';
  const r = await fetch('/api/jobs', {method:'POST', body:new FormData(e.target)});
  const data = await r.json();
  if(!r.ok){ statusEl.textContent = JSON.stringify(data, null, 2); return; }
  pollSingleJob(data.id);
};

async function pollSingleJob(id) {
  const r = await fetch('/api/jobs/' + id), j = await r.json();
  const statusEl = document.getElementById('singleStatus');
  statusEl.textContent = `任务 ${id}\n引擎: ${j.engine}\n状态: ${j.status}` + (j.error?`\n${j.error}`:'');
  if(j.status === 'completed') {
    statusEl.innerHTML = `任务 ${id}<br>状态: completed<br><a href="/api/jobs/${id}/video" target="_blank" style="color:#60a5fa">打开生成视频</a>`;
    return;
  }
  if(j.status !== 'failed') setTimeout(() => pollSingleJob(id), 2500);
}

loadCatalog().then(() => {
  loadRecentLectureSessions();
  const urlParams = new URLSearchParams(window.location.search);
  const sid = urlParams.get('session_id');
  if (sid) {
    loadLectureSessionById(sid, parseInt(urlParams.get('step')) || 2);
  }
});
</script>
</body>
</html>'''


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return HTML


@app.get("/api/health")
def health() -> dict:
    return manager.readiness()


@app.get("/api/catalog")
def catalog() -> dict:
    profiles = []
    for item in list_avatar_profiles():
        profiles.append(
            {
                "id": item["id"],
                "name": item["name"],
                "prompt_preset": item.get("prompt_preset"),
                "prompt": item.get("prompt", ""),
                "has_image": bool(item.get("image") and Path(item["image"]).exists()),
                "has_master_video": bool(item.get("master_video") and Path(item["master_video"]).exists()),
                "clone_voice": bool((item.get("tts") or {}).get("ref_audio")),
            }
        )
    return {"prompts": list_prompt_presets(), "profiles": profiles}


# ==========================================
# Digital Human Profile Studio APIs
# ==========================================

@app.get("/api/profiles")
def list_profiles_endpoint() -> list[dict[str, Any]]:
    """Retrieve full catalog of custom and builtin avatar profiles."""
    profiles = []
    for item in list_avatar_profiles():
        profile_id = item["id"]
        ref_audio = (item.get("tts") or {}).get("ref_audio")
        has_voice = bool(ref_audio and Path(ref_audio).exists())
        has_img = bool(item.get("image") and Path(item["image"]).exists())
        has_video = bool(item.get("master_video") and Path(item["master_video"]).exists())

        profiles.append(
            {
                "id": profile_id,
                "name": item["name"],
                "prompt_preset": item.get("prompt_preset"),
                "prompt": item.get("prompt", ""),
                "has_image": has_img,
                "has_master_video": has_video,
                "clone_voice": has_voice,
                "ref_text": (item.get("tts") or {}).get("ref_text", ""),
                "provider": (item.get("tts") or {}).get("provider", "cosyvoice2"),
                "is_builtin": profile_id == "dan",
                "image_url": f"/api/profiles/{profile_id}/image" if has_img else "",
                "video_url": f"/api/profiles/{profile_id}/video" if has_video else "",
                "audio_url": f"/api/profiles/{profile_id}/audio" if has_voice else "",
            }
        )
    return profiles


@app.get("/api/profiles/{profile_id}/image")
def get_profile_image(profile_id: str):
    """Retrieve avatar portrait image."""
    item = get_avatar_profile(profile_id)
    if not item or not item.get("image"):
        raise HTTPException(404, f"Profile image not found: {profile_id}")
    img_path = Path(item["image"]).resolve()
    if not img_path.exists():
        raise HTTPException(404, "Profile image file missing")
    media_type = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(img_path, media_type=media_type)


@app.get("/api/profiles/{profile_id}/video")
def get_profile_video(profile_id: str):
    """Retrieve master reference video for MuseTalk driving."""
    item = get_avatar_profile(profile_id)
    if not item or not item.get("master_video"):
        raise HTTPException(404, f"Profile master video not found: {profile_id}")
    video_path = Path(item["master_video"]).resolve()
    if not video_path.exists():
        raise HTTPException(404, "Profile master video file missing")
    return FileResponse(video_path, media_type="video/mp4")


@app.get("/api/profiles/{profile_id}/audio")
def get_profile_audio(profile_id: str):
    """Retrieve reference voice clone audio."""
    item = get_avatar_profile(profile_id)
    ref_audio = (item.get("tts") or {}).get("ref_audio") if item else None
    if not ref_audio:
        raise HTTPException(404, f"Profile audio not found: {profile_id}")
    audio_path = Path(ref_audio).resolve()
    if not audio_path.exists():
        raise HTTPException(404, "Profile audio file missing")
    return FileResponse(audio_path, media_type="audio/wav")


@app.post("/api/profiles")
async def create_profile_endpoint(
    name: str = Form(...),
    profile_id: str | None = Form(None),
    image: UploadFile = File(...),
    audio: UploadFile | None = File(None),
    master_video: UploadFile | None = File(None),
    ref_text: str = Form(""),
    prompt_preset: str = Form("energy_training_studio"),
    prompt: str = Form(""),
    provider: str = Form("cosyvoice2"),
) -> dict[str, Any]:
    """Create and persist a custom digital human profile with image and cloned voice."""
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "必须上传数字人形象照片")

    audio_bytes = await audio.read() if audio else None
    video_bytes = await master_video.read() if master_video else None

    profile = create_avatar_profile(
        name=name,
        image_bytes=image_bytes,
        image_filename=image.filename or "portrait.png",
        profile_id=profile_id,
        audio_bytes=audio_bytes,
        audio_filename=audio.filename if audio else None,
        ref_text=ref_text,
        master_video_bytes=video_bytes,
        master_video_filename=master_video.filename if master_video else None,
        prompt_preset=prompt_preset,
        prompt=prompt,
        provider=provider,
    )
    return {"status": "ok", "profile": profile}


@app.post("/api/profiles/{profile_id}")
@app.put("/api/profiles/{profile_id}")
@app.post("/api/profiles/{profile_id}/update")
async def update_profile_endpoint(
    profile_id: str,
    name: str | None = Form(None),
    image: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
    master_video: UploadFile | None = File(None),
    ref_text: str | None = Form(None),
    prompt_preset: str | None = Form(None),
    prompt: str | None = Form(None),
    provider: str | None = Form(None),
) -> dict[str, Any]:
    """Update an existing digital human profile (e.g. modify master video, portrait, voice)."""
    image_bytes = await image.read() if image and image.filename else None
    audio_bytes = await audio.read() if audio and audio.filename else None
    video_bytes = await master_video.read() if master_video and master_video.filename else None

    try:
        updated = update_avatar_profile(
            profile_id=profile_id,
            name=name,
            image_bytes=image_bytes,
            image_filename=image.filename if image else None,
            audio_bytes=audio_bytes,
            audio_filename=audio.filename if audio else None,
            ref_text=ref_text,
            master_video_bytes=video_bytes,
            master_video_filename=master_video.filename if master_video else None,
            prompt_preset=prompt_preset,
            prompt=prompt,
            provider=provider,
        )
        return {"status": "ok", "profile": updated}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"更新人设失败: {e}")


@app.delete("/api/profiles/{profile_id}")
def delete_profile_endpoint(profile_id: str) -> dict[str, Any]:
    """Delete a custom avatar profile and its associated files."""
    ok = delete_avatar_profile(profile_id)
    if not ok:
        raise HTTPException(400, f"无法删除内置人设或未找到该人设: {profile_id}")
    return {"status": "ok", "message": f"人设 {profile_id} 已成功删除"}



def _save_upload(upload: UploadFile, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return target


def _profile_asset(profile: dict | None, key: str) -> Path | None:
    if not profile or not profile.get(key):
        return None
    path = Path(str(profile[key])).expanduser().resolve()
    return path if path.exists() else None



# ==========================================
# PPT Micro-Course Studio APIs
# ==========================================

@app.post("/api/lecture/parse")
def parse_lecture_ppt(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload and parse a PPTX or PDF file into slides with extracted notes and 1080p preview images."""
    suffix = Path(file.filename or "deck.pptx").suffix.lower()
    if suffix not in {".pptx", ".ppt", ".pdf"}:
        raise HTTPException(400, "仅支持上传 .pptx 或 .pdf 课件格式")

    session_id = f"sess-{int(uuid.uuid4().int % 100000000):08d}"
    stage_dir = settings.workspace_dir / "lecture_uploads" / session_id
    stage_dir.mkdir(parents=True, exist_ok=True)

    saved_file = stage_dir / f"source{suffix}"
    _save_upload(file, saved_file)

    try:
        deck: CourseDeck = PresentationParser.parse(saved_file)
        # Render 1080P slide preview thumbnails
        slides_dir = stage_dir / "slides"
        PPTRenderer.render_deck(deck, slides_dir)
    except Exception as exc:
        raise HTTPException(500, f"课件解析与图像导出失败: {exc}") from exc

    slides_info = []
    for s in deck.slides:
        slides_info.append(
            {
                "index": s.index,
                "title": s.title,
                "bullets": s.bullets,
                "notes": s.notes,
                "narration": s.narration,
                "layout": s.layout,
                "thumbnail_url": f"/api/lecture/sessions/{session_id}/slides/{s.index}/thumbnail",
            }
        )

    # Detect actual slide image dimensions
    slide_w, slide_h = 1920, 1080
    first_slide_img = stage_dir / "slides" / "slide_001.png"
    if first_slide_img.exists():
        try:
            from PIL import Image
            with Image.open(first_slide_img) as _im:
                slide_w, slide_h = _im.size
        except Exception:
            pass
    aspect_ratio = round(slide_w / slide_h, 4) if slide_h else 1.7778

    # Save parsed manifest cache
    meta = {
        "session_id": session_id,
        "title": deck.title,
        "source_file": str(saved_file),
        "total_slides": deck.total_slides,
        "slide_width": slide_w,
        "slide_height": slide_h,
        "aspect_ratio": aspect_ratio,
        "slides_layout": {},
        "slides": slides_info,
    }
    (stage_dir / "deck_info.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return meta


@app.get("/api/lecture/sessions/{session_id}/slides/{slide_index}/thumbnail")
def get_slide_thumbnail(session_id: str, slide_index: int):
    """Retrieve 1080P rendered thumbnail image for a specific slide."""
    slide_file = settings.workspace_dir / "lecture_uploads" / session_id / "slides" / f"slide_{slide_index:03d}.png"
    if not slide_file.exists():
        raise HTTPException(404, f"Slide thumbnail not found: {session_id} / {slide_index}")
    return FileResponse(slide_file, media_type="image/png")


@app.get("/api/lecture/sessions/recent")
def get_recent_lecture_sessions():
    """List recent parsed lecture deck sessions for quick loading."""
    uploads_dir = settings.workspace_dir / "lecture_uploads"
    if not uploads_dir.exists():
        return {"sessions": []}

    sessions = []
    for item in sorted(uploads_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not item.is_dir():
            continue
        info_file = item / "deck_info.json"
        if info_file.exists():
            try:
                data = json.loads(info_file.read_text(encoding="utf-8"))
                sessions.append({
                    "session_id": data.get("session_id", item.name),
                    "title": data.get("title", item.name),
                    "total_slides": data.get("total_slides", len(data.get("slides", []))),
                    "updated_at": item.stat().st_mtime,
                })
            except Exception:
                continue
    return {"sessions": sessions[:10]}


@app.get("/api/lecture/sessions/{session_id}")
@app.get("/api/lecture/session/{session_id}")
def get_lecture_session(session_id: str):
    """Retrieve full lecture deck details for a specific session."""
    stage_dir = settings.workspace_dir / "lecture_uploads" / session_id
    info_file = stage_dir / "deck_info.json"
    if not info_file.exists():
        raise HTTPException(404, f"Session not found: {session_id}")
    try:
        data = json.loads(info_file.read_text(encoding="utf-8"))
        if "aspect_ratio" not in data:
            slide_w, slide_h = 1920, 1080
            first_slide_img = stage_dir / "slides" / "slide_001.png"
            if first_slide_img.exists():
                try:
                    from PIL import Image
                    with Image.open(first_slide_img) as _im:
                        slide_w, slide_h = _im.size
                except Exception:
                    pass
            data["slide_width"] = slide_w
            data["slide_height"] = slide_h
            data["aspect_ratio"] = round(slide_w / slide_h, 4)
        return data
    except Exception as exc:
        raise HTTPException(500, f"Failed to read session data: {exc}")


@app.post("/api/lecture/sessions/{session_id}/layout")
def save_lecture_session_layout(session_id: str, payload: dict[str, Any] = Body(...)):
    """Persist user custom canvas layouts into session deck_info.json."""
    info_file = settings.workspace_dir / "lecture_uploads" / session_id / "deck_info.json"
    if not info_file.exists():
        raise HTTPException(404, f"Session not found: {session_id}")
    try:
        data = json.loads(info_file.read_text(encoding="utf-8"))
        data["slides_layout"] = payload.get("slides_layout", {})
        info_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", "message": "排版配置已成功保存", "slides_layout": data["slides_layout"]}
    except Exception as exc:
        raise HTTPException(500, f"保存排版配置失败: {exc}")



@app.get("/api/lecture/backgrounds")
def list_lecture_backgrounds():
    """List preset and custom uploaded background images."""
    bg_dir = settings.workspace_dir / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)
    items = []

    preset_names = {
        "studio_tech_blue.jpg": "🏢 现代科技蓝演播室 (预设)",
        "studio_executive_dark.jpg": "🏛️ 高端商务暗黑发布会 (预设)",
        "studio_academic_warm.jpg": "📚 典雅学术暖调书房 (预设)",
        "studio_cyber_neon.jpg": "🔮 极简流光微课展台 (预设)",
    }

    for f in sorted(bg_dir.glob("*.*")):
        if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            if f.name in preset_names:
                name = preset_names[f.name]
            else:
                m = re.match(r"^custom_(.+)_\d+_[a-f0-9]+(\.[a-zA-Z0-9]+)$", f.name)
                if m:
                    name = f"🖼️ 自定义: {m.group(1)}{m.group(2)}"
                else:
                    name = f"🖼️ 自定义: {f.name}"
            items.append({
                "id": f.name,
                "name": name,
                "url": f"/api/lecture/backgrounds/{f.name}",
                "file_path": str(f.resolve()),
                "is_preset": f.name in preset_names,
            })
    return {"backgrounds": items}


@app.post("/api/lecture/backgrounds/upload")
def upload_lecture_background(file: UploadFile = File(...)):
    """Upload custom background image for micro-courses."""
    suffix = Path(file.filename or "bg.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "仅支持上传 JPG、PNG 或 WEBP 格式背景图片")

    bg_dir = settings.workspace_dir / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)
    raw_stem = Path(file.filename or "bg").stem
    clean_stem = re.sub(r'[^a-zA-Z0-9_\-\u4e00-\u9fa5]', '_', raw_stem)[:24]
    filename = f"custom_{clean_stem}_{int(time.time())}_{uuid.uuid4().hex[:4]}{suffix}"
    saved_path = bg_dir / filename
    _save_upload(file, saved_path)

    return {
        "id": filename,
        "name": f"🖼️ 自定义: {file.filename}",
        "url": f"/api/lecture/backgrounds/{filename}",
        "file_path": str(saved_path.resolve()),
    }


@app.get("/api/lecture/backgrounds/{filename}")
def get_lecture_background_image(filename: str):
    """Serve background image."""
    bg_file = settings.workspace_dir / "backgrounds" / filename
    if not bg_file.exists():
        raise HTTPException(404, "Background image not found")
    suf = bg_file.suffix.lower()
    if suf == ".png":
        media_type = "image/png"
    elif suf == ".webp":
        media_type = "image/webp"
    else:
        media_type = "image/jpeg"
    return FileResponse(bg_file, media_type=media_type)


@app.post("/api/lecture/build")
def create_lecture_job(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Start asynchronous background lecture video production."""
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(400, "session_id is required")

    stage_dir = settings.workspace_dir / "lecture_uploads" / session_id
    deck_meta_file = stage_dir / "deck_info.json"
    if not deck_meta_file.exists():
        raise HTTPException(404, "Lecture session expired or not found")

    meta = json.loads(deck_meta_file.read_text(encoding="utf-8"))
    source_file = Path(meta["source_file"])
    if not source_file.exists():
        raise HTTPException(404, "Source presentation file missing")

    job = lecture_job_manager.create_job(
        ppt_path=source_file,
        manifest_override=payload,
    )
    return {"job_id": job.id, "status": job.status, "message": job.message}


@app.get("/api/lecture/jobs/{job_id}")
def get_lecture_job(job_id: str) -> dict[str, Any]:
    job = lecture_job_manager.get(job_id)
    if not job:
        raise HTTPException(404, "Lecture job not found")
    return job.to_dict()


@app.get("/api/lecture/jobs/{job_id}/video")
def get_lecture_video(job_id: str):
    job = lecture_job_manager.get(job_id)
    if not job or job.status != "completed" or not job.output_video:
        raise HTTPException(404, "Video not ready or job failed")
    output = Path(job.output_video).resolve()
    if not output.exists():
        raise HTTPException(404, "Video file not found on disk")
    return FileResponse(output, media_type="video/mp4", filename=f"{job.title or job_id}.mp4")


@app.get("/api/lecture/jobs/{job_id}/subtitles")
def get_lecture_subtitles(job_id: str):
    job = lecture_job_manager.get(job_id)
    if not job or not job.srt_path:
        raise HTTPException(404, "Subtitles not ready")
    srt_file = Path(job.srt_path).resolve()
    if not srt_file.exists():
        raise HTTPException(404, "SRT file not found")
    return FileResponse(srt_file, media_type="text/plain", filename=f"{job_id}.srt")


# ==========================================
# Original Single-Task Generation APIs
# ==========================================

@app.post("/api/jobs")
def create_job(
    engine: str = Form("musetalk"),
    audio: UploadFile = File(...),
    video: UploadFile | None = File(None),
    profile_id: str = Form(""),
    variant: str | None = Form(None),
    musetalk_variant: str = Form("q8"),
) -> dict:
    if engine != "musetalk":
        raise HTTPException(400, "engine must be musetalk")

    profile = get_avatar_profile(profile_id) if profile_id else None
    if profile_id and profile is None:
        raise HTTPException(400, f"avatar profile not found: {profile_id}")

    stage = settings.workspace_dir / "uploads" / uuid.uuid4().hex
    stage.mkdir(parents=True, exist_ok=True)
    audio_suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    audio_path = _save_upload(audio, stage / f"audio{audio_suffix}")

    resolved_variant = variant or musetalk_variant
    if resolved_variant not in {"q4", "q8", "fp16"}:
        raise HTTPException(400, "MuseTalk variant must be q4, q8 or fp16")
    if video is not None:
        video_suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
        video_path = _save_upload(video, stage / f"video{video_suffix}")
    else:
        video_path = _profile_asset(profile, "master_video")
    if video_path is None:
        raise HTTPException(400, "MuseTalk requires an uploaded video or a profile with master_video")
    job = manager.create("musetalk", video=video_path, audio=audio_path, variant=resolved_variant)
    return job.to_dict()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/video")
def get_video(job_id: str):
    job = manager.get(job_id)
    if not job or job.status != "completed" or not job.output:
        raise HTTPException(404, "completed video not found")
    output = Path(job.output).resolve()
    root = settings.outputs_dir.resolve()
    if root not in output.parents:
        raise HTTPException(403, "invalid output path")
    return FileResponse(output, media_type="video/mp4", filename=f"{job_id}.mp4")


@app.get("/api/demo/passionate/video")
def get_passionate_demo_video():
    video = settings.outputs_dir / "demo_passionate" / "passionate_115x_demo.mp4"
    if not video.exists():
        raise HTTPException(404, "Demo video not found")
    return FileResponse(video, media_type="video/mp4")


@app.get("/api/demo/passionate/audio")
def get_passionate_demo_audio():
    audio = settings.outputs_dir / "demo_passionate" / "speech_115x_passionate.wav"
    if not audio.exists():
        raise HTTPException(404, "Demo audio not found")
    return FileResponse(audio, media_type="audio/wav")


@app.get("/api/demo/passionate/avatar")
def get_passionate_demo_avatar():
    avatar = settings.outputs_dir / "demo_passionate" / "avatar_dynamic_musetalk.mp4"
    if not avatar.exists():
        raise HTTPException(404, "Dynamic avatar not found")
    return FileResponse(avatar, media_type="video/mp4")


@app.get("/api/demo/wudan2/video")
def get_wudan2_demo_video():
    video = settings.outputs_dir / "test_wudan2" / "wudan2_lecture_demo.mp4"
    if not video.exists():
        raise HTTPException(404, "吴丹2微课视频未找到")
    return FileResponse(video, media_type="video/mp4")


@app.get("/api/demo/wudan2/avatar")
def get_wudan2_demo_avatar():
    avatar = settings.outputs_dir / "test_wudan2" / "wudan2_avatar_demo.mp4"
    if not avatar.exists():
        raise HTTPException(404, "吴丹2数字人切片未找到")
    return FileResponse(avatar, media_type="video/mp4")


@app.get("/api/demo/wudan2/audio")
def get_wudan2_demo_audio():
    audio = settings.outputs_dir / "test_wudan2" / "speech_115x.wav"
    if not audio.exists():
        raise HTTPException(404, "吴丹2克隆音频未找到")
    return FileResponse(audio, media_type="audio/wav")
