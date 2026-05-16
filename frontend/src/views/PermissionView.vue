<template>
  <div class="permission-page">
    <div class="permission-header">
      <h1>权限管理</h1>
      <p class="sub">管理员可设置用户部门和公共查询权限</p>
    </div>

    <div class="permission-content">
      <!-- 左侧：用户管理 -->
      <div class="user-panel">
        <div class="panel-title">用户管理</div>
        <div class="user-list">
          <div
            v-for="user in users"
            :key="user.user_id"
            :class="['user-item', { active: selectedUserId === user.user_id }]"
            @click="selectUser(user.user_id)"
          >
            <el-icon size="16"><User /></el-icon>
            <div class="user-meta">
              <span class="user-name">{{ user.username }}</span>
              <div class="user-tags">
                <el-tag size="small" :type="roleTagType(user.role)">
                  {{ roleLabel(user.role) }}
                </el-tag>
                <el-tag v-if="user.department" size="small" type="info">
                  {{ user.department }}
                </el-tag>
              </div>
            </div>
          </div>
          <div v-if="users.length === 0" class="empty-tip">暂无用户</div>
        </div>
      </div>

      <!-- 右侧：设置面板 -->
      <div class="right-panel">
        <!-- 用户部门设置 -->
        <div class="section" v-if="selectedUser">
          <div class="section-title">
            <el-icon><OfficeBuilding /></el-icon>
            <span>部门设置 — {{ selectedUser.username }}</span>
          </div>
          <div class="section-body">
            <p class="hint">为员工指定部门后，该员工可上传和管理该部门的文档。清空部门则降为普通用户。</p>
            <div class="dept-form">
              <el-input
                v-model="deptInput"
                placeholder="输入部门名称，如：技术部、市场部"
                clearable
                style="width: 280px"
              />
              <el-button type="primary" :loading="savingDept" @click="saveDepartment">
                保存
              </el-button>
            </div>
          </div>
        </div>

        <!-- 公共文档权限 -->
        <div class="section">
          <div class="section-title">
            <el-icon><View /></el-icon>
            <span>公共查询权限</span>
          </div>
          <div class="section-body">
            <p class="hint">勾选后，所有用户（包括普通用户）均可查询该文档。未勾选的文档仅管理员和对应部门员工可见。</p>
            <div class="doc-list" v-loading="loadingDocs">
              <div v-if="documents.length === 0" class="empty-tip">暂无文档</div>
              <div
                v-for="doc in documents"
                :key="doc.doc_id"
                class="doc-item"
              >
                <el-checkbox
                  v-model="publicMap[doc.doc_id]"
                  size="large"
                >
                  <span class="doc-name">{{ doc.title || doc.filename }}</span>
                  <el-tag v-if="doc.department" size="small" type="info" class="doc-dept">
                    {{ doc.department }}
                  </el-tag>
                </el-checkbox>
              </div>
            </div>
            <div class="section-footer">
              <el-button type="primary" :loading="savingPublic" @click="savePublicPermissions">
                保存公共权限
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { User, OfficeBuilding, View } from '@element-plus/icons-vue'
import {
  listUsers,
  listDocuments,
  setUserDepartment,
  listPublicDocuments,
  setPublicDocument,
  revokePublicDocument,
} from '../api/api'

const users = ref([])
const documents = ref([])
const selectedUserId = ref('')
const publicMap = reactive({})
const publicDocIds = ref(new Set())
const savingDept = ref(false)
const savingPublic = ref(false)
const loadingDocs = ref(false)
const deptInput = ref('')

const selectedUser = computed(() =>
  users.value.find((u) => u.user_id === selectedUserId.value)
)

const roleLabel = (role) => {
  const map = { admin: '管理员', staff: '员工', user: '普通用户' }
  return map[role] || role
}

const roleTagType = (role) => {
  if (role === 'admin') return 'danger'
  if (role === 'staff') return 'warning'
  return ''
}

