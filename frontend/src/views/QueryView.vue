<template>
  <div class="query-page">
    <!-- 左侧会话列表 -->
    <div class="session-sidebar">
      <div class="session-header">
        <button class="new-session-btn" @click="createNewSession">
          <el-icon size="16"><Plus /></el-icon>
          <span>新会话</span>
        </button>
      </div>
      <div class="session-list" ref="sessionListRef">
        <div
          v-for="session in conversations"
          :key="session.conversation_id"
          :class="['session-item', { active: currentConversationId === session.conversation_id }]"
          @click="switchConversation(session.conversation_id)"
        >
          <div class="session-info">
            <el-icon size="14"><ChatRound /></el-icon>
            <span class="session-title">{{ session.title }}</span>
          </div>
          <el-icon
            size="14"
            class="session-delete"
            @click.stop="removeConversation(session.conversation_id)"
          >
            <Delete />
          </el-icon>
        </div>
        <div v-if="conversations.length === 0" class="session-empty">
          暂无会话，点击上方新建
        </div>
      </div>
    </div>

    <!-- 右侧聊天区域 -->
    <div class="chat-wrapper">
      <!-- 顶部标题 -->
      <div class="query-header">
        <div class="header-content">
          <h1>智能问答</h1>
          <p class="query-sub">基于企业知识库的智能检索问答，支持混合检索与引用溯源</p>
        </div>
      </div>

      <!-- 聊天区域 -->
      <div class="chat-messages" ref="messagesRef">
        <!-- 空状态 -->
        <div v-if="messages.length === 0" class="empty-chat">
          <div class="empty-brand">
            <div class="empty-logo">
              <el-icon size="40" color="#fff"><ChatDotRound /></el-icon>
            </div>
            <h2>有什么可以帮您？</h2>
            <p class="empty-desc">基于企业私有知识库，为您提供精准、可溯源的智能问答</p>
          </div>
          <div class="suggestion-hint">
            <p>在下方输入框中提问，系统将基于知识库为您检索答案</p>
          </div>
        </div>

        <!-- 消息列表 -->
        <template v-else>
          <div
            v-for="(msg, idx) in messages"
            :key="msg.id || idx"
            :class="['msg-row', msg.role]"
          >
            <!-- AI 消息：头像在左 -->
            <template v-if="msg.role === 'assistant'">
              <div class="msg-avatar ai">
                <div class="avatar-glow">
                  <el-icon size="18" color="#fff"><CPU /></el-icon>
                </div>
              </div>
              <div class="msg-body">
                <div class="msg-bubble ai-bubble">
                  <div v-if="msg.content" class="ai-text" v-html="renderMarkdown(msg.content)"></div>
                  <div v-else-if="msg.streaming" class="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>

                  <!-- 引用来源 -->
                  <div v-if="msg.sources?.length" class="sources-section">
                    <div
                      class="sources-toggle"
                      :class="{ expanded: msg.showSources }"
                      @click="msg.showSources = !msg.showSources"
                    >
                      <div class="toggle-left">
                        <el-icon size="14"><Document /></el-icon>
                        <span>{{ msg.sources.length }} 条引用来源</span>
                      </div>
                      <el-icon size="14" class="toggle-arrow"><ArrowDown /></el-icon>
                    </div>
                    <transition name="fold">
                      <div v-show="msg.showSources" class="sources-panel">
                        <div
                          v-for="(src, i) in msg.sources"
                          :key="i"
                          class="source-card"
                        >
                          <div class="source-header">
                            <span class="source-badge">{{ i + 1 }}</span>
                            <span class="source-title">{{ src.title || src.filename || '未知文档' }}</span>
                            <span class="source-score">{{ typeof src.score === 'number' ? src.score.toFixed(3) : src.score }}</span>
                          </div>
                          <div class="source-text">{{ src.content }}</div>
                        </div>
                      </div>
                    </transition>
                  </div>

                  <div v-if="msg.time" class="msg-meta">
                    <el-icon size="12"><Timer /></el-icon>
                    <span>{{ msg.time }}ms</span>
                  </div>
                </div>
              </div>
            </template>

            <!-- 用户消息：头像在右 -->
            <template v-else>
              <div class="msg-body user-body">
                <div class="msg-bubble user-bubble">
                  <div class="user-text">{{ msg.content }}</div>
                </div>
              </div>
              <div class="msg-avatar user">
                <div class="avatar-glow user-glow">
                  <el-icon size="18" color="#fff"><UserFilled /></el-icon>
                </div>
              </div>
            </template>
          </div>

          <!-- 加载中 -->
          <div v-if="loading" class="msg-row assistant loading-row">
            <div class="msg-avatar ai">
              <div class="avatar-glow pulse">
                <el-icon size="18" color="#fff"><CPU /></el-icon>
              </div>
            </div>
            <div class="msg-body">
              <div class="msg-bubble ai-bubble loading-bubble">
                <div class="typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 输入区域 -->
      <div class="chat-input-area">
        <div class="input-container">
          <div class="input-box" :class="{ focused: isFocused }">
            <textarea
              v-model="inputText"
              rows="1"
              placeholder="输入您的问题，按 Enter 发送..."
              @keydown.enter.prevent="handleSend"
              @input="autoResize"
              @focus="isFocused = true"
              @blur="isFocused = false"
              ref="textareaRef"
            />
            <div class="input-toolbar">
              <div class="toolbar-options">
                <el-tooltip content="启用重排序（Rerank）提升答案精度" placement="top">
                  <div
                    class="option-pill"
                    :class="{ active: useRerank }"
                    @click="toggleRerank"
                  >
                    <el-icon size="13"><Rank /></el-icon>
                    <span>重排</span>
                    <div class="pill-indicator" :class="{ on: useRerank }"></div>
                  </div>
                </el-tooltip>
                <el-tooltip content="流式输出实时显示" placement="top">
                  <div
                    class="option-pill"
                    :class="{ active: useStream }"
                    @click="toggleStream"
                  >
                    <el-icon size="13"><VideoPlay /></el-icon>
                    <span>流式</span>
                    <div class="pill-indicator" :class="{ on: useStream }"></div>
                  </div>
                </el-tooltip>
              </div>
              <button
                class="send-button"
                :class="{ disabled: !inputText.trim() || loading, ready: inputText.trim() && !loading }"
                :disabled="!inputText.trim() || loading"
                @click="handleSend"
              >
                <el-icon size="18"><Position /></el-icon>
              </button>
            </div>
          </div>
          <div class="input-hint">
            <el-icon size="11"><InfoFilled /></el-icon>
            <span>AI 生成内容仅供参考，重要决策请核实原始文档</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { query, createConversation, listConversations, getConversation, deleteConversation } from '../api/api'
