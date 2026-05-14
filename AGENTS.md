# Enterprise RAG Agent - Agent 指南

## 项目概述
企业级本地私有化 RAG Agent，基于 FastAPI + Milvus + Ollama + Vue 3。
支持多格式文档解析、7 种分块策略、混合检索、重排序、LLM 生成。

## 技术栈
- **后端**: FastAPI + Pydantic + SQLAlchemy 2.0 (async)
- **向量存储**: Milvus 2.4+ (IVF_FLAT + COSINE)
- **元数据存储**: SQLite (aiosqlite) / 可切换 PostgreSQL
- **Embedding**: Ollama bge-m3 (1024维)
- **LLM**: Ollama qwen2.5:7b-instruct / vLLM
- **前端**: Vue 3 + Element Plus + Vite
- **检索**: 向量检索 + BM25 + RRF 融合 + 重排序

## 分块策略系统 (Dify 风格)

### 会话记忆系统

### 数据库表
- **conversations** — 会话表：`conversation_id`, `title`, `created_at`, `updated_at`
- **messages** — 消息表：`message_id`, `conversation_id`, `role`, `content`, `sources_json`, `model`, `processing_time_ms`, `created_at`

### API 接口
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/conversations` | 创建会话 |
| GET | `/api/conversations` | 获取会话列表（按更新时间倒序） |
| GET | `/api/conversations/{id}` | 获取会话详情（含消息历史） |
| PUT | `/api/conversations/{id}` | 更新会话标题 |
| DELETE | `/api/conversations/{id}` | 删除会话及消息 |

### 多轮对话
- `POST /api/query` 和 `POST /api/query/stream` 支持 `conversation_id` 参数
- 未提供 `conversation_id` 时自动创建新会话（以首条问题前 30 字为标题）
- RAGService 自动加载该会话最近 10 条消息（5 轮）作为 LLM 上下文
- 问答完成后自动保存用户消息和助手消息到数据库

### 前端功能
- 左侧会话侧边栏：显示会话列表、支持切换/删除
- 点击会话自动加载历史消息
- "新会话"按钮快速创建空白会话
- `localStorage` 持久化当前会话ID和设置（重排/流式开关）

## 支持的策略
| 策略 | 说明 | 适用场景 |
|------|------|----------|
| auto | 自动选择最优策略 | 通用 |
| fixed_size | 固定字符数切分 | 结构化数据、表格 |
| recursive | 递归分块（段落→句子→单词→字符） | 通用长文本 |
| semantic | 语义边界分块 | 保持语义完整 |
| structured | 按标题层级/表格结构分块 | Markdown/Word/结构化文档 |
| parent_child | 父块上下文+子块精确检索 | 需要完整上下文的场景 |
| llm_smart | LLM 智能分析分块 | 高质量需求、成本不敏感 |

### 策略参数
每种策略支持独立参数配置（通过 `strategy_params` JSON 传递）：
- **fixed_size**: `chunk_size`, `chunk_overlap`, `separator`
- **recursive**: `chunk_size`, `chunk_overlap`, `separators`
- **semantic**: `chunk_size`, `chunk_overlap`
- **structured**: `chunk_size`, `heading_levels`, `preserve_tables`
- **parent_child**: `parent_chunk_size`, `child_chunk_size`, `parent_overlap`, `child_overlap`
- **llm_smart**: `temperature`, `max_tokens`

### 预览功能
- `POST /api/chunk-preview` - 上传文件预览分块效果（不入库）
- 支持策略选择和参数调整
- 返回分块列表、统计信息
- 限制最大预览字符数（默认 30000）

### 父子分块架构
- 父块：大段上下文（如整节），向量化存入 Milvus
- 子块：小片段，向量化存入 Milvus，用于精确检索
- 关系维护：通过 `parent_id` 字段关联，元数据存 SQLite
- 检索增强：检索到子块后，自动获取父块内容作为上下文

## 会话记忆系统

### 数据库表
- **conversations** — 会话表：`conversation_id`, `title`, `created_at`, `updated_at`
- **messages** — 消息表：`message_id`, `conversation_id`, `role`, `content`, `sources_json`, `model`, `processing_time_ms`, `created_at`

### API 接口
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/conversations` | 创建会话 |
| GET | `/api/conversations` | 获取会话列表（按更新时间倒序） |
| GET | `/api/conversations/{id}` | 获取会话详情（含消息历史） |
| PUT | `/api/conversations/{id}` | 更新会话标题 |
| DELETE | `/api/conversations/{id}` | 删除会话及消息 |

### 多轮对话
- `POST /api/query` 和 `POST /api/query/stream` 支持 `conversation_id` 参数
- 未提供 `conversation_id` 时自动创建新会话（以首条问题前 30 字为标题）
- RAGService 自动加载该会话最近 10 条消息（5 轮）作为 LLM 上下文
- 问答完成后自动保存用户消息和助手消息到数据库

### 前端功能
- 左侧会话侧边栏：显示会话列表、支持切换/删除
- 点击会话自动加载历史消息
- "新会话"按钮快速创建空白会话
- `localStorage` 持久化当前会话ID和设置（重排/流式开关）

## 代码结构

```
backend/
  app/
    main.py              # FastAPI 入口
    config.py            # Pydantic Settings 配置
    logger.py            # 结构化日志
    models/schemas.py    # Pydantic 模型（含 Conversation/Message）
    api/routes/          # API 路由
      upload.py          # 文档上传
      chunk_preview.py   # 分块预览
      document.py        # 文档管理
      conversation.py    # 会话管理（CRUD + 消息历史）
      query.py           # 问答查询（支持 conversation_id 多轮对话）
      health.py          # 健康检查
    core/                # 核心模块
      chunking.py        # 分块引擎（7种策略）
      parser.py          # 文档解析
      embedding.py       # Embedding 服务
      milvus_store.py    # Milvus 封装
      metadata_store.py  # SQLite 元数据存储（含会话/消息表）
      retrieval.py       # 混合检索
      reranker.py        # 重排序
      llm.py             # LLM 服务
    services/            # 业务服务
      document_service.py # 文档处理编排
      rag_service.py     # RAG 问答编排（支持历史消息上下文）

frontend/
  src/
    views/
      UploadView.vue     # 上传页面（含预览）
      QueryView.vue      # 问答页面（含会话侧边栏、历史加载）
      DocumentView.vue   # 文档管理
    components/
      ChunkPreviewPanel.vue # 分块预览面板
    api/api.js           # API 调用（含会话管理 API）
```

## 开发规范

### 日志
- 使用 `app.logger.get_logger(__name__)` 获取 logger
- 自动携带 trace_id，支持 JSON 文件日志
- Windows 控制台可能显示乱码，不影响文件日志

### 错误处理
- API 层捕获异常，返回 `{code, message, data}` 格式
- 服务层抛异常，由 API 层统一处理

### 数据库
- SQLite 默认路径 `./metadata.db`
- 可切换 PostgreSQL：修改 `METADATA_DB_URL` 配置
- 使用 SQLAlchemy 2.0 async 模式

### Milvus
- 当前使用 `IVF_FLAT` + `COSINE` 距离
- Schema 包含 `parent_id`, `chunk_type`, `section_title` 等字段
- 动态字段 `enable_dynamic_field=True`

## 环境要求
- Python 3.11+
- Node.js 20+
- Milvus 2.4+ (Docker)
- Ollama (本地运行 bge-m3 和 qwen2.5:7b-instruct)

## 启动命令
```bash
# 后端
conda activate RAG-Agent
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd frontend
npm run dev -- --host
```