const loadUsers = async () => {
  try {
    const { data } = await listUsers()
    if (data.code === 200) {
      users.value = data.data || []
    }
  } catch {
    ElMessage.error('加载用户列表失败')
  }
}

const loadDocuments = async () => {
  loadingDocs.value = true
  try {
    const { data } = await listDocuments()
    if (data.code === 200) {
      documents.value = data.data || []
    }
  } catch {
    ElMessage.error('加载文档列表失败')
  } finally {
    loadingDocs.value = false
  }
}

const loadPublicPermissions = async () => {
  try {
    const { data } = await listPublicDocuments()
    if (data.code === 200) {
      const ids = new Set((data.data || []).map((d) => d.doc_id))
      publicDocIds.value = ids
      Object.keys(publicMap).forEach((k) => delete publicMap[k])
      documents.value.forEach((doc) => {
        publicMap[doc.doc_id] = ids.has(doc.doc_id)
      })
    }
  } catch {
    ElMessage.error('加载公共权限失败')
  }
}

const selectUser = (userId) => {
  selectedUserId.value = userId
  const user = users.value.find((u) => u.user_id === userId)
  deptInput.value = user?.department || ''
}

const saveDepartment = async () => {
  if (!selectedUserId.value) return
  savingDept.value = true
  try {
    const dept = deptInput.value.trim() || null
    const { data } = await setUserDepartment(selectedUserId.value, dept)
    if (data.code === 200) {
      ElMessage.success(dept ? `已设置部门为: ${dept}` : '已清空部门')
      await loadUsers()
      // 更新选中用户
      const user = users.value.find((u) => u.user_id === selectedUserId.value)
      if (user) deptInput.value = user.department || ''
    } else {
      ElMessage.error(data.message || '设置失败')
    }
  } catch {
    ElMessage.error('设置部门失败')
  } finally {
    savingDept.value = false
  }
}

const savePublicPermissions = async () => {
  savingPublic.value = true
  try {
    const currentIds = new Set(
      Object.entries(publicMap)
        .filter(([, v]) => v)
        .map(([k]) => k)
    )
    const originalIds = publicDocIds.value

    const toAdd = [...currentIds].filter((id) => !originalIds.has(id))
    const toRemove = [...originalIds].filter((id) => !currentIds.has(id))

    for (const docId of toAdd) {
      await setPublicDocument(docId)
    }
    for (const docId of toRemove) {
      await revokePublicDocument(docId)
    }

    ElMessage.success('公共权限保存成功')
    await loadPublicPermissions()
  } catch {
    ElMessage.error('保存公共权限失败')
  } finally {
    savingPublic.value = false
  }
}

onMounted(() => {
  loadUsers()
  loadDocuments().then(loadPublicPermissions)
})
</script>

<style scoped>
.permission-page {
  padding: 32px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.permission-header {
  margin-bottom: 24px;
}

.permission-header h1 {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
}

.sub {
  font-size: 13px;
  color: #94a3b8;
  margin-top: 4px;
}

.permission-content {
  flex: 1;
  display: flex;
  gap: 20px;
  overflow: hidden;
}

.user-panel {
  width: 300px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow: hidden;
}

.section {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-title,
.section-title {
  padding: 16px 20px;
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-body {
  padding: 20px;
  flex: 1;
  overflow-y: auto;
}

.section-footer {
  padding: 12px 20px;
  border-top: 1px solid #f1f5f9;
  display: flex;
  justify-content: flex-end;
}

.hint {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 16px;
  line-height: 1.5;
}

.dept-form {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.user-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: #475569;
}

.user-item:hover {
  background: #f8fafc;
}

.user-item.active {
  background: linear-gradient(90deg, #eff6ff, #e0e7ff);
  color: #1e40af;
}

.user-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
}

.user-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.doc-list {
  max-height: 320px;
  overflow-y: auto;
}

.doc-item {
  display: flex;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #f8fafc;
}

.doc-name {
  font-size: 13px;
  color: #334155;
}

.doc-dept {
  margin-left: 8px;
}

.empty-tip {
  padding: 40px;
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
}
</style>
