# Roadmap

## Phase 1 — 本地口播 MVP（当前）

- 母版视频 + 新音频 → 口型同步 MP4
- Apple Silicon / MLX 优先
- CLI / Web / FastAPI
- 本地任务与日志
- M5 Pro 48GB 首机验收

## Phase 2 — 数字讲师增强

- 集成 FasterLivePortrait-MLX
- 表情、眨眼、头部动作增强
- 母版模板管理
- 片段自动拼接
- 字幕与片头片尾

## Phase 3 — 声音克隆与课程生产

- 可插拔 TTS / voice clone provider
- 中文长文本分段和韵律控制
- PPT / PDF → 页面脚本 → TTS → 数字讲师 → 成片
- 课程批量任务

## Phase 4 — 实时数字专家

- ASR → LLM/Agent → TTS → 数字人
- WebRTC / 低延迟流
- RAG / 企业知识库
- 工具调用与业务 Agent

## 设计原则

1. 上游模型与业务编排解耦。
2. 默认本地处理用户视频和声音。
3. 不把模型大文件提交到 Git。
4. 对不同引擎提供统一 Adapter。
5. 先稳定，再追求全身生成和复杂动作。
