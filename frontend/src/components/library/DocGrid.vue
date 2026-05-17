<script setup>
import { ref, computed } from 'vue'
import { AlertCircle, TriangleAlert } from 'lucide-vue-next'
import { useLibraryStore } from '../../stores/libraryStore'
import libraryApi from '../../api/library'

const libraryStore = useLibraryStore()

// ==================== 文件选择 ====================
function handleDocClick(docId, event) {
  libraryStore.toggleDocSelect(docId)
}

// ==================== 下载状态 ====================
const downloadingIds = ref(new Set())

async function handleDownload(doc, event) {
  event.stopPropagation()
  if (downloadingIds.value.has(doc.id)) return
  downloadingIds.value.add(doc.id)
  try {
    await libraryApi.downloadDoc(doc.id, doc.name)
  } catch (e) {
    console.error('download error:', e)
  } finally {
    setTimeout(() => {
      downloadingIds.value.delete(doc.id)
    }, 1000)
  }
}

// ==================== 文件上传 ====================
const isDragOver = ref(false)

function triggerUpload() {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.accept = '.pdf,.doc,.docx,.xlsx,.xls,.txt,.md,.csv,.pptx,.ppt'
  input.onchange = handleFileSelect
  input.click()
}

async function handleFileSelect(event) {
  const files = Array.from(event.target.files)
  if (files.length > 0 && libraryStore.currentSpaceId) {
    try {
      await libraryStore.uploadDocs(libraryStore.currentSpaceId, files)
    } catch (e) {
      console.error('upload error:', e)
    }
  }
  event.target.value = ''
}

function handleDrop(event) {
  event.preventDefault()
  isDragOver.value = false
  const files = Array.from(event.dataTransfer.files)
  if (files.length > 0 && libraryStore.currentSpaceId) {
    libraryStore.uploadDocs(libraryStore.currentSpaceId, files)
  }
}

function handleDragOver(event) {
  event.preventDefault()
  isDragOver.value = true
}

function handleDragLeave() {
  isDragOver.value = false
}

// ==================== 删除文档 ====================
const showDeleteModal = ref(false)
const deleteTargetDoc = ref(null)
const isDeleting = ref(false)
const deleteError = ref('')

function openDeleteDocModal(doc, event) {
  event.stopPropagation()
  deleteTargetDoc.value = doc
  deleteError.value = ''
  showDeleteModal.value = true
}

async function confirmDeleteDoc() {
  if (!deleteTargetDoc.value) return
  isDeleting.value = true
  deleteError.value = ''
  try {
    await libraryStore.deleteDoc(deleteTargetDoc.value.id)
    showDeleteModal.value = false
    deleteTargetDoc.value = null
  } catch (e) {
    deleteError.value = e.message || '删除失败，请重试'
  } finally {
    isDeleting.value = false
  }
}

function closeDeleteDocModal() {
  showDeleteModal.value = false
  deleteTargetDoc.value = null
}

// ==================== 批量删除 ====================
const showBatchDeleteModal = ref(false)
const isBatchDeleting = ref(false)
const batchDeleteError = ref('')

function openBatchDeleteModal() {
  batchDeleteError.value = ''
  showBatchDeleteModal.value = true
}

async function confirmBatchDelete() {
  isBatchDeleting.value = true
  batchDeleteError.value = ''
  try {
    await libraryStore.deleteSelectedDocs()
    showBatchDeleteModal.value = false
  } catch (e) {
    batchDeleteError.value = e.message || '批量删除失败，请重试'
  } finally {
    isBatchDeleting.value = false
  }
}

function closeBatchDeleteModal() {
  showBatchDeleteModal.value = false
}

// ==================== 批量导出 ====================
const batchExportError = ref('')

async function handleBatchExport() {
  if (libraryStore.selectedCount === 0 || libraryStore.isExporting) return
  batchExportError.value = ''
  try {
    await libraryStore.exportSelectedDocs()
  } catch (e) {
    batchExportError.value = e.message || '批量导出失败，请重试'
  }
}

