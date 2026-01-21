# K8s Helm E2E Boilerplate: TaskFlow

A robust full-stack portfolio project demonstrating a modern DevOps workflow. This project deploys a 3-tier application (React Frontend, FastAPI Backend, Redis/PostgreSQL) using **Helm** on Kubernetes, utilizing **GitHub Actions** for CI/CD.

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

### 1. Preparation: Log in to Docker Hub

First, ensure that you are logged into Docker Hub in your terminal.

```bash
# In the terminal, enter your Docker Hub username and password (or Access Token) as prompted
docker login
```

### 2. Build and Push

Execute the following commands in the root directory of the project:

A. Build and Push Backend

```bash
# 1. Build the image (note the dot . at the end)
docker build -t <your_repo>/taskflow-backend:v1.0.0 ./src/backend

# 2. Push the image
docker push <your_repo>/taskflow-backend:v1.0.0
```

B. Build and Push Frontend

```bash
# 1. Build the image
docker build -t <your_repo>/taskflow-frontend:v1.0.0 ./src/frontend

# 2. Push the image
docker push <your_repo>/taskflow-frontend:v1.0.0
```

## 🏃‍♂️ Getting Started

1. install the dependency
    ```bash
    # Enter the chart directory
    cd charts/taskflow

    # Download dependencies (this will generate .tgz files in the charts/ directory)
    helm dependency build

    # Return to the root directory
    cd ../..
    ```

2. **Configuration:**
  Check `charts/taskflow/values.yaml` to configure image tags, resource limits, and database credentials.
  
3. Deploy the application to your Kubernetes cluster.
    ```bash
    # Install the chart
    helm upgrade taskflow ./charts/taskflow -n taskflow --create-namespace --install --create-namespace
    ```

---

## Verify Deployment Status

### 1. Check Pod Status

Run the following command:

```bash
kubectl get pods -n taskflow
```

> You should see 4 Pods (Frontend, Backend, Redis, Postgres), all in `Running` or `Completed` status.
>
> ⚠️ **Note**: If you see `CrashLoopBackOff`, it's usually a DB connection issue or a misconfigured Secret.

### 2. Check Service

Run the following command:

```bash
kubectl get svc -n taskflow
```

**Expected Result:**
> You should see the following Services:
> - `taskflow-backend`
> - `taskflow-frontend`
> - `taskflow-redis-master`
> - `taskflow-postgresql`

---


### 3. Enable Port Forwarding


Open a new terminal window:

```bash
# Format: kubectl port-forward svc/<service-name> <local-port>:<container-port>
kubectl port-forward svc/taskflow-frontend -n taskflow
```

Open your browser and go to: [http://localhost:8080](http://localhost:8080)

You should able to see page like below:
![alt text](image.png)


## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
