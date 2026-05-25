import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import sessionApi from '../api/sessions'
import messageApi from '../api/messages'
import fileApi from '../api/files'
import agentApi from '../api/agents'
import { getAccessToken } from '../api/auth'
import { useFileStore } from './fileStore'

const SESSIONS_KEY = 'doc_sessions'
const MESSAGES_KEY = 'doc_messages_'

function readCache(key) {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function writeCache(key, data) {
  try {
    localStorage.setItem(key, JSON.stringify({ _ts: Date.now(), ...data }))
  } catch {}
}

function removeCache(key) {
  try {
    localStorage.removeItem(key)
  } catch {}
}

let messageIdCounter = 0

function createMessageId(prefix = 'msg') {
  messageIdCounter += 1
  return `${prefix}_${Date.now()}_${messageIdCounter}_${Math.random().toString(36).slice(2, 8)}`
}

function getFileCategory(fileName) {
  if (/.(docx?|pdf|txt|md)$/i.test(fileName)) return 'document'
  if (/.(xlsx?|csv)$/i.test(fileName)) return 'excel'
  return 'unknown'
}

function isTemplateFileMeta(f) {
  if (!f) return false
  if (String(f.file_type || '').toLowerCase() === 'template') return true
  return /模板|template/i.test(String(f.file_name || ''))
}

/** 数据源 Excel + 模板 → 走 table_filling 直达填表（避免混合模式只出 JSON） */
function shouldDirectTableFill(files, template_files, content = '') {
  const tpls = (template_files || []).filter(Boolean)
  if (!tpls.length) return false
  const dataExcel = (files || []).filter(
    (f) => getFileCategory(f?.file_name) === 'excel' && !isTemplateFileMeta(f),
  )
  if (!dataExcel.length) return false
  const docFiles = (files || []).filter((f) => getFileCategory(f?.file_name) === 'document')
  const fillIntent = /填|写入|导入|套用|模板|合并|同步/.test(String(content || ''))
  // 仅 Excel 数据源 + 模板（无 PDF 等文档）时直接填表
  if (docFiles.length === 0) return true
  // 同时有文档时交给混合模式（先提取再填表）
  if (docFiles.length > 0) return false
  return fillIntent
}

function tableFillHasFilledOutput(generated_files, tableData) {
  const list = [
    ...normalizeGeneratedFiles(generated_files),
    ...normalizeGeneratedFiles(tableData?.generated_files),
    ...fallbackGeneratedFilesFromTableData(tableData),
  ]
  return list.some((f) => {
    const name = String(f?.file_name || '').toLowerCase()
    const ft = String(f?.file_type || '').toLowerCase()
    return ['xlsx', 'xls', 'docx', 'doc'].includes(ft) || /\.(xlsx|xls|docx|doc)$/.test(name)
  })
}

function expandTableFillPrompt(content) {
  const t = String(content || '').trim()
  if (!t || /^(进行)?填表$/.test(t)) {
    return '先读取模板表头确定要填的字段，再从数据源按列名取对应数据并填入模板；若无额外筛选条件，使用全部数据行。'
  }
  if (/填|写入|套用|导入/.test(t) && !/筛选|过滤|大于|小于|从.*到|包含|等于|\d{4}/.test(t)) {
    return `${t}（先按模板字段在数据源中匹配列；若无额外筛选条件，使用全部数据行）`
  }
  return t
}

function finalizeTableFillProgressMessage(progressMsg, result, template_files, labels) {
  if (!progressMsg) return
  const tf = result?.resp?.tableFillingData || progressMsg.tableFillingData
  const files = normalizeGeneratedFiles(result?.generated_files)
  const filled = tableFillHasFilledOutput(files, tf)
  const baseMsg = String(tf?.message || '').trim()
  if (filled) {
    progressMsg.content = `填表完成：已将「${labels.src}」写入模板「${labels.tpl}」`
  } else if ((template_files || []).length) {
    progressMsg.content =
      baseMsg ||
      `未能生成填好的 Excel，仅输出筛选 JSON。请确认模板列名与数据源一致，并在「模板」栏勾选 ${labels.tpl}。`
  } else if (baseMsg) {
    progressMsg.content = baseMsg
  }
}

function saveSessionsCache(sessions, currentSessionId) {
  writeCache(SESSIONS_KEY, { sessions, currentSessionId })
}

function loadSessionsCache() {
  return readCache(SESSIONS_KEY)
}

async function sessionExistsOnServer(sessionId) {
  if (!sessionId) return false
  try {
    await sessionApi.get(sessionId)
    return true
  } catch {
    return false
  }
}

function parseApiTime(isoString) {
  if (isoString == null) return null
  if (typeof isoString === 'number' && Number.isFinite(isoString)) {
    const d = new Date(isoString)
    return isNaN(d.getTime()) ? null : d
  }
  let s = String(isoString).trim()
  if (!s) return null
  if (/^\d{10,13}$/.test(s)) {
    const ms = s.length === 10 ? Number(s) * 1000 : Number(s)
    const d = new Date(ms)
    return isNaN(d.getTime()) ? null : d
  }
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(s)) {
    s = s.replace(' ', 'T')
  }
  const hasTz = /[zZ]$/.test(s) || /(?:[+-]\d{2}:?\d{2}|[+-]\d{2})$/.test(s)
  const d = new Date(hasTz ? s : (s.includes('T') ? `${s}Z` : `${s}T00:00:00Z`))
  return isNaN(d.getTime()) ? null : d
}

function pickNewerIso(a, b) {
  const da = parseApiTime(a)
  const db = parseApiTime(b)
  if (!da && !db) return a || b || ''
  if (!da) return b || ''
  if (!db) return a || ''
  return da.getTime() >= db.getTime() ? (a || b) : (b || a)
}

function normalizeSessionItem(s) {
  const now = new Date().toISOString()
  if (!s) return { title: '新会话', created_at: now, updated_at: now }
  let created = s.created_at || s.updated_at || ''
  let updated = s.updated_at || s.created_at || ''
  if (!parseApiTime(updated) && parseApiTime(created)) updated = created
  if (!parseApiTime(created) && parseApiTime(updated)) created = updated
  if (!parseApiTime(updated) && !parseApiTime(created)) {
    created = now
    updated = now
  }
  const dc = parseApiTime(created)
  const du = parseApiTime(updated)
  return {
    ...s,
    created_at: dc ? dc.toISOString() : created || now,
    updated_at: du ? du.toISOString() : updated || now,
  }
}

function saveMessagesCache(sessionId, messages) {
  writeCache(MESSAGES_KEY + sessionId, { messages })
}

function loadMessagesCache(sessionId) {
  return readCache(MESSAGES_KEY + sessionId)
}

function normalizeGeneratedFiles(rawFiles) {
  if (Array.isArray(rawFiles)) return rawFiles
  if (!rawFiles) return []
  if (typeof rawFiles === 'string') {
    return [{ file_path: rawFiles, file_name: rawFiles.split(/[\\/]/).pop() || 'result' }]
  }
  if (typeof rawFiles === 'object') {
    return [rawFiles]
  }
  return []
}

function fallbackGeneratedFilesFromTableData(tableData) {
  if (!tableData || typeof tableData !== 'object') return []
  const out = []
  const templateOutput = tableData.template_output || tableData.templateOutput
  const outputJson = tableData.output_json || tableData.outputJson
  const suffixFromPath = (path) => {
    if (!path || typeof path !== 'string') return 'file'
    const ext = path.split(/[\\/]/).pop()?.split('.').pop()
    return ext ? ext.toLowerCase() : 'file'
  }
  if (templateOutput) {
    const path = String(templateOutput)
    out.push({
      file_path: path,
      file_name: path.split(/[\\/]/).pop() || `table_filling_result.${suffixFromPath(path)}`,
      download_label: '填好的表格',
    })
  }
  if (outputJson) {
    const path = String(outputJson)
    out.push({
      file_path: path,
      file_name: path.split(/[\\/]/).pop() || 'table_filling_result.json',
      download_label: '筛选数据 JSON',
    })
  }
  return out
}

function fallbackGeneratedFilesFromDocumentEditing(data) {
  if (!data || typeof data !== 'object') return []
  const existing = normalizeGeneratedFiles(data.generated_files || data.generatedFiles)
  if (existing.length > 0) return existing
  const outputFile = data.output_file || data.outputFile
  if (!outputFile) return []
  const path = String(outputFile)
  const suffix = path.split(/[\\/]/).pop()?.split('.').pop()
  return [
    {
      file_path: path,
      file_name: path.split(/[\\/]/).pop() || `edited.${suffix || 'docx'}`,
      download_label: '编辑后的文档',
    },
  ]
}

/** 识别文档编辑模式返回的 JSON 字符串 */
function tryParseDocumentEditingJson(text) {
  const s = String(text || '').trim()
  if (!s.startsWith('{')) return null
  try {
    const parsed = JSON.parse(s)
    if (!parsed || typeof parsed !== 'object') return null
    if (
      parsed.success === true ||
      parsed.generated_files ||
      parsed.generatedFiles ||
      parsed.output_file ||
      parsed.outputFile ||
      (typeof parsed.message === 'string' &&
        /文档编辑|ActionType|set_font|generated_files/i.test(parsed.message + JSON.stringify(parsed)))
    ) {
      return parsed
    }
  } catch {
    return null
  }
  return null
}

