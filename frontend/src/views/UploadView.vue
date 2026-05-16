<template>
  <div class="upload-page">
    <div class="page-header">
      <h1>文档上传</h1>
      <p class="page-desc">上传文档，选择分块策略，预览效果后确认入库</p>
    </div>

    <div class="upload-layout" :class="{ 'has-file': selectedFile }">
      <!-- 左侧：配置面板 -->
      <div class="upload-main">
        <!-- 步骤引导 -->
        <div v-if="!selectedFile" class="steps-guide">
          <div class="step-item">
            <div class="step-num">1</div>
            <div class="step-content">
              <div class="step-title">上传文档</div>
              <div class="step-desc">支持 PDF、Word、PPT、Excel、TXT 等格式</div>
            </div>
          </div>
          <div class="step-arrow"><el-icon><ArrowRight /></el-icon></div>
          <div class="step-item">
            <div class="step-num">2</div>
            <div class="step-content">
              <div class="step-title">选择分块策略</div>
              <div class="step-desc">预览分块效果，调整参数</div>
            </div>
          </div>
          <div class="step-arrow"><el-icon><ArrowRight /></el-icon></div>
          <div class="step-item">
            <div class="step-num">3</div>
            <div class="step-content">
              <div class="step-title">确认入库</div>
              <div class="step-desc">生成向量 Embedding 存入知识库</div>
            </div>
          </div>
        </div>

        <!-- 上传区域 -->
        <div class="upload-zone" :class="{ 'has-file': selectedFile, dragging }"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="handleDrop"
        >
          <input
            ref="fileInput"
            type="file"
            class="file-input"
            accept=".pdf,.docx,.pptx,.xlsx,.csv,.json,.txt,.md,.html,.epub"
            @change="handleFileChange"
          />

          <div v-if="!selectedFile" class="upload-placeholder" @click="$refs.fileInput.click()">
            <div class="upload-icon-wrap">
              <el-icon size="48" color="#3b82f6"><UploadFilled /></el-icon>
            </div>
            <h3>拖拽文件到此处</h3>
            <p>或 <span class="click-text">点击选择文件</span></p>
            <div class="format-tags">
              <span v-for="fmt in formats" :key="fmt" class="fmt-tag">{{ fmt }}</span>
            </div>
          </div>

          <div v-else class="file-preview">
            <div class="file-icon" :style="{ background: getFileColor(selectedFile.name) }">
              <el-icon size="32" color="#fff"><Document /></el-icon>
            </div>
            <div class="file-info">
              <div class="file-name">{{ selectedFile.name }}</div>
              <div class="file-size">{{ formatSize(selectedFile.size) }}</div>
            </div>
            <el-button circle size="small" @click.stop="clearFile">
              <el-icon><Close /></el-icon>
            </el-button>
          </div>
        </div>

        <!-- 策略选择 -->
        <div class="strategy-section" v-if="selectedFile">
          <h4>分块策略</h4>
          <div class="strategy-grid">
            <div
              v-for="s in strategies"
              :key="s.value"
              class="strategy-card"
              :class="{ active: form.strategy === s.value }"
              @click="form.strategy = s.value"
            >
              <div class="strategy-card-header">
                <el-tag
                  v-if="form.strategy === s.value"
                  type="primary"
                  size="small"
                  effect="dark"
                  class="strategy-check"
                >已选</el-tag>
              </div>
              <div class="strategy-name">{{ s.label }}</div>
              <div class="strategy-desc">{{ s.desc }}</div>
            </div>
          </div>
        </div>

        <!-- 策略参数 -->
        <div class="params-section" v-if="selectedFile && paramFields.length > 0">
          <h4>策略参数</h4>
          <div class="params-grid">
            <div v-for="field in paramFields" :key="field.key" class="param-item">
              <label>{{ field.label }}</label>
              <el-input-number
                v-if="field.type === 'number'"
                v-model="form.params[field.key]"
                :min="field.min"
                :max="field.max"
                :step="field.step || 1"
                size="small"
                style="width: 100%"
              />
              <el-select
                v-else-if="field.type === 'select'"
                v-model="form.params[field.key]"
                size="small"
                style="width: 100%"
              >
                <el-option
                  v-for="opt in field.options"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-switch
                v-else-if="field.type === 'switch'"
                v-model="form.params[field.key]"
              />
              <el-input
                v-else
                v-model="form.params[field.key]"
                size="small"
                :placeholder="field.placeholder"
              />
            </div>
          </div>
        </div>

        <!-- 存入部门 -->
        <div class="title-section" v-if="selectedFile">
          <h4>存入部门/数据库</h4>
          <div v-if="isStaff" class="staff-dept-info">
            <el-tag type="info" size="large">{{ userDepartment || '未分配部门' }}</el-tag>
            <p class="dept-hint">员工只能上传到自己所属部门</p>
          </div>
          <div v-else-if="isAdmin" class="dept-mode">
            <el-radio-group v-model="deptMode" size="small" style="margin-bottom: 12px;">
              <el-radio-button label="existing">选择现有部门</el-radio-button>
              <el-radio-button label="new">新建部门</el-radio-button>
            </el-radio-group>
            <el-select
              v-if="deptMode === 'existing'"
              v-model="form.department"
              placeholder="选择已有部门"
              style="width: 100%"
              clearable
            >
              <el-option
                v-for="dept in departmentOptions"
                :key="dept"
                :label="dept"
                :value="dept"
              />
              <template #empty>
                <div style="padding: 10px; text-align: center; color: #999;">暂无部门，请创建新部门</div>
              </template>
            </el-select>
            <el-input
              v-else
              v-model="form.department"
              placeholder="输入新部门名称，如：市场部、财务部"
              clearable
            />
          </div>
          <div v-else>
            <el-tag type="warning" size="large">普通用户无权上传</el-tag>
          </div>
        </div>

        <!-- 上传模式选择 -->
        <div class="mode-section" v-if="selectedFile">
          <h4>上传模式</h4>
          <el-radio-group v-model="uploadMode" size="small">
            <el-radio-button label="sync">
              <el-icon><Timer /></el-icon> 同步（小文件）
            </el-radio-button>
            <el-radio-button label="async">
              <el-icon><Clock /></el-icon> 异步（大文件推荐）
            </el-radio-button>
          </el-radio-group>
          <p v-if="autoAsync" class="mode-hint">
            文件超过 10MB，已自动切换为异步模式
          </p>
          <p v-else class="mode-hint">
            {{ uploadMode === 'async' ? '后台处理，可离开页面，通过任务状态查看进度' : '即时处理，完成后返回结果' }}
          </p>
        </div>

        <!-- 文档标题 -->
        <div class="title-section" v-if="selectedFile">
          <h4>文档标题</h4>
          <el-input v-model="form.title" placeholder="默认使用文件名" clearable />
        </div>

        <!-- 操作按钮 -->
        <div class="action-bar" v-if="selectedFile">
          <el-button
            type="primary"
            :loading="previewing"
            @click="doPreview"
            :icon="Refresh"
          >
            {{ previewing ? '预览中...' : '重新预览' }}
          </el-button>
          <el-button
            type="success"
            :loading="uploading"
            @click="submitUpload"
            :icon="Upload"
            :disabled="chunkList.length === 0"
          >
            {{ uploadBtnText }}
          </el-button>
        </div>

        <!-- 异步任务状态 -->
        <div v-if="taskId" class="task-status-card">
          <h4>处理进度</h4>
          <div class="task-meta">
            <el-tag size="small">任务ID: {{ taskId.slice(0, 12) }}...</el-tag>
            <el-tag :type="taskStatusType" size="small">{{ taskStatusText }}</el-tag>
          </div>
          <el-progress
            v-if="taskProgress !== null"
            :percentage="taskProgress"
            :status="taskProgressStatus"
            :stroke-width="10"
            striped
            striped-flow
          />
          <p v-if="taskMessage" class="task-message">{{ taskMessage }}</p>
          <div v-if="taskResult" class="task-result">
            <el-result
              :icon="taskResult.icon"
              :title="taskResult.title"
              :sub-title="taskResult.subtitle"
            >
              <template #extra>
                <el-button type="primary" @click="reset">继续上传</el-button>
                <el-button @click="$router.push('/query')">去问答</el-button>
              </template>
            </el-result>
          </div>
        </div>

        <!-- 同步上传结果 -->
        <el-result
          v-if="result && !taskId"
          :icon="result.icon"
          :title="result.title"
          :sub-title="result.subtitle"
          class="result-card"
        >
          <template #extra>
            <el-button type="primary" @click="reset">继续上传</el-button>
            <el-button @click="$router.push('/query')">去问答</el-button>
          </template>
        </el-result>
      </div>

      <!-- 右侧：预览面板 -->
      <div class="preview-sidebar" v-if="selectedFile">
        <div class="preview-header">
          <h4>分块预览</h4>
          <el-tag v-if="previewStrategy" type="info" size="small">{{ previewStrategy }}</el-tag>
        </div>
        <ChunkPreviewPanel
          :chunks="chunkList"
          :stats="previewStats"
          :preview-truncated="previewTruncated"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Document, Close, Refresh, Upload, ArrowRight, Timer, Clock } from '@element-plus/icons-vue'