import { marked } from 'marked'

const messages = ref([])
const inputText = ref('')
const loading = ref(false)
const useStream = ref(false)
const useRerank = ref(true)
const messagesRef = ref(null)
const textareaRef = ref(null)
const isFocused = ref(false)

// 会话状态
const conversations = ref([])
const currentConversationId = ref('')
const sessionListRef = ref(null)

// 从 localStorage 读取设置
const loadSettings = () => {
  try {
    const s = JSON.parse(localStorage.getItem('rag_settings') || '{}')
    if (typeof s.useStream === 'boolean') useStream.value = s.useStream
    if (typeof s.useRerank === 'boolean') useRerank.value = s.useRerank
    if (s.currentConversationId) currentConversationId.value = s.currentConversationId
  } catch {}
}

const saveSettings = () => {
  localStorage.setItem('rag_settings', JSON.stringify({
    useStream: useStream.value,
    useRerank: useRerank.value,
    currentConversationId: currentConversationId.value,
  }))
}

const toggleStream = () => {
  useStream.value = !useStream.value
  saveSettings()
}

const toggleRerank = () => {
  useRerank.value = !useRerank.value
  saveSettings()
}



const renderMarkdown = (text) => {
  if (!text) return ''
  return marked.parse(text, { breaks: true })
}

const autoResize = () => {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}