/** 将技术向摘要转为用户可读文案；兼容历史消息里残留的 JSON 正文 */
function humanizeDocumentEditMessage(raw) {
  let s = String(raw || '').trim()
  if (!s) return '文档编辑完成，已生成可下载文件。'
  const parsed = tryParseDocumentEditingJson(s)
  if (parsed) {
    s = String(parsed.message || '').trim()
  }
  s = s
    .replace(/\bActionType\.SET_FONT_FAMILY\b/gi, '设置正文字体')
    .replace(/\bActionType\.SET_FONT_COLOR\b/gi, '设置字体颜色')
    .replace(/\bActionType\.SET_FONT_SIZE\b/gi, '设置字号')
    .replace(/\bActionType\.(\w+)\b/g, (_, name) => {
      const key = String(name).toLowerCase()
      const map = {
        set_font_family: '设置字体',
        set_font_color: '设置字体颜色',
        set_font_size: '设置字号',
      }
      return map[key] || key.replace(/_/g, ' ')
    })
  if (!s || s.startsWith('{')) return '文档编辑完成，已生成可下载文件。'
  return s
}

function applyDocumentEditingResultToAssistantMessage(parsed) {
  if (!parsed || typeof parsed !== 'object') return
  const normalizedChunkFiles = normalizeGeneratedFiles(parsed.generated_files || parsed.generatedFiles)
  const fallbackFiles = fallbackGeneratedFilesFromDocumentEditing(parsed)
  if (normalizedChunkFiles.length > 0) {
    parsed.generated_files = normalizedChunkFiles
  } else if (fallbackFiles.length > 0) {
    parsed.generated_files = fallbackFiles
  }
  const summary = humanizeDocumentEditMessage(parsed.message || parsed)
  const lastMsg = messages.value[messages.value.length - 1]
  if (lastMsg && lastMsg.role === 'assistant') {
    lastMsg.content = summary
    lastMsg.documentEditingData = parsed
    if (parsed.generated_files?.length) {
      lastMsg.generated_files = parsed.generated_files
    }
  } else {
    messages.value.push({
      id: createMessageId('assistant'),
      role: 'assistant',
      content: summary,
      created_at: new Date().toISOString(),
      documentEditingData: parsed,
      generated_files: parsed.generated_files || [],
    })
  }
  pendingResultData = { documentEditingData: parsed }
}

async function loadJsonRowsFromArtifacts(sessionId, tableData, generatedFiles = []) {
  const candidates = []
  const outputJson = tableData?.output_json || tableData?.outputJson
  if (outputJson) {
    candidates.push({ kind: 'path', value: outputJson })
  }

  for (const artifact of [...normalizeGeneratedFiles(tableData?.generated_files), ...normalizeGeneratedFiles(generatedFiles)]) {
    if (!artifact || typeof artifact !== 'object') continue
    if (artifact.file_id != null) {
      candidates.push({ kind: 'session_file', file_id: artifact.file_id })
    }
    if (artifact.file_path) {
      candidates.push({ kind: 'path', value: artifact.file_path })
    }
  }

  const toRows = (parsed) => {
    if (Array.isArray(parsed)) return parsed
    if (!parsed || typeof parsed !== 'object') return []
    if (Array.isArray(parsed.rows)) return parsed.rows
    if (Array.isArray(parsed.filtered_rows)) return parsed.filtered_rows
    if (Array.isArray(parsed.previewData)) return parsed.previewData
    if (Array.isArray(parsed.entities)) return parsed.entities
    return []
  }

  for (const candidate of candidates) {
    try {
      let response = null
      if (candidate.kind === 'session_file' && sessionId && candidate.file_id != null) {
        const url = `/api/sessions/${encodeURIComponent(sessionId)}/files/${encodeURIComponent(candidate.file_id)}/download`
        response = await fetch(url)
      } else if (candidate.kind === 'path' && candidate.value) {
        const url = `/api/files/download?path=${encodeURIComponent(String(candidate.value))}`
        response = await fetch(url)
      }

      if (!response || !response.ok) continue

      const parsed = await response.json()
      const rows = toRows(parsed)
      if (rows.length > 0) return rows
    } catch (e) {
      continue
    }
  }

  return []
}

function normalizeMessageForResultDisplay(msg) {
  if (!msg || typeof msg !== 'object') return msg
  const normalized = { ...msg }
  let metadata = normalized.metadata
  if (typeof metadata === 'string') {
    try {
      metadata = JSON.parse(metadata)
    } catch {
      metadata = null
    }
  }
  if (!metadata || typeof metadata !== 'object') metadata = {}

  const rootGenerated = normalizeGeneratedFiles(
    normalized.generated_files || normalized.generatedFiles || normalized.output_files
  )
  const metaGenerated = normalizeGeneratedFiles(
    metadata.generated_files || metadata.generatedFiles || metadata.output_files
  )
  const finalGenerated = rootGenerated.length > 0 ? rootGenerated : metaGenerated
  if (finalGenerated.length > 0) {
    normalized.generated_files = finalGenerated
  }

  const tf = normalized.tableFillingData || metadata.tableFillingData || metadata.table_filling_data
  if (tf && typeof tf === 'object') {
    const tfGenerated = normalizeGeneratedFiles(tf.generated_files || tf.generatedFiles)
    const tfFallback = fallbackGeneratedFilesFromTableData(tf)
    normalized.tableFillingData = {
      ...tf,
      generated_files: tfGenerated.length > 0 ? tfGenerated : tfFallback,
    }
  }

  const de =
    normalized.documentEditingData ||
    metadata.documentEditingData ||
    metadata.document_editing_data
  if (de && typeof de === 'object') {
    const deGenerated = normalizeGeneratedFiles(de.generated_files || de.generatedFiles)
    const deFallback = fallbackGeneratedFilesFromDocumentEditing(de)
    normalized.documentEditingData = {
      ...de,
      generated_files: deGenerated.length > 0 ? deGenerated : deFallback,
    }
    if (!normalized.generated_files?.length && normalized.documentEditingData.generated_files?.length) {
      normalized.generated_files = normalized.documentEditingData.generated_files
    }
  }

  if (normalized.role === 'assistant' && normalized.content) {
    const inlineParsed = tryParseDocumentEditingJson(normalized.content)
    if (inlineParsed) {
      if (!normalized.documentEditingData) {
        normalized.documentEditingData = inlineParsed
      }
      const files = fallbackGeneratedFilesFromDocumentEditing(normalized.documentEditingData)
      if (files.length && !normalized.generated_files?.length) {
        normalized.generated_files = files
      }
    }
    normalized.content = humanizeDocumentEditMessage(
      normalized.documentEditingData?.message || normalized.content
    )
  }

  normalized.metadata = metadata
  return normalized
}

function findLatestMixedProgressMessage(messages, taskIndex, fileName = '') {
  if (!Array.isArray(messages) || messages.length === 0) return null
  const targetName = String(fileName || '').trim()
  // 优先按 taskIndex + 文件名从后往前匹配，避免命中历史旧消息
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (!m || m.role !== 'assistant' || !m.isProgressMessage) continue
    if (m.mixedTaskIndex !== taskIndex) continue
    if (targetName && String(m.content || '').includes(targetName)) return m
  }
  // 回退：仅按 taskIndex 从后往前匹配最近一条
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (!m || m.role !== 'assistant' || !m.isProgressMessage) continue
    if (m.mixedTaskIndex === taskIndex) return m
  }
  return null
}

