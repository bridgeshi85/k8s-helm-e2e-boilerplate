# TaskFlow Backend

这是一个基于FastAPI的TaskFlow后端应用，使用Redis进行缓存，SQLAlchemy与PostgreSQL数据库交互。

## 功能特性

- **任务管理**：创建和获取任务列表
- **Redis缓存**：支持键值对缓存操作
- **数据库集成**：使用PostgreSQL存储任务数据
- **RESTful API**：提供标准的REST API端点

## API端点

### 根端点
- `GET /` - 欢迎消息

### 任务管理
- `GET /tasks` - 获取所有任务
- `POST /tasks` - 创建新任务（参数：title, description）

### 缓存操作
- `GET /cache/{key}` - 获取缓存值
- `POST /cache` - 设置缓存值（参数：key, value）

## 安装和运行

### 方法1：本地开发
1. 激活虚拟环境：
   ```bash
   cd src/backend
   source .venv/bin/activate
   ```

2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

3. 启动服务器：
   ```bash
   python main.py
   ```
   或
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

服务器将在 http://localhost:8000 启动。

### 方法2：使用Docker Compose
1. 确保安装Docker和Docker Compose。
2. 在项目根目录运行：
   ```bash
   docker-compose up --build
   ```

这将启动整个应用栈，包括后端（端口8000）、前端（端口3000）、Redis和PostgreSQL。

## 环境变量

- `REDIS_HOST`：Redis主机地址（默认：redis）
- `DATABASE_URL`：PostgreSQL数据库URL（默认：postgresql://taskflow:changeme@postgres:5432/taskflow）

## 依赖

- FastAPI
- Uvicorn
- SQLAlchemy
- psycopg2-binary
- Redis

## 许可证

请查看LICENSE文件。