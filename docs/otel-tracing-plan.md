# OpenTelemetry 分布式链路追踪接入计划

分支：`feat/opentelemetry-tracing`

## 目标

给 FastAPI backend + worker 接入 OpenTelemetry SDK，把 trace 通过 OTLP 推给 Grafana Tempo，最终在 Grafana 里能看到一条完整的端到端链路：

```
Frontend → Ingress → Gateway(nginx) → Backend(POST /api/tasks)
    → RabbitMQ(TaskCreated) → Worker(process_message) → PostgreSQL(update status)
```

## 现状（决定了实现方式的几个约束）

- 已有一套自建的请求关联机制：`X-Request-ID` header → `context.py` 里的 `ContextVar` → 写进日志（backend/worker 的 `logging_config.py`），RabbitMQ 消息通过 `headers={"x-request-id": ...}` 传递（见 [`src/backend/main.py`](../src/backend/main.py) `publish_task_created`，[`src/worker/main.py`](../src/worker/main.py) `process_message`）。这套东西不会替换掉，Tempo trace_id 是新增的第二条关联链，两者并存（原因见下方"开放问题"）。
- Gateway 是纯 nginx 反向代理（[`src/gateway/nginx.conf`](../src/gateway/nginx.conf)），没有也不打算做 embedded tracing——它只是 `proxy_pass`，默认会透传未显式设置的 header，root span 从 backend 的 FastAPI 中间件开始即可，不需要在 nginx 层生成 trace。
- RabbitMQ 传递是 `aio_pika` 手写 publish/consume，**没有**现成的 OTel auto-instrumentation 包能覆盖，trace context 的注入/提取必须手写（用 `opentelemetry.propagate.inject/extract` 操作 message headers）。
- `charts/observability` 目前用 `kube-prometheus-stack` + `loki` + `promtail` 三个独立 helm 依赖（[`Chart.yaml`](../charts/observability/Chart.yaml)），Grafana 的 datasource 目前**只有** kube-prometheus-stack 自动注入的 Prometheus——连 Loki 都没有配成 datasource（大概率是之前遗漏的）。Tempo 会照抄 Loki 现在的部署模式（`grafana/tempo` chart，`deploymentMode: SingleBinary`、`storage: filesystem`、关掉 minio），datasource 会用 `kube-prometheus-stack.grafana.additionalDataSources` 一次性把 Tempo（顺手把 Loki 也补上）接进去。

## 任务拆解

### 1. `charts/observability` — 部署 Tempo，暴露 OTLP receiver

- [ ] `Chart.yaml` 新增依赖：`tempo`（`grafana/tempo`，参考 loki 用的仓库 `https://grafana.github.io/helm-charts`），加 `condition: tempo.enabled`
- [ ] `values.yaml` 新增 `tempo:` 配置块，仿照现有 `loki:` 的资源限制/`filesystem` storage 风格，开启 OTLP gRPC(4317)/HTTP(4318) receiver
- [ ] `values.yaml` 的 `kube-prometheus-stack.grafana.additionalDataSources` 里加 Tempo datasource（`type: tempo`, `url: http://observability-tempo:3100`），并顺手补上 Loki datasource（现状缺失，不补的话 Tempo 的 "Trace to logs" 联动也用不了）
- [ ] `helm dependency build` 后 `helm lint` + `helm template` 验证

### 2. `src/backend` — FastAPI 自动 + 手动埋点

- [ ] `requirements.txt` 新增：`opentelemetry-sdk`、`opentelemetry-exporter-otlp-proto-grpc`、`opentelemetry-instrumentation-fastapi`、`opentelemetry-instrumentation-sqlalchemy`、`opentelemetry-instrumentation-logging`（把 trace_id/span_id 塞进现有日志 record，方便和 Loki 日志做关联）
- [ ] `main.py`：初始化 `TracerProvider` + `OTLPSpanExporter`（endpoint 走环境变量），`FastAPIInstrumentor.instrument_app(app)`，`SQLAlchemyInstrumentor().instrument(engine=engine)`
- [ ] `publish_task_created`：用 `opentelemetry.propagate.inject(headers)` 把当前 span context 写进 RabbitMQ message headers（新增一个 header，不动现有的 `x-request-id`），并显式包一个 `with tracer.start_as_current_span("rabbitmq.publish")` 子 span

### 3. `src/worker` — OTel SDK（无 FastAPI，全手动）

- [ ] `requirements.txt` 同步新增 SDK + OTLP exporter + `opentelemetry-instrumentation-sqlalchemy` + `opentelemetry-instrumentation-logging`
- [ ] `main.py`：初始化 TracerProvider（同 backend 配置模式），`process_message` 里用 `opentelemetry.propagate.extract(message.headers)` 拿到 backend 传过来的 context，再 `with tracer.start_as_current_span("worker.process_task", context=ctx)` 续上链路，把 `update_task_status` 的两次调用各包一个子 span