export const useSessionStore = defineStore('session', () => {
  const sessions = ref([])
  const currentSessionId = ref(null)
  const messages = ref([])
  const isLoading = ref(false)
  const isInitializing = ref(true)
  const isStreaming = ref(false)
  const isCreatingSession = ref(false)
  const isUploadingFiles = ref(false)
  const uploadProgress = ref('')
  const sidebarCollapsed = ref(false)
  const ws = ref(null)
  const wsConnecting = ref(false)
  const wsSessionId = ref(null) // 追踪当前 WebSocket 连接对应的 session_id

  // 进度条相关（混合模式/实体提取/表格填表）
  const progressValue = ref(0)
  const progressMessage = ref('')
  const showProgressBar = ref(false)

  // WebSocket 回调（用于混合模式多任务处理）
  let pendingResolve = null
  let pendingResultData = null
  let loadingMsgId = null // 当前 loading 消息的 ID
  let isSending = false // 标记是否正在发送消息

  /** 移除 WebSocket 流式时的「三个点」loading 气泡（chunk/done/error/断线均需调用） */
  function removeAssistantLoadingBubble() {
    if (loadingMsgId === null) return
    const idx = messages.value.findIndex((m) => m.id === loadingMsgId)
    if (idx > -1) messages.value.splice(idx, 1)
    loadingMsgId = null
  }

  // 模式相关
  const currentMode = ref('default_conversation')
  const modeConfig = {
    'default_conversation': { requiresData: false, requiresTemplate: false },
    'document_understanding': { requiresData: true, requiresTemplate: false },
    'document_editing': { requiresData: true, requiresTemplate: false },
  }
  const currentModeConfig = computed(() => modeConfig[currentMode.value] || modeConfig['default_conversation'])

  function mapLibraryFileForPayload(f) {
    return {
      id: f.id,
      library_doc_id: f.library_doc_id || f.id,
      file_name: f.file_name,
      file_size: f.file_size,
      file_type: f.file_type || 'data',
      space_id: f.space_id,
      source: 'library',
      is_selected: true,
    }
  }

  function getSelectedFilesPayload() {
    const fileStore = useFileStore()
    const selected = (list) => list.filter((f) => f.is_selected)

    const tempDataFiles = selected(fileStore.tempFiles.data).filter((f) => f.original_file)
    const tempTemplateFiles = selected(fileStore.tempFiles.template).filter((f) => f.original_file)

    const libraryDataFiles = selected(fileStore.tempFiles.data)
      .filter((f) => f.library_doc_id && !f.original_file)
      .map(mapLibraryFileForPayload)
    const libraryTemplateFiles = selected(fileStore.tempFiles.template)
      .filter((f) => f.library_doc_id && !f.original_file)
      .map((f) => mapLibraryFileForPayload({ ...f, file_type: 'template' }))

    const uploadedDataFiles = selected(fileStore.tempFiles.data)
      .filter((f) => !f.original_file && !f.library_doc_id && (f.file_path || f.storage_key))
      .map((f) => ({
        id: f.id,
        file_name: f.file_name,
        file_path: f.file_path,
        storage_key: f.storage_key || f.file_path,
        file_size: f.file_size,
        file_type: f.file_type || 'data',
        is_selected: true,
      }))
    const uploadedTemplateFiles = selected(fileStore.tempFiles.template)
      .filter((f) => !f.original_file && !f.library_doc_id && (f.file_path || f.storage_key))
      .map((f) => ({
        id: f.id,
        file_name: f.file_name,
        file_path: f.file_path,
        storage_key: f.storage_key || f.file_path,
        file_size: f.file_size,
        file_type: 'template',
        is_selected: true,
      }))

    return {
      tempFiles: tempDataFiles.map((f) => ({ ...f })),
      tempTemplateFiles: tempTemplateFiles.map((f) => ({ ...f })),
      files: [...libraryDataFiles, ...uploadedDataFiles],
      template_files: [...libraryTemplateFiles, ...uploadedTemplateFiles],
    }
  }

  async function uploadTempFiles(tempDataFiles, tempTemplateFiles, onProgress) {
    const fileStore = useFileStore()
    const uploadedFiles = []
    const uploadedTemplateFiles = []
    const allFiles = [...tempDataFiles, ...tempTemplateFiles]
    let uploadedCount = 0

    for (const file of tempDataFiles) {
      try {
        const res = await fileApi.upload(currentSessionId.value, file.original_file, 'data')
        uploadedCount++
        onProgress?.(uploadedCount, allFiles.length)
        const filePath = res.file_path || res.path || res.storage_key || ''
        const updatedFileInfo = {
          id: res.id,
          file_name: res.file_name || file.file_name,
          file_path: filePath,
          storage_key: filePath,
          file_size: res.file_size || file.file_size,
          file_type: 'data',
          is_selected: true,
          created_at: res.created_at || new Date().toISOString(),
        }
        const index = fileStore.tempFiles.data.findIndex((f) => f.id === file.id)
        if (index > -1) {
          const prev = fileStore.tempFiles.data[index]
          const u = prev?.file_url
          if (u && String(u).startsWith('blob:')) {
            try { URL.revokeObjectURL(u) } catch (_) {}
          }
          fileStore.tempFiles.data[index] = updatedFileInfo
        }
        uploadedFiles.push(updatedFileInfo)
      } catch (e) {
        console.error('[uploadTempFiles] 上传数据文件失败:', e)
      }
    }

    for (const file of tempTemplateFiles) {
      try {
        const res = await fileApi.upload(currentSessionId.value, file.original_file, 'template')
        uploadedCount++
        onProgress?.(uploadedCount, allFiles.length)
        const filePath = res.file_path || res.path || res.storage_key || ''
        const updatedTemplateInfo = {
          id: res.id,
          file_name: res.file_name || file.file_name,
          file_path: filePath,
          storage_key: filePath,
          file_size: res.file_size || file.file_size,
          file_type: 'template',
          is_selected: true,
          created_at: res.created_at || new Date().toISOString(),
        }
        const index = fileStore.tempFiles.template.findIndex((f) => f.id === file.id)
        if (index > -1) {
          const prev = fileStore.tempFiles.template[index]
          const u = prev?.file_url
          if (u && String(u).startsWith('blob:')) {
            try { URL.revokeObjectURL(u) } catch (_) {}
          }
          fileStore.tempFiles.template[index] = updatedTemplateInfo
        }
        uploadedTemplateFiles.push(updatedTemplateInfo)
      } catch (e) {
        console.error('[uploadTempFiles] 上传模板文件失败:', e)
      }
    }

    return { uploadedFiles, uploadedTemplateFiles }
  }

  // 清除所有选中的文件（仅本地缓冲区，不请求后端）
  function clearAllSelectedFiles() {
    const fileStore = useFileStore()
    fileStore.tempFiles.data.forEach(f => { f.is_selected = false })
    fileStore.tempFiles.template.forEach(f => { f.is_selected = false })
  }

  /** 上传区不展示/同步会话服务端文件列表，保留空实现以兼容创建/切换会话时的调用 */
  async function loadFiles(_sessionId) {}

  const currentSession = computed(() =>
    sessions.value.find(s => s.session_id === currentSessionId.value)
  )

  function formatTime(isoString) {
    const date = parseApiTime(isoString)
    if (!date) return ''
    const now = new Date()
    const diff = now - date
    const diffDays = Math.floor(diff / 86400000)

    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
    if (diff < 86400000) {
      // 今天：显示 HH:mm
      return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
    }
    if (diffDays < 3) {
      return `${diffDays}天前`
    }
    // 3天及以上：显示日期
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}/${month}/${day}`
  }

  async function switchMode(mode) {
    if (currentMode.value === mode) return
    currentMode.value = mode

    const modeNames = {
      'default_conversation': '默认对话',
      'document_understanding': '文档理解',
      'document_editing': '文档编辑',
      'mixed': '提取与填表',
    }

    messages.value.push({
      id: createMessageId('system'),
      role: 'system',
      content: `已切换至「${modeNames[mode] || mode}」模式`,
      created_at: new Date().toISOString(),
    })

    // 同步模式到服务器
    if (currentSessionId.value) {
      const idx = sessions.value.findIndex(s => s.session_id === currentSessionId.value)
      if (idx !== -1) {
        sessions.value[idx] = { ...sessions.value[idx], current_mode: mode }
        saveSessionsCache(sessions.value, currentSessionId.value)
      }
      sessionApi.update(currentSessionId.value, { current_mode: mode }).catch(e =>
        console.warn('[switchMode] 更新模式失败:', e.message)
      )
    }
  }

  async function loadSessions() {
    try {
      const cached = loadSessionsCache()
      const cachedById = new Map((cached?.sessions || []).map(s => [s.session_id, s]))

      const res = await sessionApi.list()
      let items = (res.items || []).map(s => {
        const hit = cachedById.get(s.session_id)
        return normalizeSessionItem({
          ...(hit || {}),
          ...s,
          created_at: s.created_at || hit?.created_at,
          updated_at: pickNewerIso(s.updated_at, hit?.updated_at) || s.updated_at || hit?.updated_at,
        })
      })

      sessions.value = items
      saveSessionsCache(sessions.value, currentSessionId.value)

      // 如果有当前会话，同步 current_mode
      if (currentSessionId.value) {
        const sess = sessions.value.find(s => s.session_id === currentSessionId.value)
        console.log('[loadSessions] 查找当前会话:', currentSessionId.value, '结果:', sess)
        if (sess?.current_mode) {
          currentMode.value = sess.current_mode
          console.log('[loadSessions] 从服务器同步 currentMode:', currentMode.value)
        } else {
          console.log('[loadSessions] 服务器会话无current_mode, 保持 currentMode:', currentMode.value)
        }
      }
    } catch (e) {
      console.error('[loadSessions] 加载会话列表失败:', e)
    }
  }

  function _clearChatSurface() {
    isStreaming.value = false
    showProgressBar.value = false
    progressValue.value = 0
    messages.value = []
  }

  function _waitPaint() {
    return new Promise((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(resolve))
    })
  }

  async function createSession() {
    if (isCreatingSession.value) return
    isCreatingSession.value = true

    const previousSessionId = currentSessionId.value

    const prevWs = ws.value
    if (prevWs) {
      prevWs.onclose = null
      prevWs.onerror = null
      prevWs.close()
      ws.value = null
    }

    _clearChatSurface()
    await _waitPaint()

    try {
      const now = new Date().toISOString()
      const res = await sessionApi.create({ title: '新会话', current_mode: 'default_conversation' })
      const normalized = normalizeSessionItem({
        ...res,
        created_at: res.created_at || now,
        updated_at: res.updated_at || now,
      })
      sessions.value = [normalized, ...sessions.value.filter((s) => s.session_id !== res.session_id)]
      currentSessionId.value = res.session_id
      currentMode.value = 'default_conversation'
      saveSessionsCache(sessions.value, res.session_id)
      connectWebSocket()
      loadFiles(res.session_id).catch(console.error)
    } catch (e) {
      console.error('创建会话失败:', e)
      if (previousSessionId) {
        await selectSession(previousSessionId)
      }
    } finally {
      isCreatingSession.value = false
    }
  }

  async function selectSession(sessionId) {
    if (currentSessionId.value === sessionId) return

    const prevWs = ws.value
    if (prevWs) {
      prevWs.onclose = null
      prevWs.onerror = null
      prevWs.close()
    }

    currentSessionId.value = sessionId

    // 切换到该会话保存的模式（如果没有则使用默认模式）
    const sess = sessions.value.find(s => s.session_id === sessionId)
    currentMode.value = sess?.current_mode || 'default_conversation'

    messages.value = []
    await new Promise(resolve => setTimeout(resolve, 100))
    connectWebSocket()

    const cachedMsgs = loadMessagesCache(sessionId)
    if (cachedMsgs && cachedMsgs.messages?.length > 0) {
      messages.value = cachedMsgs.messages
    } else {
      loadMessages(sessionId).catch(console.error)
    }

    // 从数据库加载文件列表
    loadFiles(sessionId).catch(console.error)

    saveSessionsCache(sessions.value, sessionId)
  }

  async function deleteSession(sessionId) {
    const wasCurrentSession = currentSessionId.value === sessionId
    const remainingSessions = sessions.value.filter(s => s.session_id !== sessionId)
    sessions.value = remainingSessions

    const nextSession = remainingSessions[0]
    const nextSessionId = nextSession?.session_id || null
    saveSessionsCache(remainingSessions, nextSessionId)
    removeCache(MESSAGES_KEY + sessionId)

    if (wasCurrentSession) {
      if (nextSession) {
        currentSessionId.value = nextSession.session_id
        messages.value = []
        const wsPrev = ws.value
        if (wsPrev) {
          wsPrev.onclose = null
          wsPrev.onerror = null
          wsPrev.close()
        }
        connectWebSocket()
        const cachedMsgs = loadMessagesCache(nextSession.session_id)
        if (cachedMsgs?.messages?.length > 0) {
          messages.value = cachedMsgs.messages
        } else {
          loadMessages(nextSession.session_id).catch(console.error)
        }
      } else {
        currentSessionId.value = null
        messages.value = []
        disconnectWebSocket()
      }
    }

    try {
      await sessionApi.delete(sessionId)
    } catch (e) {
      console.error('删除会话失败:', e)
    }
  }

  async function updateSessionTitle(sessionId, title) {
    try {
      const res = await sessionApi.update(sessionId, { title })
      const idx = sessions.value.findIndex(s => s.session_id === sessionId)
      if (idx !== -1) {
        sessions.value[idx] = { ...sessions.value[idx], ...res }
        saveSessionsCache(sessions.value, currentSessionId.value)
      }
    } catch (e) {
      console.error('更新会话失败:', e)
    }
  }

  function persistMessages(sessionId, msgs) {
    saveMessagesCache(sessionId, msgs)
    if (!sessionId) return
    const iso = new Date().toISOString()
    const idx = sessions.value.findIndex(s => s.session_id === sessionId)
    if (idx !== -1) {
      sessions.value[idx] = { ...sessions.value[idx], updated_at: iso }
      saveSessionsCache(sessions.value, currentSessionId.value)
    }
  }

  async function loadMessages(sessionId) {
    try {
      const res = await messageApi.list(sessionId)
      const msgs = (Array.isArray(res) ? res : []).map(normalizeMessageForResultDisplay)
      if (msgs.length > 0 || currentSessionId.value === sessionId) {
        messages.value = msgs
        persistMessages(sessionId, msgs)
      }
    } catch (e) {
      console.warn('加载消息失败:', e.message)
    }
  }

  async function connectWebSocket(targetSessionId = null) {
    // 如果没有指定 sessionId，使用当前的
    const sessionId = targetSessionId || currentSessionId.value
    
    // 跳过临时 ID（会话尚未在服务器上创建）
    if (!sessionId || sessionId.startsWith('temp_')) {
      console.log('[connectWebSocket] 跳过临时 session_id:', sessionId)
      return
    }

    // 如果有连接正在进行，等待它完成后再继续
    if (wsConnecting.value) {
      console.log('[connectWebSocket] 等待现有连接完成...')
      const result = await waitForWebSocketOpen(3000)
      // 等待后再次检查
      if (ws.value && wsSessionId.value === sessionId && ws.value.readyState === WebSocket.OPEN) {
        console.log('[connectWebSocket] 等待后连接已就绪')
        return
      }
      // 如果等待后连接已关闭或失败，重置状态
      if (!ws.value || ws.value.readyState === WebSocket.CLOSED) {
        console.log('[connectWebSocket] 等待后发现连接已关闭，重置状态')
        wsConnecting.value = false
        ws.value = null
        wsSessionId.value = null
      }
    }

    // 如果已有活跃连接且 session_id 相同，不再创建新连接
    if (ws.value && wsSessionId.value === sessionId) {
      if (ws.value.readyState === WebSocket.OPEN) {
        console.log('[connectWebSocket] 已存在相同 session_id 的 OPEN 连接，保持不变')
        return
      }
      if (ws.value.readyState === WebSocket.CONNECTING) {
        console.log('[connectWebSocket] 相同 session_id 正在连接中，等待...')
        await waitForWebSocketOpen(5000)
        return
      }
      // 连接已关闭或失败
      if (ws.value.readyState === WebSocket.CLOSED) {
        console.log('[connectWebSocket] 旧连接已关闭')
        ws.value = null
        wsSessionId.value = null
      }
    }

    // 仅当「目标会话」与当前 WS 一致且连接可用时才复用；换会话时必须走到下方关闭旧连接再建新连接。
    if (
      ws.value &&
      wsSessionId.value === sessionId &&
      (ws.value.readyState === WebSocket.OPEN || ws.value.readyState === WebSocket.CONNECTING)
    ) {
      return
    }

    if (wsConnecting.value) return

    // 如果有现有连接，先关闭
    if (ws.value) {
      console.log('[connectWebSocket] 关闭旧连接')
      ws.value.onclose = null
      ws.value.onerror = null
      try {
        ws.value.close()
      } catch (e) {
        console.warn('[connectWebSocket] 关闭旧连接失败:', e)
      }
      ws.value = null
      wsSessionId.value = null
    }

    isStreaming.value = false
    wsConnecting.value = true
    wsSessionId.value = sessionId
    console.log('[connectWebSocket] 创建新连接, session_id:', wsSessionId.value)

    ws.value = messageApi.connect(sessionId)

    ws.value.onmessage = (event) => {
      let data
      try {
        data = JSON.parse(event.data)
      } catch (parseErr) {
        console.error('[WebSocket onmessage] JSON 解析失败:', parseErr, event.data?.slice?.(0, 200))
        removeAssistantLoadingBubble()
        isStreaming.value = false
        isSending = false
        return
      }
      console.log('[WebSocket onmessage] 收到消息:', event.data)
      console.log('[WebSocket onmessage] 解析后:', data)
      if (data.type === 'start') {
        console.log('[WebSocket onmessage] type=start, 收到开始信号')
        isStreaming.value = true
        // 实体提取/表格填表/混合模式显示进度条
        const isEntityOrTable = data.result_type === 'entity_extraction' ||
                               data.result_type === 'table_filling' ||
                               data.mode === 'entity_extraction' ||
                               data.mode === 'table_filling'
        console.log('[WebSocket onmessage] isEntityOrTable:', isEntityOrTable, 'result_type:', data.result_type, 'mode:', data.mode)
        if (isEntityOrTable) {
          showProgressBar.value = true
          progressValue.value = 0
          progressMessage.value = data.result_type === 'table_filling' || data.mode === 'table_filling'
            ? '正在将数据填入模板...'
            : '开始提取...'
        }
      } else if (data.type === 'progress') {
        console.log('[WebSocket onmessage] type=progress:', data.progress, data.message)
        progressValue.value = data.progress
        progressMessage.value = data.message
      } else if (data.type === 'chunk') {
        console.log('[WebSocket onmessage] type=chunk, result_type:', data.result_type, 'content长度:', data.content?.length)
        isStreaming.value = false
        removeAssistantLoadingBubble()
        const piece =
          typeof data.content === 'string'
            ? data.content
            : data.content == null
              ? ''
              : String(data.content)
        // 实体提取结果处理
        if (data.result_type === 'entity_extraction') {
          try {
            const parsed = JSON.parse(data.content)
            if (parsed?.success === false) {
              const errText = parsed.message || '实体提取失败'
              const lastErr = messages.value[messages.value.length - 1]
              if (lastErr && lastErr.role === 'assistant') {
                lastErr.content = errText
                lastErr.entitiesData = []
              } else {
                messages.value.push({
                  id: createMessageId('assistant'),
                  role: 'assistant',
                  content: errText,
                  created_at: new Date().toISOString(),
                })
              }
              pendingResultData = { extractionData: parsed, entities: [] }
              console.warn('[WebSocket onmessage] 实体提取失败:', errText)
            } else {
              const entities = Array.isArray(parsed?.entities) ? parsed.entities : []
              const count = entities.length
              const summary = `实体提取完成，共提取 ${count} 条数据`
              const lastMsg = messages.value[messages.value.length - 1]
              if (lastMsg && lastMsg.role === 'assistant') {
                lastMsg.content = summary
                lastMsg.entitiesData = entities
              } else {
                messages.value.push({
                  id: createMessageId('assistant'),
                  role: 'assistant',
                  content: summary,
                  created_at: new Date().toISOString(),
                  entitiesData: entities,
                })
              }
              pendingResultData = { extractionData: parsed, entities }
              console.log('[WebSocket onmessage] 实体提取结果解析成功, count:', count, 'keys:', Object.keys(parsed))
            }
          } catch (e) {
            console.error('[WebSocket onmessage] 解析实体提取结果失败:', e)
          }
        } else if (data.result_type === 'table_filling') {
          try {
            let parsed = null
            if (typeof data.content === 'string') {
              parsed = JSON.parse(data.content)
            } else if (data.content && typeof data.content === 'object') {
              parsed = data.content
            }
            if (!parsed || typeof parsed !== 'object') {
              throw new Error('table_filling chunk 内容不是有效对象')
            }
            console.log('[WebSocket onmessage] table_filling parsed, keys:', Object.keys(parsed), 'generated_files:', parsed.generated_files)
            const normalizedChunkFiles = normalizeGeneratedFiles(
              parsed.generated_files || parsed.generatedFiles || parsed.output_files
            )
            if (!Array.isArray(parsed.generated_files) || parsed.generated_files.length === 0) {
              const fallbackFiles = fallbackGeneratedFilesFromTableData(parsed)
              if (normalizedChunkFiles.length > 0) {
                parsed.generated_files = normalizedChunkFiles
              } else if (fallbackFiles.length > 0) {
                parsed.generated_files = fallbackFiles
              }
            }
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.tableFillingData = parsed
            } else {
              messages.value.push({
                id: createMessageId('assistant'),
                role: 'assistant',
                content: parsed.message || '',
                created_at: new Date().toISOString(),
                tableFillingData: parsed,
              })
            }
            pendingResultData = { tableFillingData: parsed }
            console.log('[WebSocket onmessage] table_filling stored, msg count:', messages.value.length, 'lastMsg.tableFillingData:', !!messages.value[messages.value.length - 1]?.tableFillingData)
          } catch (e) {
            console.error('[WebSocket onmessage] 解析表格填表结果失败:', e)
          }
        } else if (data.result_type === 'document_editing') {
          try {
            let parsed = null
            if (typeof data.content === 'string') {
              parsed = JSON.parse(data.content)
            } else if (data.content && typeof data.content === 'object') {
              parsed = data.content
            }
            if (!parsed || typeof parsed !== 'object') {
              throw new Error('document_editing chunk 内容不是有效对象')
            }
            applyDocumentEditingResultToAssistantMessage(parsed)
          } catch (e) {
            console.error('[WebSocket onmessage] 解析文档编辑结果失败:', e)
            const fallback = tryParseDocumentEditingJson(piece)
            if (fallback) {
              applyDocumentEditingResultToAssistantMessage(fallback)
            }
          }
        } else {
          const docEditParsed = tryParseDocumentEditingJson(piece)
          if (docEditParsed) {
            applyDocumentEditingResultToAssistantMessage(docEditParsed)
          } else {
            // 普通流式文本
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.content += piece
            } else {
              messages.value.push({
                id: createMessageId('assistant'),
                role: 'assistant',
                content: piece,
                created_at: new Date().toISOString(),
              })
            }
          }
        }
      } else if (data.type === 'done') {
        console.log('[WebSocket onmessage] type=done, pendingResolve:', !!pendingResolve, 'generated_files:', data.generated_files)
        removeAssistantLoadingBubble()
        isStreaming.value = false
        isSending = false
        showProgressBar.value = false
        progressValue.value = 100
        progressMessage.value = '处理完成'
        const normalizedDoneFiles = normalizeGeneratedFiles(
          data.generated_files || data.generatedFiles || data.output_files
        )
        const pendingTableData = pendingResultData?.tableFillingData
        const pendingDocEditData = pendingResultData?.documentEditingData
        const pendingTableFiles = normalizeGeneratedFiles(
          pendingTableData?.generated_files || pendingTableData?.generatedFiles
        )
        const pendingDocEditFiles = normalizeGeneratedFiles(
          pendingDocEditData?.generated_files || pendingDocEditData?.generatedFiles
        )
        const pendingFallbackFiles = fallbackGeneratedFilesFromTableData(pendingTableData)
        const pendingDocEditFallback = fallbackGeneratedFilesFromDocumentEditing(pendingDocEditData)
        const doneDocEditData = data.document_editing_data || data.documentEditingData
        const doneDocEditFallback = fallbackGeneratedFilesFromDocumentEditing(doneDocEditData)
        let finalGeneratedFiles = normalizedDoneFiles
        if (!finalGeneratedFiles.length) {
          finalGeneratedFiles =
            pendingDocEditFiles.length > 0
              ? pendingDocEditFiles
              : pendingDocEditFallback.length > 0
                ? pendingDocEditFallback
                : doneDocEditFallback
        }
        if (!finalGeneratedFiles.length) {
          finalGeneratedFiles =
            pendingTableFiles.length > 0 ? pendingTableFiles : pendingFallbackFiles
        }
        // 把 generated_files 存入最后一条助手消息
        if (finalGeneratedFiles.length > 0) {
          let lastMsg = messages.value[messages.value.length - 1]
          if (!lastMsg || lastMsg.role !== 'assistant') {
            lastMsg = {
              id: createMessageId('assistant'),
              role: 'assistant',
              content: '',
              created_at: new Date().toISOString(),
            }
            messages.value.push(lastMsg)
          }
          lastMsg.generated_files = finalGeneratedFiles
          // 表格填表 chunk 与 done 分开发字段时，合并进 tableFillingData 便于前端统一展示/下载
          if (lastMsg.tableFillingData && typeof lastMsg.tableFillingData === 'object') {
            lastMsg.tableFillingData.generated_files = finalGeneratedFiles
          } else if (pendingTableData && typeof pendingTableData === 'object') {
            lastMsg.tableFillingData = {
              ...pendingTableData,
              generated_files: finalGeneratedFiles,
            }
          }
          if (lastMsg.documentEditingData && typeof lastMsg.documentEditingData === 'object') {
            lastMsg.documentEditingData.generated_files = finalGeneratedFiles
          } else if (pendingDocEditData && typeof pendingDocEditData === 'object') {
            lastMsg.documentEditingData = {
              ...pendingDocEditData,
              generated_files: finalGeneratedFiles,
            }
          }
          const deForText =
            lastMsg.documentEditingData || doneDocEditData || pendingDocEditData
          if (tryParseDocumentEditingJson(lastMsg.content) || deForText) {
            lastMsg.content = humanizeDocumentEditMessage(
              deForText?.message || lastMsg.content
            )
          }
        }
        if (!finalGeneratedFiles.length) {
          const last = messages.value[messages.value.length - 1]
          const emptyAssistant =
            last && last.role === 'assistant' && !(String(last.content || '').trim())
          const noAssistant = !last || last.role !== 'assistant'
          if (noAssistant || emptyAssistant) {
            const text = '（未收到模型输出，请检查 LLM 配置、网络或服务端日志）'
            if (noAssistant) {
              messages.value.push({
                id: createMessageId('assistant'),
                role: 'assistant',
                content: text,
                created_at: new Date().toISOString(),
              })
            } else {
              last.content = text
            }
          }
        }
        if (currentSessionId.value) {
          persistMessages(currentSessionId.value, messages.value)
        }
        if (pendingResolve) {
          const resolveData = { success: true, resp: pendingResultData }
          if (finalGeneratedFiles.length > 0) resolveData.generated_files = finalGeneratedFiles
          console.log('[WebSocket onmessage] 调用 pendingResolve', resolveData)
          pendingResolve(resolveData)
          pendingResolve = null
          pendingResultData = null
        }
      } else if (data.type === 'error') {
        const errorMsg = typeof data.message === 'string' ? data.message : JSON.stringify(data.message)
        console.error('[WebSocket onmessage] type=error:', errorMsg, 'pendingResolve:', !!pendingResolve)
        removeAssistantLoadingBubble()
        isStreaming.value = false
        isSending = false
        showProgressBar.value = false
        if (pendingResolve) {
          pendingResolve({ success: false, error: errorMsg })
          pendingResolve = null
          pendingResultData = null
        } else {
          messages.value.push({
            id: createMessageId('assistant'),
            role: 'assistant',
            content: `回复失败：${errorMsg}`,
            created_at: new Date().toISOString(),
          })
          if (currentSessionId.value) {
            persistMessages(currentSessionId.value, messages.value)
          }
        }
      } else {
        console.log('[WebSocket onmessage] 未知类型:', data.type)
      }
    }

    ws.value.onclose = () => {
      console.log('[WebSocket onclose] 连接已关闭, session_id:', wsSessionId.value, 'pendingResolve:', !!pendingResolve)
      const notifyDisconnect =
        !pendingResolve && (isSending || isStreaming.value || loadingMsgId !== null)
      removeAssistantLoadingBubble()
      ws.value = null
      wsSessionId.value = null
      isStreaming.value = false
      isSending = false
      wsConnecting.value = false
      if (notifyDisconnect) {
        messages.value.push({
          id: createMessageId('assistant'),
          role: 'assistant',
          content: '连接已断开，请确认后端已启动（建议在 src 目录下运行 uvicorn）并重试。',
          created_at: new Date().toISOString(),
        })
        if (currentSessionId.value) {
          persistMessages(currentSessionId.value, messages.value)
        }
      }
    }

    ws.value.onerror = (err) => {
      console.warn('[WebSocket onerror] 连接失败:', err, 'pendingResolve:', !!pendingResolve)
      removeAssistantLoadingBubble()
      ws.value = null
      wsSessionId.value = null
      wsConnecting.value = false
      if (pendingResolve) {
        console.log('[WebSocket onerror] 通过 pendingResolve 报告失败')
        pendingResolve({ success: false, error: 'WebSocket连接错误' })
        pendingResolve = null
        pendingResultData = null
      }
    }

    ws.value.onopen = () => {
      console.log('[WebSocket] onopen - 连接已建立, session_id:', wsSessionId.value)
      wsConnecting.value = false
    }

    ws.value.send = new Proxy(ws.value.send, {
      apply(target, thisArg, args) {
        console.log('[WebSocket] 发送消息:', args[0] ? JSON.parse(args[0]) : args[0])
        return target.apply(thisArg, args)
      }
    })
  }

  function disconnectWebSocket() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
      wsSessionId.value = null
    }
    isStreaming.value = false
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  async function waitForWebSocketOpen(maxMs = 8000) {
    return new Promise((resolve) => {
      const socket = ws.value
      if (!socket) {
        console.log('[waitForWebSocketOpen] 无 WebSocket 实例')
        resolve(false)
        return
      }
      console.log('[waitForWebSocketOpen] readyState:', socket.readyState, '(0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED)')
      if (socket.readyState === WebSocket.OPEN) {
        console.log('[waitForWebSocketOpen] 已 OPEN')
        resolve(true)
        return
      }
      if (socket.readyState === WebSocket.CLOSED) {
        console.log('[waitForWebSocketOpen] 连接已关闭，重置状态')
        wsConnecting.value = false
        ws.value = null
        wsSessionId.value = null
        resolve(false)
        return
      }
      if (socket.readyState === WebSocket.CONNECTING) {
        console.log('[waitForWebSocketOpen] 等待 CONNECTING...')
      }
      const start = Date.now()
      const t = setInterval(() => {
        if (!ws.value || ws.value !== socket) {
          console.log('[waitForWebSocketOpen] WebSocket 实例已变化')
          clearInterval(t)
          resolve(false)
          return
        }
        console.log('[waitForWebSocketOpen] polling readyState:', socket.readyState)
        if (socket.readyState === WebSocket.OPEN) {
          clearInterval(t)
          console.log('[waitForWebSocketOpen] OPEN!')
          resolve(true)
          return
        }
        if (socket.readyState === WebSocket.CLOSED || socket.readyState === WebSocket.CLOSING) {
          clearInterval(t)
          console.log('[waitForWebSocketOpen] 已 CLOSED/CLOSING，重置状态')
          wsConnecting.value = false
          ws.value = null
          wsSessionId.value = null
          resolve(false)
          return
        }
        if (Date.now() - start > maxMs) {
          clearInterval(t)
          console.log('[waitForWebSocketOpen] 超时')
          resolve(false)
          return
        }
      }, 50)
    })
  }

  async function sendMessage(content, mode = 'default_conversation') {
    if (!content.trim()) return

    if (!currentSessionId.value) {
      await createSession()
    }

    let sessionId = currentSessionId.value
    const listed = sessions.value.some((s) => s.session_id === sessionId)
    if (!listed || !(await sessionExistsOnServer(sessionId))) {
      console.warn('[sendMessage] 当前会话在服务端不存在，重新创建:', sessionId)
      if (sessionId) {
        sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
        removeCache(MESSAGES_KEY + sessionId)
      }
      await createSession()
      sessionId = currentSessionId.value
    }
    if (!sessionId) return
    const payload = getSelectedFilesPayload()
    const {
      tempFiles,
      tempTemplateFiles,
      files: uploadedFiles,
      template_files: uploadedTemplateFiles,
    } = payload
    const effectiveMode = mode || currentMode.value || 'default_conversation'
    const hasPendingFiles = tempFiles.length > 0 || tempTemplateFiles.length > 0

    const tempMsgId = createMessageId('user')
    messages.value.push({
      id: tempMsgId,
      role: 'user',
      content: content.trim(),
      created_at: new Date().toISOString(),
      metadata: {
        files: [
          ...uploadedFiles.map((f) => ({ ...f, pending: false })),
          ...tempFiles.map((f) => ({ file_name: f.file_name, file_size: f.file_size, pending: true })),
        ],
        template_files: [
          ...uploadedTemplateFiles.map((f) => ({ ...f, pending: false })),
          ...tempTemplateFiles.map((f) => ({ file_name: f.file_name, file_size: f.file_size, pending: true })),
        ],
      },
    })

    isStreaming.value = true

    let allFiles = [...uploadedFiles]
    let allTemplateFiles = [...uploadedTemplateFiles]

    if (hasPendingFiles) {
      const totalFiles = tempFiles.length + tempTemplateFiles.length
      isUploadingFiles.value = true
      uploadProgress.value = `正在上传文件 (0/${totalFiles})...`

      uploadTempFiles(tempFiles, tempTemplateFiles, (count, total) => {
        uploadProgress.value = `正在上传文件 (${count}/${total})...`
      })
        .then(({ uploadedFiles: newFiles, uploadedTemplateFiles: newTemplateFiles }) => {
          allFiles = [...allFiles, ...newFiles]
          allTemplateFiles = [...allTemplateFiles, ...newTemplateFiles]
          isUploadingFiles.value = false

          const msgIndex = messages.value.findIndex((m) => m.id === tempMsgId)
          if (msgIndex > -1) {
            messages.value[msgIndex].metadata = {
              files: allFiles.map((f) => ({ ...f, pending: false })),
              template_files: allTemplateFiles.map((f) => ({ ...f, pending: false })),
            }
          }

          sendToBackend(sessionId, content.trim(), effectiveMode, allFiles, allTemplateFiles)
        })
        .catch((err) => {
          console.error('[sendMessage] 上传文件失败:', err)
          isUploadingFiles.value = false
          sendToBackend(sessionId, content.trim(), effectiveMode, allFiles, allTemplateFiles)
        })
    } else {
      sendToBackend(sessionId, content.trim(), effectiveMode, allFiles, allTemplateFiles)
    }
  }

  async function sendToBackend(sessionId, content, mode, files, template_files) {
    // 数据源 + 模板 + 填表意图：优先走 table_filling（避免混合模式只筛 JSON 不填模板）
    if (shouldDirectTableFill(files, template_files, content)) {
      await runDirectTableFillTask(content, files, template_files)
      return
    }

    // 混合模式：自动分发任务
    if (mode === 'mixed') {
      await runMixedMode(content, files, template_files)
      return
    }

    if (mode === 'entity_extraction') {
      const hasSource = Array.isArray(files) && files.length > 0
      const hasTemplate = Array.isArray(template_files) && template_files.length > 0
      if (!hasSource || !hasTemplate) {
        isStreaming.value = false
        messages.value.push({
          id: createMessageId('assistant'),
          role: 'assistant',
          content:
            '实体提取需要同时提供：① 待提取文档（txt / docx / pdf / md）② Excel 模板（xlsx）。请在上传区分别添加「数据文件」和「模板文件」后再发送。',
          created_at: new Date().toISOString(),
        })
        return
      }
    }

    console.log('[sendToBackend] 发送请求:', { sessionId, content, mode, files, template_files })
    
    // 添加助手 loading 消息（立即显示）
    loadingMsgId = createMessageId('assistant-loading')
    messages.value.push({
      id: loadingMsgId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      isLoading: true,
    })
    
    // 检查 WebSocket 连接是否匹配当前 session
    let canStream = await waitForWebSocketOpen(5000) // 等待最多 5 秒
    const wsMatch = ws.value && wsSessionId.value === sessionId
    
    // 如果需要但没有匹配的 WebSocket 连接，建立新连接
    if (!wsMatch || !canStream) {
      console.log('[sendToBackend] 建立 WebSocket 连接, sessionId:', sessionId)
      connectWebSocket(sessionId)
      canStream = await waitForWebSocketOpen(5000)
    }

    // 重连后必须用当前状态判断（勿复用上面的 wsMatch，否则永远走 HTTP 回退）
    const wsReady =
      ws.value &&
      ws.value.readyState === WebSocket.OPEN &&
      wsSessionId.value === sessionId &&
      canStream

    if (wsReady) {
      console.log('[sendToBackend] 通过 WebSocket 发送, session_id:', sessionId)
      clearAllSelectedFiles()
      isSending = true
      ws.value.send(JSON.stringify({
        content,
        mode,
        files,
        template_files,
      }))
    } else {
      console.log('[sendToBackend] 通过 API 发送, wsMatch:', wsMatch, 'canStream:', canStream)
      clearAllSelectedFiles()
      try {
        await messageApi.send(sessionId, {
          content,
          mode,
          files,
          template_files,
          metadata: {
          },
        })
        try {
          await loadMessages(sessionId)
        } catch (le) {
          console.warn('[sendToBackend] 消息已发送，但刷新历史失败:', le.message)
        }
      } catch (e) {
        console.error('[sendToBackend] 发送消息失败:', e)
        messages.value.push({
          id: createMessageId('assistant'),
          role: 'assistant',
          content: `发送失败: ${e.message}`,
          created_at: new Date().toISOString(),
        })
      } finally {
        isStreaming.value = false
        isSending = false
      }
    }
  }

  // 合并混合模式多个任务的实体数据
  async function mergeMixedEntities(results) {
    const mergedEntities = []
    let entityCount = 0
    let tableRowCount = 0

    for (const r of results) {
      const mode = r?.task?.mode || r?.mode || r?.result_type
      if (mode === 'entity_extraction') {
        const entities = r?.resp?.extractionData?.entities || []
        for (const entity of entities) {
          if (entity && typeof entity === 'object') {
            mergedEntities.push(entity)
            entityCount += 1
          }
        }
      } else if (mode === 'table_filling') {
        const tf = r?.resp?.tableFillingData
        if (!tf || typeof tf !== 'object') continue

        const rows = await loadJsonRowsFromArtifacts(
          currentSessionId.value,
          tf,
          r?.generated_files || []
        )
        if (!rows.length) {
          if (Array.isArray(tf.filtered_rows) && tf.filtered_rows.length) {
            rows.push(...tf.filtered_rows)
          } else if (Array.isArray(tf.previewData) && tf.previewData.length) {
            rows.push(...tf.previewData)
          }
        }

        const mapping = tf.template_mapping && typeof tf.template_mapping === 'object'
          ? tf.template_mapping
          : {}
        const hasMapping = Object.keys(mapping).length > 0

        for (const row of rows) {
          if (!row || typeof row !== 'object' || Array.isArray(row)) continue
          if (hasMapping) {
            const entity = {}
            for (const [tplCol, srcCol] of Object.entries(mapping)) {
              entity[tplCol] = row[srcCol]
            }
            mergedEntities.push(entity)
          } else {
            mergedEntities.push(row)
          }
          tableRowCount += 1
        }
      }
    }

    return {
      entities: mergedEntities,
      entityCount,
      tableRowCount,
      totalCount: entityCount + tableRowCount,
    }
  }

  /** 单次 table_filling：数据源 Excel + 模板 → 填好的表格 */
  async function runDirectTableFillTask(content, files, template_files) {
    const dataFiles = (files || []).filter((f) => !isTemplateFileMeta(f))
    const tplName = template_files?.[0]?.file_name || '模板'
    const srcName =
      dataFiles.find((f) => getFileCategory(f.file_name) === 'excel')?.file_name ||
      dataFiles[0]?.file_name ||
      '数据源'
    const labels = { src: srcName, tpl: tplName }

    showProgressBar.value = true
    progressValue.value = 0
    progressMessage.value = `表格填表：${srcName} → ${tplName}`

    const progressMsg = {
      id: createMessageId('progress'),
      role: 'assistant',
      content: `正在将「${srcName}」填入模板「${tplName}」…`,
      created_at: new Date().toISOString(),
      mixedSource: 'table_fill',
      isProgressMessage: true,
    }
    messages.value.push(progressMsg)

    const canStream = await waitForWebSocketOpen()
    if (!canStream || !ws.value || ws.value.readyState !== WebSocket.OPEN) {
      progressMsg.content = 'WebSocket 连接失败，请重试'
      isStreaming.value = false
      return
    }

    const result = await new Promise((resolve) => {
      pendingResolve = resolve
      try {
        ws.value.send(
          JSON.stringify({
            content: expandTableFillPrompt(content),
            mode: 'table_filling',
            files: dataFiles.map((f) => ({ ...f, is_selected: true })),
            template_files: template_files || [],
          }),
        )
      } catch (e) {
        pendingResolve = null
        resolve({ success: false, error: e.message })
      }
    })

    const taskGeneratedFiles = normalizeGeneratedFiles(result?.generated_files)
    if (taskGeneratedFiles.length > 0) {
      progressMsg.generated_files = taskGeneratedFiles
    }
    const taskTableData = result?.resp?.tableFillingData
    if (taskTableData && typeof taskTableData === 'object') {
      const tableFiles = normalizeGeneratedFiles(taskTableData.generated_files)
      const fallbackFiles = fallbackGeneratedFilesFromTableData(taskTableData)
      progressMsg.tableFillingData = {
        ...taskTableData,
        generated_files: tableFiles.length > 0 ? tableFiles : fallbackFiles,
      }
    }

    finalizeTableFillProgressMessage(progressMsg, result, template_files, labels)
    clearAllSelectedFiles()
    isStreaming.value = false
    showProgressBar.value = false
    progressValue.value = 100
  }

  // 混合模式主逻辑：按文件类型分发任务
  async function runMixedMode(content, files, template_files) {
    if (shouldDirectTableFill(files, template_files, content)) {
      await runDirectTableFillTask(content, files, template_files)
      return
    }
    const docFiles = files.filter(f => getFileCategory(f.file_name) === 'document')
    const excelFiles = files.filter(f => getFileCategory(f.file_name) === 'excel' && !isTemplateFileMeta(f))

    // 无文件或纯文本：通过 WebSocket 流式发送
    if (docFiles.length === 0 && excelFiles.length === 0) {
      const canStream = await waitForWebSocketOpen()
      if (ws.value && ws.value.readyState === WebSocket.OPEN && canStream) {
        isStreaming.value = true
        clearAllSelectedFiles()
        ws.value.send(JSON.stringify({
          content: content.trim(),
          mode: 'mixed',
          files: files,
          template_files: template_files,
        }))
      } else {
        // WebSocket 不可用，fallback 到 REST API
        try {
          await messageApi.send(currentSessionId.value, {
            content: content.trim(),
            mode: 'mixed',
            files: files,
            template_files: template_files,
          })
          await loadMessages(currentSessionId.value)
        } catch (e) {
          console.error('发送消息失败:', e)
        }
      }
      return
    }

    // 构建任务列表
    const taskList = []
    docFiles.forEach(f => taskList.push({ file: f, mode: 'entity_extraction' }))
    excelFiles.forEach(f => taskList.push({ file: f, mode: 'table_filling' }))

    const results = []
    const originalMode = currentMode.value

    for (let i = 0; i < taskList.length; i++) {
      const task = taskList[i]
      const taskTypeName =
        task.mode === 'entity_extraction'
          ? '实体提取任务'
          : (template_files?.length ? '表格填表' : '表格处理任务')

      console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} -> ${taskTypeName} | 文件: ${task.file.file_name}`)

      // 显示进度条
      showProgressBar.value = true
      progressValue.value = 0
      const currentProgressMsg = `处理文件 ${i + 1}/${taskList.length} - ${taskTypeName}: ${task.file.file_name}`
      progressMessage.value = currentProgressMsg

      // 添加任务进度消息
      messages.value.push({
        id: createMessageId('progress'),
        role: 'assistant',
        content: currentProgressMsg,
        created_at: new Date().toISOString(),
        mixedSource: 'single',
        mixedTaskIndex: i,
        isProgressMessage: true,
      })

      // 等待 WebSocket 连接
      const canStream = await waitForWebSocketOpen()
      if (!canStream || !ws.value || ws.value.readyState !== WebSocket.OPEN) {
        messages.value.push({
          id: createMessageId('assistant'),
          role: 'assistant',
          content: 'WebSocket 连接失败，请重试',
          created_at: new Date().toISOString(),
        })
        results.push({ task, success: false })
        continue
      }

      // 发送任务并等待结果
      console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} - 发送前 ws.readyState:`, ws.value?.readyState)
      const result = await new Promise((resolve) => {
        pendingResolve = resolve
        try {
          const msg = JSON.stringify({
            content: content.trim(),
            mode: task.mode,
            files: [{ ...task.file, is_selected: true }],
            template_files: template_files,
          })
          console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} - 发送消息:`, JSON.parse(msg))
          ws.value.send(msg)
          console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} - 发送完成，等待结果...`)
        } catch (e) {
          console.error(`[混合模式] 任务 ${i + 1}/${taskList.length} - 发送失败:`, e)
          pendingResolve = null
          resolve({ success: false, error: e.message })
        }
      })
      console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} - 收到结果:`, result)

      // WS 偶发丢字段/丢包时，从历史消息回补本次子任务结果
      if (task.mode === 'table_filling') {
        const hasLiveGenerated = normalizeGeneratedFiles(result?.generated_files).length > 0
        const hasLiveTableData = !!(result?.resp?.tableFillingData && typeof result.resp.tableFillingData === 'object')
        if (!hasLiveGenerated || !hasLiveTableData) {
          try {
            const hist = await messageApi.list(currentSessionId.value, { limit: 30, offset: 0 })
            const normalizedHist = (Array.isArray(hist) ? hist : []).map(normalizeMessageForResultDisplay)
            for (let h = normalizedHist.length - 1; h >= 0; h--) {
              const m = normalizedHist[h]
              if (m?.role !== 'assistant') continue
              const modeFlag = m?.metadata?.mode || m?.mode
              const tf = m?.tableFillingData
              const gf = normalizeGeneratedFiles(m?.generated_files)
              const looksLikeTableResult = !!tf || gf.length > 0
              if ((modeFlag === 'table_filling' || looksLikeTableResult) && looksLikeTableResult) {
                if (!result.resp || typeof result.resp !== 'object') result.resp = {}
                if (tf && !result.resp.tableFillingData) result.resp.tableFillingData = tf
                if (gf.length > 0 && normalizeGeneratedFiles(result.generated_files).length === 0) {
                  result.generated_files = gf
                }
                break
              }
            }
          } catch (e) {
            console.warn('[混合模式] 历史消息回补失败:', e)
          }
        }
      }

      // 将子任务结果回填到对应进度消息，避免因返回字段差异导致下载按钮不显示
      const progressMsg = findLatestMixedProgressMessage(messages.value, i, task.file?.file_name)
      if (progressMsg) {
        const taskGeneratedFiles = normalizeGeneratedFiles(result?.generated_files)
        if (taskGeneratedFiles.length > 0) {
          progressMsg.generated_files = taskGeneratedFiles
        }
        const taskTableData = result?.resp?.tableFillingData
        if (taskTableData && typeof taskTableData === 'object') {
          const tableFiles = normalizeGeneratedFiles(taskTableData.generated_files)
          const fallbackFiles = fallbackGeneratedFilesFromTableData(taskTableData)
          progressMsg.tableFillingData = {
            ...taskTableData,
            generated_files: tableFiles.length > 0 ? tableFiles : fallbackFiles,
          }
        }
        if (task.mode === 'table_filling' && template_files?.length) {
          finalizeTableFillProgressMessage(progressMsg, result, template_files, {
            src: task.file?.file_name || '数据源',
            tpl: template_files[0]?.file_name || '模板',
          })
        }
      }

      results.push({ task, ...result })
    }

    // 清空选中状态（注意：混合模式在每个任务完成后才清空，不是发送前清空）
    clearAllSelectedFiles()
    currentMode.value = originalMode

    // 单文件直接返回
    if (taskList.length === 1) {
      console.log('[混合模式] 单文件处理完成')
      return
    }

    // 多文件合并结果
    const successfulResults = results.filter(r => r.success)
    const failedResults = results.filter(r => !r.success)
    const mergeResult = await mergeMixedEntities(successfulResults)
    const mergedGeneratedFiles = []
    
    // 收集所有文件：从成功的任务中收集
    for (const r of successfulResults) {
      // 从 r.generated_files 收集（WebSocket done消息中的文件）
      const gf = normalizeGeneratedFiles(r?.generated_files)
      if (gf.length > 0) mergedGeneratedFiles.push(...gf)
      
      // 从 tableFillingData.generated_files 收集（表格填表的文件）
      const tf = r?.resp?.tableFillingData
      if (tf && typeof tf === 'object') {
        const tfGf = normalizeGeneratedFiles(tf.generated_files)
        if (tfGf.length > 0) mergedGeneratedFiles.push(...tfGf)
      }
    }
    
    // 去重处理（防止同一文件被添加多次）
    const uniqueFiles = []
    const seenPaths = new Set()
    for (const f of mergedGeneratedFiles) {
      if (f?.path && !seenPaths.has(f.path)) {
        seenPaths.add(f.path)
        uniqueFiles.push(f)
      }
    }

    // 收集表格填表的预览数据
    let tableFillingPreviewData = null
    for (const r of successfulResults) {
      if (r?.task?.mode === 'table_filling' && r?.resp?.tableFillingData) {
        const tf = r.resp.tableFillingData
        if (tf && typeof tf === 'object') {
          tableFillingPreviewData = {
            previewData: tf.previewData || tf.filtered_rows || [],
            matched_rows: tf.matched_rows || 0,
            total_rows: tf.total_rows,
            success: tf.success,
          }
          break  // 只取第一个表格填表结果
        }
      }
    }

    // mixed统一填表：把合并后的实体写入一个模板，生成真正的合并文件
    let mixedFillFiles = []
    let mixedFillPreviewData = null
    if (mergeResult.entities.length > 0 && Array.isArray(template_files) && template_files.length > 0 && currentSessionId.value) {
      const excelTpl = template_files.find(f => getFileCategory(f?.file_name || '') === 'excel')
      const selectedTemplate = excelTpl || template_files[0]
      const templateRef = selectedTemplate?.storage_key || selectedTemplate?.file_path || selectedTemplate?.path || ''

      if (templateRef) {
        try {
          const mixedFillResp = await agentApi.mixedFill({
            session_id: currentSessionId.value,
            entities: mergeResult.entities,
            template_file: templateRef,
            output_json: '',
            output_template: '',
          })
          const mixedData = mixedFillResp?.data || {}
          mixedFillFiles = normalizeGeneratedFiles(mixedData.file_ids)

          // 用 mixed-fill 的 output_json 构建预览，确保看到的是“合并后”结果
          const rows = await loadJsonRowsFromArtifacts(currentSessionId.value, mixedData, mixedFillFiles)
          if (rows.length > 0) {
            mixedFillPreviewData = {
              previewData: rows.slice(0, 50),
              matched_rows: rows.length,
              total_rows: rows.length,
              success: true,
            }
          }
        } catch (e) {
          console.error('[混合模式] mixed-fill 调用失败:', e)
        }
      }
    }

    // 构建最终消息
    let finalContent = ''
    const totalCount = mergeResult.totalCount
    const entityCount = mergeResult.entityCount
    const tableCount = mergeResult.tableRowCount
    const successCount = successfulResults.length
    const failCount = failedResults.length
    
    if (failCount === 0) {
      // 全部成功
      finalContent = `混合模式完成，共 ${totalCount} 条记录（实体: ${entityCount}, 表格: ${tableCount}；来自 ${successCount} 个文件）`
    } else if (successCount === 0) {
      // 全部失败
      const failReasons = failedResults.map(r => `${r.task.file.file_name}: ${r.error || '处理失败'}`).join('; ')
      finalContent = `混合模式处理失败 (${failCount}/${taskList.length} 个文件): ${failReasons}`
    } else {
      // 部分成功部分失败
      const failReasons = failedResults.map(r => `${r.task.file.file_name}: ${r.error || '处理失败'}`).join('; ')
      finalContent = `混合模式部分完成 - 成功: ${successCount}, 失败: ${failCount}\n成功结果: 共 ${totalCount} 条记录（实体: ${entityCount}, 表格: ${tableCount}）\n失败原因: ${failReasons}`
    }

    messages.value.push({
      id: createMessageId('assistant'),
      role: 'assistant',
      content: finalContent,
      created_at: new Date().toISOString(),
      mixedSource: 'merged',
      entitiesData: mergeResult.entities,
      tableFillingPreview: mixedFillPreviewData || tableFillingPreviewData,
      generated_files: mixedFillFiles.length > 0 ? mixedFillFiles : uniqueFiles,
    })
  }

  async function init() {
    console.log('[init] 开始初始化')
    isInitializing.value = true

    const cached = loadSessionsCache()
    console.log('[init] 缓存数据:', cached)
    if (cached?.currentSessionId) {
      currentSessionId.value = cached.currentSessionId
      const sess = cached.sessions?.find(s => s.session_id === cached.currentSessionId)
      currentMode.value = sess?.current_mode || 'default_conversation'
      const cachedMsgs = loadMessagesCache(cached.currentSessionId)
      if (cachedMsgs?.messages) {
        messages.value = cachedMsgs.messages
      }
    } else {
      currentMode.value = 'default_conversation'
    }

    try {
      await loadSessions()
    } catch (e) {
      console.warn('[init] loadSessions失败:', e)
    }

    const staleId = currentSessionId.value
    if (staleId) {
      const inList = sessions.value.some((s) => s.session_id === staleId)
      const onServer = inList && (await sessionExistsOnServer(staleId))
      if (!onServer) {
        console.warn('[init] 本地缓存的会话在服务端不存在，丢弃:', staleId)
        removeCache(MESSAGES_KEY + staleId)
        sessions.value = sessions.value.filter((s) => s.session_id !== staleId)
        currentSessionId.value = sessions.value[0]?.session_id ?? null
        messages.value = []
      }
    }

    if (!currentSessionId.value && sessions.value.length > 0) {
      currentSessionId.value = sessions.value[0].session_id
    }

    if (!currentSessionId.value) {
      console.log('[init] 无有效会话，在服务端创建新会话')
      await createSession()
    }

    console.log('[init] 初始化完成, currentMode:', currentMode.value, 'isInitializing设为false')
    isInitializing.value = false

    if (currentSessionId.value) {
      connectWebSocket()
      await loadMessages(currentSessionId.value)
    }
  }

  return {
    sessions,
    currentSessionId,
    messages,
    isLoading,
    isInitializing,
    isStreaming,
    isCreatingSession,
    isUploadingFiles,
    uploadProgress,
    currentSession,
    currentMode,
    currentModeConfig,
    progressValue,
    progressMessage,
    showProgressBar,
    init,
    loadSessions,
    createSession,
    selectSession,
    deleteSession,
    updateSessionTitle,
    loadMessages,
    sendMessage,
    switchMode,
    connectWebSocket,
    disconnectWebSocket,
    toggleSidebar,
    sidebarCollapsed,
    formatTime,
    parseApiTime,
    loadFiles,
  }
})