import { uploadDocument, uploadDocumentAsync, getTaskStatus, previewChunks } from '../api/api'
import ChunkPreviewPanel from '../components/ChunkPreviewPanel.vue'

const formats = ['PDF', 'DOCX', 'PPTX', 'XLSX', 'CSV', 'JSON', 'TXT', 'MD', 'HTML', 'EPUB']

const strategies = [
  { value: 'auto', label: '自动选择', desc: '根据文档特征自动选择最优策略' },
  { value: 'fixed_size', label: '固定大小', desc: '按固定字符数均匀切分' },
  { value: 'recursive', label: '递归分块', desc: '按段落→句子→单词递归切分' },
  { value: 'semantic', label: '语义分块', desc: '按语义边界合并保持完整' },
  { value: 'structured', label: '结构分块', desc: '按标题层级表格结构切分' },
  { value: 'parent_child', label: '父子分块', desc: '父块上下文+子块精确检索' },
  { value: 'llm_smart', label: 'LLM智能', desc: '大模型分析智能分块' },
]

// 策略参数配置
const strategyParamsConfig = {
  fixed_size: [
    { key: 'chunk_size', label: '块大小', type: 'number', min: 50, max: 4096, step: 50 },
    { key: 'chunk_overlap', label: '重叠大小', type: 'number', min: 0, max: 1024, step: 50 },
  ],
  recursive: [
    { key: 'chunk_size', label: '块大小', type: 'number', min: 50, max: 4096, step: 50 },
    { key: 'chunk_overlap', label: '重叠大小', type: 'number', min: 0, max: 1024, step: 50 },
  ],
  semantic: [
    { key: 'chunk_size', label: '块大小', type: 'number', min: 50, max: 4096, step: 50 },
    { key: 'chunk_overlap', label: '重叠大小', type: 'number', min: 0, max: 1024, step: 50 },
  ],
  structured: [
    { key: 'chunk_size', label: '块大小', type: 'number', min: 50, max: 4096, step: 50 },
    { key: 'preserve_tables', label: '表格单独成块', type: 'switch' },
  ],
  parent_child: [
    { key: 'parent_chunk_size', label: '父块大小', type: 'number', min: 200, max: 8192, step: 256 },
    { key: 'child_chunk_size', label: '子块大小', type: 'number', min: 50, max: 1024, step: 50 },
    { key: 'parent_overlap', label: '父块重叠', type: 'number', min: 0, max: 2048, step: 64 },
    { key: 'child_overlap', label: '子块重叠', type: 'number', min: 0, max: 512, step: 32 },
  ],
  llm_smart: [
    { key: 'temperature', label: '温度', type: 'number', min: 0, max: 1, step: 0.1 },
    { key: 'max_tokens', label: '最大Token', type: 'number', min: 512, max: 8192, step: 512 },
  ],
}

