<template>
  <div class="preview-panel">
    <!-- 统计卡片 -->
    <div class="stats-bar" v-if="stats">
      <div class="stat-item">
        <div class="stat-value">{{ stats.total_chunks }}</div>
        <div class="stat-label">分块数</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.avg_length }}</div>
        <div class="stat-label">平均长度</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.max_length }}</div>
        <div class="stat-label">最大长度</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.min_length }}</div>
        <div class="stat-label">最小长度</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ formatNumber(stats.total_chars) }}</div>
        <div class="stat-label">总字符</div>
      </div>
    </div>

    <div v-if="previewTruncated" class="truncate-warning">
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>
          文本过长，仅预览前 {{ formatNumber(stats?.total_chars) }} 字符的分块效果
        </template>
      </el-alert>
    </div>

    <!-- Chunk 列表 -->
    <div class="chunk-list" v-if="chunks.length > 0">
      <div
        v-for="chunk in chunks"
        :key="chunk.index"
        class="chunk-card"
        :class="{ 'is-parent': chunk.chunk_type === 'parent', 'is-child': chunk.chunk_type === 'child' }"
      >
        <div class="chunk-header">
          <div class="chunk-meta">
            <span class="chunk-index">#{{ chunk.index + 1 }}</span>
            <el-tag v-if="chunk.chunk_type === 'parent'" type="warning" size="small" effect="dark">父块</el-tag>
            <el-tag v-else-if="chunk.chunk_type === 'child'" type="info" size="small">子块</el-tag>
            <el-tag v-else type="success" size="small" effect="plain">普通</el-tag>
            <span class="chunk-size">{{ chunk.char_count }} 字符</span>
          </div>
          <div class="chunk-title" v-if="chunk.section_title">
            <el-icon><Document /></el-icon>
            <span>{{ chunk.section_title }}</span>
          </div>
        </div>
        <div class="chunk-body">
          <div class="chunk-text" :class="{ expanded: expandedChunks.has(chunk.index) }">
            {{ chunk.content }}
          </div>
          <div v-if="chunk.content.length > 120" class="chunk-toggle">
            <el-button
              link
              type="primary"
              size="small"
              @click="toggleExpand(chunk.index)"
            >
              {{ expandedChunks.has(chunk.index) ? '收起' : '展开全部' }}
            </el-button>
          </div>
        </div>
        <div class="chunk-footer" v-if="chunk.parent_id">
          <span class="parent-link">父块ID: {{ chunk.parent_id }}</span>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty v-else description="暂无预览数据，请先上传文件并预览" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Document } from '@element-plus/icons-vue'

const props = defineProps({
  chunks: { type: Array, default: () => [] },
  stats: { type: Object, default: null },
  previewTruncated: { type: Boolean, default: false },
})

const expandedChunks = ref(new Set())

const toggleExpand = (index) => {
  const set = new Set(expandedChunks.value)
  if (set.has(index)) {
    set.delete(index)
  } else {
    set.add(index)
  }
  expandedChunks.value = set
}

const formatNumber = (num) => {
  if (num === undefined || num === null) return '-'
  if (num >= 10000) return (num / 10000).toFixed(1) + 'w'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'k'
  return num.toString()
}
</script>

<style scoped>
.preview-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.stats-bar {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  flex-shrink: 0;
}

.stat-item {
  background: linear-gradient(135deg, #f8fafc, #f1f5f9);
  border-radius: 10px;
  padding: 12px 4px;
  text-align: center;
  border: 1px solid #e2e8f0;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.2;
}

.stat-label {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
}

.truncate-warning {
  flex-shrink: 0;
}

.chunk-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}

.chunk-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
  transition: all 0.2s;
}

.chunk-card:hover {
  border-color: #3b82f6;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.08);
}

.chunk-card.is-parent {
  border-left: 3px solid #f59e0b;
  background: linear-gradient(90deg, #fffbeb, #fff);
}

.chunk-card.is-child {
  border-left: 3px solid #94a3b8;
}

.chunk-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 6px;
}

.chunk-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chunk-index {
  font-size: 13px;
  font-weight: 700;
  color: #3b82f6;
  background: #eff6ff;
  padding: 2px 8px;
  border-radius: 6px;
  min-width: 36px;
  text-align: center;
}

.chunk-size {
  font-size: 11px;
  color: #94a3b8;
}

.chunk-title {
  font-size: 12px;
  color: #64748b;
  display: flex;
  align-items: center;
  gap: 4px;
}

.chunk-body {
  background: #f8fafc;
  border-radius: 8px;
  padding: 10px 12px;
}

.chunk-text {
  font-size: 13px;
  line-height: 1.7;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow: hidden;
  position: relative;
}

.chunk-text::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 30px;
  background: linear-gradient(transparent, #f8fafc);
  pointer-events: none;
}

.chunk-text.expanded {
  max-height: none;
}

.chunk-text.expanded::after {
  display: none;
}

.chunk-toggle {
  margin-top: 6px;
  text-align: center;
}

.chunk-footer {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
}

.parent-link {
  font-size: 11px;
  color: #94a3b8;
  font-family: monospace;
}
</style>
