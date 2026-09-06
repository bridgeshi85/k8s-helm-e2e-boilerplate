# 排坑指南：Grafana Tempo 在压测期间反复重启（OOMKilled / 探针超时被杀）

分支：`feat/opentelemetry-tracing`
最后更新：2026-09-04

## 背景

`charts/observability` 里的 Tempo（`deploymentMode: SingleBinary` / `storage: filesystem`，见
[CLAUDE.md](../CLAUDE.md) 的"分布式追踪"一节）用来接收 backend/worker 通过 OTel Collector 转发来的
trace。日常查看几条 trace 时完全没问题，但**只要配合 k6 压测、同时在 Grafana 里开着面板盯着某个
批次的 trace**，Tempo 就会在几分钟到十几分钟内反复重启，`kubectl get pod` 显示 `CrashLoopBackOff`
或重启计数不断增加。

这篇记录的是两次表现不同、但**根因同源**的崩溃，以及每次的排查方法——排查手法比结论本身更值得复用。

## 现象一：`OOMKilled`

```
kubectl describe pod -n observability observability-tempo-0
```

```
Warning  Unhealthy  ...  Liveness probe failed: HTTP probe failed with statuscode: 503
Warning  BackOff    ...  Back-off restarting failed container tempo in pod observability-tempo-0
```

`describe` 里的 503 只是表象。真正的死因要看 `lastState`：

```bash
kubectl get pod -n observability observability-tempo-0 \
  -o jsonpath='{.status.containerStatuses[0].lastState}' | python3 -m json.tool
```

```json
{
    "terminated": {
        "exitCode": 137,
        "reason": "OOMKilled",
        "startedAt": "...",
        "finishedAt": "..."
    }
}
```

`exitCode 137`（= 128 + SIGKILL）+ `reason: OOMKilled` 是 cgroup 内存被打爆的铁证，跟 503 探针失败
没有直接关系——只是容器已经被内核 OOM-killer 杀死，接下来几秒的探针检查自然连不上。

### 定位触发源

看崩溃前的日志（**用 `--previous`，不是当前这次启动的日志**）：

```bash
kubectl logs -n observability observability-tempo-0 --previous --tail=200
```

日志里有几千条几毫秒间隔的：

```
msg="search tag values request" tenant=single-tenant handler=SearchTagValuesV2 tag=name
msg="search tag values request" tenant=single-tenant handler=SearchTagValuesV2 tag=status
msg="search tag values request" tenant=single-tenant handler=SearchTagValuesV2 tag=resource.service.name
```

`name` / `status` / `resource.service.name` 这三个 tag 循环出现，是 Grafana Explore 的 TraceQL
查询构建器每次渲染都要去拉这几个下拉框候选值——如果面板开着很短的 auto-refresh，就会变成对 Tempo
`SearchTagValuesV2` 接口的高频轰炸，扫描 block 数据吃内存吃得很快。

### 根因

`charts/observability/values.yaml` 里 Tempo 的内存 limit 只给了 512Mi（照抄 Loki 那份"sandbox
环境"的保守值），在这种高频 tag 搜索下完全不够用。

## 现象二：探针超时被强杀（不是 OOM）

加大内存之后过了几天，Tempo 又重启了，但这次 `lastState.reason` 是 `"Error"`，不是
`"OOMKilled"`，节点也没有 `MemoryPressure`。日志（`--previous`）显示的是另一种模式：

```
msg="search request" query="{ .test.load_test_id = \"k6-...\" }" ...
```

同一条 TraceQL（按 k6 的 `load_test_id` 过滤）在 8 分钟内被**反复请求**，间隔 10~15 秒；每次
`inspected_bytes` 都比上一次大（因为压测还在跑、trace 数据还在往里灌，range 查询要扫的数据越滚越
多），单次查询耗时从 ~100ms 涨到 ~260ms。查询变慢到一定程度，`/ready` 健康检查（默认
`timeoutSeconds: 5` / `failureThreshold: 3`，约 30 秒容忍窗口）连续超时，kubelet 直接把容器杀了：

