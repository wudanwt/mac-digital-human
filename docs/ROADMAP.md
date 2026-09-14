# Roadmap

## Phase 1 — 双引擎本地 MVP（完成代码，待真机验收）

- [x] MuseTalk：母版视频 + 新音频 → 快速口型同步 MP4
- [x] LongCat Avatar 1.5：参考照片 + 音频 + Prompt → 高质量动态数字人
- [x] Apple Silicon / MLX 优先
- [x] M5 Pro 48GB：MuseTalk Q8 + LongCat Q4 merged 默认配置
- [x] CLI / Web / FastAPI 统一入口
- [x] 单机串行任务队列与日志
- [x] GitHub CI：compile + unit tests
- [ ] M5 Pro 48GB 首机真实样例验收

## Phase 2 — 生产流程产品化（当前）

- [x] M5 Pro 真机 benchmark 记录器
- [x] LongCat Prompt 预设
- [x] 本地人物 Profile：照片 / 母版 / Prompt / TTS 参考统一复用
- [x] Web 人物模板 / Prompt 预设选择
- [x] MLX-Audio + Qwen3-TTS Apple Silicon TTS
- [x] Qwen3-TTS CustomVoice 中文预设音色
- [x] Qwen3-TTS Base 参考音频声音克隆接口
- [x] JSON Course Manifest
- [x] 课程脚本 → TTS → 数字人批量任务
- [x] hero / intro / section 自动优先 LongCat
- [x] body 自动使用 MuseTalk
- [x] LongCat 超长片段自动回退 MuseTalk（auto 模式）
- [x] FFmpeg 统一规格 + LongCat / MuseTalk 自动拼接
- [ ] 母版视频预处理缓存
- [ ] 自动字幕
- [ ] PPT 页面画面插入
- [ ] 片头片尾 / 转场 / 背景音乐 ducking
- [ ] LongCat continuation / 长视频分段策略

## Phase 3 — 数字讲师增强

- [ ] FasterLivePortrait-MLX 价值与兼容性评估
- [ ] 表情、眨眼、头部动作增强是否值得进入主链
- [ ] 中文长文本自动切句和韵律控制
- [ ] PPT / PDF → 页面脚本 → TTS → 数字讲师 → 成片
- [ ] 课程模板 / 批量项目管理

## Phase 4 — 实时数字专家

- [ ] ASR → LLM/Agent → TTS → 实时头像
- [ ] WebRTC / 低延迟流
- [ ] RAG / 企业知识库
- [ ] 工具调用与业务 Agent
- [ ] 能源 / 电力市场数字专家场景

## 当前优先顺序

1. 在 M5 Pro 48GB 上跑 LongCat Q4 的 61 帧和 93 帧 benchmark。
2. 建立真实人物 Profile，并验证照片、母版、声音参考能否稳定复用。
3. 用一个 4~6 段真实培训脚本跑通 Course Manifest。
4. 根据首轮成片决定是否优先做字幕 / PPT 合成，而不是继续增加模型。
5. FasterLivePortrait 与实时 Agent 保持评估状态，等主生产链稳定后再进入。

## 设计原则

1. 上游模型与业务编排解耦。
2. 同一任务接口支持多种生成引擎。
3. 默认本地处理人物照片、视频和声音。
4. 模型、素材、中间文件和生成结果默认不进入 Git。
5. 单机默认串行，避免统一内存争抢。
6. MuseTalk 负责效率，LongCat 负责高质量，不强求一个模型覆盖所有场景。
7. TTS 在视频模型前批量生成并主动释放，避免 48GB 统一内存同时驻留多个大模型。
8. 首先优化课程生产链，不为了“模型数量”增加维护复杂度。
