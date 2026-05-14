"""
元数据存储层
使用 SQLite (aiosqlite) 存储文档和 chunk 的元数据
支持父子分块的关系维护
"""
import json
import time
from typing import Dict, List, Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

Base = declarative_base()


# ========================== 数据模型 ==========================

class DocumentModel(Base):
    """文档元数据表"""
    __tablename__ = "documents"

    doc_id = Column(String(64), primary_key=True)
    filename = Column(String(256), nullable=False)
    title = Column(String(256))
    file_type = Column(String(32))
    chunk_strategy = Column(String(32), nullable=False)
    chunk_count = Column(Integer, default=0)
    file_size_bytes = Column(Integer)
    department = Column(String(64), nullable=True, index=True)  # 文档所属部门/数据库
    created_at = Column(Integer)
    updated_at = Column(Integer)


class ChunkModel(Base):
    """Chunk 元数据表"""
    __tablename__ = "chunks"

    chunk_id = Column(String(64), primary_key=True)
    doc_id = Column(String(64), nullable=False, index=True)
    parent_id = Column(String(64), nullable=True, index=True)
    chunk_type = Column(String(16), default="normal", index=True)  # normal | parent | child
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    section_title = Column(String(256))
    heading_level = Column(Integer)
    page_number = Column(Integer)
    char_count = Column(Integer)
    metadata_json = Column(Text)
    created_at = Column(Integer)


class ConversationModel(Base):
    """会话表"""
    __tablename__ = "conversations"

    conversation_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, index=True, default="")
    title = Column(String(256))
    created_at = Column(Integer)
    updated_at = Column(Integer)


class MessageModel(Base):
    """消息表"""
    __tablename__ = "messages"

    message_id = Column(String(64), primary_key=True)
    conversation_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    sources_json = Column(Text)  # JSON 字符串，存储引用来源
    model = Column(String(64))
    processing_time_ms = Column(Integer)
    created_at = Column(Integer)


class UserModel(Base):
    """用户表"""
    __tablename__ = "users"

    user_id = Column(String(64), primary_key=True)
    username = Column(String(32), nullable=False, unique=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), nullable=False, default="user")  # admin | staff | user
    department = Column(String(64), nullable=True, index=True)  # 员工所属部门
    created_at = Column(Integer)


class UserDocPermissionModel(Base):
    """用户文档权限表"""
    __tablename__ = "user_doc_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False, index=True)
    granted_by = Column(String(64))
    created_at = Column(Integer)


# ========================== 存储层 ==========================

