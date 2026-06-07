<script setup>
defineOptions({ name: 'ChatView' })

import { ref, onMounted, onUnmounted, onActivated, nextTick, watch, computed } from 'vue'
import { marked } from 'marked'
import { MessagesSquare, Send, FolderOpen, Upload, X, User, Bot, Info, Loader2 } from 'lucide-vue-next'
import { useSessionStore } from '../../stores/sessionStore'
import { useFileStore } from '../../stores/fileStore'
import { useLibraryStore } from '../../stores/libraryStore'
import ChatSidebar from './ChatSidebar.vue'
import SidebarToggle from '../common/SidebarToggle.vue'
import { saveResultFile, saveResultFileLabel } from '../../utils/saveResultFile'

// 配置 marked
marked.setOptions({
  breaks: true,
  gfm: true,
})

const sessionStore = useSessionStore()
const fileStore = useFileStore()
const libraryStore = useLibraryStore()

const messagesContainer = ref(null)
const inputText = ref('')
const textareaRef = ref(null)
const previewEntities = ref({})
const libraryPickerOpen = ref(false)
const attachSource = ref(null)
const isDragover = ref(false)

const selectedDataFiles = computed(() =>
  fileStore.tempFiles.data.filter((f) => f.is_selected),
)
const selectedTemplateFiles = computed(() =>
  fileStore.tempFiles.template.filter((f) => f.is_selected),
)
const hasSelectedFiles = computed(
  () => selectedDataFiles.value.length + selectedTemplateFiles.value.length > 0,
)
const allSelectedChips = computed(() => [
  ...selectedDataFiles.value.map((f) => ({ ...f, _type: 'data' })),
  ...selectedTemplateFiles.value.map((f) => ({ ...f, _type: 'template' })),
])

const showProgress = computed(() => sessionStore.showProgressBar)
const progressVal = computed(() => sessionStore.progressValue)
const progressMsg = computed(() => sessionStore.progressMessage)

const chatModes = ['default_conversation', 'document_understanding', 'document_editing', 'mixed']
const modeLabels = {
  default_conversation: '默认对话',
  document_understanding: '文档理解',
  document_editing: '文档编辑',
  mixed: '提取与填表'
}

function switchChatMode(mode) {
  sessionStore.switchMode(mode)
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

watch(() => sessionStore.currentSessionId, () => {
  scrollToBottom()
})

watch(() => sessionStore.messages.length, () => {
  scrollToBottom()
})

watch(() => sessionStore.isStreaming, (streaming) => {
  if (streaming) scrollToBottom()
})

onMounted(async () => {
  sessionStore.sidebarCollapsed = false
  sessionStore.connectWebSocket()
  await fileStore.ensureSpacesLoaded()
  if (fileStore.pickerSpaceId) {
    await fileStore.loadPickerDocs()
  }
  scrollToBottom()
})

onActivated(() => {
  sessionStore.sidebarCollapsed = false
})

onUnmounted(() => {
  sessionStore.disconnectWebSocket()
})

function renderMarkdown(content) {
  if (content == null || content === '') return ''
  return marked.parse(String(content))
}

function assistantHasRenderableText(msg) {
  return msg?.role === 'assistant' && String(msg?.content ?? '').trim().length > 0
}

function hasGeneratedFiles(msg) {
  const gf = msg?.generated_files
  if (Array.isArray(gf) && gf.length > 0) return true
  const tf = msg?.tableFillingData?.generated_files
  if (Array.isArray(tf) && tf.length > 0) return true
  const de = msg?.documentEditingData?.generated_files
  if (Array.isArray(de) && de.length > 0) return true
  return false
}

function autoResize() {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 200) + 'px'
  }
}

function handleKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || sessionStore.isStreaming) return

  inputText.value = ''
  libraryPickerOpen.value = false
  attachSource.value = null
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }

  await sessionStore.sendMessage(text, sessionStore.currentMode)
}

async function onPickerSpaceChange(event) {
  await fileStore.setPickerSpace(event.target.value)
}

function openLibraryAttach() {
  if (libraryPickerOpen.value) {
    libraryPickerOpen.value = false
    attachSource.value = null
    return
  }
  attachSource.value = 'library'
  libraryPickerOpen.value = true
  if (fileStore.pickerSpaceId) {
    fileStore.loadPickerDocs()
  }
}

function openLocalAttach() {
  attachSource.value = 'local'
  libraryPickerOpen.value = false
  triggerFileInput()
}

function handleDragOver(e) {
  e.preventDefault()
  isDragover.value = true
}

function handleDragLeave() {
  isDragover.value = false
}

function handleDrop(e) {
  e.preventDefault()
  isDragover.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length > 0) {
    const type = fileStore.currentFileType
    files.forEach((file) => fileStore.addFile(type, file))
    attachSource.value = 'local'
    libraryPickerOpen.value = false
  }
}

function handleFileInput(e) {
  const files = Array.from(e.target.files || [])
  if (files.length > 0) {
    const type = fileStore.currentFileType
    files.forEach((file) => fileStore.addFile(type, file))
    attachSource.value = null
  }
}

function triggerFileInput() {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.accept = '.pdf,.doc,.docx,.xlsx,.xls,.txt,.md,.csv'
  input.onchange = handleFileInput
  input.click()
}

function togglePickerDoc(doc) {
  fileStore.toggleLibraryDoc(doc, fileStore.currentFileType)
}