function getFileIconSvg(extension) {
  const ext = (extension || '').toLowerCase()
  const icons = {
    pdf:  { bg: '#FEE2E2', label: 'PDF',  tc: '#B91C1C' },
    doc:  { bg: '#DBEAFE', label: 'DOC',  tc: '#1D4ED8' },
    docx: { bg: '#DBEAFE', label: 'DOCX', tc: '#1D4ED8' },
    xls:  { bg: '#DCFCE7', label: 'XLS',  tc: '#15803D' },
    xlsx: { bg: '#DCFCE7', label: 'XLSX', tc: '#15803D' },
    csv:  { bg: '#DCFCE7', label: 'CSV',  tc: '#15803D' },
    ppt:  { bg: '#FFEDD5', label: 'PPT',  tc: '#C2410C' },
    pptx: { bg: '#FFEDD5', label: 'PPTX', tc: '#C2410C' },
    txt:  { bg: '#F1F5F9', label: 'TXT',  tc: '#475569' },
    md:   { bg: '#F1F5F9', label: 'MD',   tc: '#475569' },
    json: { bg: '#F1F5F9', label: 'JSON', tc: '#475569' },
    xml:  { bg: '#F1F5F9', label: 'XML',  tc: '#475569' },
    zip:  { bg: '#FEF9C3', label: 'ZIP',  tc: '#A16207' },
    rar:  { bg: '#FEF9C3', label: 'RAR',  tc: '#A16207' },
    '7z': { bg: '#FEF9C3', label: '7Z',   tc: '#A16207' },
    png:  { bg: '#F3E8FF', label: 'PNG',  tc: '#7E22CE' },
    jpg:  { bg: '#F3E8FF', label: 'JPG',  tc: '#7E22CE' },
    jpeg: { bg: '#F3E8FF', label: 'JPEG', tc: '#7E22CE' },
    gif:  { bg: '#F3E8FF', label: 'GIF',  tc: '#7E22CE' },
    webp: { bg: '#F3E8FF', label: 'WEBP', tc: '#7E22CE' },
    svg:  { bg: '#F3E8FF', label: 'SVG',  tc: '#7E22CE' },
    mp3:  { bg: '#CFFAF3', label: 'MP3',  tc: '#0F766E' },
    wav:  { bg: '#CFFAF3', label: 'WAV',  tc: '#0F766E' },
    mp4:  { bg: '#FCE7F3', label: 'MP4',  tc: '#9D174D' },
    mov:  { bg: '#FCE7F3', label: 'MOV',  tc: '#9D174D' },
    avi:  { bg: '#FCE7F3', label: 'AVI',  tc: '#9D174D' },
    py:   { bg: '#EFF6FF', label: 'PY',   tc: '#1E40AF' },
    js:   { bg: '#EFF6FF', label: 'JS',   tc: '#1E40AF' },
    ts:   { bg: '#EFF6FF', label: 'TS',   tc: '#1E40AF' },
    html: { bg: '#EFF6FF', label: 'HTML', tc: '#1E40AF' },
    css:  { bg: '#EFF6FF', label: 'CSS',  tc: '#1E40AF' },
  }
  const { bg, label, tc } = icons[ext] || { bg: '#F8FAFC', label: 'FILE', tc: '#64748B' }
  const lx = label.length > 4 ? 16 : 18
  const fs = label.length > 4 ? 10 : 11
  return `<svg viewBox="0 0 64 72" xmlns="http://www.w3.org/2000/svg"><rect width="64" height="72" rx="8" ry="8" fill="${bg}"/><path d="M44 0 L64 0 L64 20 Z" fill="${bg}" stroke="rgba(0,0,0,0.12)" stroke-width="1"/><line x1="10" y1="24" x2="54" y2="24" stroke="rgba(0,0,0,0.07)" stroke-width="1.5"/><line x1="10" y1="30" x2="54" y2="30" stroke="rgba(0,0,0,0.07)" stroke-width="1.5"/><line x1="10" y1="36" x2="40" y2="36" stroke="rgba(0,0,0,0.07)" stroke-width="1.5"/><rect x="6" y="46" width="52" height="18" rx="4" fill="rgba(0,0,0,0.06)"/><text x="${lx}" y="59" font-family="Arial" font-size="${fs}" font-weight="700" fill="${tc}" text-anchor="middle" dominant-baseline="middle">${label}</text></svg>`
}

function getFileIcon(extension) {
  return getFileIconSvg(extension)
}
</script>

