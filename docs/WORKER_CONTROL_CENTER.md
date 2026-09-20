# Worker 控制中心

## 目标

SaaS 版把本地、局域网和公网 Worker 统一视为受管算力节点。控制中心负责节点注册、运行状态、资源观测、维护 Drain、凭据吊销和任务追踪；Worker 继续通过现有 heartbeat / claim / lease 协议执行任务。

## 控制面与 Worker 的职责边界

控制面配置以下字段，并在 Worker 重启后保持不变：

- Worker 名称
- 分组（group_name）
- 并发槽位（slots_total）
- 备注
- accepting_tasks / Drain 状态
- 凭据状态

Worker 注册只刷新运行时事实：

- host / platform / machine
- capabilities
- code_version / model_version / render_contract_version
- versions

Worker 心跳刷新：

- last_seen_at
- current runtime status
- CPU 使用率
- 内存使用率
- 可用内存
- 可用磁盘
- 最近错误

## 新增 Worker

平台超级管理员进入「算力中心」点击「新增 Worker」，填写名称、分组和并发槽位。系统生成一次性 Enrollment Code。

目标 Mac 使用现有 Agent 完成 Enrollment。长期 Worker Token 仍由 macOS Keychain 保存，不在运营后台重复展示。

推荐分组：

- production：正式生产
- mac-cluster：Apple Silicon Worker
- cuda-cluster：未来 CUDA Worker
- test：测试节点

## 状态语义

- pending：等待 Enrollment
- online：在线空闲
- busy：有槽位正在执行任务
- draining：停止接新任务，等待当前任务完成
- disk_low：磁盘可用空间低于系统阈值
- incompatible：Render Contract / 代码 / 模型版本不兼容
- offline：心跳超时
- revoked：凭据已吊销

维护节点时优先使用 Drain，不要直接吊销正在工作的 Worker。

## 健康监控

Worker 每次 heartbeat 都上报当前资源快照。服务端约每 30 秒保留一个采样点，并清理 24 小时以前的采样。

详情页展示近 2 小时：

- CPU 趋势
- 内存趋势
- 平均 / 峰值 CPU
- 平均内存
- 忙碌采样占比

当前告警规则：

- CPU >= 90%：CPU 高负载
- 内存 >= 90%：内存高负载
- 磁盘低于 distributed_min_disk_free_gb：disk_low
- Render Contract / 版本不匹配：incompatible

CPU / 内存高负载目前只做告警，不自动 Drain；磁盘不足仍沿用现有自动 eligibility gate。

## 任务统计

Worker 详情展示最近 100 次 RenderAttempt，并可按成功、失败、运行中筛选。

同时计算：

- 24 小时任务尝试数
- 24 小时成功率
- 24 小时平均成功耗时
- 7 天成功率

辅助任务（语音试听、抠像等）继续显示当前有效 Lease。

## 本地 Worker 兼容

旧 Redis / 本地队列 Worker 仍通过原 worker status 机制运行，并在算力中心的「本地队列 Worker（兼容模式）」区域只读展示。

受管 Worker 与兼容模式 Worker 可以并存。新增节点建议统一走 Enrollment，以获得分组、详情、资源趋势和控制能力。

## 关于调度权重

当前分布式架构是 Worker 主动 claim。单独增加一个 weight 字段不会可靠地改变哪个 Worker 抢到任务，因此控制中心暂不暴露“调度权重”假配置。

如后续需要真正的权重 / GPU 优先 / 分组定向调度，应升级为以下任一方式：

1. 控制面发放 claim 配额或令牌。
2. 任务写入 required_capabilities / target_group，由 claim 查询严格匹配。
3. 控制面直接选择 Worker 并分配任务。

CUDA Worker 接入时建议优先采用第 2 + 第 3 种能力模型。

## 数据库升级

本功能新增迁移：

- 0013_worker_management_metrics

部署已有数据库时执行：

```bash
alembic upgrade head
```

新增字段：

- worker_nodes.group_name
- worker_nodes.notes
- worker_nodes.cpu_percent
- worker_nodes.memory_percent

新增表：

- worker_heartbeat_samples

## API

平台超级管理员接口：

- GET /api/saas/admin/workers/overview
- GET /api/saas/admin/workers/{node_id}
- PATCH /api/saas/admin/workers/{node_id}

沿用原 Worker 控制接口：

- POST /api/saas/distributed/workers/enrollments
- PATCH /api/saas/distributed/workers/{node_id}/accepting
- POST /api/saas/distributed/workers/{node_id}/revoke

Worker 内部接口沿用：

- POST /api/saas/internal/render/enroll
- POST /api/saas/internal/render/register
- POST /api/saas/internal/render/heartbeat
- POST /api/saas/internal/render/tasks/claim

## 后续建议

下一阶段再做：

- Worker 事件时间线 / 日志采集
- required_capabilities / target_group 的任务定向
- CUDA / MLX 混合算力路由
- 更长周期监控数据下沉到 Prometheus / VictoriaMetrics
- 节点升级提示与版本发布管理
