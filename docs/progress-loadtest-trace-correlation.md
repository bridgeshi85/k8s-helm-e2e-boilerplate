# 进展记录：可观测性 POC — 压测批次 → Dashboard → Trace 定位

分支：`feat/opentelemetry-tracing`
最后更新：2026-08-30

## POC 叙事（最终收敛版）

一句话：**k6 跑一批压测 → 创建任务时按概率随机注入慢查询 → 部分请求超时/失败 →
在 Grafana Dashboard 按「压测批次号」筛出这一批 → 看到任务成功率下降、处理时间变长 →
点开该批次的 Trace → 定位到 `chaos.slow_query` span 吃掉了大部分耗时。**

演示动线：
1. k6 发起一批压测，产生唯一批次号 `load_test_id`（k6 指标带该 label，trace 带该 span 属性）
2. 打开关联 Dashboard，用 `$load_test_id` 变量选中这一批
3. 面板看到：任务成功率（< 100%）、创建任务 P95/P99 延迟（明显抬高）
4. Dashboard 上的 Tempo 面板列出该批次的慢 trace，点开瀑布图
5. 看到 `POST /tasks` 下的 `chaos.slow_query` span 占了绝大部分时间 → 定位完成

## 已完成（未提交，工作区改动）

### 保留并有用
- `src/backend/tracing.py` / `src/worker/tracing.py`
  - `BaggageToAttributesSpanProcessor`：`on_start` 把 Baggage 里 `test.load_test_id` 提升为 span 属性
  - 两份，`_BAGGAGE_SPAN_ATTRIBUTE_KEYS = {"test.load_test_id"}` 需同步
- `src/backend/main.py`
  - `load_test_baggage_middleware`：`X-Load-Test-ID` header → OTel Baggage
  - `FastAPIInstrumentor.instrument_app(app)` 移到自定义 middleware 之后注册（否则 root span 的 fresh Context 冲掉 Baggage）—— 有详细注释
- `src/backend/models.py`
  - 连接池参数改读环境变量（`DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT`）
  - `maybe_inject_slow_query(db, override_seconds=None)`：`SELECT pg_sleep(:s)`
- `k6_load_test/taskflow-loadtest.js`
  - `setup()` 生成 `loadTestId`（可被 `LOAD_TEST_ID` env 覆盖），每个请求 header 带 `X-Load-Test-ID`
- `charts/taskflow/values.yaml`：backend env `SLOW_QUERY_ENABLED` / `SLOW_QUERY_SECONDS` + 连接池参数
- 镜像 tag backend `v1.1.7-otel` / worker `v1.1.9-otel`，`pullPolicy: IfNotPresent`

### 需要调整 / 回退
- `src/backend/main.py` 的 `GET /tasks?slow_seconds=` + `chaos.slow_query` span
  —— **注入点要从 GET 挪到 `POST /tasks`（create_task）**，GET 上的 chaos 逻辑去掉
- `src/worker/main.py` 的 `otel_context.attach` 改动可保留（对 POST 链路的跨服务 span 有益），
  但**不在 worker 加任何 chaos 注入**

## 待办

### 步骤 1 — 批次号外部生成，喂给 k6 指标 + header  ✅ 已完成
- 新增 `scripts/run-loadtest.sh`：
  - `LOAD_TEST_ID="${LOAD_TEST_ID:-k6-$(date +%s)-$RANDOM}"`，打印出来 + 对应的 Grafana/Tempo 过滤表达式
  - `export LOAD_TEST_ID`（k6 `setup()` 已支持读 `__ENV.LOAD_TEST_ID`）
  - `k6 run --out experimental-prometheus-rw --tag load_test_id=$LOAD_TEST_ID "$@" $SCRIPT`
  - 透传 BASE_URL / K6_PROMETHEUS_RW_* env，额外 CLI 参数透传给 k6
- k6 脚本：GET 那段当初只是讨论、从未真正加进文件，无需回退；只发 `POST /tasks`，header 带 `X-Load-Test-ID`（原样保留）
- `k6_load_test/README.md` 第 3 节改为推荐 wrapper 脚本

### 步骤 2 — 慢查询注入挪到 POST /tasks，加随机概率  ✅ 已完成（已部署）
- backend 已改：`create_task` 里 `with tracer.start_as_current_span("chaos.slow_query")` 包
  `maybe_inject_slow_query(db, span)`；`models.py` 的 helper 改为 `(db, span)` 签名，
  `SLOW_QUERY_ENABLED` + `random() < SLOW_QUERY_PROBABILITY` 双重门控，注入/未注入都打
  `chaos.slow_query.injected` 属性