function switchFileType(type) {
  fileStore.switchFileType(type)
}

function removeFile(id, type) {
  fileStore.removeFile(id, type)
}

function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

/** 附件条展示用短名，完整名放 title */
function truncateFileName(name, max = 26) {
  const s = String(name || '').trim()
  if (s.length <= max) return s
  const dot = s.lastIndexOf('.')
  if (dot > 0 && dot < s.length - 1) {
    const ext = s.slice(dot)
    const baseMax = Math.max(6, max - ext.length - 1)
    return `${s.slice(0, baseMax)}…${ext}`
  }
  return `${s.slice(0, max - 1)}…`
}

function getFileExt(fileName) {
  if (!fileName || typeof fileName !== 'string') return 'FILE'
  const ext = fileName.split('.').pop()
  return ext ? ext.toUpperCase() : 'FILE'
}

async function saveGeneratedResultFile(fileInfo) {
  const result = await saveResultFile(fileInfo, {
    sessionId: sessionStore.currentSessionId,
  })
  if (result.canceled) return
  if (!result.ok && result.error) {
    alert(`保存失败：${result.error}`)
  }
}

// ============ 实体提取表格预览 ============
function getPreviewEntities(msg) {
  if (!msg) return []
  if (previewEntities.value[msg.id]) return previewEntities.value[msg.id]
  const entities = msg.entitiesData || []
  if (entities.length > 0) {
    previewEntities.value[msg.id] = entities
  }
  return entities
}

function getEntityHeaders(msg) {
  const entities = getPreviewEntities(msg)
  if (!entities || entities.length === 0) return []
  return Object.keys(entities[0])
}

function getEntityCells(entity, header) {
  const val = entity[header]
  if (val === undefined || val === null) return ''
  if (Array.isArray(val)) return val[0] ?? ''
  return String(val)
}

function downloadEntitiesJson(msg) {
  const entities = getPreviewEntities(msg)
  if (!entities.length) return
  const json = JSON.stringify(entities, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'extraction_result.json'
  a.click()
  URL.revokeObjectURL(url)
}

/** WebSocket 写在根上；历史消息可能在 metadata.tableFillingData */
function getTableFillingData(msg) {
  if (!msg || msg.role !== 'assistant') return null
  let metadata = msg.metadata
  if (typeof metadata === 'string') {
    try {
      metadata = JSON.parse(metadata)
    } catch {
      metadata = null
    }
  }
  return msg.tableFillingData ?? metadata?.tableFillingData ?? metadata?.table_filling_data ?? null
}

function rankTableFillDownload(f) {
  const name = String(f?.file_name || '').toLowerCase()
  const ft = String(f?.file_type || '').toLowerCase()
  if (['xlsx', 'xls', 'docx', 'doc'].includes(ft) || /\.(xlsx|xls|docx|doc)$/.test(name)) return 0
  if (ft === 'json' || name.endsWith('.json')) return 2
  return 1
}

function sortTableFillDownloads(files) {
  return [...(files || [])].sort((a, b) => rankTableFillDownload(a) - rankTableFillDownload(b))
}

function saveFileButtonLabel(f) {
  return saveResultFileLabel(f)
}

function getTableFillDownloadFiles(msg) {
  const tf = getTableFillingData(msg)
  let list = []
  if (Array.isArray(tf?.generated_files) && tf.generated_files.length) {
    list = tf.generated_files
  } else if (Array.isArray(tf?.generatedFiles) && tf.generatedFiles.length) {
    list = tf.generatedFiles
  } else if (Array.isArray(msg?.generated_files) && msg.generated_files.length && tf) {
    list = msg.generated_files
  } else if (Array.isArray(msg?.generatedFiles) && msg.generatedFiles.length && tf) {
    list = msg.generatedFiles
  } else {
    const fallback = []
    const templateOutput = tf?.template_output || tf?.output_template
    if (templateOutput) {
      const path = String(templateOutput)
      const suffix = path.split(/[\\/]/).pop()?.split('.').pop() || 'docx'
      fallback.push({
        file_path: path,
        file_name: path.split(/[\\/]/).pop() || `table_filling_result.${suffix}`,
        download_label: '填好的表格',
      })
    }
    if (tf?.output_json) {
      const path = String(tf.output_json)
      fallback.push({
        file_path: path,
        file_name: path.split(/[\\/]/).pop() || 'table_filling_result.json',
        download_label: '筛选数据 JSON',
      })
    }
    list = fallback
  }
  return sortTableFillDownloads(list)
}

const TABLE_PREVIEW_MAX_ROWS = 50

function tablePreviewRows(tf) {
  if (!tf || typeof tf !== 'object') return []
  const a = tf.previewData
  const b = tf.filtered_rows
  if (Array.isArray(a) && a.length) return a
  if (Array.isArray(b) && b.length) return b
  return []
}

function tablePreviewDisplayRows(tf) {
  return tablePreviewRows(tf).slice(0, TABLE_PREVIEW_MAX_ROWS)
}

function tablePreviewExtraCount(tf) {
  const n = tablePreviewRows(tf).length
  return n > TABLE_PREVIEW_MAX_ROWS ? n - TABLE_PREVIEW_MAX_ROWS : 0
}

function tablePreviewColumns(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return []
  const ordered = []
  const seen = new Set()
  const first = rows[0]
  if (first && typeof first === 'object' && !Array.isArray(first)) {
    for (const k of Object.keys(first)) {
      ordered.push(k)
      seen.add(k)
    }
  }
  for (const row of rows) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) continue
    for (const k of Object.keys(row)) {
      if (!seen.has(k)) {
        seen.add(k)
        ordered.push(k)
      }
    }
  }
  return ordered
}