```
Warning  Unhealthy  Liveness probe failed: Get ".../ready": context deadline exceeded
Normal   Killing    Container tempo failed liveness probe, will be restarted
```

### 根因

跟第一次同源：**压测期间开着短间隔 auto-refresh 的 Grafana 面板，反复戳 Tempo 的查询接口**。
区别只是这次打中的是"探针超时"这个更敏感的开关，而不是内存上限。

## 解决方案

`charts/observability/values.yaml`：

```yaml
tempo:
  tempo:
    resources:
      limits:
        cpu: 1000m
        memory: 1.5Gi
      requests:
        cpu: 300m
        memory: 512Mi

    # 默认 timeoutSeconds:5 / failureThreshold:3（约 30s 容忍窗口）在压测期间
    # 反复查同一个 TraceQL 导致查询变慢时太容易被打满，kubelet 会直接强杀重启。
    # 放宽到 10s / 6 次失败（约 60s），给查询变慢留缓冲。
    livenessProbe:
      httpGet:
        path: /ready
        port: 3200
      initialDelaySeconds: 30
      periodSeconds: 10
      timeoutSeconds: 10
      failureThreshold: 6
      successThreshold: 1
    readinessProbe:
      httpGet:
        path: /ready
        port: 3200
      initialDelaySeconds: 20
      periodSeconds: 10
      timeoutSeconds: 10
      failureThreshold: 6
      successThreshold: 1
```

（`resources` 起初只加到 `1Gi` / `256Mi`，第二次探针超时暴露出来后进一步调到 `1.5Gi` / `512Mi`，
并补了 CPU limit/request，避免压测峰值时被 cgroup 节流成额外的延迟抖动。）

应用前记得：

```bash
helm lint ./charts/observability
helm template observability ./charts/observability -n observability \
  -s charts/tempo/templates/statefulset.yaml | grep -A10 "port: 3200"   # 确认 probe 真的渲染出来了
helm upgrade observability ./charts/observability -n observability --reuse-values
```

## 经验总结（可复用的排坑方法论）

1. **`describe pod` 看到的探针失败/503 往往只是果，不是因**——先查
   `.status.containerStatuses[0].lastState`，`exitCode` + `reason` 才是第一手线索。
   `137 + OOMKilled` 是内存问题；`137 + Error` 更可能是 kubelet 主动杀（探针失败、优雅终止超时等）。
2. **一定要看 `--previous` 日志**，当前这次启动的日志是新进程刚起来的干净现场，看不到死因；
   `--previous` 拿到的才是上一条命的临终遗言。
3. **重复出现的相同请求模式，几乎总能顺藤摸瓜找到触发源**——本例里 `SearchTagValuesV2`
   三件套、或反复出现的同一条 TraceQL，都是 Grafana 面板 auto-refresh 的指纹。
4. **资源限制和探针阈值要一起看**：加内存治标于 OOM，但如果瓶颈其实是"查询变慢触发探针超时"，
   只加内存不放宽探针，Tempo 还是会被强杀——两次崩溃分别踩中了这两个不同的开关。
5. **sandbox/demo 环境的资源值不能直接照抄别的组件**（这里最初是照抄 Loki 的 512Mi），
   不同组件的查询模式（尤其是"频繁被面板轮询"这种用法）对资源的实际需求差异很大。

## 相关

- Trace 排查方法本身：Grafana → **Explore** → 选 Tempo 数据源，而不是在 Dashboards 列表里找
  （这个仓库没有配置专门的 "Traces" Dashboard 面板，见 [CLAUDE.md](../CLAUDE.md)）
- [progress-loadtest-trace-correlation.md](./progress-loadtest-trace-correlation.md) —— 压测批次号
  →Dashboard→Trace 关联 POC 的整体设计记录
