# Internet Remote Worker

本仓库的 page-level distributed render Worker 可以运行在与 SaaS Center 不同的网络中。公网模式继续复用现有 WorkerNode、RenderSubtask、RenderAttempt、Lease、Heartbeat 与 ContentCache；Center 不需要反向连接 Mac，所有连接均由 Worker 主动发起。

## 架构

```text
Browser
   |
   v
SaaS / Worker API
https://worker-api.example.com
   |
   +-- PostgreSQL
   +-- Redis
   +-- Distributed Center
   |
   +---------------- control plane -------------------+
                                                      |
                                           Remote Mac Worker
                                                      |
                                  signed GET / HTTPS  |
                                                      v
                                             S3 / OSS / COS
```

控制面负责注册、心跳、claim、lease、progress、complete 与上传回执。大体积不可变输入在启用 direct download 后由 Worker 使用短时 signed URL 直接从对象存储下载。Worker 不持有 PostgreSQL、Redis、S3、OSS 或 COS 凭据。

Internet V2 可将 page_audio / page_video 通过短时 Signed PUT URL 直接上传到对象存储。Center 只签发目标 object key，并在提交时执行 HEAD/size 校验；最终 finalize 仍会重新 materialize 并校验 SHA-256。若对象存储不支持 Signed PUT、URL 不安全/不可达或直传失败，Worker 自动回退到原有 Center 8MB 分片上传。

## 1. 暴露 HTTPS Center

公网只暴露 443。不要把 PostgreSQL、Redis 或 FastAPI 8918 直接暴露到互联网。

示例 Nginx 反向代理：

```nginx
server {
    listen 443 ssl http2;
    server_name worker-api.example.com;

    # TLS certificate configuration is deployment-specific.
    ssl_certificate     /etc/letsencrypt/live/worker-api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/worker-api.example.com/privkey.pem;

    client_max_body_size 520m;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:8918;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_request_buffering off;
    }
}
```

生产 Center 至少设置：

```env
SAAS_ENV=production
SAAS_DISTRIBUTED_RENDER_ENABLED=true
SAAS_TRUSTED_HOSTS=worker-api.example.com
SAAS_RENDER_CONTRACT_VERSION=v1
SAAS_DISTRIBUTED_EXPECTED_CODE_VERSION=0.5.0
SAAS_DISTRIBUTED_EXPECTED_MODEL_VERSION=musetalk-mlx
```

## 2. 配置私有对象存储

生产环境使用 `s3`、`oss` 或 `cos`。例如 OSS：

```env
STORAGE_BACKEND=oss
STORAGE_BUCKET=your-private-bucket
STORAGE_ENDPOINT=https://oss-cn-xxx.aliyuncs.com
OSS_ACCESS_KEY_ID=...
OSS_ACCESS_KEY_SECRET=...
STORAGE_SIGNED_URL_SECONDS=3600
SAAS_DISTRIBUTED_DIRECT_DOWNLOADS=true
SAAS_DISTRIBUTED_DIRECT_UPLOADS=true
```

开启 `SAAS_DISTRIBUTED_DIRECT_DOWNLOADS=true` 后，claim manifest 会优先返回：

```json
{
  "transfer_mode": "direct",
  "url": "https://object-store/...signed...",
  "fallback_url": "/api/saas/internal/render/tasks/.../assets/...",
  "url_expires_in": 3600
}
```

如果对象存储不能生成 signed URL，或开关关闭，manifest 自动保持 `proxy` 模式。

对于自建 MinIO，生成 signed URL 时使用的 endpoint 必须能够被远程 Mac 访问。若 MinIO 只存在于 Center 内网，请保持 direct download 关闭，继续使用 Center proxy。

## 3. V3：一次性 Enrollment + macOS Keychain

推荐的新 Worker 接入方式不再把长期 `wrk_...` Token 交给安装人员。

Center 管理员执行：

```bash
python -m app.saas.manage create-worker-enrollment \
  --name remote-mac-01 \
  --slots 1
```

输出一个短时、单次使用的：

```text
REMOTE_WORKER_ENROLLMENT_CODE=enr_...
```

默认 30 分钟过期，可用 `SAAS_DISTRIBUTED_ENROLLMENT_MINUTES` 调整。数据库只保存注册码哈希。

在目标 Mac 上执行：

```bash
python -m app.saas.remote_worker_agent enroll \
  --center https://worker-api.example.com/api/saas/internal/render \
  --name remote-mac-01 \
  --install
```

