"""
Prometheus Metrics 模块

如果 prometheus_client 未安装，所有指标操作变为空操作（no-op），
应用仍可正常启动和运行。
"""
try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


class _NoOpMetric:
    """当 prometheus_client 不可用时使用的空操作指标替身"""

    def labels(self, *args, **kwargs):
        return self

    def observe(self, value):
        pass

    def inc(self, amount=1):
        pass

    def time(self):
        import contextlib

        @contextlib.contextmanager
        def _cm():
            yield

        return _cm()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _metric(cls, name, doc, labels, buckets=None, registry=None):
    """创建指标：如果 prometheus 可用则创建真实指标，否则创建 no-op"""
    if _PROMETHEUS_AVAILABLE:
        kwargs = {}
        if buckets is not None:
            kwargs["buckets"] = buckets
        if registry is not None:
            kwargs["registry"] = registry
        return cls(name, doc, labels, **kwargs)
    return _NoOpMetric()


# ---------- HTTP 层 ----------

HTTP_DURATION = _metric(
    Histogram, "http_request_duration_seconds", "HTTP 请求处理时间（秒）",
    ["method", "path", "status_code"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

HTTP_REQUESTS = _metric(
    Counter, "http_requests_total", "HTTP 请求总数",
    ["method", "path", "status_code"],
)

# ---------- Embedding 层 ----------

EMBEDDING_DURATION = _metric(
    Histogram, "embedding_duration_seconds", "Embedding 调用延迟（秒）",
    ["model", "batch_size"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)

EMBEDDING_REQUESTS = _metric(
    Counter, "embedding_requests_total", "Embedding 调用次数",
    ["model", "status"],
)

EMBEDDING_BATCH_SIZE = _metric(
    Histogram, "embedding_batch_size", "Embedding 批量大小分布",
    [],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500],
)

# ---------- LLM 层 ----------

LLM_DURATION = _metric(
    Histogram, "llm_duration_seconds", "LLM 调用延迟（秒）",
    ["provider", "model", "endpoint"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

LLM_REQUESTS = _metric(
    Counter, "llm_requests_total", "LLM 调用次数",
    ["provider", "model", "endpoint", "status"],
)

LLM_TOKENS_GENERATED = _metric(
    Counter, "llm_tokens_generated_total", "LLM 生成 token 总数",
    ["provider", "model"],
)

# ---------- 检索层 ----------

RETRIEVAL_DURATION = _metric(
    Histogram, "retrieval_duration_seconds", "检索调用延迟（秒）",
    ["type"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

RETRIEVAL_RESULTS = _metric(
    Counter, "retrieval_results_total", "检索返回结果数",
    ["type"],
)

RERANKER_DURATION = _metric(
    Histogram, "reranker_duration_seconds", "重排序调用延迟（秒）",
    ["model"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# ---------- Celery 层 ----------

CELERY_TASKS = _metric(
    Counter, "celery_tasks_total", "Celery 任务总数",
    ["task_name", "status"],
)

CELERY_TASK_DURATION = _metric(
    Histogram, "celery_task_duration_seconds", "Celery 任务执行时间",
    ["task_name"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
)

# ---------- 工具函数 ----------

if _PROMETHEUS_AVAILABLE:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
    REGISTRY = CollectorRegistry()

    def get_metrics_response():
        """生成 Prometheus 格式的 metrics 响应"""
        return generate_latest(REGISTRY)

    CONTENT_TYPE = CONTENT_TYPE_LATEST
else:
    REGISTRY = None

    def get_metrics_response():
        """prometheus_client 未安装时返回空响应"""
        return b"# prometheus_client not installed\n"

    CONTENT_TYPE = "text/plain; charset=utf-8"


def observe_http_request(method: str, path: str, status_code: int, duration: float):
    """记录 HTTP 请求指标"""
    normalized_path = _normalize_path(path)
    HTTP_DURATION.labels(method=method, path=normalized_path, status_code=str(status_code)).observe(duration)
    HTTP_REQUESTS.labels(method=method, path=normalized_path, status_code=str(status_code)).inc()


def _normalize_path(path: str) -> str:
    """规范化路径：将动态 ID 替换为占位符"""
    import re
    path = re.sub(r'/conversations/[^/]+', '/conversations/{id}', path)
    path = re.sub(r'/documents/[^/]+', '/documents/{id}', path)
    path = re.sub(r'/permissions/[^/]+', '/permissions/{id}', path)
    path = re.sub(r'/users/[^/]+', '/users/{id}', path)
    path = re.sub(r'/tasks/[^/]+', '/tasks/{id}', path)
    return path
