# Roadmap

## Phase 1 — 双引擎本地 MVP（当前）

- MuseTalk：母版视频 + 新音频 → 快速口型同步 MP4
- LongCat Avatar 1.5：参考照片 + 音频 + Prompt → 高质量动态数字人
- Apple Silicon / MLX 优先
- M5 Pro 48GB：MuseTalk Q8 + LongCat Q4 merged
- CLI / Web / FastAPI 统一入口
- 单机串行任务队列与日志
- M5 Pro 48GB 首机真实样例验收

## Phase 2 — 生产效率

- LongCat 参考人物模板与 Prompt 预设
- 母版视频预处理缓存
- 批量任务清单
- 字幕、片头片尾、背景音乐
- LongCat 精品片段 + MuseTalk 正文自动混剪
- LongCat continuation / 长视频分段策略

## Phase 3 — 数字讲师增强

- 集成 FasterLivePortrait-MLX
- 表情、眨眼、头部动作增强
- 声音克隆 / 可插拔 TTS
- 中文长文本分段与韵律控制
- PPT / PDF → 页面脚本 → TTS → 数字讲师 → 成片

## Phase 4 — 实时数字专家

- ASR → LLM/Agent → TTS → 实时头像
- WebRTC / 低延迟流
- RAG / 企业知识库
- 工具调用与业务 Agent
- 能源 / 电力市场数字专家场景

## 设计原则

1. 上游模型与业务编排解耦。
2. 同一任务接口支持多种生成引擎。
3. 默认本地处理人物照片、视频和声音。
4. 模型、素材、中间文件和生成结果默认不进入 Git。
5. 单机默认串行，避免统一内存争抢。
6. MuseTalk 负责效率，LongCat 负责高质量，不强求一个模型覆盖所有场景。
7. 先通过 M5 Pro 真机稳定性验收，再扩展声音、PPT 和实时能力。