function formatTablePreviewCell(val) {
  if (val === null || val === undefined || val === '') return '—'
  if (typeof val === 'object') {
    try {
      return JSON.stringify(val)
    } catch {
      return String(val)
    }
  }
  return String(val)
}

/** 每条助手消息最多算一次预览结构，避免模板里对每格重复 tablePreviewColumns */
function buildTableFillPreviewBundle(msg) {
  const tf = getTableFillingData(msg)
  if (!tf || tf.success === undefined) return null
  const rows = tablePreviewRows(tf)
  if (!rows.length) return null
  const columns = tablePreviewColumns(rows)
  const displayRows = rows.slice(0, TABLE_PREVIEW_MAX_ROWS)
  const extra = Math.max(0, rows.length - TABLE_PREVIEW_MAX_ROWS)
  return { tf, columns, displayRows, totalRows: rows.length, extra }
}

const tableFillPreviewByMessageKey = computed(() => {
  const list = sessionStore.messages
  const out = {}
  for (let i = 0; i < list.length; i++) {
    const msg = list[i]
    if (msg.role !== 'assistant') continue
    const key = msg.id != null && msg.id !== '' ? String(msg.id) : `_i_${i}`
    const b = buildTableFillPreviewBundle(msg)
    if (b) out[key] = b
  }
  return out
})

function tablePreviewBundleFor(msg, index) {
  const key = msg.id != null && msg.id !== '' ? String(msg.id) : `_i_${index}`
  return tableFillPreviewByMessageKey.value[key] || null
}

function tablePreviewBundleList(msg, index) {
  const b = tablePreviewBundleFor(msg, index)
  return b ? [b] : []
}

function getFileStyle(fileName) {
  const ext = (fileName || '').split('.').pop().toLowerCase()
  const label = fileStore.getFileTypeLabel(fileName)
  const map = {
    pdf:  { bg: 'rgba(37, 99, 235, 0.1)', text: '#2563eb', icon: label },
    doc:  { bg: 'rgba(37, 99, 235, 0.08)', text: '#1d4ed8', icon: label },
    docx: { bg: 'rgba(37, 99, 235, 0.08)', text: '#1d4ed8', icon: label },
    xls:  { bg: 'rgba(14, 165, 233, 0.12)', text: '#0284c7', icon: label },
    xlsx: { bg: 'rgba(14, 165, 233, 0.12)', text: '#0284c7', icon: label },
    txt:  { bg: 'rgba(100, 116, 139, 0.12)', text: '#64748b', icon: label },
    md:   { bg: 'rgba(100, 116, 139, 0.12)', text: '#64748b', icon: label },
  }
  return map[ext] || { bg: 'rgba(100, 116, 139, 0.12)', text: '#64748b', icon: label || '文件' }
}

function userMessageAttachments(msg) {
  const m = msg.metadata || {}
  const data = (m.files || []).map((f) => ({ ...f, _kind: 'data' }))
  const tpl = (m.template_files || []).map((f) => ({ ...f, _kind: 'template' }))
  return [...data, ...tpl]
}
</script>