<template>
  <div
    class="library-content"
    @drop="handleDrop"
    @dragover="handleDragOver"
    @dragleave="handleDragLeave"
  >
    <!-- Content Header -->
    <div class="content-header">
      <div class="current-space">
        <span>{{ libraryStore.currentSpace?.name || '请选择空间' }}</span>
        <span v-if="libraryStore.isUploading" class="upload-indicator">
          上传中... {{ libraryStore.uploadProgress }}%
        </span>
      </div>
      <div class="header-right">
        <div class="selected-info" v-if="libraryStore.selectedCount > 0">
          <span>已选择 <strong>{{ libraryStore.selectedCount }}</strong> 个文档</span>
          <button
            class="lib-btn primary-sm"
            :disabled="libraryStore.isExporting"
            @click="handleBatchExport"
          >
            <span v-if="libraryStore.isExporting" class="btn-spinner inline-spinner" />
            <span v-else>批量导出</span>
          </button>
          <button class="lib-btn danger-sm" @click="openBatchDeleteModal">批量删除</button>
          <button class="lib-btn" @click="libraryStore.clearSelection">取消选择</button>
          <span v-if="batchExportError" class="batch-export-error">{{ batchExportError }}</span>
        </div>
        <div v-else-if="libraryStore.currentSpaceId" class="header-actions">
          <button class="lib-btn" @click="triggerUpload">
            <span>导入文档</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Drag Overlay -->
    <div v-if="isDragOver" class="drag-overlay">
      <div class="drag-inner">
        <span class="drag-cue" aria-hidden="true" />
        <span class="drag-text">松开以上传文件</span>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="libraryStore.isLoading" class="docs-loading">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
    </div>

    <!-- Empty State -->
    <div v-else-if="!libraryStore.currentSpaceId" class="docs-empty">
      <h3>请先选择一个文档空间</h3>
      <p>在左侧选择一个空间，或创建一个新空间</p>
    </div>

    <!-- Empty Docs -->
    <div v-else-if="libraryStore.filteredDocs.length === 0" class="docs-empty">
      <h3>该空间暂无文档</h3>
      <p>点击上方「导入文档」按钮上传文件</p>
      <p class="drop-hint">或直接将文件拖拽到此处</p>
    </div>

    <!-- Document Grid -->
    <div v-else class="doc-grid">
      <div
        v-for="doc in libraryStore.filteredDocs"
        :key="doc.id"
        class="doc-card"
        :class="{ selected: libraryStore.isDocSelected(doc.id) }"
        @click="handleDocClick(doc.id, $event)"
      >
        <!-- Checkbox -->
        <div class="doc-checkbox">
          <span v-if="libraryStore.isDocSelected(doc.id)" class="doc-check-visual" aria-hidden="true" />
        </div>

        <!-- Delete Button -->
        <button
          class="doc-delete-btn"
          title="删除文档"
          @click="openDeleteDocModal(doc, $event)"
        >
          ×
        </button>

        <!-- Download Button -->
        <button
          class="doc-download-btn"
          :class="{ downloading: downloadingIds.has(doc.id) }"
          title="下载文档"
          @click="handleDownload(doc, $event)"
        >
          <span v-if="downloadingIds.has(doc.id)" class="download-spinner"></span>
          <span v-else>↓</span>
        </button>

        <!-- File Icon -->
        <div class="doc-icon" v-html="getFileIconSvg(doc.file_extension)"></div>

        <!-- File Name -->
        <div class="doc-name" :title="doc.name">{{ doc.name }}</div>

        <!-- Meta -->
        <div class="doc-meta">
          <span>{{ doc.size }}</span>
          <span>{{ doc.time }}</span>
        </div>
      </div>
    </div>

    <!-- Upload Progress Bar -->
    <div v-if="libraryStore.isUploading" class="upload-progress-bar">
      <div class="progress-track">
        <div class="progress-fill" :style="{ width: libraryStore.uploadProgress + '%' }"></div>
      </div>
      <span class="progress-text">正在上传... {{ libraryStore.uploadProgress }}%</span>
    </div>

    <!-- ==================== 删除单个文档确认弹窗 ==================== -->
    <Teleport to="body">
      <div class="modal-overlay" :class="{ active: showDeleteModal }" @click.self="closeDeleteDocModal">
        <div class="modal">
          <div class="modal-header">
            <span class="modal-title">删除文档</span>
            <button class="modal-close" @click="closeDeleteDocModal">×</button>
          </div>
          <div class="modal-body">
            <div v-if="deleteError" class="modal-error">
              <span class="error-icon" aria-hidden="true">
                <AlertCircle :size="16" :stroke-width="2" />
              </span>
              <span>{{ deleteError }}</span>
            </div>
            <div class="confirm-box">
              <div class="confirm-icon" aria-hidden="true">
                <TriangleAlert :size="28" :stroke-width="1.75" />
              </div>
              <p class="confirm-text">确定要删除文档 <strong>"{{ deleteTargetDoc?.name }}"</strong> 吗？</p>
              <p class="confirm-subtext">删除后将无法恢复。</p>
            </div>
          </div>
          <div class="modal-footer">
            <button class="modal-btn cancel" @click="closeDeleteDocModal">取消</button>
            <button class="modal-btn danger" :disabled="isDeleting" @click="confirmDeleteDoc">
              <span v-if="isDeleting" class="btn-spinner"></span>
              <span v-else>确认删除</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ==================== 批量删除确认弹窗 ==================== -->
    <Teleport to="body">
      <div class="modal-overlay" :class="{ active: showBatchDeleteModal }" @click.self="closeBatchDeleteModal">
        <div class="modal">
          <div class="modal-header">
            <span class="modal-title">批量删除文档</span>
            <button class="modal-close" @click="closeBatchDeleteModal">×</button>
          </div>
          <div class="modal-body">
            <div v-if="batchDeleteError" class="modal-error">
              <span class="error-icon" aria-hidden="true">
                <AlertCircle :size="16" :stroke-width="2" />
              </span>
              <span>{{ batchDeleteError }}</span>
            </div>
            <div class="confirm-box">
              <div class="confirm-icon batch-icon" aria-hidden="true">
                <TriangleAlert :size="28" :stroke-width="1.75" />
              </div>
              <p class="confirm-text">确定要删除选中的 <strong>{{ libraryStore.selectedCount }}</strong> 个文档吗？</p>
              <p class="confirm-subtext">删除后将无法恢复。</p>
            </div>
          </div>
          <div class="modal-footer">
            <button class="modal-btn cancel" @click="closeBatchDeleteModal">取消</button>
            <button class="modal-btn danger" :disabled="isBatchDeleting" @click="confirmBatchDelete">
              <span v-if="isBatchDeleting" class="btn-spinner"></span>
              <span v-else>确认删除</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* Library Content */
