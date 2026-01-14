# K8s Helm E2E Boilerplate: TaskFlow

A robust full-stack portfolio project demonstrating a modern DevOps workflow. This project deploys a 3-tier application (React Frontend, FastAPI Backend, Redis/PostgreSQL) using **Helm** on Kubernetes, utilizing **GitHub Actions** for CI/CD, and validating deployments with **Playwright** End-to-End (E2E) tests.

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

## 🏃‍♂️ Getting Started

### 1. Local Development (Docker Compose)

Run the full stack locally without Kubernetes for rapid development.

```bash
docker-compose up --build
```

Access the services:
*   Frontend: `http://localhost:3000` (or configured port)
*   Backend API Docs: `http://localhost:8000/docs`

### 2. Kubernetes Deployment (Helm)

Deploy the application to your Kubernetes cluster.

```bash
# Install dependencies (Redis/Postgres)
helm dependency update charts/taskflow

# Install the chart
helm install taskflow ./charts/taskflow --namespace taskflow --create-namespace
```

**Configuration:**
Check `charts/taskflow/values.yaml` to configure image tags, resource limits, and database credentials.

## 🔄 CI/CD & E2E Testing

This project emphasizes automated quality assurance.

1.  **Continuous Integration**: On every push to `main`, GitHub Actions triggers:
    *   Linting (Python/JS)
    *   Unit Tests (Pytest)
    *   Docker Image Builds

2.  **End-to-End Testing (Playwright)**:
    *   *Planned/In-Progress*: A dedicated job spins up the environment (using Kind or a staging cluster) and runs Playwright tests to simulate user interactions (creating tasks, checking cache persistence).
    *   This ensures that the Helm chart deployment results in a fully functional application.

## 📝 Features

*   **Task Management**: Create, read, update, and delete tasks (PostgreSQL backed).
*   **Caching**: High-performance data retrieval using Redis.
*   **Scalability**: Microservices architecture ready for horizontal scaling in K8s.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