不传 `--code` 时会以隐藏输入方式提示粘贴 Enrollment Code，避免注册码进入 shell history。

Enrollment 成功后：

- Center 生成真正的长期 Worker credential。
- Mac 将 credential 写入 macOS Keychain，service 为 `com.mac-digital-human.remote-worker`。
- 本地 `~/Library/Application Support/MacDigitalHumanWorker/config.json` 只保存 Center API、Worker ID、名称，权限为 `0600`。
- Enrollment Code 立即失效，重复提交会被拒绝。
- `--install` 会安装并启动用户级 LaunchAgent；重复安装是幂等的。
- 启动脚本优先使用显式环境变量，未设置 `REMOTE_WORKER_TOKEN` 时自动从 Keychain 读取。

查看本机接入状态：

```bash
python -m app.saas.remote_worker_agent status
```

它只显示 Center、Worker ID、名称和 Keychain 是否就绪，不打印 credential。

旧的手工模式仍保留：

```bash
python -m app.saas.manage create-worker --name remote-mac-01 --slots 1
```

但生产公网 Worker 建议使用 Enrollment + Keychain。

## 4. 配置远程 Mac

```bash
cp .env.remote-worker.example .env.remote-worker
```

关键配置：

```env
REMOTE_WORKER_API_BASE=https://worker-api.example.com/api/saas/internal/render
REMOTE_WORKER_TOKEN=wrk_...
REMOTE_WORKER_NAME=remote-mac-01

REMOTE_WORKER_CODE_VERSION=0.5.0
REMOTE_WORKER_MODEL_VERSION=musetalk-mlx
REMOTE_WORKER_RENDER_CONTRACT_VERSION=v1
```

公网域名和公网 IP 默认必须使用 HTTPS。私有 IP、localhost 与 `.local` 地址仍允许 HTTP，方便局域网开发。不要在公网使用 `REMOTE_WORKER_ALLOW_INSECURE_HTTP=1`。

启动：

```bash
bash scripts/saas/start_remote_page_worker_mac.sh
```

## 5. 数据传输安全边界

Worker 内部使用两个独立 HTTP client：

- `control_client`：只访问 Center，携带 `Authorization: Bearer wrk_...` 和 lease headers。
- `transfer_client`：只访问对象存储 signed URL，不携带 Worker Token 或 Lease Token。

signed URL 直连失败时 Worker 会自动回退到 `fallback_url`，使用原有 Center 鉴权下载。下载完成后无论来自 direct 还是 proxy，都会继续验证声明的文件大小与 SHA-256，然后才进入 ContentCache。

## 6. 验收

至少完成以下检查：

1. 远程 Mac 不在 Center 局域网内，仍能 register / heartbeat / claim。
2. Worker 页面显示该节点 online。
3. 开启 direct downloads 后，任务 manifest 为 `transfer_mode=direct`。
4. 对象存储访问日志能看到 Mac 直接 GET，大文件不再经过 FastAPI。
5. 临时使 signed URL 失败，Worker 能自动走 Center fallback。
6. 同一数字人第二次任务命中 ContentCache，不重复下载母版视频。
7. Worker Token 不出现在对象存储请求头或对象存储日志中。
8. 开启 direct uploads 后，对象存储访问日志能看到 Worker 直接 PUT page_audio/page_video。
9. 临时让 Signed PUT 返回失败，Worker 能自动回退 Center resumable upload。
10. Center direct-commit 只接受当前 attempt 对应的 deterministic object key，且会校验对象大小。
11. finalize 会重新计算下载后文件的 SHA-256；错误哈希不能进入最终成片。

## Internet V2 上传协议

Worker 在上传每个 page artifact 前先调用：

```text
POST /tasks/{task_id}/artifacts/{kind}/direct-upload
```

Center 返回 `mode=direct` 时包含短时 `upload_url` 与由 Center 生成的 `object_key`。Worker 使用无凭据的 transfer client 直接 PUT，成功后调用：

```text
POST /tasks/{task_id}/artifacts/{kind}/direct-commit
```

Center 校验 active lease、attempt ownership、object key 和对象大小后创建 `RenderArtifact`。Worker 不拥有对象存储永久凭据，也不能选择任意 object key。

## 下一阶段

当单页输出明显超过普通 PUT 的可靠传输范围时，再增加真正的 multipart upload session、分片 ETag 列表和服务端 abort/cleanup。当前数字人单页 MP4/WAV 保留 Signed PUT + Center chunk fallback，协议更简单且已有完整失败回退。