- GET /tasks 的 chaos 已回退干净
- `values.yaml`：backend tag `v1.1.7 → v1.1.8-otel`，新增 `SLOW_QUERY_PROBABILITY: "0.2"`，
  `SLOW_QUERY_ENABLED` 保持 `"false"`（演示时开）
- 镜像已 build（wsl-remote，host IP `192.168.31.184`）+ `kind load` + 部署，
  当前集群 backend = `v1.1.8-otel`，REVISION 22
- **helm 坑**：该 release 的 user-supplied values 里有历史遗留的 `backend.image.tag: v1.1.7-otel`，
  `helm upgrade` 不带 `-f` 时会沿用它、覆盖 chart values.yaml。以后升级必须显式带
  `-f charts/taskflow/values.yaml`（或 `--set`）
- 待办：镜像 360MB（含本地 `.venv`）——加 `src/backend/.dockerignore`
- 待办：本地已验证注入生效（`SLOW_QUERY_PROBABILITY=1.0` 时 curl 耗时 ~3s、日志 `Injecting 3.0s slow query`）
- 待办：gateway nginx `proxy_read_timeout` 未确认（让"慢"稳定转成"失败"）

<details><summary>原步骤 2 细则（已落实）</summary>

- `src/backend/main.py` `create_task`：写库前后包一个 `chaos.slow_query` span，
  调 `maybe_inject_slow_query`
- `src/backend/models.py` `maybe_inject_slow_query`：加概率判断
  - 新 env `SLOW_QUERY_PROBABILITY`（0~1，默认 0）
  - 逻辑：`SLOW_QUERY_ENABLED == true` 且 `random() < SLOW_QUERY_PROBABILITY` 时 `pg_sleep(SLOW_QUERY_SECONDS)`
  - span 上打属性：`chaos.slow_query.injected`(bool)、`chaos.slow_query.seconds`
- `charts/taskflow/values.yaml`：backend env 加 `SLOW_QUERY_PROBABILITY: "0.2"`（演示时开 `SLOW_QUERY_ENABLED`）
- 删掉 `GET /tasks` 的 `slow_seconds` 参数和 chaos span
- 让「慢」真的能导致「失败」：确认 gateway(nginx) 的 `proxy_read_timeout` 或 k6 的超时 < `SLOW_QUERY_SECONDS`
  （现象：部分 POST 502/504 或 k6 check `is status 202` 失败）—— 需要查 `src/gateway` nginx 配置

</details>

### 步骤 3 — 关联 Dashboard
- 新增 `charts/observability/dashboards/loadtest-slow-query.json` + `dashboards.loadtestSlowQuery.enabled: true`
- 模板变量 `$load_test_id`：`label_values(k6_http_reqs_total, load_test_id)`
- 面板：
  1. **任务成功率**：`1 - (sum(rate(k6_http_req_failed{load_test_id="$load_test_id"}[1m])) / sum(rate(k6_http_reqs_total{load_test_id="$load_test_id"}[1m])))`
     —— 或 backend 侧 `rate(http_server_...{status=~"5.."})`
  2. **创建任务处理时间**：`k6_http_req_duration{load_test_id="$load_test_id"}` P50/P95/P99
  3. **VUs / RPS**：`k6_vus{...}`、`rate(k6_http_reqs_total{...}[1m])`
  4. **该批次的慢 Trace**（Tempo 数据源 TraceQL 面板）：
     `{ span.test.load_test_id = "$load_test_id" && span.chaos.slow_query.injected = true }`
     或 `{ span.test.load_test_id = "$load_test_id" && duration > 1s }`
- datasource 变量记得同时设 `pluginId` + `query`（见 CLAUDE.md 的坑）
- Tempo datasource 已在 `charts/observability/values.yaml` 配好，`tracesToLogsV2` 也有

### 步骤 4 — 校验 + 提交
- `helm lint ./charts/taskflow` + `helm lint ./charts/observability` + `helm template`
- 重新 build backend 镜像（bump tag）→ `kind load` → `helm upgrade --set backend.image.tag=...`
- 端到端跑一次 `scripts/run-loadtest.sh`，在 Dashboard 里验证动线
- Conventional Commits，建议拆分：
  - `feat: k6 压测批次号关联到 trace（baggage → span 属性）`
  - `feat: 创建任务时按概率注入慢查询用于可观测性演示`
  - `feat: 压测批次 → 成功率/延迟/trace 关联 dashboard`

## 遗留 / 注意
- CLAUDE.md 引用了不存在的 `docs/otel-tracing-plan.md` —— 补写或删引用
- backend CPU limit 仅 500m，压测峰值会被 cgroup throttle 造成额外抖动 —— 演示前考虑调大，避免混淆归因
- `_BAGGAGE_SPAN_ATTRIBUTE_KEYS` backend/worker 各一份
- 需确认 gateway nginx 超时配置，才能让"慢"稳定地转化成"失败"
