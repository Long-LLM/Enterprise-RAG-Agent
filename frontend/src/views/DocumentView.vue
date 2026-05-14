<template>
  <div class="doc-page">
    <div class="page-header">
      <div class="header-left">
        <h1>文档管理</h1>
        <p class="page-desc">管理知识库中的所有文档，共 {{ documents.length }} 个</p>
      </div>
      <el-button type="primary" @click="$router.push('/upload')">
        <el-icon><Plus /></el-icon>
        <span>上传新文档</span>
      </el-button>
    </div>

    <div class="doc-grid" v-loading="loading">
      <!-- 空状态 -->
      <div v-if="!loading && documents.length === 0" class="empty-state">
        <div class="empty-illustration">
          <el-icon size="80" color="#cbd5e1"><Document /></el-icon>
        </div>
        <h3>知识库空空如也</h3>
        <p>上传文档后即可在此管理，支持 PDF、Word、Excel、TXT 等多种格式</p>
        <el-button type="primary" size="large" @click="$router.push('/upload')">
          <el-icon><Plus /></el-icon>
          <span>上传第一份文档</span>
        </el-button>
      </div>

      <div
        v-for="doc in documents"
        :key="doc.doc_id"
        class="doc-card"
      >
        <div class="doc-icon" :style="{ background: getFileColor(doc.filename) }">
          <el-icon size="28" color="#fff"><Document /></el-icon>
        </div>
        <div class="doc-info">
          <div class="doc-title" :title="doc.title || doc.filename">
            {{ doc.title || doc.filename }}
          </div>
          <div class="doc-meta">
            <el-tag size="small" effect="plain">{{ doc.file_type || '未知' }}</el-tag>
            <el-tag v-if="doc.department" size="small" type="info">{{ doc.department }}</el-tag>
            <span class="doc-status" :class="doc.status">
              <span class="status-dot"></span>
              {{ doc.status === 'active' ? '正常' : doc.status }}
            </span>
          </div>
          <div class="doc-id">ID: {{ doc.doc_id }}</div>
        </div>
        <div class="doc-actions">
          <el-popconfirm
            title="确定删除该文档吗？"
            confirm-button-text="删除"
            cancel-button-text="取消"
            confirm-button-type="danger"
            @confirm="handleDelete(doc.doc_id)"
          >
            <template #reference>
              <el-button circle size="small" type="danger" plain>
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, Plus } from '@element-plus/icons-vue'
import { listDocuments, deleteDocument } from '../api/api.js'

const documents = ref([])
const loading = ref(false)

const getFileColor = (name) => {
  const ext = name?.split('.').pop()?.toLowerCase()
  const map = { pdf: '#ef4444', docx: '#3b82f6', pptx: '#f97316', xlsx: '#22c55e', csv: '#10b981', txt: '#64748b', md: '#6366f1', html: '#f59e0b', json: '#8b5cf6', epub: '#ec4899' }
  return map[ext] || '#64748b'
}

const fetchDocuments = async () => {
  loading.value = true
  try {
    const { data } = await listDocuments()
    documents.value = data.data || []
  } catch (err) {
    ElMessage.error('获取文档列表失败')
  } finally {
    loading.value = false
  }
}

const handleDelete = async (docId) => {
  try {
    await deleteDocument(docId)
    ElMessage.success('删除成功')
    fetchDocuments()
  } catch (err) {
    ElMessage.error('删除失败')
  }
}

onMounted(fetchDocuments)
</script>

<style scoped>
.doc-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 28px;
}

.page-header h1 {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
}

.page-desc {
  color: #64748b;
  font-size: 14px;
  margin-top: 4px;
}

.doc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  min-height: 400px;
}

/* 空状态 */
.empty-state {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 60px 20px;
  background: #fff;
  border-radius: 16px;
  border: 2px dashed #e2e8f0;
}

.empty-illustration {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: linear-gradient(135deg, #f1f5f9, #e2e8f0);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
}

.empty-state h3 {
  font-size: 18px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 8px;
}

.empty-state p {
  font-size: 14px;
  color: #94a3b8;
  margin-bottom: 24px;
  max-width: 400px;
  line-height: 1.6;
}

.doc-card {
  background: #fff;
  border-radius: 14px;
  padding: 20px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  border: 1px solid #f1f5f9;
  transition: all 0.2s ease;
}

.doc-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
  border-color: #e2e8f0;
}

.doc-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.doc-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #22c55e;
}

.doc-status .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22c55e;
}

.doc-id {
  font-size: 11px;
  color: #94a3b8;
  font-family: monospace;
}

.doc-actions {
  opacity: 0;
  transition: opacity 0.2s;
}

.doc-card:hover .doc-actions {
  opacity: 1;
}
</style>
