# Code Review Report — k8s-helm-e2e-boilerplate

**Review Date**: 2026-06-01  
**Reviewer**: Claude Code (automated multi-angle review)  
**Branch**: main  
**Scope**: Full project codebase

---

## Summary

Multi-angle review covering correctness bugs, security/config issues, cleanup, and altitude. 7 finder angles × 6 candidates → verified → 10 confirmed/plausible findings.

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High     | 4 |
| Medium   | 2 |
| Low      | 2 |

---

## Findings

### 🔴 Critical

---

#### [Issue #9] Worker default DB password mismatches actual PostgreSQL password

**File**: `src/worker/models.py:20`  
**GitHub**: https://github.com/bridgeshi85/k8s-helm-e2e-boilerplate/issues/9

**Problem**

`src/worker/models.py` falls back to password `changeme` when `DATABASE_URL` is not set, but `charts/taskflow/values.yaml` configures PostgreSQL with password `taskflowDatabase`. In any environment where `DATABASE_URL` is not explicitly injected, the worker silently fails all DB writes — tasks remain stuck in `RUNNING` state forever. SQLAlchemy only validates credentials on the first query, so no startup error is raised.

```python
# src/worker/models.py:20 — wrong default
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://taskflow:changeme@localhost:5432/taskflow")

# src/backend/models.py — correct default
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://taskflow:taskflowDatabase@localhost:5432/taskflow")
```

**Fix**

1. Align the default password in `src/worker/models.py` with `src/backend/models.py`.
2. Enable `pool_pre_ping=True` on the SQLAlchemy engine so connection errors surface at startup, not silently at query time.

---

#### [Issue #10] RabbitMQ URL missing credentials — all task creation fails with ACCESS_REFUSED

**File**: `charts/taskflow/values.yaml:22`  
**GitHub**: https://github.com/bridgeshi85/k8s-helm-e2e-boilerplate/issues/10

**Problem**

`RABBITMQ_URL` is set to `amqp://taskflow-rabbitmq:5672/` with no `user:pass`, but the RabbitMQ subchart requires `guest:guest` credentials (lines 113–114). The broker returns `ACCESS_REFUSED` on every connection attempt → every `POST /tasks` request fails with HTTP 500.

```yaml
# values.yaml:22 — missing credentials
RABBITMQ_URL: "amqp://taskflow-rabbitmq:5672/"

# RabbitMQ subchart config
auth:
  username: "guest"
  password: "guest"
```

**Fix**

```yaml
RABBITMQ_URL: "amqp://guest:guest@taskflow-rabbitmq:5672/"
```

Better — drive from the subchart auth values to avoid drift:

```yaml
RABBITMQ_URL: "amqp://{{ .Values.rabbitmq.auth.username }}:{{ .Values.rabbitmq.auth.password }}@{{ .Release.Name }}-rabbitmq:5672/"
```

---

### 🟠 High

---

#### [Issue #11] Worker silently ACKs and drops malformed messages missing `task_id`

**File**: `src/worker/main.py:39`  
**GitHub**: https://github.com/bridgeshi85/k8s-helm-e2e-boilerplate/issues/11

**Problem**

When a consumed message lacks the `task_id` key, the function returns early inside `async with message.process()`. `aio_pika` interprets the clean exit as a positive ACK — the message is permanently removed from the queue with no log, no dead-letter routing, and no error record.

```python
async with message.process():
    task_id = body.get("task_id")
    if not task_id:
        return   # ← message ACK'd and permanently lost
```

**Fix**

```python
if not task_id:
    logger.error("Received message without task_id, discarding: %s", body)
    await message.reject(requeue=False)  # route to dead-letter exchange
    return
```

---

#### [Issue #12] Gateway `containerPort` templated from `service.port` but nginx hardcodes `listen 80`

**File**: `charts/taskflow/templates/gateway-deployment.yaml:29`  
**GitHub**: https://github.com/bridgeshi85/k8s-helm-e2e-boilerplate/issues/12

**Problem**

The Deployment uses `containerPort: {{ .Values.gateway.service.port }}` (dynamic) but the nginx ConfigMap hardcodes `listen 80` (static). Changing `gateway.service.port` in `values.yaml` updates the Service target and Deployment annotation but not the actual nginx listener — all traffic to the pod is silently dropped.

**Fix**

Make `listen` dynamic in the ConfigMap:

```nginx
listen {{ .Values.gateway.service.port }};
```

Or pin both to the same fixed value in `values.yaml` and the ConfigMap.

---

#### [Issue #13] Nginx trailing-slash `proxy_pass` strips `/api/` prefix — direct backend calls return 404

**File**: `charts/taskflow/templates/gateway-configmap.yaml:26`  
**GitHub**: https://github.com/bridgeshi85/k8s-helm-e2e-boilerplate/issues/13

**Problem**

```nginx
location /api/ {
    proxy_pass http://.../backend:8000/;  # trailing slash rewrites /api/foo → /foo
}
```

The trailing slash causes nginx to strip the `/api/` prefix. Any internal caller (integration test, sidecar, inter-service call) that hits the backend Service directly at `/api/tasks` gets 404, because the route is registered as `/tasks`. This is invisible during gateway-proxied testing.

