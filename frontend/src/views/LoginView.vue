<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <div class="brand-logo">
          <el-icon size="32" color="#fff"><Collection /></el-icon>
        </div>
        <h1>企业 RAG Agent</h1>
        <p>智能知识库系统</p>
      </div>

      <div class="login-tabs">
        <div
          :class="['tab-item', { active: mode === 'login' }]"
          @click="switchMode('login')"
        >登录</div>
        <div
          :class="['tab-item', { active: mode === 'register' }]"
          @click="switchMode('register')"
        >注册</div>
      </div>

      <div class="login-form">
        <div class="form-group">
          <label>用户名</label>
          <input
            v-model="form.username"
            type="text"
            placeholder="请输入用户名"
            @keydown.enter="handleSubmit"
          />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            @keydown.enter="handleSubmit"
          />
        </div>
        <div v-if="mode === 'register'" class="form-group">
          <label>确认密码</label>
          <input
            v-model="form.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            @keydown.enter="handleSubmit"
          />
        </div>

        <button
          class="submit-btn"
          :disabled="loading"
          @click="handleSubmit"
        >
          <span v-if="loading">处理中...</span>
          <span v-else>{{ mode === 'login' ? '登录' : '注册' }}</span>
        </button>

        <div class="login-hint">
          <el-icon size="12"><InfoFilled /></el-icon>
          <span>默认管理员账号：admin / admin</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login, register } from '../api/api'

const router = useRouter()
const mode = ref('login')
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
})

const switchMode = (newMode) => {
  mode.value = newMode
  form.username = ''
  form.password = ''
  form.confirmPassword = ''
}

const handleSubmit = async () => {
  if (!form.username.trim() || !form.password.trim()) {
    ElMessage.warning('请填写用户名和密码')
    return
  }

  if (mode.value === 'register') {
    if (form.password !== form.confirmPassword) {
      ElMessage.warning('两次输入的密码不一致')
      return
    }
    if (form.password.length < 6) {
      ElMessage.warning('密码长度至少6位')
      return
    }
  }

  loading.value = true
  try {
    if (mode.value === 'login') {
      const { data } = await login({
        username: form.username.trim(),
        password: form.password,
      })
      if (data.code === 200) {
        const tokenData = data.data
        localStorage.setItem('access_token', tokenData.access_token)
        localStorage.setItem('user_info', JSON.stringify(tokenData.user))
        window.dispatchEvent(new Event('auth-change'))
        ElMessage.success('登录成功')
        router.push('/query')
      } else {
        ElMessage.error(data.message || '登录失败')
      }
    } else {
      const { data } = await register({
        username: form.username.trim(),
        password: form.password,
      })
      if (data.code === 200) {
        ElMessage.success('注册成功，请登录')
        mode.value = 'login'
        form.password = ''
        form.confirmPassword = ''
      } else {
        ElMessage.error(data.message || '注册失败')
      }
    }
  } catch (err) {
    const msg = err.response?.data?.detail || err.response?.data?.message || err.message || '请求失败'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
}

.login-card {
  width: 400px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 20px;
  padding: 40px;
  box-shadow: 0 25px 50px rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(20px);
}

.login-brand {
  text-align: center;
  margin-bottom: 32px;
}

.brand-logo {
  width: 64px;
  height: 64px;
  border-radius: 16px;
  background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.3);
}

.login-brand h1 {
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 4px;
}

.login-brand p {
  font-size: 13px;
  color: #94a3b8;
}

.login-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  background: #f1f5f9;
  border-radius: 12px;
  padding: 4px;
}

.tab-item {
  flex: 1;
  text-align: center;
  padding: 10px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab-item.active {
  background: #fff;
  color: #3b82f6;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #475569;
  margin-bottom: 6px;
}

.form-group input {
  width: 100%;
  padding: 12px 14px;
  border: 1.5px solid #e2e8f0;
  border-radius: 12px;
  font-size: 14px;
  color: #1e293b;
  background: #fff;
  transition: all 0.2s ease;
  outline: none;
}

.form-group input:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-group input::placeholder {
  color: #cbd5e1;
}

.submit-btn {
  width: 100%;
  padding: 14px;
  margin-top: 8px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s ease;
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.3);
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.login-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 16px;
  font-size: 12px;
  color: #94a3b8;
}
</style>
