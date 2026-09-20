# 讲稿驱动内容镜头（Script Media Cues）V1 产品与技术设计

> 状态：V1 设计基线  
> 目标：在“文稿确认”阶段，通过标记讲稿文字来插入视频、图片等内容镜头，并在最终成片中按讲稿实际语音时间自动切换画面。  
> 原则：用户编辑的是“讲稿与内容”，不是传统时间轴；最终时间轴由 TTS/语音对齐结果自动生成。

---

## 1. 需求背景

当前课程生成链路以逐页 PPT + 讲稿 + 数字人讲解为核心。实际企业培训、产品介绍、方案讲解中，经常存在以下场景：

- 讲到某个案例时，需要切入现场视频。
- 讲到某个设备时，需要展示实拍照片或结构图。
- 讲到某个过程时，需要播放动画、录屏或演示视频。
- 某一段讲稿需要临时替换 PPT 区域，而数字人继续讲解。
- 某一段需要完全切为全屏素材，讲完后再恢复 PPT + 数字人。
- 用户希望按照“这句话对应这个素材”的方式编辑，而不是手工计算第几秒切换。

因此 V1 引入“内容镜头（Media Cue）”。

---

## 2. 核心产品定义

### 2.1 什么是内容镜头

内容镜头是绑定到一段讲稿文字上的媒体指令。

例如：

```text
下面我们来看一个实际案例。

[内容镜头：储能站现场.mp4]
这是某新能源园区储能系统在晚高峰期间的实际运行画面。

从画面中可以看到，系统在十八点以后开始放电……
```

系统在生成语音后自动计算：

```text
“这是某新能源园区……”开始时间：08.42 s
“……实际运行画面。”结束时间：15.67 s
```

最终转化为画面事件：

```text
08.42s 进入内容镜头
15.67s 退出内容镜头
```

用户不直接编辑 08.42s / 15.67s。

### 2.2 产品定位

不是：

```text
简化版剪映 / Premiere 时间轴
```

而是：

```text
讲稿驱动的自动分镜系统
```

核心交互单位始终是：

```text
文字 → 内容镜头 → 自动时间轴
```

---

## 3. V1 支持范围

### 3.1 媒体类型

V1 正式支持：

1. 视频
2. 图片

数据结构预留：

- GIF / 动画
- 屏幕录制
- PDF 截图
- 网页截图
- AI 生成素材
- 图表

统一使用 `media_cue` 模型，不设计 `video_cue` 专用结构。

### 3.2 显示模式

V1 支持三种主模式。

#### A. 全屏替换 fullscreen

```text
PPT + 数字人
      ↓
全屏视频 / 图片
      ↓
PPT + 数字人
```

适用：

- 现场案例
- 实拍视频
- 产品宣传片段
- 大图展示

默认行为：

- PPT 暂时隐藏
- 数字人暂时隐藏
- 讲解音频继续
- 素材原声默认关闭

#### B. PPT 区域替换 content_area

```text
┌──────────────────────┬────────┐
│                      │        │
│   视频 / 图片素材     │ 数字人 │
│                      │        │
└──────────────────────┴────────┘
```

适用：

- 现场画面配数字人讲解
- 产品演示
- 操作过程
- 案例视频

这是 V1 推荐默认模式。

原则：

- 保留当前页数字人布局。
- 使用“当前页 PPT 框”的几何区域替换 PPT。
- 内容镜头结束后恢复原 PPT。
- 用户无需重新摆放数字人。

#### C. 画中画 overlay

```text
┌───────────────────────────────┐
│ PPT                           │
│        ┌──────────────┐       │
│        │ 视频 / 图片   │       │
│        └──────────────┘       │
│                      数字人    │
└───────────────────────────────┘
```

V1 提供预设位置：

- 左上
- 右上
- 左下
- 右下
- 居中

并支持大小：

- 小
- 中
- 大

V1 不提供任意关键帧动画。

---

## 4. 文稿确认页交互

### 4.1 基本操作

用户在某页讲稿中选中文字：

```text
这是某新能源园区储能系统在晚高峰期间的实际运行画面。
```

出现浮动工具条：

```text
┌────────────────────────────────────┐
│ + 内容镜头  |  发音校正  | 试听    │
└────────────────────────────────────┘
```

