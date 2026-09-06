# Grafana 中通过 TraceID 查询 Tempo + Loki 的完整指南

## 前置条件
- Port-forward Grafana: `./scripts/port-forward-all.sh`
- 访问 http://localhost:3000（默认用户: admin/strongpassword）
- 已配置 Prometheus、Tempo、Loki 三个数据源

---

## 方法一：Tempo 面板查找 TraceID

### 步骤 1: 进入 Tempo Explore
1. 左侧菜单 → **Explore**
2. 顶部数据源下拉框选择 **Tempo**
3. 查询模式选择 **Search** (默认)

### 步骤 2: 输入 TraceID 搜索
**在搜索框输入完整 TraceID：**
```
b88b1708ff9380323b5c70fa9697994a
```
点击 **Run query**

**结果页面显示：**
- Service Graph（服务依赖图）
- Trace timeline（时间轴）
- Spans list（所有 span 列表）

### 步骤 3: 查看详细 Span 信息
点击任何 span 展开，可看到：
- `Duration`（耗时）
- `Attributes`（span 属性）
  - `trace_id` = b88b1708ff9380323b5c70fa9697994a
  - `service.name` = taskflow-backend / taskflow-worker
  - `span.name` = POST /tasks / worker.process_task 等
  - **`test.load_test_id`** = k6-1788700428042-qowmqc（压测批次号）
  - **`chaos.slow_query.injected`** = true/false（注入状态）

---

## 方法二：TraceQL 高级查询（按条件过滤）

### 场景 1: 查找所有慢查询被注入的 trace
在 Tempo Explore，切换到 **TraceQL** 模式，输入：
```traceql
{ span.chaos.slow_query.injected = true }
```
点击 **Run query**，会列出所有注入了慢查询的 trace

### 场景 2: 查找特定压测批次的所有 trace
```traceql
{ span.test.load_test_id = "k6-1788700428042-qowmqc" }
```

### 场景 3: 查找耗时超过 5 秒的 trace
```traceql
{ duration > 5s }
```

### 场景 4: 综合查询 —— 特定压测批次 + 慢查询注入
```traceql
{ span.test.load_test_id = "k6-1788700428042-qowmqc" && span.chaos.slow_query.injected = true && duration > 3s }
```

---

## 方法三：从 Trace 跳转到 Loki 日志

### 前提：Trace 必须配置 tracesToLogsV2

检查 Tempo 数据源配置是否已启用 tracesToLogsV2（通常 CLAUDE.md 部署时已配）

### 步骤：点击 Trace 中的 Loki 链接
1. 打开某个 trace（如上面查到的 b88b1708...）
2. 找到任何 span，点击 span 卡片
3. 在 span 详情面板右下角，应能看到 **"Logs"** 链接
4. 点击会自动跳转到 Loki，按 `trace_id` 过滤该 trace 对应的所有日志

**Loki 跳转后的日志过滤语句自动变为：**
```loki
{namespace="taskflow",pod="taskflow-backend-xxx"} | grep "54d236be" or similar
```

或用更精确的 JSON 字段匹配：
```loki
{namespace="taskflow"} | json | trace_id="b88b1708ff9380323b5c70fa9697994a"
```

---

## 方法四：Loki 中主动搜索 TraceID

### 步骤 1: 进入 Loki Explore
1. 左侧菜单 → **Explore**
2. 顶部数据源下拉框选择 **Loki**

### 步骤 2: 输入日志查询语句

**最简单的方式 —— 按 namespace + 容器，然后 grep traceID：**
```loki
{namespace="taskflow",container="backend"} |= "b88b1708ff9380323b5c70fa9697994a"
```

**更灵活的方式 —— 用正则提取 traceID 字段然后过滤：**
```loki
{namespace="taskflow"} | json | trace_id="b88b1708ff9380323b5c70fa9697994a"
```

**查找特定压测批次的所有日志（如果日志中含 load_test_id）：**
```loki
{namespace="taskflow"} | json | load_test_id="k6-1788700428042-qowmqc"
```

**查找错误日志 + 对应 trace：**
```loki
{namespace="taskflow",container=~"backend|worker"} |= "error" or |= "traceback" | json | trace_id !=""
```

### 步骤 3: 查看日志结果

每条日志行会显示：
- 时间戳
- 日志级别（INFO/WARN/ERROR）
- 消息内容
- 关键字段（如果 JSON 格式化了）

点击某条日志左侧的 **"{ }"** 按钮可展开该行的 JSON 字段详情。

---

## 方法五：一张 Dashboard 上同时看 Trace + 日志 + 指标

这是最推荐的做法（loadtest-correlation dashboard 的目标）：

### 构建跨数据源 Panel

**Panel 1: TraceID 输入框（变量）**
- 类型：Text box query
- 变量名：`trace_id`
- 输入框中粘贴 TraceID

