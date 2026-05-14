import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 600000,
})

// 请求拦截器：自动注入 JWT Token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：处理 401 未授权
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user_info')
      if (window.location.pathname !== '/login') {
        ElMessage.error('登录已过期，请重新登录')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// 健康检查
export const checkHealth = () => api.get('/health')

// ========== 鉴权 ==========

export const login = (data) => api.post('/auth/login', data)

export const register = (data) => api.post('/auth/register', data)

export const getMe = () => api.get('/auth/me')

// ========== 用户管理（管理员） ==========

export const listUsers = () => api.get('/users')

// ========== 权限管理 ==========

export const listMyPermissions = () => api.get('/permissions/me')

export const grantPermission = (data) => api.post('/permissions', data)

export const revokePermission = (userId, docId) =>
  api.delete('/permissions', { params: { user_id: userId, doc_id: docId } })

export const getUserPermissions = (userId) =>
  api.get(`/permissions/${userId}`)

export const setUserDepartment = (userId, department) =>
  api.post(`/users/${userId}/department`, null, { params: { department } })

export const listDepartments = () =>
  api.get('/departments')

export const setPublicDocument = (docId) =>
  api.post(`/documents/${docId}/public`)

export const revokePublicDocument = (docId) =>
  api.delete(`/documents/${docId}/public`)

export const listPublicDocuments = () =>
  api.get('/documents/public')

// ========== 文档上传 ==========

export const uploadDocument = (file, title, chunkStrategy, strategyParams = null, department = null) => {
  const formData = new FormData()
  formData.append('file', file)
  if (title) formData.append('title', title)
  formData.append('chunk_strategy', chunkStrategy || 'auto')
  if (strategyParams) {
    formData.append('strategy_params', JSON.stringify(strategyParams))
  }
  if (department) {
    formData.append('department', department)
  }
  return api.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 分块预览
export const previewChunks = (file, strategy, params = {}) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('strategy', strategy || 'auto')
  if (params.chunk_size) formData.append('chunk_size', params.chunk_size)
  if (params.chunk_overlap) formData.append('chunk_overlap', params.chunk_overlap)
  if (params.parent_chunk_size) formData.append('parent_chunk_size', params.parent_chunk_size)
  if (params.child_chunk_size) formData.append('child_chunk_size', params.child_chunk_size)
  if (params.heading_levels) formData.append('heading_levels', JSON.stringify(params.heading_levels))
  if (params.preserve_tables !== undefined) formData.append('preserve_tables', params.preserve_tables)
  if (Object.keys(params).length > 0) {
    formData.append('strategy_params', JSON.stringify(params))
  }
  return api.post('/chunk-preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 文档列表
export const listDocuments = () => api.get('/documents')

// 删除文档
export const deleteDocument = (docId) => api.delete(`/documents/${docId}`)

// 非流式问答
export const query = (data) => api.post('/query', data)

// 流式问答 (SSE)
export const queryStream = (data) => {
  return new EventSource('/api/query/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

// 检索调试
export const retrieve = (data) => api.post('/retrieve', data)

// ========== 会话管理 ==========

export const createConversation = (title = '新会话') =>
  api.post('/conversations', { title })

export const listConversations = () =>
  api.get('/conversations')

export const getConversation = (conversationId) =>
  api.get(`/conversations/${conversationId}`)

export const updateConversation = (conversationId, title) =>
  api.put(`/conversations/${conversationId}`, { title })

export const deleteConversation = (conversationId) =>
  api.delete(`/conversations/${conversationId}`)