点击“+ 内容镜头”。

弹出编辑抽屉。

### 4.2 内容镜头编辑抽屉

```text
内容镜头
────────────────────────────────

绑定讲稿
“这是某新能源园区储能系统在晚高峰期间的实际运行画面。”

素材
[ 上传视频 / 图片 ]
或
[ 从素材中心选择 ]

文件：储能站现场.mp4

显示方式
● 替换 PPT 区域
○ 全屏展示
○ 画中画

播放方式
● 跟随讲稿区间
○ 完整播放
○ 指定素材片段

素材片段
00:12.0 ───────────── 00:26.0

视频原声
● 静音
○ 保留 20%
○ 保留 50%
○ 使用原声替代讲解

进入
● 直接
○ 淡入

退出
● 直接
○ 淡出

[取消]                 [保存]
```

### 4.3 文稿中的可视化标记

保存后，讲稿中不是简单高亮，而显示为明确的“镜头块”：

```text
下面我们来看一个实际案例。

┌ 🎬 内容镜头 01 · 储能站现场.mp4
│ 这是某新能源园区储能系统在晚高峰期间的实际运行画面。
│ [替换PPT区] [静音] [编辑] [删除]
└

从画面中可以看到，系统在十八点以后开始放电……
```

图片则显示：

```text
┌ 🖼 内容镜头 02 · 储能系统结构图.png
│ 电池簇、PCS 与 EMS 共同构成储能系统核心控制链路。
│ [画中画·右上] [编辑] [删除]
└
```

### 4.4 页面级镜头清单

每页右侧或底部增加：

```text
本页内容镜头 2

01  🎬 储能站现场.mp4
    替换 PPT 区域

02  🖼 储能系统结构图.png
    右上画中画
```

点击可定位到对应文字。

---

## 5. 讲稿锚点设计

### 5.1 V1 不保存纯时间

禁止以以下结构作为源数据：

```json
{
  "start_seconds": 8.42,
  "end_seconds": 15.67
}
```

原因：

讲稿修改后时间会变化。

### 5.2 锚点必须绑定文字语义

建议 V1 同时保存：

- `start_offset`
- `end_offset`
- `selected_text`
- 前后文摘要
- 稳定 cue id

示例：

```json
{
  "id": "cue_a1b2c3",
  "slide_index": 3,
  "anchor": {
    "start_offset": 24,
    "end_offset": 54,
    "selected_text": "这是某新能源园区储能系统在晚高峰期间的实际运行画面。",
    "prefix": "下面我们来看一个实际案例。",
    "suffix": "从画面中可以看到"
  }
}
```

### 5.3 讲稿修改后的锚点恢复

文稿保存时执行：

1. 如果原 offset 对应文字仍一致：直接保留。
2. offset 变化但 `selected_text` 唯一存在：自动重新定位。
3. selected_text 有多个匹配：结合 prefix / suffix。
4. 无法匹配：标记为 `needs_review`。
5. 不允许悄悄把 cue 放到错误文字上。

UI：

```text
⚠ 内容镜头 02 的绑定文字已发生变化，请重新确认
```

---

## 6. 数据模型

V1 为了保持历史课程零迁移、Local Worker / Remote Worker 同构，以及提交任务时可以直接冻结整页配置，内容镜头随对应页面存放在 `course.script_json[].media_cues` 中。

示例：

```json
{
  "index": 3,
  "narration": "这是某新能源园区储能系统的实际运行画面。",
  "media_cues": [
    {
      "id": "cue_a1b2c3",
      "asset_id": "asset_xxx",
      "media_type": "video",
      "display_mode": "content_area",
      "status": "valid",
      "anchor": {
        "start_offset": 0,
        "end_offset": 22,
        "selected_text": "这是某新能源园区储能系统的实际运行画面。",
        "prefix": "",
        "suffix": ""
      },
      "source_start_ms": 12000,
      "source_end_ms": 26000,
      "audio_mode": "mute",
      "audio_gain": 0.2,
      "enter_transition": "cut",
      "exit_transition": "cut",
      "overlay_position": "right_top"
    }
  ]
}
```

### 6.1 V1 嵌入式存储的原因