### 4. `charts/taskflow` — 环境变量注入

- [ ] `values.yaml` 的 `backend.env` / `worker.env` 新增：`OTEL_SERVICE_NAME`（`taskflow-backend` / `taskflow-worker`）、`OTEL_EXPORTER_OTLP_ENDPOINT`（`http://observability-tempo.observability.svc.cluster.local:4317`）、`OTEL_TRACES_EXPORTER=otlp`
- [ ] 确认 `backend-deployment.yaml` / `worker-deployment.yaml` 的 `{{- range $key, $val := .Values.xxx.env }}` 循环已经能吃到新变量，不用改模板本身

### 5. 验证

- [ ] `helm upgrade` 两个 chart，确认 backend/worker pod 正常起来（重点看有没有因为 exporter 初始化失败导致启动报错——OTLP exporter 对下游不可达应该是异步重试，不阻塞启动，但要实测确认）
- [ ] 跑一次 `POST /api/tasks`（或直接用 k6 打一轮），去 Grafana Explore 选 Tempo datasource，按 `service.name=taskflow-backend` 搜 trace
- [ ] 确认一条 trace 里能看到 4 段 span 且父子关系正确：`HTTP POST /tasks`（backend）→ `rabbitmq.publish`（backend）→ `worker.process_task`（worker）→ DB 相关 span（SQLAlchemy 自动埋点）
- [ ] 确认 trace 总耗时和后端日志/RabbitMQ 消息时间线对得上（worker 里有 5s 模拟处理延迟，span 时长应该能看出这个 5s）

## 开放问题（需要在动手前或过程中定夺，先给了推荐值）

1. **X-Request-ID 和 trace_id 要不要合并？** 推荐：**终态统一，但分两个 PR 做**，不在本次范围内一次性合并。
   - 现状：`request_id_middleware`（[`main.py:61-67`](../src/backend/main.py#L61-L67)）是 `request.headers.get("X-Request-ID")` 原样接受任意字符串；k6 发的是 `k6-perf-<random10>`（[`taskflow-loadtest.js:79`](../k6_load_test/taskflow-loadtest.js#L79)），是自由格式的调试标签，**不是**合法的 W3C trace id。OTel 的 `trace_id` 是固定 128-bit 值，只能由 SDK 自动生成或从合法 `traceparent` header 解析，不能直接塞一个任意字符串进去——所以"合并"没法是一次简单的改名，必然牵动 k6 脚本的取值方式。
   - 本 PR（阶段一）：`opentelemetry-instrumentation-logging` 已经会把 `trace_id`/`span_id` 注入日志 record（见任务 2/3），**顺手把它加进日志输出格式**，这样 Loki 日志从第一天起就带 `trace_id`，Grafana 的 "logs ↔ traces" 联动马上能用，`X-Request-ID` 体系保持不动、不破坏现有压测脚本和日志检索习惯。
   - 后续 PR（阶段二，范围外）：砍掉 `context.py`/两边 `logging_config.py` 里的自建 `request_id` 机制，日志关联改成完全依赖 `trace_id`；同步改 `k6_load_test/taskflow-loadtest.js` 和 README 里"用 X-Request-ID 检索日志"的说明。如果还想保留"发个好记字符串来调试"的体验，用 OTel `baggage` 机制携带，而不是复用 `trace_id` 本身。
2. **Tempo 存储用什么？** 推荐跟 Loki 一样用 `filesystem`（本地磁盘，关掉 minio/对象存储），因为这是单集群 sandbox 环境，没有必要引入额外的对象存储依赖。
3. **要不要上 OTel Collector（sidecar/gateway 模式）？** 推荐**不上**，先让 backend/worker SDK 直连 Tempo 的 OTLP endpoint。链路短、组件少，符合这个仓库"轻量试验田"的定位；以后要接多语言服务/加采样策略/加 batch 处理能力时再引入 collector。
4. **采样策略？** 默认 `AlwaysOn`（全量采集）。当前是压测/演示场景，数据量可控；生产化时需要换成 `TraceIdRatioBased` 或 tail-based sampling，先记录在这里，不在本次范围内处理。

## 明确不做的事（范围外）

- Frontend（React）不接 OTel（前端 tracing 是另一个课题，SDK/浏览器埋点方式完全不同）
- Gateway（nginx）不接 tracing
- 不引入 OTel Collector
- 不改造现有 `X-Request-ID`/Loki 日志关联体系
