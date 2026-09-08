# 第一次在 M5 Pro 48GB 上运行

```bash
git clone https://github.com/wudanwt/mac-digital-human.git
cd mac-digital-human
bash scripts/setup.sh
```

确认全部模型和依赖：

```bash
.venv/bin/python scripts/check_runtime.py --variant q8
```

启动图形界面：

```bash
bash scripts/run_web.sh
```

浏览器访问：`http://127.0.0.1:8000`

上传一段 20~30 秒母版视频和 10~20 秒中文音频进行第一轮验收。

如果失败，查看：

```text
workspace/<job-id>/render.log
```

并参考 `docs/TROUBLESHOOTING.md`。
