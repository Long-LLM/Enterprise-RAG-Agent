"""
Enterprise RAG Agent - 生产级统一日志模块

特性：
- 结构化 JSON 日志（便于 ELK/Loki 收集）
- 控制台彩色输出（开发友好）
- 日志自动轮转（按大小 + 按日期）
- 请求 Trace ID 全链路追踪
- 性能耗时自动记录
- 按模块分级配置
- 异常自动捕获与堆栈记录

使用方式：
    from app.logger import get_logger
    logger = get_logger(__name__)
    logger.info("消息", extra={"key": "value"})
    logger.bind(user_id="123").info("带上下文的消息")
"""
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
import traceback
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

# ---------- 全局 Trace ID 上下文 ----------
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_current_trace_id() -> str:
    """获取当前上下文中的 Trace ID"""
    return trace_id_var.get()


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """设置 Trace ID，未提供则自动生成"""
    tid = trace_id or uuid.uuid4().hex[:16]
    trace_id_var.set(tid)
    return tid


# ---------- 配置 ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 模块级别配置：可针对不同模块设置不同日志级别
MODULE_LEVELS = {
    # 示例：降低第三方库的日志级别
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "pymilvus": "WARNING",
    "unstructured": "WARNING",
    "transformers": "WARNING",
    "sentence_transformers": "WARNING",
}

# 日志保留配置
MAX_BYTES = 50 * 1024 * 1024       # 单个日志文件 50MB
BACKUP_COUNT = 10                   # 保留 10 个备份


# ---------- 日志记录模型 ----------
@dataclass
class LogRecord:
    """结构化日志记录"""
    timestamp: str
    level: str
    logger: str
    message: str
    trace_id: str
    module: str
    function: str
    line: int
    thread: str
    extra: Optional[Dict[str, Any]] = None
    exception: Optional[str] = None
    duration_ms: Optional[float] = None


# ---------- 格式化器 ----------