const fileInput = ref(null)
const selectedFile = ref(null)
const dragging = ref(false)
const uploading = ref(false)
const previewing = ref(false)
const result = ref(null)

// 异步上传状态
const uploadMode = ref('sync')  // 'sync' | 'async'
const taskId = ref(null)
const taskStatus = ref(null)
const taskProgress = ref(null)
const taskMessage = ref('')
const taskResult = ref(null)
let pollTimer = null

const chunkList = ref([])
const previewStats = ref(null)
const previewStrategy = ref('')
const previewTruncated = ref(false)

const form = reactive({
  title: '',
  strategy: 'auto',
  params: {},
  department: '',
})

const deptMode = ref('existing')  // 'existing' | 'new'

// 文件超过 10MB 自动切换异步
const ASYNC_THRESHOLD = 10 * 1024 * 1024
const autoAsync = computed(() => selectedFile.value?.size > ASYNC_THRESHOLD)

watch(autoAsync, (isLarge) => {
  if (isLarge) uploadMode.value = 'async'
})

const uploadBtnText = computed(() => {
  if (uploading.value) {
    return uploadMode.value === 'async' ? '提交任务中...' : '入库中...'
  }
  return uploadMode.value === 'async' ? '后台入库' : '确认入库'
})

const taskStatusText = computed(() => {
  const map = {
    PENDING: '等待中',
    STARTED: '已开始',
    PROGRESS: '处理中',
    SUCCESS: '已完成',
    FAILURE: '失败',
    RETRY: '重试中',
  }
  return map[taskStatus.value] || taskStatus.value || '未知'
})

