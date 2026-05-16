<template>
  <div class="app-root">
    <!-- 未登录：只渲染路由视图 -->
    <template v-if="!isLoggedIn">
      <router-view />
    </template>

    <!-- 已登录：完整布局 -->
    <el-container v-else class="app-container">
      <el-aside width="240px" class="sidebar">
        <div class="logo">
          <div class="logo-icon">
            <el-icon size="26"><Collection /></el-icon>
          </div>
          <div class="logo-text">
            <div class="logo-title">企业 RAG Agent</div>
            <div class="logo-sub">智能知识库系统</div>
          </div>
        </div>

        <div class="nav-section">
          <div class="nav-label">功能导航</div>
          <div
            v-for="item in navItems"
            :key="item.path"
            :class="['nav-item', { active: $route.path === item.path }]"
            @click="$router.push(item.path)"
          >
            <el-icon size="18"><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </div>
        </div>

        <div class="sidebar-footer">
          <!-- 用户信息 -->
          <div class="user-card">
            <el-icon size="16"><UserFilled /></el-icon>
            <div class="user-info">
              <div class="user-name">{{ userInfo.username }}</div>
              <div class="user-tags">
                <el-tag size="small" :type="userInfo.role === 'admin' ? 'danger' : userInfo.role === 'staff' ? 'warning' : 'info'">
                  {{ userInfo.role === 'admin' ? '管理员' : userInfo.role === 'staff' ? '员工' : '普通用户' }}
                </el-tag>
                <el-tag v-if="userInfo.department" size="small" type="info">
                  {{ userInfo.department }}
                </el-tag>
              </div>
            </div>
            <el-icon size="14" class="logout-icon" @click="handleLogout"><SwitchButton /></el-icon>
          </div>
          <!-- 健康状态 -->
          <div class="status-card">
            <div class="status-dot" :class="healthStatus"></div>
            <div class="status-info">
              <div class="status-text">{{ healthText }}</div>
              <div class="status-detail">{{ healthDetail }}</div>
            </div>
          </div>
        </div>
      </el-aside>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { checkHealth, listMyPermissions } from './api/api'

const router = useRouter()

const isLoggedIn = ref(!!localStorage.getItem('access_token'))
const userInfo = ref({})
const hasDocPermission = ref(false)

try {
  userInfo.value = JSON.parse(localStorage.getItem('user_info') || '{}')
} catch {
  userInfo.value = {}
}

const updateAuthState = () => {
  isLoggedIn.value = !!localStorage.getItem('access_token')
  try {
    userInfo.value = JSON.parse(localStorage.getItem('user_info') || '{}')
  } catch {
    userInfo.value = {}
  }
  // 登录状态变化时重新检查权限
  if (isLoggedIn.value) {
    fetchPermissions()
  } else {
    hasDocPermission.value = false
  }
}

window.addEventListener('auth-change', updateAuthState)

const fetchPermissions = async () => {
  try {
    const { data } = await listMyPermissions()
    hasDocPermission.value = (data.data || []).length > 0
  } catch {
    hasDocPermission.value = false
  }
}

const baseNavItems = [
  { path: '/query', label: '智能问答', icon: 'ChatDotRound' },
]

const navItems = computed(() => {
  const items = [...baseNavItems]
  const role = userInfo.value.role
  // admin 和 staff 显示上传/管理
  if (role === 'admin' || role === 'staff') {
    items.push({ path: '/upload', label: '文档上传', icon: 'Upload' })
    items.push({ path: '/documents', label: '文档管理', icon: 'Document' })
  }
  if (role === 'admin') {
    items.push({ path: '/permissions', label: '权限管理', icon: 'Lock' })
  }
  return items
})

const handleLogout = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('user_info')
  localStorage.removeItem('rag_settings')
  updateAuthState()
  ElMessage.success('已退出登录')
  router.push('/login')
}

// 健康检查
const healthStatus = ref('checking')
const healthText = ref('检查中')
const healthDetail = ref('...')

const check = async () => {
  try {
    const { data } = await checkHealth()
    if (data.data?.status === 'healthy') {
      healthStatus.value = 'healthy'
      healthText.value = '服务正常'
      healthDetail.value = 'Milvus + Ollama'
    } else {
      healthStatus.value = 'degraded'
      healthText.value = '服务降级'
      healthDetail.value = '部分功能受限'
    }
  } catch {
    healthStatus.value = 'error'
    healthText.value = '连接异常'
    healthDetail.value = '请检查后端服务'
  }
}

onMounted(() => {
  check()
  if (isLoggedIn.value) {
    fetchPermissions()
  }
  setInterval(check, 30000)
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; }

.app-root { height: 100vh; }

.app-container { height: 100vh; }

.sidebar {
  background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
  display: flex;
  flex-direction: column;
  color: #fff;
  box-shadow: 4px 0 20px rgba(0,0,0,0.15);
}

.logo {
  padding: 24px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.logo-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.logo-title {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.logo-sub {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 2px;
}

.nav-section {
  flex: 1;
  padding: 16px 12px;
  overflow-y: auto;
}

.nav-label {
  font-size: 11px;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 1px;
  padding: 0 12px;
  margin-bottom: 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  margin-bottom: 4px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: #cbd5e1;
  font-size: 14px;
}

.nav-item:hover {
  background: rgba(255,255,255,0.05);
  color: #fff;
}

.nav-item.active {
  background: linear-gradient(90deg, rgba(59,130,246,0.2) 0%, rgba(139,92,246,0.1) 100%);
  color: #fff;
  border-left: 3px solid #3b82f6;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid rgba(255,255,255,0.06);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.user-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: rgba(255,255,255,0.04);
  border-radius: 10px;
}

.user-info {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  margin-bottom: 2px;
}

.logout-icon {
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s ease;
}

.logout-icon:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.status-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: rgba(255,255,255,0.04);
  border-radius: 10px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.healthy { background: #22c55e; box-shadow: 0 0 8px rgba(34,197,94,0.5); }
.status-dot.degraded { background: #f59e0b; box-shadow: 0 0 8px rgba(245,158,11,0.5); }
.status-dot.error { background: #ef4444; box-shadow: 0 0 8px rgba(239,68,68,0.5); }
.status-dot.checking { background: #94a3b8; animation: pulse 1.5s infinite; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.status-text {
  font-size: 12px;
  font-weight: 600;
  color: #fff;
}

.status-detail {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}

.main-content {
  background: #f8fafc;
  padding: 0;
  overflow-y: auto;
}
</style>
