# K8s Helm E2E Boilerplate: TaskFlow

A robust full-stack portfolio project demonstrating a modern DevOps workflow. This project deploys a 3-tier application (React Frontend, FastAPI Backend, Redis/PostgreSQL) using **Helm** on Kubernetes, utilizing **GitHub Actions** for CI/CD

## 🚀 Project Overview

The goal of this project is to showcase a complete production-like environment setup and automated testing pipeline.
*   **Frontend**: React application served via Nginx.
*   **Backend**: Python FastAPI service.
*   **Databases**: PostgreSQL (persistent storage) and Redis (caching).
*   **Infrastructure**: Kubernetes (K8s) managed via Helm Charts.
*   **CI/CD**: GitHub Actions pipeline for building Docker images, linting, and running tests.

## 📂 Repository Structure

```
.
├── .github/workflows   # CI/CD configurations (GitHub Actions)
├── charts/             # Helm charts for Kubernetes deployment
│   └── taskflow/       # Main application chart
├── src/
│   ├── backend/        # FastAPI application code
│   └── frontend/       # React application code
├── docker-compose.yml  # Local development orchestration
└── README.md           # Project documentation
```

## 🛠️ Prerequisites

*   Docker & Docker Compose
*   Kubernetes Cluster (Minikube, Kind, or Cloud Provider)
*   Helm 3+
*   Node.js & Python 3.10+ (for local development)

## 🐳 Building Docker Images

### 1. 准备工作：登录 Docker Hub

首先，你需要确保在终端中已经登录了 Docker Hub。

```bash
# 在终端执行，按提示输入你的 Docker Hub 用户名和密码（或 Access Token）
docker login
```

### 2. 执行构建与推送

请在项目的根目录下执行以下命令：

A. 构建并推送后端 (Backend)

```bash
# 1. 构建镜像 (注意最后的点 .)
docker build -t <your_repo>/taskflow-backend:v1.0.0 ./src/backend

# 2. 推送镜像
docker push <your_repo>/taskflow-backend:v1.0.0
```

B. 构建并推送前端 (Frontend)

```bash
# 1. 构建镜像
docker build -t <your_repo>/taskflow-frontend:v1.0.0 ./src/frontend

# 2. 推送镜像
docker push <your_repo>/taskflow-frontend:v1.0.0
```

## 🏃‍♂️ Getting Started

1. install the dependency
```bash
# 进入 chart 目录
cd charts/taskflow

# 下载依赖 (这会在 charts/ 目录下生成 .tgz 文件)
helm dependency build

# 返回根目录
cd ../..
```

2. **Configuration:**
Check `charts/taskflow/values.yaml` to configure image tags, resource limits, and database credentials.

Deploy the application to your Kubernetes cluster.
```bash

# Install the chart
helm upgrade taskflow ./charts/taskflow -n taskflow --create-namespace --install --create-namespace
```


阶段二：基础设施验证 (Infrastructure Verification)
在跑测试用例之前，先确保“路是通的”。

1. 检查 Pod 状态
Bash

kubectl get pods
期望结果：你应该看到 4 个 Pod（Frontend, Backend, Redis, Postgres），状态都必须是 Running 或 Completed。 如果看到 CrashLoopBackOff，通常是 DB 连接问题或 Secret 没配对。

2. 检查 Service
Bash

kubectl get svc
期望结果：看到 taskflow-backend, taskflow-frontend, taskflow-redis-master, taskflow-postgresql。

阶段三：建立测试通道 (Networking)
由于我们在本地 Kind 环境，Service IP 是集群内部的，你需要通过 port-forward 将服务暴露给宿主机（你的电脑），以便浏览器和 Playwright 可以访问。

1. 开启端口转发
我们需要转发 Frontend Service。 (假设你在前端 Nginx 里配置了 /api 反向代理转发给后端，那么只需要暴露前端端口即可)

打开一个新的终端窗口（保持运行）：

Bash

# 格式: kubectl port-forward svc/<service-name> <local-port>:<container-port>
kubectl port-forward svc/taskflow-frontend 8080:80
如果你的前端 Nginx 没有配置反向代理，你可能还需要单独转发后端：

Bash

# (可选) 只有当前端直接调 localhost:8000 时才需要
kubectl port-forward svc/taskflow-backend 8000:8000
2. 手动冒烟测试 (Manual Smoke Test)
打开浏览器访问：http://localhost:8080

UI 加载：能看到 React 页面吗？

功能测试：输入 Title 和 Description，点击 "Add Task"。

数据验证：刷新页面，Task 还在吗？（如果在，说明 Postgres 写入成功）。

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