const taskStatusType = computed(() => {
  const map = {
    PENDING: 'info',
    STARTED: 'warning',
    PROGRESS: 'warning',
    SUCCESS: 'success',
    FAILURE: 'danger',
    RETRY: 'danger',
  }
  return map[taskStatus.value] || 'info'
})

const taskProgressStatus = computed(() => {
  if (taskStatus.value === 'FAILURE') return 'exception'
  if (taskStatus.value === 'SUCCESS') return 'success'
  return ''
})

const userInfo = ref({})
try {
  userInfo.value = JSON.parse(localStorage.getItem('user_info') || '{}')
} catch {
  userInfo.value = {}
}

const isAdmin = computed(() => userInfo.value.role === 'admin')
const isStaff = computed(() => userInfo.value.role === 'staff')
const userDepartment = computed(() => userInfo.value.department || '')

// 部门选项（管理员可从已有部门中选择，员工固定为自己部门）
const departmentOptions = ref([])

const loadDepartments = async () => {
  if (!isAdmin.value) return
  try {
    const { data } = await import('../api/api').then(m => m.listDepartments())
    departmentOptions.value = data.data || []
  } catch {
    departmentOptions.value = []
  }
}

// 文件选择时加载部门列表并设置默认值
watch(() => selectedFile.value, async (val) => {
  if (!val) return
  if (isStaff.value && userDepartment.value) {
    form.department = userDepartment.value
  } else if (isAdmin.value) {
    await loadDepartments()
    if (departmentOptions.value.length > 0 && !form.department) {
      form.department = departmentOptions.value[0]
    }
  }
})

const paramFields = computed(() => {
  return strategyParamsConfig[form.strategy] || []
})

// 策略切换时重置参数
watch(() => form.strategy, (newVal) => {
  const defaults = {}
  const config = strategyParamsConfig[newVal] || []
  config.forEach(field => {
    if (field.type === 'switch') defaults[field.key] = true
    else if (field.type === 'number') defaults[field.key] = field.min + (field.step || 1) * Math.floor((field.max - field.min) / (field.step || 1) / 2)
  })
  form.params = defaults
})

// 部门模式切换时重置 department
watch(() => deptMode.value, (mode) => {
  form.department = ''
  if (mode === 'existing') {
    loadDepartments()
  }
})

const getFileColor = (name) => {
  const ext = name.split('.').pop()?.toLowerCase()
  const map = { pdf: '#ef4444', docx: '#3b82f6', pptx: '#f97316', xlsx: '#22c55e', csv: '#10b981', txt: '#64748b', md: '#6366f1', html: '#f59e0b', json: '#8b5cf6', epub: '#ec4899' }
  return map[ext] || '#64748b'
}

const formatSize = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

const handleDrop = (e) => {
  dragging.value = false
  const files = e.dataTransfer.files
  if (files.length > 0) {
    selectedFile.value = files[0]
    autoPreview()
  }
}

const handleFileChange = (e) => {
  const files = e.target.files
  if (files.length > 0) {
    selectedFile.value = files[0]
    autoPreview()
  }
}

const clearFile = () => {
  selectedFile.value = null
  chunkList.value = []
  previewStats.value = null
  if (fileInput.value) fileInput.value.value = ''
}

