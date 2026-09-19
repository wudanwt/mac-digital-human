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

当前版本仍将 page_audio / page_video 通过 Center 的 resumable upload API 回传。这样保留现有 attempt/lease/SHA-256 校验与断点续传，后续可再升级为 signed PUT / multipart upload。

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

## 3. 创建 Worker 凭据

在 Center 环境执行：

```bash
python -m app.saas.manage create-worker --name remote-mac-01 --slots 1
```

命令只打印一次明文 `REMOTE_WORKER_TOKEN`。Center 数据库只保存其 SHA-256 摘要。

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
8. 任务完成后 page_audio/page_video 仍可通过 Center resumable upload 正常回传并 finalize。

## 下一阶段

Internet V2 可将输出上传也拆到数据面：Center 签发 signed PUT / multipart session，Worker 直接上传 S3/OSS/COS，再向 Center 提交 object key、size、SHA-256，由 Center HEAD 校验后创建 RenderArtifact。