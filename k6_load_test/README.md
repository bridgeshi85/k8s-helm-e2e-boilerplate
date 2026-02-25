# k6 压测脚本使用说明

本目录用于 TaskFlow 的压测与可观测实战演练。

## 1) 前置准备

- 已部署 TaskFlow + observability（Prometheus/Grafana）
- 本地已安装 `k6`
- 本地已执行端口转发：

```bash
./scripts/port-forward-all.sh
```

默认会通过 Ingress 暴露应用：`http://localhost:8080`

## 2) 脚本说明

- `taskflow-loadtest.js`
  - 混合压测 `POST /api/tasks` 与 `GET /api/tasks`
  - 附带 `X-Request-ID` 便于日志链路检索
  - 内置基础阈值（错误率与延迟）

## 3) 运行方式

```bash
# 使用默认参数
k6 run scripts/k6/taskflow-loadtest.js

# 自定义并发与时长
BASE_URL=http://localhost:8080 VUS=40 DURATION=5m SLEEP_SECONDS=0.1 k6 run scripts/k6/taskflow-loadtest.js
```

## 4) 可观测联动建议

压测期间可重点观察：

- Prometheus 指标：
  - `http_requests_total` / `http_request_duration_seconds`（应用 HTTP 指标）
  - `rabbitmq_*`（消息堆积、连接数、投递速率）
  - `db_connection_pool_active`、`db_connection_pool_size`（后端连接池）
- Grafana：
  - 对比压测前后 P95/P99 延迟、错误率、吞吐
- 日志检索：
  - 通过 `X-Request-ID` 在日志系统中抽样追踪请求