const autoPreview = async () => {
  if (!selectedFile.value) return
  await doPreview()
}

const doPreview = async () => {
  if (!selectedFile.value) return
  previewing.value = true
  try {
    const res = await previewChunks(selectedFile.value, form.strategy, form.params)
    const data = res.data.data
    chunkList.value = data.chunks || []
    previewStats.value = data.stats || null
    previewStrategy.value = data.strategy
    previewTruncated.value = data.stats?.preview_truncated || false
    ElMessage.success(`预览完成：${data.chunk_count} 个分块`)
  } catch (err) {
    ElMessage.error(err.response?.data?.message || '预览失败')
    chunkList.value = []
    previewStats.value = null
  } finally {
    previewing.value = false
  }
}

// ---------- 异步上传轮询 ----------

const startPolling = (id) => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    try {
      const { data } = await getTaskStatus(id)
      const task = data.data
      taskStatus.value = task.status
      taskProgress.value = task.progress || (task.status === 'SUCCESS' ? 100 : task.status === 'FAILURE' ? 0 : null)
      taskMessage.value = task.message || ''

      if (task.status === 'SUCCESS') {
        clearInterval(pollTimer)
        pollTimer = null
        taskResult.value = {
          icon: 'success',
          title: '文档入库完成',
          subtitle: `任务 ${id.slice(0, 12)}... 处理成功，共 ${task.result?.chunk_count || '?'} 个分块`,
        }
        ElMessage.success('异步入库任务完成')
      } else if (task.status === 'FAILURE') {
        clearInterval(pollTimer)
        pollTimer = null
        taskResult.value = {
          icon: 'error',
          title: '入库失败',
          subtitle: task.message || '异步任务执行失败',
        }
        ElMessage.error('异步入库任务失败')
      }
    } catch (err) {
      console.error('轮询任务状态失败:', err)
    }
  }, 2000)  // 每 2 秒轮询一次
}

const submitUpload = async () => {
  if (!selectedFile.value) return
  uploading.value = true
  result.value = null
  taskId.value = null
  taskStatus.value = null
  taskProgress.value = null
  taskMessage.value = ''
  taskResult.value = null

  try {
    if (uploadMode.value === 'async') {
      // 异步上传
      const res = await uploadDocumentAsync(
        selectedFile.value,
        form.title,
        form.strategy,
        form.params,
        form.department,
      )
      const data = res.data.data
      taskId.value = data.task_id
      taskStatus.value = 'PENDING'
      taskProgress.value = 0
      taskMessage.value = '任务已提交，正在排队...'
      ElMessage.success(`异步任务已提交: ${data.task_id.slice(0, 12)}...`)
      startPolling(data.task_id)
    } else {
      // 同步上传
      const res = await uploadDocument(
        selectedFile.value,
        form.title,
        form.strategy,
        form.params,
        form.department,
      )
      result.value = {
        icon: 'success',
        title: '文档入库完成',
        subtitle: `共生成 ${res.data.data.chunk_count} 个文本分块，已存入向量库`,
      }
      ElMessage.success('入库成功')
    }
  } catch (err) {
    if (uploadMode.value === 'async') {
      taskResult.value = {
        icon: 'error',
        title: '提交失败',
        subtitle: err.response?.data?.message || err.message,
      }
    } else {
      result.value = {
        icon: 'error',
        title: '入库失败',
        subtitle: err.response?.data?.message || err.message,
      }
    }
    ElMessage.error(uploadMode.value === 'async' ? '任务提交失败' : '入库失败')
  } finally {
    uploading.value = false
  }
}

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

const reset = () => {
  selectedFile.value = null
  result.value = null
  chunkList.value = []
  previewStats.value = null
  form.title = ''
  form.strategy = 'auto'
  form.params = {}
  form.department = ''
  deptMode.value = 'existing'
  uploadMode.value = 'sync'
  taskId.value = null
  taskStatus.value = null
  taskProgress.value = null
  taskMessage.value = ''
  taskResult.value = null
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}
</script>

<style scoped>
.upload-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 32px;
}

.page-header {
  margin-bottom: 28px;
}

.page-header h1 {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 6px;
}

.page-desc {
  color: #64748b;
  font-size: 14px;
}

