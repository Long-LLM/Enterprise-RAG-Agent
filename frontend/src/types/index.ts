/**
 * 前端类型定义
 */

// ========== 通用 ==========

export interface BaseResponse<T = unknown> {
  code: number
  message: string
  data: T
}

export interface UserInfo {
  user_id: string
  username: string
  role: 'admin' | 'staff' | 'user'
  department?: string
  created_at?: number
}

// ========== 文档 ==========

export interface DocumentInfo {
  doc_id: string
  filename: string
  title?: string
  chunk_count: number
  file_type?: string
  file_size?: number
  department?: string
  created_at?: string
  status?: string
}

export interface ChunkPreviewItem {
  index: number
  content: string
  char_count: number
  section_title?: string
  heading_level?: number
  chunk_type: string
  parent_id?: string
  metadata?: Record<string, unknown>
}

export interface ChunkPreviewStats {
  avg_length: number
  max_length: number
  min_length: number
  total_chunks: number
  total_chars: number
  preview_truncated: boolean
}

export interface UploadResult {
  doc_id: string
  filename: string
  chunk_count: number
  status: string
}

export interface AsyncUploadResult {
  task_id: string
  doc_id: string
  filename: string
  status: string
}

export interface TaskStatus {
  task_id: string
  status: 'PENDING' | 'STARTED' | 'PROGRESS' | 'SUCCESS' | 'FAILURE' | 'RETRY'
  result?: Record<string, unknown>
  progress?: number
  stage?: string
  message?: string
  doc_id?: string
}

// ========== 问答 ==========

export interface SourceReference {
  doc_id: string
  title?: string
  filename?: string
  content: string
  score: number
  page_number?: number
  chunk_index?: number
  parent_content?: string
  chunk_type?: string
}

export interface QueryRequest {
  question: string
  top_k?: number
  use_rerank?: boolean
  stream?: boolean
  conversation_id?: string
  filters?: Record<string, unknown>
}

export interface QueryResult {
  answer: string
  sources: SourceReference[]
  model: string
  processing_time_ms?: number
}

// ========== 会话 ==========

export interface ConversationInfo {
  conversation_id: string
  title: string
  created_at?: number
  updated_at?: number
}

export interface MessageInfo {
  message_id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceReference[]
  model?: string
  processing_time_ms?: number
  created_at?: number
}

// ========== 权限 ==========

export interface PermissionInfo {
  user_id: string
  doc_id: string
  granted_by?: string
  created_at?: number
}