const scrollToBottom = () => {
  nextTick(() => {
    const el = messagesRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// ========== 会话管理 ==========

const loadConversations = async () => {
  try {
    const { data } = await listConversations()
    if (data.code === 200) {
      conversations.value = data.data || []
    }
  } catch (err) {
    console.error('加载会话列表失败', err)
  }
}

const createNewSession = async () => {
  try {
    const { data } = await createConversation('新会话')
    if (data.code === 200) {
      const conv = data.data
      conversations.value.unshift({
        conversation_id: conv.conversation_id,
        title: conv.title,
        created_at: conv.created_at,
        updated_at: conv.updated_at,
      })
      currentConversationId.value = conv.conversation_id
      messages.value = []
      saveSettings()
    }
  } catch (err) {
    ElMessage.error('创建会话失败')
  }
}

const switchConversation = async (conversationId) => {
  if (currentConversationId.value === conversationId) return
  currentConversationId.value = conversationId
  saveSettings()
  messages.value = []
  loading.value = false

  try {
    const { data } = await getConversation(conversationId)
    if (data.code === 200 && data.data.messages) {
      messages.value = data.data.messages.map((m, i) => ({
        id: conversationId + '-' + i,
        role: m.role,
        content: m.content,
        sources: m.sources || [],
        time: m.processing_time_ms,
        showSources: false,
      }))
    }
    scrollToBottom()
  } catch (err) {
    ElMessage.error('加载会话历史失败')
  }
}

const removeConversation = async (conversationId) => {
  try {
    await ElMessageBox.confirm('确定删除该会话吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    const { data } = await deleteConversation(conversationId)
    if (data.code === 200) {
      conversations.value = conversations.value.filter(c => c.conversation_id !== conversationId)
      if (currentConversationId.value === conversationId) {
        currentConversationId.value = ''
        messages.value = []
        saveSettings()
      }
      ElMessage.success('已删除')
    }
  } catch (err) {
    ElMessage.error('删除失败')
  }
}

// ========== 消息发送 ==========

const handleSend = () => {
  const text = inputText.value.trim()
  if (!text || loading.value) return
  sendMessage(text)
}

const sendMessage = async (text) => {
  inputText.value = ''
  if (textareaRef.value) textareaRef.value.style.height = 'auto'

  messages.value.push({ id: Date.now(), role: 'user', content: text })
  loading.value = true
  scrollToBottom()

  // 如果没有当前会话，先自动创建一个
  if (!currentConversationId.value) {
    try {
      const { data } = await createConversation(text.slice(0, 30))
      if (data.code === 200) {
        const conv = data.data
        conversations.value.unshift({
          conversation_id: conv.conversation_id,
          title: conv.title,
          created_at: conv.created_at,
          updated_at: conv.updated_at,
        })
        currentConversationId.value = conv.conversation_id
        saveSettings()
      }
    } catch (err) {
      ElMessage.error('创建会话失败')
      loading.value = false
      return
    }
  }

  const conversationId = currentConversationId.value

  try {
    if (useStream.value) {
      await sendStream(text, conversationId)
    } else {
      const { data } = await query({
        question: text,
        top_k: 5,
        use_rerank: useRerank.value,
        stream: false,
        conversation_id: conversationId,
      })
      messages.value.push({
        id: Date.now(),
        role: 'assistant',
        content: data.data.answer,
        sources: data.data.sources,
        time: data.data.processing_time_ms,
        showSources: false,
      })
    }
  } catch (err) {
    ElMessage.error('请求失败')
    messages.value.push({
      id: Date.now(),
      role: 'assistant',
      content: '抱歉，请求处理失败，请稍后重试。',
      showSources: false,
    })
  } finally {
    loading.value = false
    scrollToBottom()
    // 刷新会话列表，更新标题和时间
    await loadConversations()
  }
}

const sendStream = async (text, conversationId) => {
  const token = localStorage.getItem('access_token')
  const resp = await fetch('/api/query/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      question: text,
      top_k: 5,
      use_rerank: useRerank.value,
      stream: true,
      conversation_id: conversationId,
    }),
  })

  if (!resp.ok) {
    const errText = await resp.text().catch(() => '')
    throw new Error(`HTTP ${resp.status}: ${resp.statusText}${errText ? ' - ' + errText : ''}`)
  }

  // 预先创建 assistant 消息占位，避免中途 push 导致渲染抖动
  const msgIdx = messages.value.length
  messages.value.push({
    id: Date.now(),
    role: 'assistant',
    content: '',
    sources: [],
    showSources: false,
    streaming: true,
  })
  loading.value = false  // 隐藏 loading 行，由消息气泡中的 typing-indicator 替代

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let gotDone = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const payload = JSON.parse(line.slice(6))
          if (payload.type === 'token') {
            messages.value[msgIdx].content += payload.data
          } else if (payload.type === 'sources') {
            messages.value[msgIdx].sources = payload.data
          } else if (payload.type === 'done') {
            messages.value[msgIdx].time = payload.processing_time_ms
            messages.value[msgIdx].streaming = false
            gotDone = true
          }
        } catch {}
      }
    }
    scrollToBottom()
  }

  // 处理最后可能残留的 buffer
  if (buffer.startsWith('data: ')) {
    try {
      const payload = JSON.parse(buffer.slice(6))
      if (payload.type === 'done') {
        messages.value[msgIdx].time = payload.processing_time_ms
        messages.value[msgIdx].streaming = false
        gotDone = true
      }
    } catch {}
  }

  // 流结束但未收到任何 token，给出友好提示
  if (!messages.value[msgIdx].content && !gotDone) {
    messages.value[msgIdx].content = '抱歉，未收到有效的回复内容，请稍后重试或检查服务状态。'
    messages.value[msgIdx].streaming = false
  }
}