.upload-layout {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}

.upload-layout.has-file {
  display: grid;
  grid-template-columns: 1fr 480px;
  align-items: start;
}

.upload-main {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  max-width: 720px;
}

.upload-layout.has-file .upload-main {
  max-width: none;
}

/* 步骤引导 */
.steps-guide {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 24px;
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border-radius: 16px;
  border: 1px solid #bae6fd;
  width: 100%;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.step-num {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
}

.step-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.step-desc {
  font-size: 12px;
  color: #64748b;
}

.step-arrow {
  color: #93c5fd;
  font-size: 20px;
  flex-shrink: 0;
}

@media (max-width: 900px) {
  .steps-guide {
    flex-direction: column;
    gap: 12px;
  }
  .step-arrow {
    transform: rotate(90deg);
  }
}

.upload-zone {
  position: relative;
  background: #fff;
  border: 2px dashed #cbd5e1;
  border-radius: 16px;
  padding: 40px;
  text-align: center;
  transition: all 0.3s ease;
  cursor: pointer;
}

.upload-zone:hover, .upload-zone.dragging {
  border-color: #3b82f6;
  background: #eff6ff;
}

.upload-zone.has-file {
  border-style: solid;
  border-color: #3b82f6;
  background: #fff;
}

.file-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.upload-icon-wrap {
  width: 80px;
  height: 80px;
  border-radius: 20px;
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}

.upload-placeholder h3 {
  font-size: 18px;
  color: #334155;
  margin-bottom: 6px;
}

.upload-placeholder p {
  color: #64748b;
  font-size: 14px;
}

.click-text {
  color: #3b82f6;
  font-weight: 600;
}

.format-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 20px;
}

.fmt-tag {
  padding: 4px 10px;
  background: #f1f5f9;
  border-radius: 6px;
  font-size: 12px;
  color: #64748b;
}

.file-preview {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
}

.file-icon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.file-info {
  flex: 1;
  text-align: left;
}

.file-name {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 4px;
}

.file-size {
  font-size: 13px;
  color: #94a3b8;
}

/* 策略选择 */
.strategy-section, .params-section, .title-section {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.strategy-section h4, .params-section h4, .title-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 16px;
}

.strategy-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.strategy-card {
  border: 2px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
  background: #fff;
  position: relative;
  min-height: 64px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.strategy-card:hover {
  border-color: #93c5fd;
  background: #f8fafc;
}

.strategy-card.active {
  border-color: #3b82f6;
  background: #eff6ff;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.strategy-card-header {
  position: absolute;
  top: 8px;
  right: 8px;
}

.strategy-check {
  font-size: 10px;
  height: 18px;
  padding: 0 6px;
}

.strategy-name {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 4px;
  padding-right: 36px;
}

.strategy-desc {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.4;
}

/* 参数 */
.params-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

.param-item label {
  display: block;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
}

/* 操作按钮 */
.action-bar {
  display: flex;
  gap: 12px;
}

.action-bar .el-button {
  flex: 1;
  height: 44px;
  font-size: 14px;
  border-radius: 10px;
}

/* 结果卡片 */
.result-card {
  background: #fff;
  border-radius: 12px;
}

/* 右侧预览面板 */
.preview-sidebar {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  min-height: 500px;
  max-height: calc(100vh - 140px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
}

.preview-header h4 {
  font-size: 15px;
  font-weight: 600;
  color: #334155;
}

@media (max-width: 1100px) {
  .upload-layout {
    grid-template-columns: 1fr;
  }
  .preview-sidebar {
    max-height: none;
  }
  .strategy-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .strategy-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .params-grid {
    grid-template-columns: 1fr;
  }
}

.dept-hint {
  color: #64748b;
  font-size: 12px;
  margin-top: 4px;
}

.staff-dept-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}

.dept-mode {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 上传模式选择 */
.mode-section {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.mode-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 16px;
}

.mode-hint {
  color: #94a3b8;
  font-size: 13px;
  margin-top: 10px;
}

/* 任务状态卡片 */
.task-status-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.task-status-card h4 {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 12px;
}

.task-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.task-message {
  color: #64748b;
  font-size: 13px;
  margin-top: 8px;
}

.task-result {
  margin-top: 16px;
}
</style>
