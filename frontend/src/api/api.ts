import axios from 'axios'
import { ElMessage } from 'element-plus'
import type {
  BaseResponse,
  ConversationInfo,
  DocumentInfo,
  MessageInfo,
  QueryRequest,
  QueryResult,
  TaskStatus,
  UploadResult,
  UserInfo,
} from '../types'

// 本地补充类型（未在 types/index.ts 中定义）
interface AsyncUploadResult {
  task_id: string
  doc_id: string
  filename: string
  status: string
}

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

// ========== 健康检查 ==========

export const checkHealth = () =>
  api.get<BaseResponse>('/health')

// ========== 鉴权 ==========

export const login = (data: { username: string; password: string }) =>
  api.post<BaseResponse<{ access_token: string; token_type: string; user: UserInfo }>>('/auth/login', data)

export const register = (data: { username: string; password: string }) =>
  api.post<BaseResponse<UserInfo>>('/auth/register', data)

export const getMe = () =>
  api.get<BaseResponse<UserInfo>>('/auth/me')

// ========== 用户管理（管理员） ==========

export const listUsers = () =>
  api.get<BaseResponse<UserInfo[]>>('/users')

// ========== 权限管理 ==========

export const listMyPermissions = () =>
  api.get<BaseResponse<DocumentInfo[]>>('/permissions/me')

export const grantPermission = (data: { user_id: string; doc_id: string }) =>
  api.post<BaseResponse>('/permissions', data)

export const revokePermission = (userId: string, docId: string) =>
  api.delete<BaseResponse>('/permissions', { params: { user_id: userId, doc_id: docId } })

export const getUserPermissions = (userId: string) =>
  api.get<BaseResponse<unknown[]>>(`/permissions/${userId}`)

export const setUserDepartment = (userId: string, department: string) =>
  api.post<BaseResponse>(`/users/${userId}/department`, null, { params: { department } })

export const listDepartments = () =>
  api.get<BaseResponse<string[]>>('/departments')

export const setPublicDocument = (docId: string) =>
  api.post<BaseResponse>(`/documents/${docId}/public`)

export const revokePublicDocument = (docId: string) =>
  api.delete<BaseResponse>(`/documents/${docId}/public`)

export const listPublicDocuments = () =>
  api.get<BaseResponse<DocumentInfo[]>>('/documents/public')

// ========== 文档上传 ==========

export const uploadDocument = (
  file: File,
  title: string | null,
  chunkStrategy: string,
  strategyParams: Record<string, unknown> | null = null,
  department: string | null = null
) => {
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
  return api.post<BaseResponse<UploadResult>>('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 异步上传（大文件推荐）
export const uploadDocumentAsync = (
  file: File,
  title: string | null,
  chunkStrategy: string,
  strategyParams: Record<string, unknown> | null = null,
  department: string | null = null
) => {
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
  return api.post<BaseResponse<AsyncUploadResult>>('/upload/async', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 查询异步任务状态
export const getTaskStatus = (taskId: string) =>
  api.get<BaseResponse<TaskStatus>>(`/tasks/${taskId}`)

// 分块预览
export const previewChunks = (file: File, strategy: string, params: Record<string, unknown> = {}) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('strategy', strategy || 'auto')
  if (params.chunk_size) formData.append('chunk_size', String(params.chunk_size))
  if (params.chunk_overlap) formData.append('chunk_overlap', String(params.chunk_overlap))
  if (params.parent_chunk_size) formData.append('parent_chunk_size', String(params.parent_chunk_size))
  if (params.child_chunk_size) formData.append('child_chunk_size', String(params.child_chunk_size))
  if (params.heading_levels) formData.append('heading_levels', JSON.stringify(params.heading_levels))
  if (params.preserve_tables !== undefined) formData.append('preserve_tables', String(params.preserve_tables))
  if (Object.keys(params).length > 0) {
    formData.append('strategy_params', JSON.stringify(params))
  }
  return api.post<BaseResponse<{
    strategy: string
    total_chars: number
    chunk_count: number
    chunks: ChunkPreviewItem[]
    stats: ChunkPreviewStats
  }>>('/chunk-preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 文档列表
export const listDocuments = () =>
  api.get<BaseResponse<DocumentInfo[]>>('/documents')

// 删除文档
export const deleteDocument = (docId: string) =>
  api.delete<BaseResponse>(`/documents/${docId}`)

// ========== 问答 ==========

// 非流式问答
export const query = (data: QueryRequest) =>
  api.post<BaseResponse<QueryResult>>('/query', data)

// 流式问答 (SSE)
export const queryStream = (data: QueryRequest): EventSource => {
  const options: any = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }
  // @ts-ignore EventSource 标准不支持 POST，项目中需配合 polyfill 使用
  return new EventSource('/api/query/stream', options)
}

// 检索调试
export const retrieve = (data: { query: string; top_k?: number; use_rerank?: boolean }) =>
  api.post<BaseResponse>('/retrieve', data)

// ========== 会话管理 ==========

export const createConversation = (title = '新会话') =>
  api.post<BaseResponse<ConversationInfo>>('/conversations', { title })

export const listConversations = () =>
  api.get<BaseResponse<ConversationInfo[]>>('/conversations')

export const getConversation = (conversationId: string) =>
  api.get<BaseResponse<ConversationInfo & { messages: MessageInfo[] }>>(`/conversations/${conversationId}`)

export const updateConversation = (conversationId: string, title: string) =>
  api.put<BaseResponse>(`/conversations/${conversationId}`, { title })

export const deleteConversation = (conversationId: string) =>
  api.delete<BaseResponse>(`/conversations/${conversationId}`)

type Permission = unknown
type ChunkPreviewItem = unknown
type ChunkPreviewStats = unknown