- 不需要新增数据库迁移，已有课程结构保持兼容。
- Cue 和逐页讲稿、布局天然属于同一页配置，草稿保存逻辑简单。
- Render Snapshot 可以一次性冻结讲稿、Cue 配置和 Cue 素材 SHA-256。
- Local Worker 与 Remote Worker 都读取同一个 `PageRenderPlan.override`，不会形成两套实现。
- 没有 `media_cues` 的历史课程完全沿用旧渲染路径。

### 6.2 独立 MediaCue 表作为后续规范化方向

当后续需要独立审计、跨课程复用、模板统计、素材生命周期联动或更复杂的多人协作时，再把 Cue 规范化成独立 `media_cues` 表。届时可包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | Cue ID |
| tenant_id | FK | 工作区 |
| course_id | FK | 课程 |
| slide_index | int | 页码 |
| asset_id | FK | 视频/图片素材 |
| media_type | string | video / image |
| display_mode | string | fullscreen / content_area / overlay |
| start_offset | int | 锚点开始字符 |
| end_offset | int | 锚点结束字符 |
| selected_text | text | 锚定文字 |
| anchor_prefix | text | 前文 |
| anchor_suffix | text | 后文 |
| source_start_ms | int? | 素材裁剪起点 |
| source_end_ms | int? | 素材裁剪终点 |
| audio_mode | string | mute / duck / original |
| audio_gain | float | 原声比例 |
| enter_transition | string | cut / fade |
| exit_transition | string | cut / fade |
| overlay_position | string? | 画中画位置 |
| status | string | valid / needs_review |

### 6.3 素材仍使用现有 Asset

不创建新的媒体存储体系。

上传视频：

```text
Asset.kind = "video"
```

图片：

```text
Asset.kind = "image"
```

Cue 只引用当前租户可访问的 Asset。生成前 API 会重新验证素材存在、状态和实际类型。

---

## 7. API 设计

建议：

### 查询某页镜头

```http
GET /api/saas/courses/{course_id}/media-cues?slide_index=3
```

### 创建

```http
POST /api/saas/courses/{course_id}/media-cues
```

### 修改

```http
PATCH /api/saas/courses/{course_id}/media-cues/{cue_id}
```

### 删除

```http
DELETE /api/saas/courses/{course_id}/media-cues/{cue_id}
```

### 锚点校验

文稿更新后：

```http
POST /api/saas/courses/{course_id}/media-cues/reconcile
```

可由服务端在保存 script 时自动执行，无需 UI 显式调用。

---

## 8. 从文字锚点生成时间轴

这是整个功能最关键的技术环节。

### 8.1 V1 目标

生成每页音频时得到：

```text
讲稿字符 / 词 / 句子
        ↓
对应音频时间
```

最终形成：

```json
{
  "cue_id": "cue_a1b2c3",
  "start_ms": 8420,
  "end_ms": 15670
}
```

这个数据是生成时产物，不是用户编辑源数据。

### 8.2 对齐优先级

推荐三层策略：

#### 第一层：TTS 原生时间戳

如果 CosyVoice 后续能够稳定输出 token/word timestamp，优先直接使用。

#### 第二层：句子级时长映射

V1 可以先把讲稿预切成句子，并逐句 TTS 或记录分段时长。

例如：

```text
句1 0.00 - 3.20
句2 3.20 - 8.42
句3 8.42 - 15.67
句4 15.67 - 20.10
```

Cue 绑定完整句子时可直接得到准确区间。

#### 第三层：比例估算兜底

仅在无法获得更细时间戳时使用：

```text
字符累计权重 / 全文权重 × 音频时长
```

中文按字符权重，英文按词权重，标点降低权重。

此模式应在内部 metadata 标记：

```text
alignment_quality = estimated
```

### 8.3 V1 产品约束

为了保证可靠性，V1 UI 鼓励用户：

> 尽量选择完整一句或连续几句作为内容镜头绑定范围。

如果用户只选“储能”两个字，可以提示：

```text
建议选择完整句子，镜头切换会更自然。
```

不强制阻止。

---

## 9. 页面渲染模型

每页先生成基础课程画面：

```text
base_page.mp4
= PPT + 数字人 + 字幕 + 背景
```

再根据 Media Cue 生成镜头覆盖。