**Fix**

Remove the trailing slash to preserve the full path:

```nginx
proxy_pass http://.../backend:8000;
```

---

#### [Issue #14] Gateway deployment has no liveness/readiness probes

**File**: `charts/taskflow/templates/gateway-deployment.yaml`  
**GitHub**: https://github.com/bridgeshi85/k8s-helm-e2e-boilerplate/issues/14

**Problem**

The gateway (nginx) container has no `livenessProbe` or `readinessProbe`. A crashed or hung nginx process goes undetected — the pod stays `Running` and continues receiving traffic, returning 502/504 to all clients until manual intervention.

**Fix**

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: {{ .Values.gateway.service.port }}
  initialDelaySeconds: 5
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /healthz
    port: {{ .Values.gateway.service.port }}
  initialDelaySeconds: 3
  periodSeconds: 5
```

Add `location /healthz { return 200; }` to the nginx ConfigMap.

---

### 🟡 Medium

---

#### [Issue #15] ServiceMonitor scrapes `/metrics` but app may expose metrics at `/api/metrics`

**File**: `charts/taskflow/templates/backend-servicemonitor.yaml:20`  
**GitHub**: https://github.com/bridgeshi85/k8s-helm-e2e-boilerplate/issues/15

**Problem**

The ServiceMonitor is configured with `path: /metrics`. The FastAPI app sets `root_path="/api"` and uses `fastapi-instrumentator`. If the instrumentator registers under the root path, the actual endpoint is `/api/metrics` — Prometheus scrapes `/metrics`, gets 404, and collects no backend metrics.

**Fix**

1. Verify the actual path by curling `:8000/metrics` and `:8000/api/metrics` in the running pod.
2. Update the ServiceMonitor path to match, or explicitly set the metrics mount point:

```python
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

---

#### [Issue #16] Worker uses deprecated `sqlalchemy.ext.declarative` import — `ImportError` on SQLAlchemy 2.0

**File**: `src/worker/models.py:2`  
**GitHub**: https://github.com/bridgeshi85/k8s-helm-e2e-boilerplate/issues/16

**Problem**

```python
# worker — deprecated in 1.4, removed in 2.0
from sqlalchemy.ext.declarative import declarative_base

# backend — correct
from sqlalchemy.orm import declarative_base
```

Upgrading SQLAlchemy to 2.x causes the worker pod to crash at startup with `ImportError`. The worker's `models.py` is a copy-pasted version of the backend's that has drifted in multiple ways (wrong import, wrong default password, no `pool_pre_ping`).

**Fix**

Update the import and consolidate the shared model into `src/common/models.py`.

---

### 🔵 Low

---

#### [Issue #17] `logging_config.py` duplicated verbatim across backend and worker

**File**: `src/backend/logging_config.py`, `src/worker/logging_config.py`  
**GitHub**: https://github.com/bridgeshi85/k8s-helm-e2e-boilerplate/issues/17

**Problem**

Both files implement identical `RequestIDFilter`, `setup_logging()`, and `get_logger()` logic. They have already started to diverge (different docstring languages, annotation differences). Any change to log format must be applied in two places.

**Fix**

Extract to `src/common/logging_config.py` and import from both services.

---

#### [Issue #18] E2E runner shell script baked inline in ConfigMap — cannot be shellcheck-linted

**File**: `charts/e2e-runner/templates/configmap.yaml:19`  
**GitHub**: https://github.com/bridgeshi85/k8s-helm-e2e-boilerplate/issues/18

**Problem**

`run-tests.sh` is embedded as a YAML multiline string inside the Helm template. It cannot be linted by `shellcheck` in CI, YAML indentation errors silently corrupt it, and Helm template expressions (`{{ .Values.* }}`) prevent standalone shell parsing.

**Fix**

Move to `charts/e2e-runner/files/run-tests.sh` and reference in the template:

```yaml
data:
  run-tests.sh: {{ .Files.Get "files/run-tests.sh" | tpl . | quote }}
```

---

## Refuted / Not Confirmed

The following candidates were investigated but REFUTED by the verifier:

| Candidate | Reason |
|-----------|--------|
| Worker `get_db()` resource leak | `update_task_status()` wraps the session in `try/finally` with explicit `db.close()` — no leak |
| Counter defined before use (`NameError`) | Python only evaluates function bodies at call time, not definition time — no ordering issue |
| `initContainer` subPath dirs missing on fresh PVC | The initContainer mounts the PVC root and creates the subdirectories before the main container starts — correct pattern |
| `port-forward-all.sh` silently ignores failures | The Postgres case is explicitly guarded with `\|\| echo "skipping"` |

---

## Priority Fix Order

1. **#9** + **#16** — Fix worker `models.py` (wrong password + deprecated import) — the worker is likely broken in all default deployments
2. **#10** — Fix RabbitMQ URL credentials — task creation is likely failing in all default deployments
3. **#11** — Add dead-letter / error logging for malformed messages — prevents silent data loss
4. **#14** — Add gateway probes — basic Kubernetes health management
5. **#12** + **#13** — Fix nginx port/path consistency — operational correctness
6. **#15** — Verify and fix metrics scrape path
7. **#17** + **#18** — Cleanup tasks (lower urgency)