class MetadataStore:
    """元数据存储封装"""

    def __init__(self):
        db_url = getattr(settings, "METADATA_DB_URL", "sqlite+aiosqlite:///./metadata.db")
        self.engine = create_async_engine(db_url, echo=False)
        self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def init_db(self):
        """初始化数据库表"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("[OK] 元数据数据库初始化完成")

    async def save_document(self, doc_info: Dict) -> None:
        """保存文档元数据"""
        async with self.async_session() as session:
            doc = DocumentModel(
                doc_id=doc_info["doc_id"],
                filename=doc_info.get("filename", ""),
                title=doc_info.get("title"),
                file_type=doc_info.get("file_type"),
                chunk_strategy=doc_info.get("chunk_strategy", "auto"),
                chunk_count=doc_info.get("chunk_count", 0),
                file_size_bytes=doc_info.get("file_size_bytes"),
                department=doc_info.get("department"),
                created_at=doc_info.get("created_at", int(time.time())),
                updated_at=doc_info.get("updated_at", int(time.time())),
            )
            await session.merge(doc)
            await session.commit()
            logger.info(f"文档元数据已保存: {doc_info['doc_id']}")

    async def save_chunks(self, chunks: List[Dict]) -> None:
        """批量保存 chunk 元数据"""
        if not chunks:
            return

        async with self.async_session() as session:
            for ch in chunks:
                chunk = ChunkModel(
                    chunk_id=ch.get("chunk_id", f"{ch['doc_id']}_{ch['chunk_index']}"),
                    doc_id=ch["doc_id"],
                    parent_id=ch.get("parent_id"),
                    chunk_type=ch.get("chunk_type", "normal"),
                    content=ch.get("content", "")[:4096],  # 限制长度
                    chunk_index=ch.get("chunk_index", 0),
                    section_title=ch.get("section_title"),
                    heading_level=ch.get("heading_level"),
                    page_number=ch.get("page_number"),
                    char_count=ch.get("char_count", len(ch.get("content", ""))),
                    metadata_json=json.dumps(ch.get("metadata", {}), ensure_ascii=False) if ch.get("metadata") else None,
                    created_at=ch.get("created_at", int(time.time())),
                )
                await session.merge(chunk)
            await session.commit()
            logger.info(f"已保存 {len(chunks)} 个 chunk 元数据")

    async def get_document(self, doc_id: str) -> Optional[Dict]:
        """获取文档元数据"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(DocumentModel).where(DocumentModel.doc_id == doc_id))
            doc = result.scalar_one_or_none()
            if doc:
                return {
                    "doc_id": doc.doc_id,
                    "filename": doc.filename,
                    "title": doc.title,
                    "file_type": doc.file_type,
                    "chunk_strategy": doc.chunk_strategy,
                    "chunk_count": doc.chunk_count,
                    "department": doc.department,
                    "created_at": doc.created_at,
                }
            return None

    async def get_chunks_by_doc(self, doc_id: str) -> List[Dict]:
        """获取文档的所有 chunks"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(ChunkModel).where(ChunkModel.doc_id == doc_id).order_by(ChunkModel.chunk_index)
            )
            rows = result.scalars().all()
            return [
                {
                    "chunk_id": r.chunk_id,
                    "doc_id": r.doc_id,
                    "parent_id": r.parent_id,
                    "chunk_type": r.chunk_type,
                    "content": r.content,
                    "chunk_index": r.chunk_index,
                    "section_title": r.section_title,
                    "heading_level": r.heading_level,
                    "page_number": r.page_number,
                    "char_count": r.char_count,
                    "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
                }
                for r in rows
            ]

    async def get_parent_chunk(self, parent_id: str) -> Optional[Dict]:
        """通过 parent_id 获取父块内容"""
        if not parent_id:
            return None
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(ChunkModel).where(ChunkModel.chunk_id == parent_id)
            )
            row = result.scalar_one_or_none()
            if row:
                return {
                    "chunk_id": row.chunk_id,
                    "content": row.content,
                    "chunk_type": row.chunk_type,
                    "section_title": row.section_title,
                }
            return None

    async def get_child_chunks(self, parent_id: str) -> List[Dict]:
        """获取某父块的所有子块"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(ChunkModel)
                .where(ChunkModel.parent_id == parent_id)
                .order_by(ChunkModel.chunk_index)
            )
            rows = result.scalars().all()
            return [
                {
                    "chunk_id": r.chunk_id,
                    "content": r.content,
                    "chunk_index": r.chunk_index,
                    "char_count": r.char_count,
                }
                for r in rows
            ]

    async def delete_document(self, doc_id: str) -> int:
        """级联删除文档及其 chunks"""
        async with self.async_session() as session:
            from sqlalchemy import delete
            # 先删除 chunks
            chunk_result = await session.execute(
                delete(ChunkModel).where(ChunkModel.doc_id == doc_id)
            )
            chunk_deleted = chunk_result.rowcount
            # 再删除文档
            doc_result = await session.execute(
                delete(DocumentModel).where(DocumentModel.doc_id == doc_id)
            )
            doc_deleted = doc_result.rowcount
            await session.commit()
            logger.info(f"级联删除文档 {doc_id}: {chunk_deleted} chunks, {doc_deleted} docs")
            return chunk_deleted

    async def list_documents(self) -> List[Dict]:
        """列出所有文档"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(DocumentModel).order_by(DocumentModel.created_at.desc())
            )
            rows = result.scalars().all()
            return [
                {
                    "doc_id": r.doc_id,
                    "filename": r.filename,
                    "title": r.title,
                    "file_type": r.file_type,
                    "chunk_strategy": r.chunk_strategy,
                    "chunk_count": r.chunk_count,
                    "department": r.department,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    # ---------- 会话管理 ----------

    async def create_conversation(self, conversation_id: str, title: str = None, user_id: str = "") -> None:
        """创建会话"""
        now = int(time.time())
        async with self.async_session() as session:
            conv = ConversationModel(
                conversation_id=conversation_id,
                user_id=user_id,
                title=title or "新会话",
                created_at=now,
                updated_at=now,
            )
            await session.merge(conv)
            await session.commit()
            logger.info(f"会话已创建: {conversation_id}")

    async def get_conversation(self, conversation_id: str, user_id: str = None) -> Optional[Dict]:
        """获取会话信息。若提供 user_id，则只返回属于该用户的会话"""
        async with self.async_session() as session:
            from sqlalchemy import select
            stmt = select(ConversationModel).where(ConversationModel.conversation_id == conversation_id)
            if user_id:
                stmt = stmt.where(ConversationModel.user_id == user_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                return {
                    "conversation_id": row.conversation_id,
                    "user_id": row.user_id,
                    "title": row.title,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
            return None

    async def list_conversations(self, user_id: str = None) -> List[Dict]:
        """列出会话，按更新时间倒序。若提供 user_id 则只返回该用户的会话"""
        async with self.async_session() as session:
            from sqlalchemy import select
            stmt = select(ConversationModel)
            if user_id:
                stmt = stmt.where(ConversationModel.user_id == user_id)
            stmt = stmt.order_by(ConversationModel.updated_at.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "conversation_id": r.conversation_id,
                    "user_id": r.user_id,
                    "title": r.title,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]

    async def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        """更新会话标题"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(ConversationModel).where(ConversationModel.conversation_id == conversation_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.title = title
                row.updated_at = int(time.time())
                await session.commit()
                return True
            return False

    async def update_conversation_time(self, conversation_id: str) -> bool:
        """更新会话更新时间"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(ConversationModel).where(ConversationModel.conversation_id == conversation_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.updated_at = int(time.time())
                await session.commit()
                return True
            return False

    async def delete_conversation(self, conversation_id: str) -> bool:
        """删除会话及其所有消息"""
        async with self.async_session() as session:
            from sqlalchemy import delete
            # 先删除消息
            await session.execute(
                delete(MessageModel).where(MessageModel.conversation_id == conversation_id)
            )
            # 再删除会话
            result = await session.execute(
                delete(ConversationModel).where(ConversationModel.conversation_id == conversation_id)
            )
            await session.commit()
            deleted = result.rowcount > 0
            if deleted:
                logger.info(f"会话已删除: {conversation_id}")
            return deleted

    # ---------- 消息管理 ----------

    async def save_message(self, message_id: str, conversation_id: str, role: str,
                           content: str, sources: List[Dict] = None,
                           model: str = None, processing_time_ms: int = None) -> None:
        """保存消息"""
        async with self.async_session() as session:
            msg = MessageModel(
                message_id=message_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                sources_json=json.dumps(sources, ensure_ascii=False) if sources else None,
                model=model,
                processing_time_ms=int(processing_time_ms) if processing_time_ms else None,
                created_at=int(time.time()),
            )
            await session.merge(msg)
            await session.commit()

    async def get_messages_by_conversation(self, conversation_id: str) -> List[Dict]:
        """获取会话的所有消息，按时间正序"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .order_by(MessageModel.created_at.asc())
            )
            rows = result.scalars().all()
            return [
                {
                    "message_id": r.message_id,
                    "conversation_id": r.conversation_id,
                    "role": r.role,
                    "content": r.content,
                    "sources": json.loads(r.sources_json) if r.sources_json else [],
                    "model": r.model,
                    "processing_time_ms": r.processing_time_ms,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    # ---------- 用户管理 ----------

    async def create_user(self, user_id: str, username: str, password_hash: str, role: str = "user", department: str = None) -> None:
        """创建用户"""
        now = int(time.time())
        async with self.async_session() as session:
            user = UserModel(
                user_id=user_id,
                username=username,
                password_hash=password_hash,
                role=role,
                department=department,
                created_at=now,
            )
            await session.merge(user)
            await session.commit()
            logger.info(f"用户已创建: {username} ({role}, 部门={department})")

    async def update_user_department(self, user_id: str, department: Optional[str]) -> bool:
        """更新用户所属部门"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(UserModel).where(UserModel.user_id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return False
            user.department = department
            await session.commit()
            return True

    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """通过用户名获取用户"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(UserModel).where(UserModel.username == username)
            )
            row = result.scalar_one_or_none()
            if row:
                return {
                    "user_id": row.user_id,
                    "username": row.username,
                    "password_hash": row.password_hash,
                    "role": row.role,
                    "department": row.department,
                    "created_at": row.created_at,
                }
            return None

    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """通过用户ID获取用户"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(UserModel).where(UserModel.user_id == user_id)
            )
            row = result.scalar_one_or_none()
            if row:
                return {
                    "user_id": row.user_id,
                    "username": row.username,
                    "password_hash": row.password_hash,
                    "role": row.role,
                    "department": row.department,
                    "created_at": row.created_at,
                }
            return None

    async def list_users(self) -> List[Dict]:
        """列出所有用户"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(UserModel).order_by(UserModel.created_at.desc())
            )
            rows = result.scalars().all()
            return [
                {
                    "user_id": r.user_id,
                    "username": r.username,
                    "role": r.role,
                    "department": r.department,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    async def init_default_admin(self) -> None:
        """初始化默认管理员账号（如不存在则创建）"""
        admin = await self.get_user_by_username("admin")
        if not admin:
            from app.core.security import get_password_hash
            admin_id = "admin_default_01"
            await self.create_user(
                user_id=admin_id,
                username="admin",
                password_hash=get_password_hash("admin"),
                role="admin",
            )
            logger.info("默认管理员账号已创建: admin / admin")

    # ---------- 文档权限管理 ----------

    async def grant_doc_permission(self, user_id: str, doc_id: str, granted_by: str) -> bool:
        """给用户分配文档权限，如已存在则跳过"""
        async with self.async_session() as session:
            from sqlalchemy import select
            # 检查是否已存在
            result = await session.execute(
                select(UserDocPermissionModel)
                .where(UserDocPermissionModel.user_id == user_id)
                .where(UserDocPermissionModel.doc_id == doc_id)
            )
            if result.scalar_one_or_none():
                return False  # 已存在

            perm = UserDocPermissionModel(
                user_id=user_id,
                doc_id=doc_id,
                granted_by=granted_by,
                created_at=int(time.time()),
            )
            session.add(perm)
            await session.commit()
            logger.info(f"权限分配: {user_id} -> {doc_id}")
            return True

    async def revoke_doc_permission(self, user_id: str, doc_id: str) -> bool:
        """取消用户文档权限"""
        async with self.async_session() as session:
            from sqlalchemy import delete
            result = await session.execute(
                delete(UserDocPermissionModel)
                .where(UserDocPermissionModel.user_id == user_id)
                .where(UserDocPermissionModel.doc_id == doc_id)
            )
            await session.commit()
            deleted = result.rowcount > 0
            if deleted:
                logger.info(f"权限取消: {user_id} -> {doc_id}")
            return deleted

    async def get_user_doc_permissions(self, user_id: str) -> List[str]:
        """获取用户有权限的所有 doc_id 列表"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(UserDocPermissionModel.doc_id)
                .where(UserDocPermissionModel.user_id == user_id)
            )
            rows = result.scalars().all()
            return list(rows)

    async def has_user_any_permission(self, user_id: str) -> bool:
        """检查用户是否有任何文档权限（用于判断是否有上传/管理权限）"""
        async with self.async_session() as session:
            from sqlalchemy import select, func
            result = await session.execute(
                select(func.count(UserDocPermissionModel.id))
                .where(UserDocPermissionModel.user_id == user_id)
            )
            return result.scalar() > 0

    # ---------- 公共查询权限（所有用户可查询） ----------

    PUBLIC_USER_ID = "__public__"

    async def grant_public_doc_permission(self, doc_id: str, granted_by: str) -> bool:
        """设置文档为所有用户可查询（公共权限）"""
        return await self.grant_doc_permission(self.PUBLIC_USER_ID, doc_id, granted_by)

    async def revoke_public_doc_permission(self, doc_id: str) -> bool:
        """撤销文档的公共查询权限"""
        async with self.async_session() as session:
            from sqlalchemy import delete
            result = await session.execute(
                delete(UserDocPermissionModel)
                .where(UserDocPermissionModel.user_id == self.PUBLIC_USER_ID)
                .where(UserDocPermissionModel.doc_id == doc_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def get_public_doc_permissions(self) -> List[str]:
        """获取所有用户可查询的文档ID列表"""
        return await self.get_user_doc_permissions(self.PUBLIC_USER_ID)

    async def list_departments(self) -> List[str]:
        """列出所有已存在的部门名称"""
        async with self.async_session() as session:
            from sqlalchemy import select, distinct
            result = await session.execute(
                select(distinct(DocumentModel.department))
                .where(DocumentModel.department.isnot(None))
            )
            rows = result.scalars().all()
            return sorted([r for r in rows if r])

    async def list_documents_by_department(self, department: str) -> List[Dict]:
        """按部门列出文档"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(DocumentModel)
                .where(DocumentModel.department == department)
                .order_by(DocumentModel.created_at.desc())
            )
            rows = result.scalars().all()
            return [
                {
                    "doc_id": r.doc_id,
                    "filename": r.filename,
                    "title": r.title,
                    "file_type": r.file_type,
                    "chunk_strategy": r.chunk_strategy,
                    "chunk_count": r.chunk_count,
                    "department": r.department,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    async def get_user_permission_details(self, user_id: str) -> List[Dict]:
        """获取用户权限详情列表"""
        async with self.async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(UserDocPermissionModel)
                .where(UserDocPermissionModel.user_id == user_id)
                .order_by(UserDocPermissionModel.created_at.desc())
            )
            rows = result.scalars().all()
            return [
                {
                    "user_id": r.user_id,
                    "doc_id": r.doc_id,
                    "granted_by": r.granted_by,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    async def close(self):
        await self.engine.dispose()


# 全局单例
_metadata_store: MetadataStore | None = None


async def get_metadata_store() -> MetadataStore:
    global _metadata_store
    if _metadata_store is None:
        _metadata_store = MetadataStore()
        await _metadata_store.init_db()
    return _metadata_store
