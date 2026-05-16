"""
Celery 应用配置
- Broker: Redis（任务队列）
- Backend: Redis（结果存储）
- 路由：文档处理任务发送到专用队列

启动 Worker:
    cd backend
    celery -A app.core.celery_app worker --loglevel=info --queues=celery,doc_process

启动 Beat（定时任务）:
    celery -A app.core.celery_app beat --loglevel=info
"""
import os

from celery import Celery

from app.config import get_settings

settings = get_settings()

# Redis URL：优先环境变量，其次默认值
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celery 应用实例
celery_app = Celery(
    "rag_agent",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.core.tasks",
    ],
)

# Celery 配置
celery_app.conf.update(
    # 序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,

    # 任务跟踪
    task_track_started=True,
    task_time_limit=3600,          # 硬超时 1 小时
    task_soft_time_limit=3300,     # 软超时 55 分钟（触发 SoftTimeLimitExceeded）

    # 结果存储
    result_expires=3600 * 24,      # 结果保留 24 小时
    result_backend=REDIS_URL,

    # 队列定义
    task_routes={
        "app.core.tasks.process_document": {"queue": "doc_process"},
        "app.core.tasks.rebuild_bm25_index": {"queue": "maintenance"},
    },

    # 默认队列
    task_default_queue="celery",
    task_default_exchange="celery",
    task_default_routing_key="celery",

    # Worker 配置
    worker_prefetch_multiplier=1,  # 每次只取一个任务，适合长任务
    worker_max_tasks_per_child=50, # 处理 50 个任务后重启 worker（防止内存泄漏）
)


@celery_app.task(bind=True)
def debug_task(self):
    """调试用任务"""
    print(f"Request: {self.request!r}")
    return {"status": "ok", "task_id": self.request.id}
