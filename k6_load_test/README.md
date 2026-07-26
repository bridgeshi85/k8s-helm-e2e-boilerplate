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
# 使用默认参数（BASE_URL 默认已含 /api，不要再手动拼一次）
k6 run k6_load_test/taskflow-loadtest.js

# 自定义并发与时长
BASE_URL=http://localhost:8080/api VUS=40 DURATION=5m SLEEP_SECONDS=0.1 k6 run k6_load_test/taskflow-loadtest.js
```

## 4) 推送指标到 Prometheus（供 Grafana `k6 Load Test` dashboard 使用）

`observability` chart 已开启 Prometheus 的 `enableRemoteWriteReceiver`，跑压测时加上 `-o experimental-prometheus-rw` 即可把 k6 自身的运行时指标（`k6_vus`、`k6_http_reqs_total`、`k6_http_req_duration_p50/p90/p95` 等）实时推进 Prometheus，Grafana dashboard 才会有数据：

```bash
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95)" \
BASE_URL=http://localhost:8080/api VUS=20 DURATION=5m \
k6 run -o experimental-prometheus-rw k6_load_test/taskflow-loadtest.js
```

`K6_PROMETHEUS_RW_TREND_STATS` 必须显式带上 `p(50),p(90),p(95)`——不设置的话 k6 只会上报 `p99`，dashboard 的 Duration 面板会没数据。

## 5) 可观测联动建议

压测期间可重点观察：

- Prometheus 指标：
  - `http_requests_total` / `http_request_duration_seconds`（应用 HTTP 指标）
  - `rabbitmq_*`（消息堆积、连接数、投递速率）
  - `db_connection_pool_active`、`db_connection_pool_size`（后端连接池）
- Grafana：
  - `k6 Load Test` dashboard：VUs、吞吐、P50/P90/P95 延迟、错误率、checks 通过率
  - 对比压测前后 P95/P99 延迟、错误率、吞吐
- 日志检索：
  - 通过 `X-Request-ID` 在日志系统中抽样追踪请求
