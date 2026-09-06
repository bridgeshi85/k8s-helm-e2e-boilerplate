# Prometheus 监控查询：诊断 RabbitMQ 连接池问题

## 快速诊断查询集合

### 1. 连接生命周期指标组

**查询集合**：用于判断是否存在连接泄漏或频繁重建

```promql
# 查询 A: 当前活跃连接数
rabbitmq_connections

# 查询 B: 累计打开连接数（history indicator）
rabbitmq_connections_opened_total

# 查询 C: 累计关闭连接数
rabbitmq_connections_closed_total

# 查询 D: 新建连接速率（最关键！）
rate(rabbitmq_connections_opened_total[5m])

# 查询 E: 关闭连接速率
rate(rabbitmq_connections_closed_total[5m])
```

**诊断标准**：
- ✅ 正常：`connections` = 1-2，`rate(opened_total)` ≈ 0
- ⚠️ 连接池问题：`connections` = 1，`connections_opened_total` = 100+，`rate(opened_total)` > 0.1
- ⚠️ 连接泄漏：`connections` = 20+，无法稳定

---

### 2. 通道泄漏检测

```promql
# 打开的通道总数
rabbitmq_channels

# 打开速率
rate(rabbitmq_channels_opened_total[5m])

# 关闭速率
rate(rabbitmq_channels_closed_total[5m])
```

**诊断标准**：
- ✅ 正常：`channels` = 1-2
- ⚠️ 泄漏：`channels` > 10

---

### 3. Backend 性能指标（HTTP 延迟）

```promql
# Backend POST /tasks 延迟 P95
histogram_quantile(0.95, rate(http_server_duration_seconds_bucket{service="taskflow-backend", route="POST /tasks"}[1m]))

# Backend POST /tasks 延迟 P99
histogram_quantile(0.99, rate(http_server_duration_seconds_bucket{service="taskflow-backend", route="POST /tasks"}[1m]))

# Backend 平均延迟
rate(http_server_duration_seconds_sum{service="taskflow-backend", route="POST /tasks"}[1m]) / rate(http_server_duration_seconds_count{service="taskflow-backend", route="POST /tasks"}[1m])
```

**诊断标准**：
- ✅ 有连接池：P95 < 0.5 秒
- ⚠️ 无连接池：P95 > 5 秒

---

### 4. RabbitMQ 消息发布性能

```promql
# 消息发布速率（每秒）
rate(rabbitmq_channel_messages_published_total[1m])

# 通过队列的消息数
rabbitmq_queue_messages_published_total{queue="task_queue"}

# 队列中的待处理消息
rabbitmq_queue_messages_ready{queue="task_queue"}

# 队列中的待确认消息
rabbitmq_queue_messages_unacked{queue="task_queue"}
```

---

## 完整诊断 Dashboard JSON

```json
{
  "dashboard": {
    "title": "RabbitMQ 连接池问题诊断",
    "panels": [
      {
        "title": "当前连接数 vs 累计打开连接数",
        "targets": [
          {
            "expr": "rabbitmq_connections",
            "legendFormat": "当前活跃连接"
          },
          {
            "expr": "rabbitmq_connections_opened_total",
            "legendFormat": "累计打开连接"
          }
        ]
      },
      {
        "title": "连接创建速率 (conn/s)",
        "targets": [
          {
            "expr": "rate(rabbitmq_connections_opened_total[5m])",
            "legendFormat": "新建速率"
          }
        ]
      },
      {
        "title": "Backend POST /tasks 延迟 (ms)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_server_duration_seconds_bucket{service=\"taskflow-backend\", route=\"POST /tasks\"}[1m])) * 1000",
            "legendFormat": "P95 延迟"
          },
          {
            "expr": "histogram_quantile(0.99, rate(http_server_duration_seconds_bucket{service=\"taskflow-backend\", route=\"POST /tasks\"}[1m])) * 1000",
            "legendFormat": "P99 延迟"
          }
        ]
      },
      {
        "title": "RabbitMQ 通道数",
        "targets": [
          {
            "expr": "rabbitmq_channels",
            "legendFormat": "活跃通道"
          }
        ]
      }
    ]
  }
}
```

---

## 一行诊断命令

如果你只有 5 秒时间，运行这一条：

```promql
# 在 Prometheus 中查这个，看是否 > 100 且还在增长
rabbitmq_connections_opened_total
```

- 结果 ≈ 1-2：✅ 正常
- 结果 > 100 且还在增长：⚠️ **这就是连接池问题！**

---

## 修复前后对比查询

### 修复前（无连接池）

```
time    connections  opened_total  closed_total  rate(opened)  HTTP_P95
13:37   1            394           393           0.02          10.2s
13:38   1            395           394           0.02          10.1s
13:39   1            396           395           0.02          10.0s
```

特征：
- ✅ connections = 1（看起来正常）
- ⚠️ opened_total 持续增长（每分钟增加 ~1）
- ⚠️ rate(opened) 持续 > 0（应该接近 0）
- ⚠️ HTTP_P95 ≈ 10 秒（很慢）

### 修复后（有连接池）

```
time    connections  opened_total  closed_total  rate(opened)  HTTP_P95
13:40   1            396           395           0.00          0.1s
13:41   1            396           395           0.00          0.1s
13:42   1            396           395           0.00          0.1s
```

特征：
- ✅ connections = 1
- ✅ opened_total 不再增长（稳定）
- ✅ rate(opened) ≈ 0（正常）
- ✅ HTTP_P95 ≈ 0.1 秒（快 100 倍！）

