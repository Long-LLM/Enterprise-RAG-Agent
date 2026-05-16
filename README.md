# Enterprise RAG Agent

> 企业级本地私有化 RAG 智能问答系统 — FastAPI + Milvus + Ollama + Vue 3 + Celery

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.4+-42b883.svg)](https://vuejs.org/)
[![Milvus](https://img.shields.io/badge/Milvus-2.4+-00BFFF.svg)](https://milvus.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## ✨ 特性

- 🔒 **完全私有化**：基于 Ollama 本地推理，数据不出企业
- 📚 **7 种分块策略**：auto / fixed_size / recursive / semantic / structured / parent_child / llm_smart
- 🔍 **混合检索**：向量检索 + BM25 + RRF 融合 + BGE Reranker 重排
- 💬 **流式对话**：SSE 流式输出，意图判断快速路径
- 🔄 **多轮会话**：自动维护对话历史，支持上下文理解
- ⚡ **异步处理**：Celery + Redis，大文档后台处理不阻塞 API
- 👥 **三角色权限**：Admin / Staff / User，部门级数据隔离
- 📊 **可观测性**：Prometheus 指标 + 结构化日志 + Trace ID
- 🐳 **一键部署**：Docker Compose 集成 PostgreSQL + Redis

## 🏗️ 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI · Pydantic · SQLAlchemy 2.0 (async) · Celery |
| 向量库 | Milvus 2.4+ (IVF_FLAT + COSINE) |
| 元数据库 | PostgreSQL 16（生产）/ SQLite（开发） |
| Embedding | Ollama + bge-m3 (1024 维) |
| LLM | Ollama + qwen2.5:7b-instruct（可切换 vLLM） |
| Reranker | BGE-Reranker (FlagEmbedding) |
| 任务队列 | Celery + Redis 7 |
| 前端 | Vue 3 · Element Plus · Vite · TypeScript |

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone https://github.com/Long-LLM/Enterprise-RAG-Agent.git
cd Enterprise-RAG-Agent

# 复制环境变量模板
cp .env.example .env
# 编辑 .env，至少修改 SECRET_KEY
```

### 2. 启动外部依赖

**Milvus（必需）**：

```bash
wget https://github.com/milvus-io/milvus/releases/download/v2.4.0/milvus-standalone-docker-compose.yml -O milvus.yml
docker compose -f milvus.yml up -d
```

**Ollama（必需）**：

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取模型
ollama pull bge-m3
ollama pull qwen2.5:7b-instruct
```

### 3. 启动应用

**方式 A：Docker Compose（推荐生产）**

```bash
docker compose up -d
# 自动启动 PostgreSQL + Redis + Backend
```

**方式 B：本地开发**

```bash
# 后端
cd backend
pip install -r ../requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Celery Worker（新终端）
celery -A app.core.celery_app worker --loglevel=info --queues=celery,doc_process,maintenance

# 前端（新终端）
cd frontend
npm install
npm run dev -- --host
```

### 4. 访问

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| Swagger 文档 | http://localhost:8000/docs |
| Prometheus 指标 | http://localhost:8000/metrics |
| 健康检查 | http://localhost:8000/api/health |

**默认管理员账号**：
- 用户名：`admin`
- 密码：`admin`（首次启动自动创建，**生产环境务必修改**）

## 📂 项目结构

```
Enterprise-RAG-Agent/
├── backend/                    # 后端
│   ├── app/
│   │   ├── api/routes/         # FastAPI 路由
│   │   ├── services/           # 业务编排层
│   │   ├── core/               # 核心引擎
│   │   │   ├── parser.py       # 文档解析
│   │   │   ├── chunking.py     # 7 种分块策略
│   │   │   ├── embedding.py    # Embedding (bge-m3)
│   │   │   ├── milvus_store.py # 向量存储
│   │   │   ├── retrieval.py    # 混合检索
│   │   │   ├── reranker.py     # 重排序
│   │   │   ├── llm.py          # LLM 服务
│   │   │   ├── celery_app.py   # Celery 配置
│   │   │   └── tasks.py        # 异步任务
│   │   ├── models/schemas.py   # Pydantic 模型
│   │   ├── container.py        # 依赖注入容器
│   │   ├── config.py           # 配置（Pydantic Settings）
│   │   ├── logger.py           # 日志 + Trace ID
│   │   └── main.py             # FastAPI 入口
│   ├── tests/                  # 单元测试
│   └── Dockerfile
├── frontend/                   # 前端
│   ├── src/
│   │   ├── api/api.ts          # Axios 封装
│   │   ├── views/              # 页面组件
│   │   ├── components/         # 通用组件
│   │   └── router.ts           # 路由配置
│   └── package.json
├── docker-compose.yml          # 一键部署
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量模板
├── CLAUDE.md                   # Claude Code 项目指南
├── AGENTS.md                   # Agent 与分块策略详解
├── RAG原理讲解.md              # RAG 原理科普
└── 企业工程化落地流程.md         # 企业落地完整指南
```

## 🔧 核心 API

### 文档管理

```bash
# 同步上传（小文件 < 10MB）
POST /api/upload

# 异步上传（大文件，推荐）
POST /api/upload/async        # 返回 task_id
GET  /api/tasks/{task_id}     # 轮询进度

# 分块预览（不入库）
POST /api/chunk-preview
```

### 问答

```bash
# 同步问答
POST /api/query
{
  "question": "公司年假政策是什么？",
  "conversation_id": "uuid",
  "top_k": 5,
  "use_rerank": true
}

# 流式问答（SSE）
POST /api/query/stream
```

### 会话管理

```bash
POST   /api/conversations          # 创建会话
GET    /api/conversations          # 列出会话
GET    /api/conversations/{id}     # 获取会话详情（含消息历史）
DELETE /api/conversations/{id}     # 删除会话
```

### 权限管理（Admin）

```bash
GET    /api/permissions/users              # 用户列表
POST   /api/permissions/users/{id}/role    # 修改角色
POST   /api/permissions/public-documents   # 设置公共文档
```

## 🧪 测试

```bash
cd backend

# 全量测试
python -m pytest tests/ -v

# 跳过集成测试（无需 Milvus/Ollama）
python -m pytest tests/ -m "not integration" -v

# 带覆盖率
python -m pytest tests/ --cov=app --cov-report=html
```

外部服务通过 DI 容器在测试中 mock：

```python
from app.container import container
container.override(MilvusStore, MockMilvusStore())
```

## 📊 可观测性

- **健康检查**：`GET /api/health` — Milvus / Ollama / DB / Redis 状态优雅降级
- **Prometheus 指标**：`GET /metrics` — HTTP 延迟、Celery 任务、RAG 各阶段耗时
- **结构化日志**：`backend/logs/*.log` — JSON 格式，自动注入 trace_id
- **Trace ID**：通过 `LoggingMiddleware` 贯穿请求链路，便于排障关联

## 🛡️ 权限模型

| 角色 | 文档查看 | 文档上传 | 文档删除 | 用户管理 |
|------|---------|---------|---------|---------|
| Admin | 全部 | 任意部门 | 全部 | 支持 |
| Staff | 公共 + 本部门 | 仅本部门 | 本部门 | 不支持 |
| User | 仅公共 | 不支持 | 不支持 | 不支持 |

权限过滤在 **Milvus 检索层**注入 `doc_id in [...]`，防止向量泄露。

## 📚 文档

- [RAG 原理讲解.md](./RAG原理讲解.md) — RAG 基础原理与本项目实现
- [企业工程化落地流程.md](./企业工程化落地流程.md) — 完整工程化指南
- [AGENTS.md](./AGENTS.md) — 分块策略与会话系统细节
- [CLAUDE.md](./CLAUDE.md) — Claude Code 项目指引

## ⚠️ 部署陷阱

| 问题 | 解决方案 |
|------|---------|
| `bcrypt>=5.0` 破坏 passlib | 锁定 `bcrypt<5.0` |
| Windows 端口僵尸 | 换端口启动，前端 vite 代理同步修改 |
| SQLite 无法迁移 | 切 PostgreSQL，未来引入 Alembic |
| Celery PENDING 不动 | 检查 Worker 是否监听对应队列 |
| 检索结果不相关 | 调分块策略、启用重排序、调整 `top_k` |

更多详见 [企业工程化落地流程.md](./企业工程化落地流程.md) 第九章。

## 🗺️ Roadmap

- [ ] 增量索引（文档版本管理）
- [ ] GraphRAG 知识图谱融合
- [ ] 多模态（表格/图片理解）
- [ ] Agent 化（工具调用 + 规划）
- [ ] 评估闭环（RAGAS + 人工反馈）
- [ ] Milvus 原生全文索引替代内存 BM25

## 🤝 贡献

欢迎 Issue 和 PR。本项目同时作为「企业级 RAG 落地最佳实践」配套示例代码。

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)

## 🙏 致谢

- [Milvus](https://milvus.io/) — 向量数据库
- [Ollama](https://ollama.com/) — 本地 LLM 推理
- [BGE](https://github.com/FlagOpen/FlagEmbedding) — Embedding 与 Reranker
- [Qwen](https://github.com/QwenLM/Qwen) — 中文 LLM
- [Dify](https://dify.ai/) — 分块策略设计参考