.library-content {
  flex: 1;
  padding: 24px 32px;
  overflow-y: auto;
  position: relative;
  display: flex;
  flex-direction: column;
}

/* Content Header */
.content-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-shrink: 0;
  gap: 16px;
}

.current-space {
  font-size: 18px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.upload-indicator {
  font-size: 12px;
  font-weight: 500;
  color: var(--accent-primary);
  background: rgba(37, 99, 235, 0.1);
  padding: 4px 12px;
  border-radius: 0;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.selected-info {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  color: var(--text-muted);
}

.selected-info strong {
  color: var(--accent-primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Buttons */
.lib-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.2s;
}

.lib-btn:hover {
  background: var(--bg-hover);
  border-color: var(--border-color-hover);
}

.lib-btn.danger-sm {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.lib-btn.danger-sm:hover {
  background: rgba(239, 68, 68, 0.2);
}

.lib-btn.primary-sm {
  background: rgba(99, 102, 241, 0.12);
  border-color: rgba(99, 102, 241, 0.35);
  color: var(--accent-primary, #6366f1);
}

.lib-btn.primary-sm:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.2);
}

.lib-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.batch-export-error {
  font-size: 12px;
  color: #ef4444;
  max-width: 200px;
}

.inline-spinner {
  width: 14px;
  height: 14px;
  border-width: 2px;
}

/* Drag Overlay */
.drag-overlay {
  position: absolute;
  inset: 0;
  background: rgba(99, 102, 241, 0.08);
  border: 2px dashed var(--accent-primary);
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  pointer-events: none;
}

.drag-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.drag-cue {
  width: 52px;
  height: 52px;
  border-radius: 0;
  border: 3px dashed rgba(37, 99, 235, 0.35);
  background: rgba(37, 99, 235, 0.06);
  animation: bounce-up 0.6s ease-in-out infinite alternate;
}

@keyframes bounce-up {
  from { transform: translateY(0); }
  to { transform: translateY(-12px); }
}

.drag-text {
  font-size: 18px;
  font-weight: 600;
  color: var(--accent-primary);
}

/* Loading */
.docs-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  flex: 1;
  color: var(--text-muted);
}

.loading-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--border-color);
  border-top-color: var(--accent-primary);
  border-radius: 0;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Empty State */
.docs-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 12px;
  text-align: center;
}

