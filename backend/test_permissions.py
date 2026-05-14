"""
权限管理模块测试脚本
直接测试 metadata_store 的权限逻辑，无需启动 HTTP 服务器
"""
import asyncio
import time
from app.core.metadata_store import get_metadata_store, DocumentModel
from app.core.security import get_password_hash


async def setup_test_data():
    """创建测试用户和文档"""
    store = await get_metadata_store()

    # 创建测试用户
    test_users = [
        ("test_admin", "admin", "管理部"),
        ("staff_market", "staff", "市场部"),
        ("staff_finance", "staff", "财务部"),
        ("normal_user", "user", None),
    ]

    created_users = []
    for username, role, dept in test_users:
        user = await store.get_user_by_username(username)
        if not user:
            user_id = f"test_{username}"
            await store.create_user(
                user_id=user_id,
                username=username,
                password_hash=get_password_hash("test123"),
                role=role,
                department=dept,
            )
            user = await store.get_user_by_username(username)
        created_users.append((username, user))
        print(f"  用户: {username}, role={user['role']}, dept={user.get('department')}")

    # 创建测试文档（直接写入 SQLite 元数据库）
    test_docs = [
        ("doc_market_1", "市场部产品手册.pdf", "市场部"),
        ("doc_market_2", "市场部推广方案.docx", "市场部"),
        ("doc_finance_1", "财务部年度报告.pdf", "财务部"),
        ("doc_finance_2", "财务部预算表.xlsx", "财务部"),
        ("doc_public_1", "公司规章制度.txt", None),
    ]

    for doc_id, filename, dept in test_docs:
        doc = await store.get_document(doc_id)
        if not doc:
            async with store.async_session() as session:
                doc = DocumentModel(
                    doc_id=doc_id,
                    filename=filename,
                    title=filename,
                    file_type=filename.split('.')[-1],
                    chunk_strategy="auto",
                    chunk_count=5,
                    department=dept,
                    created_at=int(time.time()),
                    updated_at=int(time.time()),
                )
                session.add(doc)
                await session.commit()
            print(f"  文档: {filename} -> {dept or '无部门'}")

    # 设置公共文档权限
    await store.grant_public_doc_permission("doc_public_1", "test_admin")
    print(f"  设置 doc_public_1 为公共文档")

    return created_users


async def test_department_isolation():
    """测试部门隔离"""
    print("\n【测试1】部门隔离 — list_documents_by_department")
    store = await get_metadata_store()

    market_docs = await store.list_documents_by_department("市场部")
    finance_docs = await store.list_documents_by_department("财务部")

    print(f"  市场部文档: {[d['filename'] for d in market_docs]}")
    print(f"  财务部文档: {[d['filename'] for d in finance_docs]}")

    assert len(market_docs) == 2, f"市场部应有2个文档，实际有{len(market_docs)}"
    assert len(finance_docs) == 2, f"财务部应有2个文档，实际有{len(finance_docs)}"
    print("  [PASS] 部门隔离正常")


async def get_accessible_docs_for_user(store, user_info: dict):
    """模拟 query.py 中的权限逻辑"""
    role = user_info.get("role", "user")
    if role == "admin":
        docs = await store.list_documents()
        return docs

    public_ids = set(await store.get_public_doc_permissions())
    allowed_doc_ids = public_ids.copy()

    if role == "staff":
        user_dept = user_info.get("department")
        if user_dept:
            dept_docs = await store.list_documents_by_department(user_dept)
            allowed_doc_ids.update(d["doc_id"] for d in dept_docs)

    # 获取所有文档并过滤
    all_docs = await store.list_documents()
    return [d for d in all_docs if d["doc_id"] in allowed_doc_ids]


async def test_role_access():
    """测试不同角色的文档访问权限"""
    print("\n【测试2】角色权限 — 模拟 get_accessible_doc_ids")
    store = await get_metadata_store()

    # Admin
    admin_user = {"user_id": "test_test_admin", "role": "admin", "department": "管理部"}
    admin_docs = await get_accessible_docs_for_user(store, admin_user)
    print(f"  Admin 可访问: {len(admin_docs)} 个文档")

    # 市场部 staff
    market_staff = {"user_id": "test_staff_market", "role": "staff", "department": "市场部"}
    market_docs = await get_accessible_docs_for_user(store, market_staff)
    print(f"  市场部员工可访问: {len(market_docs)} 个 -> {[d['doc_id'] for d in market_docs]}")

    # 财务部 staff
    finance_staff = {"user_id": "test_staff_finance", "role": "staff", "department": "财务部"}
    finance_docs = await get_accessible_docs_for_user(store, finance_staff)
    print(f"  财务部员工可访问: {len(finance_docs)} 个 -> {[d['doc_id'] for d in finance_docs]}")

    # 普通 user
    normal_user = {"user_id": "test_normal_user", "role": "user", "department": None}
    user_docs = await get_accessible_docs_for_user(store, normal_user)
    print(f"  普通用户可访问: {len(user_docs)} 个 -> {[d['doc_id'] for d in user_docs]}")

    # 验证
    assert len(admin_docs) == 5, f"Admin应能访问全部5个文档，实际{len(admin_docs)}"
    assert len(market_docs) == 3, f"市场部员工应能访问3个（2个部门+1个公共），实际{len(market_docs)}"
    assert len(finance_docs) == 3, f"财务部员工应能访问3个（2个部门+1个公共），实际{len(finance_docs)}"
    assert len(user_docs) == 1, f"普通用户应能访问1个公共文档，实际{len(user_docs)}"

    # 验证跨部门不可见
    market_doc_ids = {d['doc_id'] for d in market_docs}
    assert "doc_finance_1" not in market_doc_ids, "市场部员工不应看到财务部文档"
    assert "doc_finance_2" not in market_doc_ids, "市场部员工不应看到财务部文档"
    print("  [PASS] 角色权限隔离正常")


async def test_public_permissions():
    """测试公共文档权限"""
    print("\n【测试3】公共文档权限")
    store = await get_metadata_store()

    public_ids = await store.get_public_doc_permissions()
    print(f"  当前公共文档: {public_ids}")
    assert "doc_public_1" in public_ids, "doc_public_1 应被设为公共文档"
    print("  [PASS] 公共权限正常")


async def test_list_departments():
    """测试部门列表"""
    print("\n【测试4】部门列表")
    store = await get_metadata_store()

    depts = await store.list_departments()
    print(f"  所有部门: {depts}")
    assert "市场部" in depts, "应包含市场部"
    assert "财务部" in depts, "应包含财务部"
    print("  [PASS] 部门列表正常")


async def test_user_department_update():
    """测试用户部门更新"""
    print("\n【测试5】用户部门更新")
    store = await get_metadata_store()

    # 给普通用户分配部门
    await store.update_user_department("test_normal_user", "市场部")
    user = await store.get_user_by_id("test_normal_user")
    assert user["department"] == "市场部", f"部门应更新为市场部，实际为{user.get('department')}"
    print(f"  普通用户部门更新为: {user['department']}")

    # 清空部门
    await store.update_user_department("test_normal_user", None)
    user = await store.get_user_by_id("test_normal_user")
    assert user.get("department") is None, "部门应被清空"
    print("  [PASS] 部门更新/清空正常")


async def main():
    print("=" * 60)
    print("权限管理模块测试")
    print("=" * 60)

    print("\n【初始化】创建测试数据...")
    await setup_test_data()

    await test_department_isolation()
    await test_role_access()
    await test_public_permissions()
    await test_list_departments()
    await test_user_department_update()

    print("\n" + "=" * 60)
    print("[PASS] 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