### 9.1 fullscreen

时间区间：

```text
[t0, t1]
```

效果：

```text
base_page → media → base_page
```

讲解音频始终以课程音轨为主。

### 9.2 content_area

使用当前页面布局中 PPT 区域：

```text
ppt_rect = x / y / width / height
```

在 cue 区间内：

```text
media
  ↓ scale/crop
PPT rectangle
```

数字人层保持不变。

这是实现上最应该与当前 layout 数据结合的模式。

### 9.3 overlay

根据预设：

```text
position = top_right
scale = 0.30
```

计算实际像素框。

---

## 10. 视频素材的时长策略

### 10.1 跟随讲稿区间

例如 Cue 语音区间 7 秒，素材指定片段 15 秒。

默认：

```text
只播放前 7 秒
```

如果素材只有 4 秒：

默认 V1：

```text
最后一帧停留至 Cue 结束
```

不要自动循环现场视频，避免视觉重复。

### 10.2 完整播放

用户可选择“完整播放”。

此时存在一个产品语义：

如果素材比锚点讲稿更长，是否延长页面？

V1 建议：

- 不支持自动延长讲稿。
- “完整播放”仅在素材时长 <= 绑定讲稿区间时可用。
- 超出时提示：

```text
当前视频片段 18 秒，绑定讲稿约 9 秒。
请选择更短片段，或扩大讲稿绑定范围。
```

这样避免复杂的音画停顿逻辑。

---

## 11. 视频声音策略

V1 三种：

### mute

默认。

```text
课程讲解：100%
素材原声：0%
```

### duck

```text
课程讲解：100%
素材原声：20% / 50%
```

用于环境声。

### original

素材原声替代讲解。

V1 可以先在数据模型中保留，但 UI 暂时标为“高级”。

原因：

这意味着锚点期间课程 TTS 仍生成但最终混音需要静音，数字人口型画面也可能被隐藏。

---

## 12. 字幕行为

### fullscreen

默认：

- 保留课程字幕。
- 字幕叠加到内容镜头上。

可提供开关：

```text
☑ 内容镜头期间显示讲解字幕
```

### content_area / overlay

字幕继续使用当前课程字幕布局。

---

## 13. 文稿确认与画面排版的职责边界

### 文稿确认

负责：

- 哪句话触发素材
- 什么素材
- 素材片段
- 基本显示方式
- 声音策略

### 画面排版

负责：

- 实际预览内容镜头
- overlay 的位置/大小
- content_area 是否严格使用 PPT 区
- 全屏安全区
- 字幕遮挡检查

不在画面排版页重新编辑时间点。

---

## 13.1 画面排版中的内容镜头图层（V1 已实现）

“画面排版”阶段现在包含三类可视图层：

```text
PPT
数字人
内容镜头
```

如果当前页存在内容镜头，进入排版页时默认选中本页第一个内容镜头，并在右侧显示本页镜头清单。多个镜头逐个独立排版。

显示模式与排版规则：

- **替换 PPT 区**：内容镜头区域自动跟随当前 PPT 区，不单独拖动。
- **全屏展示**：内容镜头固定覆盖整个 16:9 画面。
- **自由画中画**：内容镜头成为可拖动、可缩放的第三图层，位置写入 `overlay_box={x,y,w,h}`。
- 画中画的 `overlay_box` 同时被浏览器快速预览和最终 FFmpeg 合成读取，保证预览与成片位置一致。
- 旧课程没有 `overlay_box` 时，仍按原有左上 / 右上 / 左下 / 右下 / 居中预设位置兼容渲染。

每个内容镜头拥有自己的独立排版，不随“应用当前排版到全部页面”复制到其他页面。

---

## 14. 内容镜头快速预览（V1 已实现）

V1 已在“文稿确认”和“画面排版”两个阶段提供浏览器侧快速预览，不需要调用 MuseTalk，也不占用 Worker。

预览链路：

```text
当前页 PPT
+ 当前数字人静态/循环预览
+ 内容镜头视频 / 图片
+ 浏览器时间轴
→ 正常页面 → 内容镜头 → 正常页面
```

交互包括：