.docs-empty .empty-icon {
  font-size: 72px;
  opacity: 0.4;
  margin-bottom: 8px;
}

.docs-empty h3 {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.docs-empty p {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

.drop-hint {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-muted);
  opacity: 0.7;
}

/* Document Grid */
.doc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

/* Document Card */
.doc-card {
  position: relative;
  background: var(--bg-card);
  border: 2px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 20px;
  cursor: pointer;
  transition: all 0.25s ease;
  user-select: none;
}

.doc-card:hover {
  border-color: var(--border-color-hover);
  transform: translateY(-4px);
  box-shadow: var(--shadow-md);
}

.doc-card.selected {
  border-color: var(--accent-primary);
  background: rgba(37, 99, 235, 0.06);
}

/* Checkbox */
.doc-checkbox {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 22px;
  height: 22px;
  background: var(--bg-tertiary);
  border: 2px solid var(--border-color);
  border-radius: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: transparent;
  transition: all 0.2s;
  opacity: 0;
}

.doc-card:hover .doc-checkbox,
.doc-card.selected .doc-checkbox {
  opacity: 1;
}

.doc-card.selected .doc-checkbox {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
}

.doc-check-visual {
  display: block;
  width: 5px;
  height: 9px;
  border: solid #fff;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
  margin-bottom: 2px;
}

/* Delete Button */
.doc-delete-btn {
  position: absolute;
  top: 12px;
  right: 42px;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 0;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 18px;
  font-weight: 300;
  opacity: 0;
  transition: all 0.2s;
  line-height: 1;
}

.doc-card:hover .doc-delete-btn {
  opacity: 1;
}

.doc-delete-btn:hover {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

/* Download Button */
.doc-download-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 0;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 16px;
  font-weight: 700;
  transition: all 0.2s;
  line-height: 1;
}

.doc-download-btn:hover {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.doc-download-btn.downloading {
  pointer-events: none;
}

.doc-download-btn.downloading .download-spinner {
  display: block;
}

.download-spinner {
  display: none;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(59, 130, 246, 0.3);
  border-top-color: #3b82f6;
  border-radius: 0;
  animation: spin 0.7s linear infinite;
}

/* Doc Icon */
.doc-icon {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.doc-icon :deep(svg) {
  width: 56px;
  height: 63px;
}

/* Doc Name */
.doc-name {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Doc Meta */
.doc-meta {
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  justify-content: space-between;
}

/* Upload Progress Bar */
.upload-progress-bar {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 16px 24px;
  box-shadow: var(--shadow-lg);
  z-index: 100;
  min-width: 300px;
}

.progress-track {
  width: 100%;
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 0;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--gradient-primary);
  border-radius: 0;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

/* ============ 弹窗样式 ============ */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  opacity: 0;
  visibility: hidden;
  transition: all 0.3s ease;
}

.modal-overlay.active {
  opacity: 1;
  visibility: visible;
}

.modal {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xl);
  width: 440px;
  max-width: 90vw;
  display: flex;
  flex-direction: column;
  transform: scale(0.9) translateY(20px);
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.6);
}

.modal-overlay.active .modal {
  transform: scale(1) translateY(0);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
}

.modal-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
}

.modal-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 22px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
  line-height: 1;
}

.modal-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.modal-body {
  padding: 24px;
}

.modal-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: #ef4444;
  margin-bottom: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
}

/* Confirm Box */
.confirm-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.confirm-icon {
  width: 56px;
  height: 56px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-danger);
}

.modal-error .error-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 0;
  background: rgba(220, 38, 38, 0.12);
  color: var(--accent-danger);
  flex-shrink: 0;
}

.batch-icon {
  background: rgba(239, 68, 68, 0.1);
}

.confirm-text {
  font-size: 15px;
  color: var(--text-primary);
  line-height: 1.6;
  margin: 0;
}

.confirm-text strong {
  color: var(--accent-primary);
}

.confirm-subtext {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.6;
  margin: 0;
}

/* Modal Buttons */
.modal-btn {
  padding: 10px 24px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
  min-width: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.modal-btn.cancel {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
}

.modal-btn.cancel:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.modal-btn.danger {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.modal-btn.danger:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.25);
  transform: translateY(-2px);
}

.modal-btn.danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Spinner */
.btn-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 0;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