class ColoredFormatter(logging.Formatter):
    """控制台彩色格式化器"""

    COLORS = {
        "DEBUG": "\x1b[38;5;247m",      # 灰色
        "INFO": "\x1b[38;5;39m",        # 蓝色
        "WARNING": "\x1b[38;5;214m",    # 橙色
        "ERROR": "\x1b[38;5;196m",      # 红色
        "CRITICAL": "\x1b[38;5;199m",   # 紫色
        "RESET": "\x1b[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]

        # 确保 asctime 存在
        record.asctime = self.formatTime(record, self.datefmt)

        trace = getattr(record, "trace_id", "") or "-"
        duration = ""
        if hasattr(record, "duration_ms") and record.duration_ms is not None:
            duration = f" | {record.duration_ms:.2f}ms"

        # 简化模块名
        module_name = record.name
        if module_name.startswith("app."):
            module_name = module_name[4:]

        msg = record.getMessage()
        # 如果有 extra 数据，格式化为 key=value
        extra = getattr(record, "extra_data", None)
        if extra and isinstance(extra, dict):
            try:
                extra_str = " ".join([f"{k}={v}" for k, v in extra.items() if isinstance(v, (str, int, float, bool))])
                if extra_str:
                    msg = f"{msg} | {extra_str}"
            except Exception:
                pass

        formatted = (
            f"{color}{record.levelname:8}{reset} "
            f"[{record.asctime}] "
            f"[{trace}] "
            f"[{module_name}] "
            f"{msg}{duration}"
        )

        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


class JSONFormatter(logging.Formatter):
    """JSON 结构化格式化器（用于文件日志）"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "") or "",
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": f"{record.threadName}({record.thread})",
            "pid": record.process,
        }

        # extra 数据（安全处理，避免循环引用和不可序列化对象）
        extra = getattr(record, "extra_data", None)
        if extra and isinstance(extra, dict):
            safe_extra = {}
            for k, v in extra.items():
                try:
                    # 先测试能否 JSON 序列化
                    json.dumps({k: v}, default=str)
                    safe_extra[k] = v
                except (TypeError, ValueError):
                    safe_extra[k] = str(v)
            if safe_extra:
                log_data["extra"] = safe_extra

        # 耗时
        duration = getattr(record, "duration_ms", None)
        if duration is not None:
            log_data["duration_ms"] = round(duration, 3)

        # 异常堆栈
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        try:
            return json.dumps(log_data, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            # 最终兜底：强制全部转字符串
            return json.dumps({k: str(v) for k, v in log_data.items()}, ensure_ascii=False)


# ---------- 日志适配器（支持 bind/extra）----------

class ContextAdapter(logging.LoggerAdapter):
    """
    增强型 LoggerAdapter
    - 支持 bind() 绑定上下文字段
    - 支持 extra={} 附加字段
    - 自动注入 trace_id
    """

    def __init__(self, logger: logging.Logger, extra: Optional[Dict] = None):
        super().__init__(logger, extra or {})
        self._context: Dict[str, Any] = {}

    def bind(self, **kwargs) -> "ContextAdapter":
        """绑定上下文字段，返回新的 adapter（不改变原对象）"""
        new_adapter = ContextAdapter(self.logger, {**self.extra})
        new_adapter._context = {**self._context, **kwargs}
        return new_adapter

    def process(self, msg: str, kwargs: Dict) -> tuple:
        """处理日志记录，注入上下文和 trace_id"""
        extra = kwargs.get("extra", {})
        if not isinstance(extra, dict):
            extra = {}

        # 合并 bind 的上下文
        merged = {**self._context, **extra}
        kwargs["extra"] = merged

        # 注入 trace_id
        trace_id = get_current_trace_id()
        merged["trace_id"] = trace_id

        return msg, kwargs

    def _log_with_extra(self, level: int, msg: str, args, **kwargs):
        """内部方法：记录日志并附加 extra_data"""
        extra = kwargs.get("extra", {})
        if extra:
            kwargs.setdefault("extra", {})["extra_data"] = extra
        super().log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        self._log_with_extra(logging.DEBUG, msg, args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        self._log_with_extra(logging.INFO, msg, args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._log_with_extra(logging.WARNING, msg, args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self._log_with_extra(logging.ERROR, msg, args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        self._log_with_extra(logging.CRITICAL, msg, args, **kwargs)

    def exception(self, msg: str, *args, exc_info=True, **kwargs):
        self._log_with_extra(logging.ERROR, msg, args, exc_info=exc_info, **kwargs)


# ---------- 日志工厂 ----------

class LoggerFactory:
    """日志工厂：负责初始化根日志器和各模块日志器"""

    _initialized = False
    _lock = threading.Lock()

    @classmethod
    def init(cls, log_level: str = LOG_LEVEL, log_dir: Path = LOG_DIR):
        """初始化全局日志系统（线程安全，幂等）"""
        with cls._lock:
            if cls._initialized:
                return
            cls._do_init(log_level, log_dir)
            cls._initialized = True

    @classmethod
    def _do_init(cls, log_level: str, log_dir: Path):
        """实际初始化逻辑"""
        root = logging.getLogger()
        root.setLevel(log_level)

        # 清除已有的 handlers（避免重复）
        for handler in root.handlers[:]:
            root.removeHandler(handler)

        # ---- 1. 控制台 Handler（彩色） ----
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_fmt = ColoredFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_fmt)
        root.addHandler(console_handler)

        # ---- 2. 应用日志文件 Handler（JSON，轮转） ----
        app_log_path = log_dir / "app.json.log"
        app_handler = logging.handlers.RotatingFileHandler(
            app_log_path,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        app_handler.setLevel(log_level)
        app_handler.setFormatter(JSONFormatter())
        root.addHandler(app_handler)

        # ---- 3. 错误日志文件 Handler（JSON，只记录 ERROR+） ----
        error_log_path = log_dir / "error.json.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_path,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        root.addHandler(error_handler)

        # ---- 4. 访问日志文件 Handler（纯文本，可读性好） ----
        access_log_path = log_dir / "access.log"
        access_handler = logging.handlers.RotatingFileHandler(
            access_log_path,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        access_handler.setLevel(logging.INFO)
        access_fmt = logging.Formatter(
            "%(asctime)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        access_handler.setFormatter(access_fmt)
        # 用一个专门的 logger 来接收访问日志
        access_logger = logging.getLogger("app.access")
        access_logger.addHandler(access_handler)
        access_logger.propagate = False  # 不向 root 传播

        # ---- 5. 模块级别日志配置 ----
        for module_name, level in MODULE_LEVELS.items():
            logging.getLogger(module_name).setLevel(level)

        root.info("日志系统初始化完成", extra={
            "log_level": log_level,
            "log_dir": str(log_dir),
            "handlers": ["console", "app.json.log", "error.json.log", "access.log"],
        })


# ---------- 公共 API ----------

def get_logger(name: str) -> ContextAdapter:
    """
    获取模块日志器
    用法：
        logger = get_logger(__name__)
        logger.info("处理完成", extra={"doc_id": "xxx"})
        logger.bind(user_id="123").info("用户操作")
    """
    LoggerFactory.init()
    return ContextAdapter(logging.getLogger(name))


def get_access_logger() -> logging.Logger:
    """获取访问日志器（用于记录 HTTP 请求）"""
    LoggerFactory.init()
    return logging.getLogger("app.access")


# ---------- 性能日志装饰器 ----------

def log_performance(
    level: int = logging.INFO,
    log_args: bool = False,
    log_result: bool = False,
    max_result_len: int = 500,
):
    """
    性能日志装饰器
    自动记录函数调用耗时

    用法：
        @log_performance()
        async def my_func():
            ...
    """
    def decorator(func: Callable) -> Callable:
        logger = get_logger(func.__module__)
        func_name = f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            trace_id = get_current_trace_id()
            extra = {"function": func_name, "trace_id": trace_id}

            if log_args:
                # 避免记录敏感信息，仅记录参数名和类型
                extra["args_count"] = len(args)
                extra["kwargs_keys"] = list(kwargs.keys())

            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                extra["duration_ms"] = duration_ms
                extra["status"] = "success"

                if log_result and result is not None:
                    result_str = str(result)
                    extra["result_preview"] = result_str[:max_result_len]
                    if len(result_str) > max_result_len:
                        extra["result_truncated"] = True

                logger.log(level, f"[{func_name}] 调用成功", extra=extra)
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                extra["duration_ms"] = duration_ms
                extra["status"] = "failed"
                extra["error_type"] = type(e).__name__
                extra["error_msg"] = str(e)
                logger.error(f"[{func_name}] 调用失败: {e}", extra=extra, exc_info=True)
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            trace_id = get_current_trace_id()
            extra = {"function": func_name, "trace_id": trace_id}

            if log_args:
                extra["args_count"] = len(args)
                extra["kwargs_keys"] = list(kwargs.keys())

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                extra["duration_ms"] = duration_ms
                extra["status"] = "success"

                if log_result and result is not None:
                    result_str = str(result)
                    extra["result_preview"] = result_str[:max_result_len]
                    if len(result_str) > max_result_len:
                        extra["result_truncated"] = True

                logger.log(level, f"[{func_name}] 调用成功", extra=extra)
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                extra["duration_ms"] = duration_ms
                extra["status"] = "failed"
                extra["error_type"] = type(e).__name__
                extra["error_msg"] = str(e)
                logger.error(f"[{func_name}] 调用失败: {e}", extra=extra, exc_info=True)
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


# 需要导入 asyncio 用于判断协程
import asyncio


# ---------- FastAPI 中间件（放在这里避免循环导入）----------

class LoggingMiddleware:
    """
    FastAPI 日志中间件
    - 为每个请求生成 Trace ID
    - 记录请求/响应日志（含耗时）
    - 记录异常日志
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request

        request = Request(scope, receive)
        trace_id = request.headers.get("x-trace-id") or set_trace_id()

        start_time = time.perf_counter()
        path = request.url.path
        method = request.method
        client = scope.get("client", ("-", "-"))[0]

        access_logger = get_access_logger()
        access_logger.info(
            f"=> {method} {path} | client={client} | trace={trace_id}"
        )

        # 包装 send 以捕获响应状态
        status_code = 200

        async def wrapped_send(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
            duration_ms = (time.perf_counter() - start_time) * 1000
            access_logger.info(
                f"<= {method} {path} | status={status_code} | duration={duration_ms:.2f}ms | trace={trace_id}"
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            access_logger.error(
                f"<= {method} {path} | status=500 | duration={duration_ms:.2f}ms | trace={trace_id} | error={e}"
            )
            # 用根 logger 记录详细异常
            logger = get_logger("app.middleware")
            logger.bind(trace_id=trace_id, path=path, method=method).error(
                f"请求处理异常: {e}", exc_info=True
            )
            raise