**Panel 2: Tempo Traces 表格**
```traceql
{ traceID = "$trace_id" }
```
显示该 trace 的所有 span 详情

**Panel 3: Loki 日志表格**
```loki
{namespace="taskflow"} | json | trace_id="$trace_id"
```
显示该 trace 对应的所有日志行

**Panel 4: Prometheus 指标时间线**
```promql
rate(http_server_duration_count{job=~".*backend.*"}[$__rate_interval])
```
显示该时间段 backend 的请求速率（通过 trace 的时间戳范围匹配）

**Panel 5: 服务依赖图 (Service Graph)**
- Tempo Service Map（自动从 trace 数据提取）

---

## 实战演练：排查 TraceID b88b1708ff9380323b5c70fa9697994a

### 问题：为什么 `rabbitmq.publish` 耗时 9.14 秒？

### 排查步骤：

**Step 1: Tempo 中查看 Span 瀑布图**
```
1. Explore → Tempo → Search
2. 输入：b88b1708ff9380323b5c70fa9697994a
3. 找到 span "rabbitmq.publish"
4. 看属性：task.id=9186, duration=9140ms
5. 确认：这个发布操作确实花了 9 秒多
```

**Step 2: 检查是否有错误**
```
1. 在同一个 trace 中搜索有无 error 或 exception span
2. 查看 span 的 status（应该是 OK 而不是 ERROR）
```

**Step 3: Loki 中查看同时间的日志**
```loki
{namespace="taskflow",container="backend"} 
| json 
| trace_id="b88b1708ff9380323b5c70fa9697994a"
```
看是否有：
- "Connecting to RabbitMQ"
- "Connection timeout"
- "Channel opened"
- "Message published" 等关键日志

**Step 4: 检查 RabbitMQ 连接数**
```promql
rabbitmq_connections{job=~".*rabbitmq.*"}
```
在 Prometheus 中画图，看该时间点是否连接数飙升

**Step 5: 对比其他 trace**
运行多个 trace，看 `rabbitmq.publish` 的耗时是否都在 9s 左右（说明是系统问题），还是某次特别长（说是是某个请求卡住了）

---

## 常见问题排查

### Q: 为什么 Trace 没有对应的日志？
**原因：**
- 日志中没有 `trace_id` 字段
- OTel instrumentation 没有把 trace context 传给日志库
- Loki 日志来源于不同的 pod，时间戳对不上

**解决：**
查看 `src/backend/logging_config.py`、`src/worker/logging_config.py` 是否配置了 OTel logging instrumentation

### Q: Tempo 查询很慢或返回 "No data"
**原因：**
- Tempo 未配置持久化存储
- TraceID 太旧（已过期）
- Collector 未成功收集 trace

**解决：**
```
1. 检查 Collector 状态：kubectl get pods -n observability | grep collector
2. 查看 Collector 日志：kubectl logs -n observability obs-observability-otel-collector-0
3. 确认 Backend 和 Worker 是否成功连接到 Collector
```

### Q: 如何按压测批次号查所有 trace？
**Tempo TraceQL：**
```traceql
{ span.test.load_test_id = "k6-1788700428042-qowmqc" }
```

**Loki：**
```loki
{namespace="taskflow"} | json | load_test_id="k6-1788700428042-qowmqc"
```

---

## 快速参考：URL 直链

假设：
- TraceID: `b88b1708ff9380323b5c70fa9697994a`
- Grafana 地址: `http://localhost:3000`
- Tempo 数据源 UID: `xxxx`（可在数据源页面查看）

### 直接打开该 Trace 的 Tempo 详情页
```
http://localhost:3000/explore?orgId=1&left=%7B%22datasource%22:%22xxxx%22,%22queries%22:%5B%7B%22refId%22:%22A%22,%22queryType%22:%22traceqlSearch%22,%22query%22:%22b88b1708ff9380323b5c70fa9697994a%22%7D%5D%7D
```

或更简单的方式（手工操作）：
1. Explore → Tempo
2. Search 框输入 TraceID
3. 右上角复制 URL，这就是直链

---

## 总结表格

| 场景 | 工具 | 查询 | 用途 |
|---|---|---|---|
| 查看 Trace 全景 | Tempo Search | `traceID` | 了解请求从入口到完成的完整链路 |
| 按条件查多条 Trace | Tempo TraceQL | `{ duration > 5s }` | 批量找出性能问题 |
| 查看日志详情 | Loki | `\| json \| trace_id="xxx"` | 找出具体的错误/警告信息 |
| 验证连接/资源问题 | Prometheus | `rabbitmq_connections` / `db_pool_active` | 确认资源是否是瓶颈 |
| 一张图看全部 | Custom Dashboard | 多 panel 组合 | loadtest-correlation dashboard 的目标 |