- 播放 / 暂停。
- 从头播放。
- 拖动时间进度条。
- 点击任一镜头时间片直接跳到切入点。
- 实时显示当前处于“PPT + 数字人”还是具体内容镜头。
- 模拟全屏、替换 PPT 区、画中画三种显示方式。
- 模拟素材起止片段、淡入淡出、静音 / 环境声 / 素材原声。

如果当前页已经生成过“TTS 试听本页”，预览会重新获取该试听音频并使用其**真实音频时长**驱动 Cue 时间轴；如果没有 TTS 试听，则使用讲稿语音权重估算页面时长，并在 UI 中明确提示“估算时间”。

快速预览不生成数字人口型，因此它用于检查：

- 镜头切入与退出是否自然。
- 素材是否选对。
- 显示区域与布局是否合理。
- 素材片段和声音策略是否合适。

最终成片仍由 Local / Remote Worker 使用真实 TTS、MuseTalk 和 FFmpeg 完成。

---

## 15. Render Snapshot

提交生成任务时必须将 Media Cue 固化到不可变快照中。

Snapshot 增加：

```json
{
  "media_cues": [
    {
      "id": "cue_a1b2c3",
      "slide_index": 3,
      "asset_id": "asset_xxx",
      "asset_sha256": "...",
      "anchor": {
        "start_offset": 24,
        "end_offset": 54,
        "selected_text": "..."
      },
      "display_mode": "content_area"
    }
  ]
}
```

这样用户在任务执行过程中修改课程，不影响已提交任务。

同时应将：

- cue asset
- cue source clip range
- display mode
- anchor
- asset SHA-256

都纳入 snapshot hash。

---

## 16. Worker 兼容设计

功能必须同时兼容：

### Local Worker

```text
start_mlx_worker_mac.sh
```

本地整课 renderer：

```text
prepare_course
→ TTS
→ MuseTalk
→ page compose + media cues
→ final concat
```

### Remote Worker

推荐分工：

#### Remote Page Worker

负责单页：

```text
TTS
MuseTalk
基础页面 segment
Media Cue 合成
```

Center 在 Task Manifest 中提供该页所需 cue asset。

例如：

```json
{
  "slide_index": 3,
  "media_cues": [
    {
      "id": "...",
      "asset": {
        "download_url": "...",
        "proxy_url": "..."
      }
    }
  ]
}
```

Remote Worker 只下载本页实际需要的内容镜头素材。

#### Center

仍负责：

- prepare
- snapshot
- page task dispatch
- final concat
- publish

### 重要原则

不要让 Center 在所有页面渲染完成后再统一做 Media Cue。

原因：

- 会造成大视频二次传输。
- Center 不应该成为视频算力瓶颈。
- 单页 Worker 已有 FFmpeg 能力。
- 内容镜头属于页面级画面逻辑。

因此：

> Media Cue 应作为 page render contract 的一部分。

---

## 17. FFmpeg 处理建议

统一先将 cue 视频转换为目标页面 contract：

```text
H.264
yuv420p
与页面相同 fps
与页面相同 timebase
AAC / 或去音轨
```

### content_area

典型链路：

```text
cue video
→ trim
→ scale
→ crop / pad
→ overlay(enable='between(t,start,end)')
```

### fullscreen

```text
base
cue
→ trim
→ scale/crop 1920x1080
→ overlay enable
```

### image

图片用：

```text
-loop 1
```

生成 cue 区间静态视频层。

### transition

V1：

- cut
- fade 0.25s

不要第一版实现复杂转场。

---

## 18. 多 Cue 冲突规则

同页允许多个 cue，但 V1 不允许时间区间重叠。

如果两个锚点对应文字交叉：

```text
Cue A 10s - 16s
Cue B 14s - 20s
```

保存时直接提示：

```text
两个内容镜头绑定范围存在重叠，请调整讲稿范围。
```

未来版本再支持图层堆叠。

---

## 19. 课程复制

复制课程时：

- MediaCue 一并复制。
- asset_id 默认仍引用同租户素材。
- 新 cue 生成新 id。
- 锚点保持。
- Render Snapshot 不复制。

如果未来跨租户课程模板：

- 必须复制素材或转为系统模板素材。

---

## 20. 权限与素材安全

创建 Cue 时：

