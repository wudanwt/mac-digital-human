# M5 Pro 48GB 真机 Benchmark

GitHub CI 只能验证语法、依赖和轻量单测，无法替代 Apple Silicon + Metal 的真实推理测试。

仓库提供 `scripts/benchmark.py`，用于统一记录：

- 机器 / 芯片信息
- 系统总内存
- 推理总耗时
- 输出视频时长
- realtime factor
- 进程树峰值 RSS
- 推理期间最低可用内存
- 引擎、variant、分辨率、帧数和 seed

## LongCat 首跑建议

先用小规格：

```bash
bash scripts/run_benchmark.sh \
  --engine longcat \
  --image samples/ref.png \
  --audio samples/voice.wav \
  --variant q4-merged \
  --width 768 \
  --height 432 \
  --num-frames 61 \
  --label m5-pro-48g-first-run
```

然后再测默认规格：

```bash
bash scripts/run_benchmark.sh \
  --engine longcat \
  --image samples/ref.png \
  --audio samples/voice.wav \
  --variant q4-merged \
  --width 832 \
  --height 480 \
  --num-frames 93 \
  --label m5-pro-48g-480p-93f
```

## MuseTalk 基准

```bash
bash scripts/run_benchmark.sh \
  --engine musetalk \
  --video samples/master.mp4 \
  --audio samples/voice.wav \
  --variant q8 \
  --label musetalk-q8
```

报告写入：

```text
benchmarks/local/<timestamp>-<engine>.json
```

生成的视频也放在该目录。`benchmarks/local/` 默认被 `.gitignore` 排除，因为 benchmark 素材和路径可能包含私人信息。

## 首机验收关注指标

LongCat 首次不要只看“能不能跑完”，还要记录：

1. 是否发生系统内存压力或 swap 明显增长。
2. Q4 61 帧与 93 帧的峰值 RSS 差异。
3. 输出视频人物身份稳定性。
4. 嘴型与中文音频同步程度。
5. 手部 / 肢体是否出现明显物理错误。
6. 相同 seed 重复运行是否稳定。
7. 连续第二次任务是否出现内存未释放。

真实数据跑出来后，再决定是否进一步测试 Q8，而不是先默认升级模型精度。