onMounted(async () => {
  loadSettings()
  await loadConversations()
  // 如果有当前会话ID，直接加载消息（绕过 switchConversation 的重复检查）
  if (currentConversationId.value) {
    const savedId = currentConversationId.value
    // 确保该会话存在于列表中
    const exists = conversations.value.some(c => c.conversation_id === savedId)
    if (exists) {
      try {
        const { data } = await getConversation(savedId)
        if (data.code === 200 && data.data.messages) {
          messages.value = data.data.messages.map((m, i) => ({
            id: savedId + '-' + i,
            role: m.role,
            content: m.content,
            sources: m.sources || [],
            time: m.processing_time_ms,
            showSources: false,
          }))
          scrollToBottom()
        }
      } catch (err) {
        console.error('恢复会话历史失败', err)
        // 恢复失败时清空当前会话ID，避免一直报错
        currentConversationId.value = ''
        saveSettings()
      }
    } else {
      // 会话已不存在，清空保存的ID
      currentConversationId.value = ''
      saveSettings()
    }
  }
})
</script>

<style scoped>
/* ========== 页面布局 ========== */
.query-page {
  display: flex;
  height: 100vh;
  background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}

/* ========== 左侧会话侧边栏 ========== */
.session-sidebar {
  width: 260px;
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid rgba(226, 232, 240, 0.6);
  display: flex;
  flex-direction: column;
}

.session-header {
  padding: 16px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.6);
}

.new-session-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
  background: #f8fafc;
  color: #475569;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.new-session-btn:hover {
  border-color: #3b82f6;
  color: #3b82f6;
  background: #eff6ff;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: #475569;
  font-size: 13px;
}

.session-item:hover {
  background: #f1f5f9;
}

.session-item.active {
  background: linear-gradient(90deg, #eff6ff, #e0e7ff);
  color: #1e40af;
  font-weight: 500;
}

.session-info {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

.session-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 170px;
}

.session-delete {
  opacity: 0;
  color: #94a3b8;
  transition: all 0.2s ease;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
}

.session-item:hover .session-delete {
  opacity: 1;
}

.session-delete:hover {
  color: #ef4444;
  background: #fee2e2;
}

.session-empty {
  padding: 24px 16px;
  text-align: center;
  color: #94a3b8;
  font-size: 12px;
}

/* ========== 右侧聊天区域 ========== */
.chat-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.query-header {
  padding: 0 32px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(226, 232, 240, 0.6);
  flex-shrink: 0;
  height: 64px;
  display: flex;
  align-items: center;
}

.header-content h1 {
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: -0.3px;
}

.query-sub {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 2px;
  font-weight: 400;
}

/* ========== 聊天消息区 ========== */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
  scroll-behavior: smooth;
}

/* ========== 空状态 ========== */
.empty-chat {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  animation: fadeInUp 0.5s ease;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.empty-brand {
  margin-bottom: 32px;
}

.empty-logo {
  width: 72px;
  height: 72px;
  border-radius: 20px;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.25);
}

.empty-chat h2 {
  font-size: 24px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 8px;
  letter-spacing: -0.5px;
}

.empty-desc {
  font-size: 14px;
  color: #94a3b8;
  max-width: 400px;
  line-height: 1.6;
}

.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  max-width: 640px;
}

.chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 24px;
  font-size: 13px;
  color: #475569;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.chip:hover {
  border-color: #3b82f6;
  color: #3b82f6;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
  transform: translateY(-1px);
}