- asset 必须属于当前 tenant，或已通过平台默认素材机制导入当前 tenant。
- 不允许引用其他租户私有 asset。
- Remote Worker 获得的只是任务期下载权限。
- Signed URL 短时有效。
- Worker 不获取对象存储永久凭据。

---

## 21. V1 数据迁移与兼容

V1 **不新增 Alembic migration**。

内容镜头直接作为可选的 `media_cues` 字段嵌入逐页 `script_json`。因此：

- 已有数据库无需迁移。
- 历史课程无需回填。
- 没有 `media_cues` 的页面不进入任何新增 FFmpeg 处理。
- 提交生成任务时，Render Snapshot 会冻结 Cue 配置及其素材哈希。
- Remote Worker 通过 `script-media-cues` capability 协商领取相关页面，旧 Worker 不会静默忽略镜头。

后续如果把 Cue 规范化为独立表，再单独增加迁移与数据回填工具。

---

## 22. 前端 V1 页面改动

### 文稿确认页

新增：

- 文本选区工具条
- “内容镜头”按钮
- Media Cue 编辑抽屉
- 文稿内镜头块
- 本页镜头列表
- 锚点失效警告

### 画面排版页

新增：

- Cue 列表
- Cue 画面预览
- overlay 位置/尺寸选择
- 只读自动时间区间

### 素材中心

已有 Asset 模型可复用。

增加可选过滤：

```text
课程内容素材
├ 视频
└ 图片
```

无需新增独立素材模块。

---

## 23. V1 验收用例

### 用例 1：视频替换 PPT 区

第 2 页选择完整一句话，上传 10 秒视频。

期望：

- Cue 可见。
- TTS 后得到时间区间。
- 该区间 PPT 区显示视频。
- 数字人一直存在。
- 讲解音频不断。
- 镜头结束恢复 PPT。

### 用例 2：全屏视频

期望：

- Cue 区间 PPT 和数字人都隐藏。
- 视频全屏。
- 字幕保留。
- 结束恢复原布局。

### 用例 3：图片画中画

期望：

- 图片只在指定句子期间显示。
- 数字人、PPT 不受影响。

### 用例 4：修改讲稿

Cue 创建后，在前面增加一句话。

期望：

- Cue 自动跟随原 selected_text。
- 不因字符 offset 变化失效。

### 用例 5：删除锚定句

期望：

- Cue 标记 needs_review。
- 禁止直接生成，或生成前明确要求用户处理。

### 用例 6：Remote Worker

期望：

- 只给领取该页的 Worker 下发所需 cue assets。
- Worker 能完成页面媒体合成。
- 其他 Worker 无需下载该素材。

### 用例 7：历史课程

期望：

- 无 Cue 的旧课程产物与当前 main 一致。

---

## 24. V1 不做

为了避免第一版膨胀，明确不做：

- 多轨时间轴
- 任意关键帧
- 视频速度曲线
- 复杂蒙版
- 多层 Cue 重叠
- 绿幕二次抠像
- 自动 B-roll 搜索
- AI 自动生成视频
- 自动根据全文推荐镜头
- 用户手工输入绝对秒数
- 跨页连续镜头

这些可作为 V2/V3。

---

## 25. V2 演进方向

V2 可以加入：

### AI 镜头建议

系统根据讲稿自动标出：

```text
“这里适合加入案例视频”
“这里适合加入产品图片”
“这里适合加入结构示意图”
```

用户确认后再生成 Cue。

### AI 素材生成

```text
选中文字
→ AI 生成内容镜头
→ 自动加入课程
```

### 自动 B-roll

企业素材库接入后：

```text
讲稿语义
→ 检索企业视频素材
→ 推荐片段
```

---

## 26. 最终产品价值

这项能力让课程生成从：

```text
PPT + 数字人 + 配音
```

升级为：

```text
讲稿
  ↓
自动语音
  ↓
数字人
  ↓
讲稿驱动内容镜头
  ↓
自动分镜
  ↓
完整课程视频
```

用户仍然只需要理解：

> “这句话，我想让观众看到什么？”

而系统负责：

- 什么时候出现
- 出现多久
- 怎么切换
- 怎么和数字人/PPT组合
- 怎么在 Local / Remote Worker 上完成最终合成

这是 V1 最核心的产品原则。