<template>
  <div class="chat-view">
    <div class="sidebar-panel left-sidebar-panel" :class="{ collapsed: sessionStore.sidebarCollapsed }">
      <ChatSidebar />
      <SidebarToggle
        side="left"
        :collapsed="sessionStore.sidebarCollapsed"
        collapse-title="收起侧边栏"
        expand-title="展开侧边栏"
        @toggle="sessionStore.toggleSidebar"
      />
    </div>
    <div class="chat-main">
      <!-- 处理模式（已隐藏：由系统根据文件+指令智能分发） -->
      <div class="mode-selector" style="display: none;">
        <span class="mode-label">处理模式:</span>
        <div class="mode-tabs">
          <button
            v-for="mode in chatModes"
            :key="mode"
            class="mode-tab"
            :class="{ active: sessionStore.currentMode === mode }"
            @click="switchChatMode(mode)"
          >
            {{ modeLabels[mode] }}
          </button>
        </div>
      </div>

      <div
        class="chat-messages"
        ref="messagesContainer"
        :class="{ 'chat-messages--transition': sessionStore.isCreatingSession }"
      >
        <div v-if="sessionStore.isInitializing" class="welcome-state">
          <div class="welcome-icon" aria-hidden="true">
            <MessagesSquare :size="48" :stroke-width="1.5" />
          </div>
          <h1 class="welcome-title">加载中...</h1>
        </div>

        <div v-else-if="sessionStore.isCreatingSession" class="welcome-state">
          <div class="welcome-icon" aria-hidden="true">
            <Loader2 class="welcome-spin" :size="48" :stroke-width="1.5" />
          </div>
          <h1 class="welcome-title">正在创建新会话</h1>
          <p class="welcome-subtitle">请稍候…</p>
        </div>

        <div v-else-if="sessionStore.messages.length === 0" class="welcome-state">
          <div class="welcome-icon" aria-hidden="true">
            <MessagesSquare :size="48" :stroke-width="1.5" />
          </div>
          <h1 class="welcome-title">智能对话</h1>
          <p class="welcome-subtitle">
            通过自然语言与系统交互，完成文档分析、信息提取、内容生成等任务
          </p>
        </div>

        <div
          v-for="(msg, index) in sessionStore.messages"
          :key="msg.id != null ? msg.id : `m-${index}`"
          class="message"
          :class="msg.role"
        >
          <div class="message-avatar" :class="'role-' + msg.role" aria-hidden="true">
            <User v-if="msg.role === 'user'" :size="20" :stroke-width="2" />
            <Bot v-else-if="msg.role === 'assistant'" :size="20" :stroke-width="2" />
            <Info v-else :size="20" :stroke-width="2" />
          </div>
          <div class="message-content">
            <div
              v-if="!msg.isLoading && msg.created_at"
              class="message-time"
            >
              {{ sessionStore.formatMessageTime(msg.created_at) }}
            </div>
            <!-- 用户消息：带附件时显示文件卡片 -->
            <template v-if="msg.role === 'user' && userMessageAttachments(msg).length > 0">
              <div class="user-attachments">
                <div
                  v-for="(att, idx) in userMessageAttachments(msg)"
                  :key="`${att.id ?? att.file_id ?? idx}-${att.file_name}`"
                  class="attachment-card"
                  :class="{ 'attachment-uploading': att.pending }"
                >
                  <div
                    class="attachment-icon"
                    :style="{ background: getFileStyle(att.file_name).bg, color: getFileStyle(att.file_name).text }"
                  >
                    <span v-if="att.pending" class="attachment-spinner" aria-hidden="true" />
                    <span v-else class="attachment-type-dot" aria-hidden="true" />
                  </div>
                  <div class="attachment-info">
                    <div class="attachment-name" :title="att.file_name">{{ att.file_name }}</div>
                    <div class="attachment-meta">
                      <span v-if="att.pending" class="upload-status">上传中...</span>
                      <template v-else>
                        {{ getFileExt(att.file_name) }}
                        <span v-if="formatFileSize(att.file_size)"> | {{ formatFileSize(att.file_size) }}</span>
                      </template>
                      <span v-if="att._kind === 'template'" class="template-badge">· 模板</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="msg.content" class="message-bubble">
                <span>{{ msg.content }}</span>
              </div>
            </template>
            <!-- 用户消息：无附件 -->
            <div v-else-if="msg.role === 'user'" class="message-bubble">
              <span>{{ msg.content }}</span>
            </div>
            <!-- 系统消息 -->
            <div v-else-if="msg.role === 'system'" class="message-bubble system">
              <span>{{ msg.content }}</span>
            </div>
            <!-- 助手消息 -->
            <div v-else class="message-bubble" :class="{ 'md-content': msg.role === 'assistant' }">
              <template v-if="msg.role === 'assistant'">
                <div v-if="assistantHasRenderableText(msg)" v-html="renderMarkdown(msg.content)"></div>
                <div v-else-if="!msg.isLoading && hasGeneratedFiles(msg)" class="assistant-empty-hint assistant-success-hint" role="status">
                  文档处理完成，请查看下方生成结果。
                </div>
                <div v-else-if="!msg.isLoading" class="assistant-empty-hint" role="status">
                  （暂无正文回复，请检查 API Key、模型名称和 Base URL 是否配置正确。）
                </div>
              </template>
              <!-- Loading 动画 -->
              <div v-if="msg.isLoading" class="typing-indicator">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
              </div>
              <!-- 表格填表预览：每条消息只取一次 bundle（computed 预聚合 + 单次 list 迭代） -->
              <template v-for="tb in tablePreviewBundleList(msg, index)" :key="(msg.id != null ? msg.id : index) + '-tbl'">
                <div class="entity-preview table-fill-preview">
                  <div class="entity-preview-header">
                    <div>
                      <span class="entity-preview-title">
                        表格结果预览（{{ tb.totalRows }} 行）
                      </span>
                      <span v-if="tb.tf.matched_rows != null" class="table-fill-stats table-fill-stats-inline">
                        命中 {{ tb.tf.matched_rows }}/{{ tb.tf.total_rows ?? '—' }} 行
                      </span>
                    </div>
                    <div v-if="getTableFillDownloadFiles(msg).length" class="entity-preview-actions">
                      <button
                        v-for="f in getTableFillDownloadFiles(msg)"
                        :key="f.file_id ?? f.file_path"
                        class="entity-action-btn"
                        type="button"
                        @click="saveGeneratedResultFile(f)"
                      >
                        {{ saveFileButtonLabel(f) }}
                      </button>
                    </div>
                  </div>
                  <div class="entity-table-wrapper">
                    <table class="entity-table">
                      <thead>
                        <tr>
                          <th v-for="col in tb.columns" :key="col">
                            {{ col }}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, ri) in tb.displayRows" :key="ri">
                          <td
                            v-for="col in tb.columns"
                            :key="col"
                            :title="formatTablePreviewCell(row && row[col] !== undefined ? row[col] : '')"
                          >
                            {{ formatTablePreviewCell(row && row[col] !== undefined ? row[col] : '') }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div v-if="tb.extra > 0" class="entity-preview-more">
                    还有 {{ tb.extra }} 行未展示，请下载生成文件查看全部
                  </div>
                </div>
              </template>
              <!-- 仅表格填表：无 previewData 时仍要下载；勿用 getTableFillDownloadFiles 单独判断，否则无 tableFillingData 时会误用 msg.generated_files 与实体提取重复 -->
              <div
                v-if="getTableFillingData(msg) && getTableFillDownloadFiles(msg).length && !tablePreviewBundleFor(msg, index)"
                class="entity-preview table-fill-preview table-fill-downloads-only"
              >
                <div class="entity-preview-header">
                  <span class="entity-preview-title">生成结果</span>
                  <div class="entity-preview-actions">
                    <button
                      v-for="f in getTableFillDownloadFiles(msg)"
                      :key="f.file_id ?? f.file_path"
                      class="entity-action-btn"
                      type="button"
                      @click="saveGeneratedResultFile(f)"
                    >
                      {{ saveFileButtonLabel(f) }}
                    </button>
                  </div>
                </div>
              </div>
              <!-- 混合模式专用：仅展示统一填表后的结果预览与下载 -->
              <template v-if="msg.mixedSource === 'merged' && (msg.tableFillingPreview || msg.generated_files?.length)">
                <div class="entity-preview table-fill-preview">
                  <div class="entity-preview-header">
                    <div>
                      <span class="entity-preview-title">混合填表结果预览</span>
                      <span v-if="msg.tableFillingPreview?.matched_rows != null" class="table-fill-stats table-fill-stats-inline">
                        共 {{ msg.tableFillingPreview.matched_rows }} 行
                      </span>
                    </div>
                    <div v-if="msg.generated_files?.length" class="entity-preview-actions">
                      <button v-for="f in msg.generated_files" :key="f.file_id ?? f.file_path" class="entity-action-btn" @click="saveGeneratedResultFile(f)">
                        {{ saveFileButtonLabel(f) }}
                      </button>
                    </div>
                  </div>
                  <div v-if="msg.tableFillingPreview?.previewData?.length" class="entity-table-wrapper">
                    <table class="entity-table">
                      <thead>
                        <tr>
                          <th v-for="col in tablePreviewColumns(msg.tableFillingPreview.previewData)" :key="col">{{ col }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, ri) in msg.tableFillingPreview.previewData.slice(0, 50)" :key="ri">
                          <td v-for="col in tablePreviewColumns(msg.tableFillingPreview.previewData)" :key="col">
                            {{ formatTablePreviewCell(row && row[col] !== undefined ? row[col] : '') }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div v-else class="entity-preview-more">
                    已生成混合填表文件，请使用下载按钮查看完整结果。
                  </div>
                  <div v-if="(msg.tableFillingPreview?.previewData?.length ?? 0) > 50" class="entity-preview-more">
                    还有 {{ msg.tableFillingPreview.previewData.length - 50 }} 行未展示，请下载生成文件查看全部
                  </div>
                </div>
              </template>
              <!-- 非混合模式的实体提取结果：表格预览 -->
              <div v-else-if="msg.entitiesData?.length && msg.mixedSource !== 'merged'" class="entity-preview table-fill-preview">
                <div class="entity-preview-header">
                  <span class="entity-preview-title">提取结果预览（共 {{ msg.entitiesData.length }} 条）</span>
                  <div class="entity-preview-actions">
                    <div
                      v-for="f in msg.generated_files"
                      :key="f.file_id"
                      class="entity-download-item"
                    >
                      <span class="entity-download-name" :title="f.file_name">{{ f.file_name }}</span>
                      <button type="button" class="entity-action-btn" @click="saveGeneratedResultFile(f)">
                        {{ saveFileButtonLabel(f) }}
                      </button>
                    </div>
                  </div>
                </div>
                <div class="entity-table-wrapper">
                  <table class="entity-table">
                    <thead>
                      <tr>
                        <th v-for="h in getEntityHeaders(msg)" :key="h">{{ h }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(entity, rowIdx) in msg.entitiesData.slice(0, 20)" :key="rowIdx">
                        <td v-for="h in getEntityHeaders(msg)" :key="h" :title="entity[h] != null ? String(entity[h]) : ''">
                          {{ getEntityCells(entity, h) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="msg.entitiesData.length > 20" class="entity-preview-more">
                  还有 {{ msg.entitiesData.length - 20 }} 条数据，下载完整文件查看全部
                </div>
              </div>
              <!-- 非混合模式的表格填表预览 -->
              <div v-if="msg.tableFillingPreview && msg.mixedSource !== 'merged'" class="entity-preview table-fill-preview">
                <div class="entity-preview-header">
                  <div>
                    <span class="entity-preview-title">表格结果预览（{{ msg.tableFillingPreview.previewData?.length ?? msg.tableFillingPreview.matched_rows ?? 0 }} 行）</span>
                    <span v-if="msg.tableFillingPreview.matched_rows != null" class="table-fill-stats table-fill-stats-inline">
                      命中 {{ msg.tableFillingPreview.matched_rows }}/{{ msg.tableFillingPreview.total_rows ?? '—' }} 行
                    </span>
                  </div>
                </div>
                <div v-if="msg.tableFillingPreview.previewData?.length" class="entity-table-wrapper">
                  <table class="entity-table">
                    <thead>
                      <tr>
                        <th v-for="col in tablePreviewColumns(msg.tableFillingPreview.previewData)" :key="col">{{ col }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, ri) in msg.tableFillingPreview.previewData.slice(0, 50)" :key="ri">
                        <td v-for="col in tablePreviewColumns(msg.tableFillingPreview.previewData)" :key="col">
                          {{ formatTablePreviewCell(row && row[col] !== undefined ? row[col] : '') }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="(msg.tableFillingPreview.previewData?.length ?? 0) > 50" class="entity-preview-more">
                  还有 {{ msg.tableFillingPreview.previewData.length - 50 }} 行未展示，请下载生成文件查看全部
                </div>
              </div>
              <!-- 仅文件下载：无 entitiesData 预览时单独展示 -->
              <div
                v-if="msg.generated_files?.length && !getTableFillingData(msg) && !msg.entitiesData?.length"
                class="entity-preview table-fill-preview table-fill-downloads-only"
              >
                <div class="entity-preview-header">
                  <span class="entity-preview-title">生成结果</span>
                  <div class="entity-preview-actions">
                    <div
                      v-for="f in msg.generated_files"
                      :key="f.file_id"
                      class="entity-download-item"
                    >
                      <span class="entity-download-name" :title="f.file_name">{{ f.file_name }}</span>
                      <button type="button" class="entity-action-btn" @click="saveGeneratedResultFile(f)">
                        {{ saveFileButtonLabel(f) }}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 上传文件进度 -->
        <div v-if="sessionStore.isUploadingFiles" class="message system">
          <div class="message-avatar role-system" aria-hidden="true">
            <Info :size="20" :stroke-width="2" />
          </div>
          <div class="message-content">
            <div class="message-bubble upload-progress">
              <span class="upload-text">{{ sessionStore.uploadProgress || '正在上传文件...' }}</span>
            </div>
          </div>
        </div>

        <!-- 进度条（实体提取/表格填表） -->
        <div v-if="showProgress && (sessionStore.currentMode === 'entity_extraction' || sessionStore.currentMode === 'table_filling' || sessionStore.currentMode === 'mixed')" class="message assistant">
          <div class="message-avatar role-assistant" aria-hidden="true">
            <Bot :size="20" :stroke-width="2" />
          </div>
          <div class="message-content">
            <div class="progress-card">
              <div class="progress-header">
                <span class="progress-title">任务处理中</span>
                <span class="progress-msg">{{ progressMsg }}</span>
                <span v-if="progressVal < 100" class="progress-indicator">●</span>
                <span v-else class="progress-done">完成</span>
              </div>
              <div class="progress-bar-container">
                <div class="progress-bar" :style="{ width: progressVal + '%' }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-input-area">
        <div
          class="chat-composer"
          :class="{ 'chat-composer--dragover': isDragover }"
          @dragover="handleDragOver"
          @dragleave="handleDragLeave"
          @drop="handleDrop"
        >
          <div v-if="hasSelectedFiles" class="composer-attachments">
            <div
              v-for="file in allSelectedChips"
              :key="`${file._type}-${file.id}`"
              class="composer-chip"
              :class="`composer-chip--${file._type}`"
            >
              <span class="composer-chip-type">{{ file._type === 'template' ? '模板' : '数据' }}</span>
              <span class="composer-chip-name" :title="file.file_name">{{ truncateFileName(file.file_name) }}</span>
              <button
                type="button"
                class="composer-chip-remove"
                aria-label="移除附件"
                @click.stop="removeFile(file.id, file._type)"
              >
                <X :size="14" :stroke-width="2" />
              </button>
            </div>
          </div>

          <div class="composer-box">
            <div class="composer-main">
              <textarea
                ref="textareaRef"
                v-model="inputText"
                class="composer-textarea"
                rows="1"
                placeholder="输入消息，Enter 发送，Shift+Enter 换行"
                @keydown="handleKeyDown"
                @input="autoResize"
              />
              <button
                type="button"
                class="composer-send"
                :class="{ loading: sessionStore.isStreaming }"
                title="发送"
                aria-label="发送"
                :disabled="!inputText.trim() || sessionStore.isStreaming"
                @click="sendMessage"
              >
                <span v-if="!sessionStore.isStreaming" class="send-btn-ico" aria-hidden="true">
                  <Send :size="18" :stroke-width="2.2" />
                </span>
                <span v-else class="send-spinner" aria-hidden="true" />
              </button>
            </div>

            <div class="composer-toolbar composer-toolbar--flow">
              <div class="composer-step">
                <span class="composer-step-label">类型</span>
                <div class="composer-step-pills">
                  <button
                    type="button"
                    class="composer-type-pill composer-type-pill--data"
                    :class="{ active: fileStore.currentFileType === 'data' }"
                    @click="switchFileType('data')"
                  >
                    数据<span v-if="fileStore.selectedDataCount" class="composer-pill-count">{{ fileStore.selectedDataCount }}</span>
                  </button>
                  <button
                    type="button"
                    class="composer-type-pill composer-type-pill--template"
                    :class="{ active: fileStore.currentFileType === 'template' }"
                    @click="switchFileType('template')"
                  >
                    模板<span v-if="fileStore.selectedTemplateCount" class="composer-pill-count">{{ fileStore.selectedTemplateCount }}</span>
                  </button>
                </div>
              </div>
              <span class="composer-toolbar-divider" aria-hidden="true" />
              <div class="composer-step">
                <span class="composer-step-label">来源</span>
                <div class="composer-step-actions">
                  <button
                    type="button"
                    class="composer-source-btn"
                    :class="{ active: libraryPickerOpen }"
                    @click="openLibraryAttach"
                  >
                    <FolderOpen :size="15" :stroke-width="2" />
                    文档库
                  </button>
                  <button
                    type="button"
                    class="composer-source-btn"
                    :class="{ active: attachSource === 'local' && !libraryPickerOpen }"
                    @click="openLocalAttach"
                  >
                    <Upload :size="15" :stroke-width="2" />
                    本地文件
                  </button>
                </div>
              </div>
              <span class="composer-toolbar-hint">
                当前添加为「{{ fileStore.currentFileType === 'template' ? '模板' : '数据' }}」；发送后附件自动清空
              </span>
            </div>
          </div>

          <div v-if="libraryPickerOpen" class="composer-library-panel">
            <div class="library-io-row">
              <label class="library-io-label">文档库空间</label>
              <select class="library-io-select" :value="fileStore.pickerSpaceId" @change="onPickerSpaceChange">
                <option value="">选择空间</option>
                <option v-for="s in libraryStore.spaces" :key="s.id" :value="s.id">{{ s.name }}</option>
              </select>
            </div>
            <p class="library-picker-hint">
              从文档库勾选「{{ fileStore.currentFileType === 'template' ? '模板' : '数据' }}」文件；切换类型请点上方「数据 / 模板」
            </p>
            <div v-if="fileStore.isLoadingDocs" class="files-empty">加载中…</div>
            <div v-else-if="!fileStore.pickerSpaceId" class="files-empty">
              <span class="empty-text">请先选择文档库空间</span>
            </div>
            <div v-else-if="fileStore.pickerDocs.length === 0" class="files-empty">
              <span class="empty-text">该空间暂无文档</span>
            </div>
            <div v-else class="library-picker-list">
              <div
                v-for="doc in fileStore.pickerDocs"
                :key="doc.id"
                class="library-picker-item"
                :class="{ selected: fileStore.isDocInSelection(doc.id, fileStore.currentFileType) }"
                @click="togglePickerDoc(doc)"
              >
                <span class="library-picker-name" :title="doc.name">{{ truncateFileName(doc.name, 36) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 进度条 */
.progress-card {
  background: var(--glass-panel-strong);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--glass-radius-sm);
  padding: 12px 16px;
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.progress-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.progress-msg {
  font-size: 12px;
  color: var(--text-muted);
  flex: 1;
}

.progress-indicator {
  font-size: 12px;
  color: var(--text-muted);
  animation: pulse 1s infinite;
}

.progress-done {
  font-size: 12px;
  color: var(--accent-success);
  font-weight: 500;
}

.progress-bar-container {
  height: 8px;
  background: rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--gradient-success);
  border-radius: 8px;
  transition: width 0.3s ease;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ============ 实体提取表格预览 ============ */
.entity-preview {
  margin-top: 12px;
  border: 1px solid var(--glass-border);
  border-radius: var(--glass-radius-sm);
  overflow: hidden;
  background: var(--glass-panel-strong);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.entity-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.06);
  border-bottom: 1px solid var(--glass-border-soft);
}

.entity-preview-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.entity-preview-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.entity-download-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
}

.entity-download-name {
  font-size: 12px;
  color: var(--text-secondary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-fill-preview .entity-download-name {
  color: #fcd34d;
}

.entity-action-btn {
  background: var(--gradient-primary);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
}

.entity-action-btn:hover {
  filter: brightness(1.08);
}

.entity-table-wrapper {
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
}

.entity-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  background: transparent;
}

.entity-table thead {
  position: sticky;
  top: 0;
  z-index: 1;
}

.entity-table th {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary);
  font-weight: 600;
  padding: 6px 10px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid var(--glass-border-soft);
  border-right: 1px solid var(--glass-border-soft);
}

.entity-table td {
  padding: 5px 10px;
  border-bottom: 1px solid var(--glass-border-soft);
  border-right: 1px solid rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: rgba(0, 0, 0, 0.12);
}

.entity-table tbody tr:hover td {
  background: var(--glass-panel-hover);
}

.entity-preview-more {
  padding: 8px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
  border-top: 1px solid var(--glass-border-soft);
}

.table-fill-preview {
  border-color: rgba(251, 191, 36, 0.45);
  background: rgba(245, 158, 11, 0.08);
}

.table-fill-preview .entity-preview-header {
  background: rgba(245, 158, 11, 0.1);
  border-bottom: 1px solid rgba(251, 191, 36, 0.25);
}

.table-fill-preview .entity-preview-title {
  color: #fcd34d;
}

.table-fill-preview .entity-table th {
  background: rgba(245, 158, 11, 0.15);
  color: #fde68a;
  border-bottom: 1px solid rgba(251, 191, 36, 0.3);
  border-right: 1px solid rgba(251, 191, 36, 0.2);
}

.table-fill-preview .entity-table td {
  border-bottom: 1px solid rgba(251, 191, 36, 0.12);
  border-right: 1px solid rgba(255, 255, 255, 0.04);
  background: rgba(0, 0, 0, 0.1);
}

.table-fill-preview .entity-table tbody tr:hover td {
  background: rgba(245, 158, 11, 0.12);
}

.table-fill-preview .entity-preview-more {
  background: rgba(245, 158, 11, 0.08);
  border-top: 1px solid rgba(251, 191, 36, 0.25);
  color: #fbbf24;
}

.table-fill-stats {
  font-size: 12px;
  color: #fbbf24;
  white-space: nowrap;
}

.table-fill-stats-inline {
  margin-left: 8px;
  font-weight: 500;
}

/* Loading 动画 */
.typing-indicator {
  display: inline-flex !important;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding: 4px 0;
}

.typing-dot {
  width: 6px;
  height: 6px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: typing-bounce 1.4s infinite ease-in-out both;
}

.typing-dot:nth-child(1) {
  animation-delay: -0.32s;
}

.typing-dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes typing-bounce {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.assistant-empty-hint {
  font-size: 14px;
  color: var(--text-muted);
  line-height: 1.55;
  padding: 6px 0;
}

.assistant-success-hint {
  color: var(--accent-success, #10b981);
}

/* ============ 聊天输入区（附件在上 + 圆角输入框） ============ */
.chat-input-area {
  display: flex;
  justify-content: center;
  padding: 12px 20px 18px;
}

.chat-composer {
  width: 100%;
  max-width: 820px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat-composer--dragover .composer-box {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
}

.composer-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 2px;
}

.composer-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: min(240px, 100%);
  padding: 4px 8px 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--glass-border-soft);
  background: var(--glass-panel-strong);
  font-size: 12px;
  line-height: 1.3;
}

.composer-chip--data {
  border-color: rgba(16, 185, 129, 0.35);
  background: rgba(16, 185, 129, 0.1);
}

.composer-chip--template {
  border-color: rgba(99, 102, 241, 0.35);
  background: rgba(99, 102, 241, 0.1);
}

.composer-chip-type {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: var(--text-muted);
}

.composer-chip--data .composer-chip-type {
  color: var(--accent-success);
}

.composer-chip--template .composer-chip-type {
  color: var(--accent-primary);
}

.composer-chip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
  min-width: 0;
}

.composer-chip-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.composer-chip-remove:hover {
  background: rgba(220, 38, 38, 0.15);
  color: var(--accent-danger);
}

.composer-box {
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--glass-radius);
  background: var(--glass-panel-strong);
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.composer-main {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 10px 12px 8px;
}

.composer-textarea {
  flex: 1;
  min-width: 0;
  min-height: 24px;
  max-height: 200px;
  padding: 8px 4px;
  border: none;
  background: transparent;
  resize: none;
  outline: none;
  font-size: 15px;
  line-height: 1.5;
  color: var(--text-primary);
  font-family: inherit;
}

.composer-textarea::placeholder {
  color: var(--text-muted);
}

.composer-send {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  margin-bottom: 2px;
  padding: 0;
  border: none;
  border-radius: 12px;
  background: var(--gradient-primary);
  color: #fff;
  cursor: pointer;
  transition: transform 0.15s, opacity 0.15s, box-shadow 0.15s;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.28);
}

.composer-send:hover:not(:disabled) {
  transform: scale(1.04);
}

.composer-send:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

.composer-send .send-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: composer-spin 0.7s linear infinite;
}

@keyframes composer-spin {
  to { transform: rotate(360deg); }
}

.composer-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px 12px 8px;
  border-top: 1px solid var(--glass-border-soft);
  background: rgba(0, 0, 0, 0.04);
}

.composer-toolbar--flow {
  gap: 10px 14px;
}

.composer-step {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.composer-step-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  white-space: nowrap;
}

.composer-step-pills,
.composer-step-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.composer-pill-count {
  margin-left: 2px;
  opacity: 0.85;
}

.composer-source-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.composer-source-btn:hover,
.composer-source-btn.active {
  background: var(--glass-panel-hover);
  border-color: var(--glass-border-soft);
  color: var(--accent-primary);
}

.composer-toolbar-divider {
  width: 1px;
  height: 16px;
  background: var(--glass-border-soft);
  flex-shrink: 0;
}

.composer-type-pill {
  padding: 3px 10px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.composer-type-pill:hover {
  color: var(--text-primary);
  background: var(--glass-panel-hover);
}

.composer-type-pill--data.active {
  color: var(--accent-success);
  border-color: rgba(16, 185, 129, 0.4);
  background: rgba(16, 185, 129, 0.12);
}

.composer-type-pill--template.active {
  color: var(--accent-primary);
  border-color: rgba(99, 102, 241, 0.4);
  background: rgba(99, 102, 241, 0.12);
}

.composer-toolbar-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

@media (max-width: 640px) {
  .composer-toolbar-hint {
    display: none;
  }
}

.composer-library-panel {
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--glass-radius-sm);
  padding: 10px 12px;
  max-height: 220px;
  overflow: auto;
  background: var(--glass-panel-strong);
}

.library-io-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.library-io-label {
  font-size: 12px;
  color: var(--text-muted);
}

.library-io-select {
  flex: 1;
  min-width: 140px;
  max-width: 100%;
}

.library-picker-panel {
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--glass-radius-sm);
  padding: 8px;
  margin-bottom: 10px;
  max-height: 200px;
  overflow: auto;
  background: var(--glass-panel-strong);
}

.library-picker-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}

.library-picker-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  cursor: pointer;
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-primary);
}

.library-picker-item:hover {
  background: var(--glass-panel-hover);
}

.library-picker-item.selected {
  background: rgba(125, 211, 252, 0.15);
  color: var(--text-primary);
}

.library-picker-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