/* ========== 消息行 ========== */
.msg-row {
  display: flex;
  gap: 12px;
  margin-bottom: 28px;
  animation: msgSlideIn 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes msgSlideIn {
  from { opacity: 0; transform: translateY(12px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.msg-row.user {
  flex-direction: row;
  justify-content: flex-end;
}

.msg-row.assistant {
  flex-direction: row;
  justify-content: flex-start;
}

/* ========== 头像 ========== */
.msg-avatar {
  flex-shrink: 0;
  display: flex;
  align-items: flex-end;
  padding-bottom: 4px;
}

.avatar-glow {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.avatar-glow.user-glow {
  background: linear-gradient(135deg, #64748b, #94a3b8);
  box-shadow: 0 2px 8px rgba(100, 116, 139, 0.25);
}

.avatar-glow.pulse {
  animation: avatarPulse 2s ease-in-out infinite;
}

@keyframes avatarPulse {
  0%, 100% { box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); }
  50% { box-shadow: 0 2px 16px rgba(59, 130, 246, 0.5); }
}

/* ========== 消息体 ========== */
.msg-body {
  max-width: 720px;
  display: flex;
  flex-direction: column;
}

.user-body {
  align-items: flex-end;
}

/* ========== 消息气泡 ========== */
.msg-bubble {
  border-radius: 18px;
  padding: 16px 20px;
  transition: transform 0.2s ease;
}

.user-bubble {
  background: linear-gradient(135deg, #3b82f6, #4f6ef7);
  color: #fff;
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.25), 0 1px 3px rgba(0, 0, 0, 0.08);
  border-bottom-right-radius: 6px;
}

.user-bubble:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.3), 0 2px 4px rgba(0, 0, 0, 0.1);
}

.ai-bubble {
  background: #fff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06), 0 0 1px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(226, 232, 240, 0.6);
  border-bottom-left-radius: 6px;
}

.ai-bubble:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08), 0 0 1px rgba(0, 0, 0, 0.04);
}

/* ========== 文本内容 ========== */
.user-text {
  font-size: 14.5px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  font-weight: 450;
}

.ai-text {
  font-size: 14.5px;
  line-height: 1.75;
  color: #334155;
  word-break: break-word;
}

/* Markdown 样式 */
.ai-text :deep(p) {
  margin: 10px 0;
}

.ai-text :deep(p:first-child) {
  margin-top: 0;
}

.ai-text :deep(p:last-child) {
  margin-bottom: 0;
}

.ai-text :deep(ul), .ai-text :deep(ol) {
  padding-left: 22px;
  margin: 10px 0;
}

.ai-text :deep(li) {
  margin: 6px 0;
}

.ai-text :deep(strong) {
  font-weight: 700;
  color: #1e293b;
}

.ai-text :deep(code) {
  background: #f1f5f9;
  padding: 2px 7px;
  border-radius: 5px;
  font-size: 13px;
  color: #3b82f6;
  font-family: 'SF Mono', Monaco, monospace;
  font-weight: 500;
}

.ai-text :deep(pre) {
  background: #1e293b;
  border-radius: 12px;
  padding: 16px 20px;
  margin: 12px 0;
  overflow-x: auto;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.ai-text :deep(pre code) {
  background: transparent;
  padding: 0;
  color: #e2e8f0;
  font-size: 13px;
  line-height: 1.7;
  font-weight: 400;
}

.ai-text :deep(blockquote) {
  border-left: 3px solid #3b82f6;
  margin: 12px 0;
  padding: 8px 16px;
  background: linear-gradient(90deg, #eff6ff, transparent);
  border-radius: 0 8px 8px 0;
  color: #475569;
}

.ai-text :deep(hr) {
  border: none;
  border-top: 1px solid #e2e8f0;
  margin: 16px 0;
}

.ai-text :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.ai-text :deep(th), .ai-text :deep(td) {
  padding: 10px 14px;
  text-align: left;
  border-bottom: 1px solid #e2e8f0;
}

.ai-text :deep(th) {
  background: #f8fafc;
  font-weight: 600;
  color: #475569;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ai-text :deep(tr:hover) {
  background: #f8fafc;
}

/* ========== 引用来源 ========== */
.sources-section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(226, 232, 240, 0.6);
}

.sources-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: linear-gradient(135deg, #eff6ff, #f0f7ff);
  border-radius: 10px;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s ease;
  border: 1px solid rgba(59, 130, 246, 0.1);
}

.sources-toggle:hover {
  background: linear-gradient(135deg, #dbeafe, #e0e7ff);
  border-color: rgba(59, 130, 246, 0.2);
}

.toggle-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #3b82f6;
  font-weight: 500;
}

.toggle-arrow {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  color: #3b82f6;
}

.sources-toggle.expanded .toggle-arrow {
  transform: rotate(180deg);
}

/* 折叠动画 */
.fold-enter-active, .fold-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.fold-enter-from, .fold-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(-8px);
}

.fold-enter-to, .fold-leave-from {
  max-height: 600px;
  opacity: 1;
  transform: translateY(0);
}

.sources-panel {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.source-card {
  padding: 12px 16px;
  background: linear-gradient(135deg, #f8fafc, #fff);
  border-radius: 10px;
  border: 1px solid rgba(226, 232, 240, 0.5);
  border-left: 3px solid #3b82f6;
  transition: all 0.2s ease;
}

.source-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  border-left-color: #2563eb;
}

.source-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.source-badge {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.source-title {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  flex: 1;
}

.source-score {
  font-size: 11px;
  color: #94a3b8;
  font-family: 'SF Mono', monospace;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 4px;
}

.source-text {
  font-size: 12.5px;
  color: #64748b;
  line-height: 1.6;
}

/* ========== 消息元信息 ========== */
.msg-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 10px;
  font-size: 11px;
  color: #94a3b8;
  font-weight: 400;
}

/* ========== 加载动画 ========== */
.loading-row {
  opacity: 0.9;
}

.loading-bubble {
  padding: 14px 20px;
}

.typing-indicator {
  display: flex;
  gap: 5px;
  padding: 4px 0;
}

.typing-indicator span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  animation: typingBounce 1.6s infinite ease-in-out both;
}

.typing-indicator span:nth-child(1) { animation-delay: -0.4s; }
.typing-indicator span:nth-child(2) { animation-delay: -0.2s; }

@keyframes typingBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ========== 输入区域 ========== */
.chat-input-area {
  padding: 16px 32px 20px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(12px);
  border-top: 1px solid rgba(226, 232, 240, 0.5);
  flex-shrink: 0;
}

.input-container {
  max-width: 800px;
  margin: 0 auto;
}

.input-box {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  background: #fff;
  border: 1.5px solid #e2e8f0;
  border-radius: 28px;
  padding: 10px 10px 10px 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04), 0 0 0 1px rgba(0, 0, 0, 0.02);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.input-box.focused {
  border-color: #3b82f6;
  box-shadow: 0 4px 20px rgba(59, 130, 246, 0.12), 0 0 0 3px rgba(59, 130, 246, 0.06);
}

.input-box textarea {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  resize: none;
  font-size: 14.5px;
  line-height: 1.6;
  max-height: 120px;
  color: #1e293b;
  padding: 6px 0;
  font-family: inherit;
}

.input-box textarea::placeholder {
  color: #94a3b8;
  font-weight: 400;
}

.input-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.toolbar-options {
  display: flex;
  gap: 6px;
}

.option-pill {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 10px;
  border-radius: 16px;
  font-size: 12px;
  color: #64748b;
  background: #f1f5f9;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
  border: 1px solid transparent;
}

.option-pill:hover {
  background: #e2e8f0;
  color: #475569;
}

.option-pill.active {
  background: linear-gradient(135deg, #eff6ff, #e0e7ff);
  color: #3b82f6;
  border-color: rgba(59, 130, 246, 0.15);
}

.pill-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #cbd5e1;
  transition: background 0.2s ease;
}

.pill-indicator.on {
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  box-shadow: 0 0 4px rgba(59, 130, 246, 0.4);
}

.send-button {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: #e2e8f0;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: not-allowed;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
}

.send-button.ready {
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}

.send-button.ready:hover {
  transform: scale(1.08) rotate(-4deg);
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.4);
}

.send-button.ready:active {
  transform: scale(0.95);
}

.input-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  font-size: 11px;
  color: #94a3b8;
  margin-top: 10px;
  font-weight: 400;
}

/* ========== 滚动条美化 ========== */
.chat-messages::-webkit-scrollbar {
  width: 5px;
}

.chat-messages::-webkit-scrollbar-track {
  background: transparent;
}

.chat-messages::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 10px;
}

.chat-messages::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

.session-list::-webkit-scrollbar {
  width: 4px;
}

.session-list::-webkit-scrollbar-track {
  background: transparent;
}

.session-list::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 10px;
}

.session-list::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>
