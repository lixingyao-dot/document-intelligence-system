import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import workflowApi from '../api/workflow'
import { useFileStore } from './fileStore'
import { useLibraryStore } from './libraryStore'

/** 工作流画布：固定 1 个文档输入 → 可选中间节点 → 1 个文档输出（与后端 execute 校验一致） */
export const SCHEMA_DOCUMENT_INPUT = 'schema-document-input'
export const SCHEMA_LIBRARY_OUTPUT = 'schema-library-output'

/** @param {string} schemaKey */
function legacySchemaKeyToFileKind(schemaKey) {
  const m = String(schemaKey || '').toLowerCase()
  if (m === 'schema-pdf-input') return 'pdf'
  if (m === 'schema-md-input') return 'md'
  if (m === 'schema-txt-input') return 'txt'
  if (m === 'schema-docx-input') return 'docx'
  if (m === 'schema-xlsx-input') return 'xlsx'
  return 'pdf'
}

/** @param {string} filename @param {string} kind pdf|md|txt|docx|xlsx */
export function workflowFileMatchesKind(filename, kind) {
  const name = String(filename || '').trim().toLowerCase()
  if (!name) return false
  switch (kind) {
    case 'pdf':
      return name.endsWith('.pdf')
    case 'md':
      return name.endsWith('.md')
    case 'txt':
      return name.endsWith('.txt')
    case 'docx':
      return name.endsWith('.docx') || name.endsWith('.doc')
    case 'xlsx':
      return name.endsWith('.xlsx') || name.endsWith('.xls')
    default:
      return true
  }
}

export const useWorkflowStore = defineStore('workflow', () => {
  // ==================== 状态 ====================

  const currentWorkflowId = ref(null)
  const workflowName = ref('新建工作流')

  // 选中的文档（来自文档库或本地上传）
  const selectedDocs = ref([])
  const localFiles = ref([])       // 本地上传的文件（File 对象）

  // 当前选中的节点 ID
  const selectedNodeId = ref(null)

  // 每个节点的配置值（key: nodeId, value: { paramKey: paramValue }）
  const nodeConfigs = ref({})

  // 画布节点列表
  const canvasNodes = ref([])

  // ==================== 动态数据（从 API 加载） ====================

  const workflows = ref({})
  const availableModels = ref([])
  const availableLanguages = ref([])
  const outputFormats = ref([])
  const autoSaveStatus = ref('idle') // idle | pending | saving | saved | error

  let autoSaveTimer = null
  let isHydratingWorkflow = false
  let saveGeneration = 0

  function scheduleAutoSave() {
    if (isHydratingWorkflow || !currentWorkflowId.value) return
    autoSaveStatus.value = 'pending'
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    autoSaveTimer = setTimeout(() => {
      autoSaveTimer = null
      flushPendingSave()
    }, 600)
  }

  async function flushPendingSave() {
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
      autoSaveTimer = null
    }
    if (!currentWorkflowId.value) return
    const gen = ++saveGeneration
    autoSaveStatus.value = 'saving'
    try {
      await persistCurrentWorkflow()
      if (gen === saveGeneration) {
        autoSaveStatus.value = 'saved'
        setTimeout(() => {
          if (autoSaveStatus.value === 'saved') autoSaveStatus.value = 'idle'
        }, 2000)
      }
    } catch (e) {
      console.error('autoSave error:', e)
      if (gen === saveGeneration) autoSaveStatus.value = 'error'
    }
  }

  // ==================== 节点 Schema（无硬编码值，所有选项由 API 决定） ====================

  const nodeSchemas = ref({
    [SCHEMA_DOCUMENT_INPUT]: {
      icon: '', iconClass: 'input',
      title: '文档输入', subtitle: '统一输入',
      fields: [
        { key: '_hint_in', type: 'static', text: '支持所有格式（PDF、TXT、Markdown、Word、Excel）。从文档库勾选或本地选择待处理文档。' },
        { key: 'inputFileKinds', type: 'hidden', defaultValue: ['pdf', 'txt', 'md', 'docx', 'xlsx'] },
        { key: 'skipExisting', label: '跳过已处理文档（有同名输出则跳过）', type: 'toggle' }
      ]
    },
    'schema-translate': {
      icon: '', iconClass: 'ai',
      title: 'AI 翻译', subtitle: '翻译节点',
      fields: [
        { key: 'targetLanguage', label: '目标语言', type: 'language-selector' },
        { key: 'prompt', label: '翻译提示词', type: 'textarea' }
      ]
    },
    'schema-extract-summary': {
      icon: '', iconClass: 'ai',
      title: '内容提取', subtitle: '提取节点',
      fields: [
        { key: 'extractType', label: '提取类型', type: 'select',
          options: [{ value: 'summary', label: '生成摘要' }, { value: 'keypoints', label: '提取要点' }, { value: 'both', label: '摘要+要点' }] },
        { key: 'summaryLength', label: '摘要长度', type: 'select',
          options: [{ value: 'short', label: '简短' }, { value: 'medium', label: '适中' }, { value: 'detailed', label: '详细' }] },
        { key: 'prompt', label: '自定义提示词', type: 'textarea' }
      ]
    },
    'schema-extract-data': {
      icon: '', iconClass: 'ai',
      title: '数据抽取', subtitle: '抽取节点',
      fields: [
        { key: '_hint_data', type: 'static', text: '从文档中提取结构化数据，输出为 JSON 格式的记录列表。' },
        { key: 'extractFields', label: '要提取的字段', type: 'textarea', placeholder: '例: 名称,日期,金额（逗号分隔）' },
        { key: 'prompt', label: '提取规则描述', type: 'textarea' }
      ]
    },
    'schema-analyze-content': {
      icon: '', iconClass: 'ai',
      title: '内容分析', subtitle: '分析节点',
      fields: [
        { key: 'analysisType', label: '分析类型', type: 'select',
          options: [{ value: 'keywords', label: '关键词提取' }, { value: 'entities', label: '实体识别' }, { value: 'all', label: '全面分析' }] },
        { key: 'entityTypes', label: '实体类型', type: 'select-multiple',
          options: [{ value: 'person', label: '人名' }, { value: 'location', label: '地名' }, { value: 'org', label: '机构' }, { value: 'date', label: '日期' }] },
        { key: 'topK', label: '关键词数量', type: 'input', placeholder: '默认10' },
        { key: 'prompt', label: '自定义分析要求', type: 'textarea' }
      ]
    },
    'schema-enhance-text': {
      icon: '', iconClass: 'ai',
      title: '文本增强', subtitle: '增强节点',
      fields: [
        { key: 'enhanceType', label: '增强类型', type: 'select',
          options: [{ value: 'grammar', label: '语法检查' }, { value: 'polish', label: '文本润色' }, { value: 'rephrase', label: '改写' }, { value: 'all', label: '全面优化' }] },
        { key: 'style', label: '文本风格', type: 'select',
          options: [{ value: 'concise', label: '简洁' }, { value: 'formal', label: '学术' }, { value: 'casual', label: '口语' }, { value: 'professional', label: '专业' }] },
        { key: 'prompt', label: '自定义要求', type: 'textarea' }
      ]
    },
    'schema-sensitive-masking': {
      icon: '', iconClass: 'ai',
      title: '敏感信息脱敏', subtitle: '安全节点',
      fields: [
        { key: 'maskToken', label: '掩码符号', type: 'input', placeholder: '默认 *' },
        { key: 'prompt', label: '自定义脱敏规则', type: 'textarea' }
      ]
    },
    'schema-outline-generate': {
      icon: '', iconClass: 'ai',
      title: '结构化提纲生成', subtitle: '分析节点',
      fields: [
        { key: 'maxDepth', label: '最大层级', type: 'input', placeholder: '默认 3' },
        { key: 'prompt', label: '自定义规则', type: 'textarea' }
      ]
    },
    'schema-compare-docs': {
      icon: '', iconClass: 'ai',
      title: '文档对比', subtitle: '对比节点',
      fields: [
        { key: '_hint_cmp', type: 'static', text: '将当前文档与「参考文件」逐项对比，输出差异报告。下方选择参考文件来源。' },
        { key: 'compareMode', label: '对比模式', type: 'select',
          options: [
            { value: 'detailed', label: '详细对比（默认）' },
            { value: 'brief', label: '摘要对比' },
            { value: 'comprehensive', label: '全面深度对比' }
          ] },
        { key: 'summaryLevel', label: '报告详细度', type: 'select',
          options: [
            { value: 'brief', label: '精简（5条以内）' },
            { value: 'detailed', label: '详细（按类别分组）' },
            { value: 'comprehensive', label: '全面（逐项+影响分析）' }
          ] },
        { key: 'prompt', label: '自定义对比提示词', type: 'textarea', placeholder: '可选，支持变量: {file_a}, {file_b}, {content_a}, {content_b}' }
      ]
    },
    'schema-save': {
      icon: '', iconClass: 'output',
      title: '保存文件', subtitle: '输出节点',
      fields: [
        { key: 'savePath', label: '保存路径', type: 'input' },
        { key: 'outputFormat', label: '输出格式', type: 'format-selector' }
      ]
    },
    'schema-library-output': {
      icon: '', iconClass: 'output',
      title: '文档输出', subtitle: '统一输出',
      fields: [
        { key: '_hint_out', type: 'static', text: '输入仅从文档库读取；输出可选择本地目录或写入文档库。' },
        { key: 'outputMode', label: '输出方式', type: 'output-mode-select' },
        {
          key: 'savePath',
          label: '输出目录',
          type: 'input',
          placeholder: '如 D:\\exports\\workflow（留空则使用系统临时目录，可在执行结果中下载）',
          conditionField: 'outputMode',
          conditionValue: 'external'
        },
        {
          key: 'targetSpaceId',
          label: '输出文档库',
          type: 'library-selector',
          conditionField: 'outputMode',
          conditionValue: 'library'
        },
        { key: 'namingRule', label: '文件命名规则', type: 'input' },
        { key: 'outputFormat', label: '输出格式', type: 'format-selector' },
        { key: 'sheetName', label: '工作表名称', type: 'input', placeholder: '默认 Sheet1', conditionField: 'outputFormat', conditionValue: 'xlsx' },
        { key: 'outputEncoding', label: '文本编码', type: 'select',
          options: [{ value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' }],
          conditionField: 'outputFormat', conditionValue: 'txt' },
        { key: 'lineEnding', label: '换行符', type: 'select',
          options: [{ value: 'lf', label: 'LF' }, { value: 'crlf', label: 'CRLF' }],
          conditionField: 'outputFormat', conditionValue: 'txt' }
      ]
    },
    // —— 以下为《工作流编排-待办与用例》「节点配置」对齐的专项 schema ——
    'schema-entity-extraction': {
      icon: '', iconClass: 'ai',
      title: '实体提取', subtitle: '实体与结构化字段',
      fields: [
        { key: '_hint_entity', type: 'static', text: '从上游文档中抽取结构化实体；字段名与类型将随工作流保存到 config。' },
        { key: 'entityFieldList', label: '提取字段列表', type: 'textarea', placeholder: '每行一个字段，或逗号分隔，例：姓名\n日期\n金额' },
        { key: 'customEntityTypes', label: '自定义实体类型', type: 'textarea', placeholder: '可选：描述需识别的自定义类型，如「合同条款」「项目阶段」' },
        { key: 'aliasMap', label: '字段别名映射', type: 'textarea', placeholder: '可选：买方=甲方; 卖方=乙方（分号或换行分隔）' },
        { key: 'prompt', label: '补充抽取规则', type: 'textarea', placeholder: '对模型或规则的额外说明' }
      ]
    },
    'schema-save-text': {
      icon: '', iconClass: 'output',
      title: '保存文本', subtitle: '输出节点',
      fields: [
        { key: 'outputEncoding', label: '编码', type: 'select',
          options: [{ value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' }] },
        { key: 'lineEnding', label: '换行符', type: 'select',
          options: [{ value: 'lf', label: 'LF (Unix)' }, { value: 'crlf', label: 'CRLF (Windows)' }] },
        { key: 'savePath', label: '文件名或前缀', type: 'input' },
        { key: 'prompt', label: '备注', type: 'textarea' }
      ]
    }
  })

  // ==================== 工具箱（无硬编码值） ====================

  const toolboxItems = ref([
    {
      section: '中间环节（仅可插在输入与输出之间）',
      items: [
        {
          icon: '', name: 'AI 翻译', type: 'ai', title: 'AI 翻译', body: '使用大模型进行智能翻译处理',
          schemaKey: 'schema-translate',
          schema: null
        },
        {
          icon: '', name: '内容提取', type: 'ai', title: '内容提取', body: '生成摘要和提取关键要点',
          schemaKey: 'schema-extract-summary',
          schema: null
        },
        {
          icon: '', name: '数据抽取', type: 'ai', title: '数据抽取', body: '从文档中提取结构化数据',
          schemaKey: 'schema-extract-data',
          schema: null
        },
        {
          icon: '', name: '实体提取', type: 'ai', title: '实体提取', body: '按字段与自定义实体类型抽取结构化信息',
          schemaKey: 'schema-entity-extraction',
          schema: null
        },
        {
          icon: '', name: '内容分析', type: 'ai', title: '内容分析', body: '关键词提取和实体识别',
          schemaKey: 'schema-analyze-content',
          schema: null
        },
        {
          icon: '', name: '文本增强', type: 'ai', title: '文本增强', body: '语法检查、润色和改写',
          schemaKey: 'schema-enhance-text',
          schema: null
        },
        {
          icon: '', name: '敏感信息脱敏', type: 'ai', title: '敏感信息脱敏', body: '手机号/身份证/邮箱等自动掩码',
          schemaKey: 'schema-sensitive-masking',
          schema: null
        },
        {
          icon: '', name: '结构化提纲生成', type: 'ai', title: '结构化提纲生成', body: '按层级输出目录提纲',
          schemaKey: 'schema-outline-generate',
          schema: null
        },
        {
          icon: '', name: '文档对比', type: 'ai', title: '文档对比', body: '对比两份文档，输出差异报告',
          schemaKey: 'schema-compare-docs',
          schema: null
        }
      ]
    }
  ])

  function _defaultOutputConfigValues() {
    return {
      outputMode: 'external',
      savePath: '',
      targetSpaceId: null,
      namingRule: '{original_name}_out',
      outputFormat: 'pdf'
    }
  }

  function _normalizeOutputMode(raw) {
    const m = String(raw || 'library').toLowerCase()
    return m === 'external' || m === 'download' ? 'external' : 'library'
  }

  /** 与 canvas-inner 宽度一致（WorkflowCanvas），整条流水线水平居中，避免节点总挤在左侧或新节点落在最右缘 */
  const PIPELINE_INNER_W = 3000
  const PIPELINE_NODE_SPACING = 260
  const PIPELINE_NODE_SLOT_W = 216

  function applyHorizontalPipelineLayout(nodesArr) {
    const list = nodesArr || []
    const n = list.length
    if (n === 0) return
    const span = (n - 1) * PIPELINE_NODE_SPACING + PIPELINE_NODE_SLOT_W
    const startX = Math.round(Math.max(40, (PIPELINE_INNER_W - span) / 2))
    list.forEach((node, i) => {
      node.x = startX + i * PIPELINE_NODE_SPACING
      node.y = 160
    })
  }

  /** 画布固定结构：索引 0 为统一输入，末项为统一输出 */
  function buildShellNodes(baseTime = Date.now()) {
    const inId = 'n_in_' + baseTime
    const outId = 'n_out_' + (baseTime + 1)
    const inputNode = {
      id: inId,
      type: 'input',
      icon: '',
      title: '文档输入',
      body: '先选定源格式，仅选用匹配扩展名的文件',
      x: 30,
      y: 160,
      configValues: {
        inputFileKinds: ['pdf', 'txt', 'md', 'docx', 'xlsx'],
        inputFileKind: 'pdf',
        inputSource: 'library',
        spaceId: null,
        skipExisting: false
      },
      schemaKey: SCHEMA_DOCUMENT_INPUT,
      schema: nodeSchemas.value[SCHEMA_DOCUMENT_INPUT]
    }
    const outputNode = {
      id: outId,
      type: 'output',
      icon: '',
      title: '文档输出',
      body: '选择下载或入库及目标格式（含 txt / md 等）',
      x: 290,
      y: 160,
      configValues: { ..._defaultOutputConfigValues() },
      schemaKey: SCHEMA_LIBRARY_OUTPUT,
      schema: nodeSchemas.value[SCHEMA_LIBRARY_OUTPUT]
    }
    const shell = [inputNode, outputNode]
    applyHorizontalPipelineLayout(shell)
    return shell
  }

  function _migrateOutputNodeFromLegacy(node) {
    const cv = { ...(node.configValues || {}) }
    const sk = String(node.schemaKey || '')
    if (sk === 'schema-save-text') {
      return {
        ...node,
        title: '文档输出',
        body: '选择下载或入库及目标格式（含 txt / md 等）',
        schemaKey: SCHEMA_LIBRARY_OUTPUT,
        schema: nodeSchemas.value[SCHEMA_LIBRARY_OUTPUT],
        configValues: {
          ..._defaultOutputConfigValues(),
          outputFormat: 'txt',
          outputEncoding: cv.outputEncoding || 'utf-8',
          lineEnding: cv.lineEnding || 'lf',
          savePath: cv.savePath,
          outputMode: 'library'
        }
      }
    }
    if (sk === SCHEMA_LIBRARY_OUTPUT) {
      const merged = { ..._defaultOutputConfigValues(), ...cv }
      merged.outputMode = _normalizeOutputMode(merged.outputMode)
      return {
        ...node,
        title: '文档输出',
        body: '选择下载或入库及目标格式（含 txt / md 等）',
        configValues: merged,
        schema: nodeSchemas.value[SCHEMA_LIBRARY_OUTPUT]
      }
    }
    return {
      ...node,
      title: '文档输出',
      body: '选择下载或入库及目标格式（含 txt / md 等）',
      schemaKey: SCHEMA_LIBRARY_OUTPUT,
      schema: nodeSchemas.value[SCHEMA_LIBRARY_OUTPUT],
      configValues: { ..._defaultOutputConfigValues(), ...cv }
    }
  }

  function _migrateInputNodeFromLegacy(node) {
    const cv = { ...(node.configValues || {}) }
    let kind = cv.inputFileKind
    if (!kind || typeof kind !== 'string') {
      kind = legacySchemaKeyToFileKind(node.schemaKey)
    }
    return {
      ...node,
      title: '文档输入',
      body: '先选定源格式，仅选用匹配扩展名的文件',
      type: 'input',
      schemaKey: SCHEMA_DOCUMENT_INPUT,
      schema: nodeSchemas.value[SCHEMA_DOCUMENT_INPUT],
      configValues: {
        inputFileKinds: cv.inputFileKinds || (kind ? [kind] : ['pdf', 'txt', 'md', 'docx', 'xlsx']),
        inputFileKind: kind,
        inputSource: cv.inputSource || 'library',
        spaceId: cv.spaceId ?? null,
        skipExisting: !!cv.skipExisting
      }
    }
  }

  /**
   * 将任意历史 nodes 规整为：[统一输入] + 中间(ai…) + [统一输出]
   */
  function normalizeCanvasImportedNodes(nodes) {
    const raw = Array.isArray(nodes) ? [...nodes] : []
    if (raw.length === 0) return buildShellNodes()

    const inputCandidates = raw.filter(n => String(n.type).toLowerCase() === 'input')
    const outputCandidates = raw.filter(n => String(n.type).toLowerCase() === 'output')
    const middles = raw.filter(
      n => !['input', 'output'].includes(String(n.type).toLowerCase())
    )

    const inSrc =
      inputCandidates[0] || {
        id: 'n_in_fallback',
        type: 'input',
        schemaKey: SCHEMA_DOCUMENT_INPUT,
        configValues: {}
      }

    let outSrc = outputCandidates[outputCandidates.length - 1]
    if (!outSrc) {
      outSrc = {
        id: 'n_out_fallback',
        type: 'output',
        schemaKey: SCHEMA_LIBRARY_OUTPUT,
        configValues: _defaultOutputConfigValues()
      }
    }

    const migratedIn = _migrateInputNodeFromLegacy({ ...inSrc, type: 'input' })
    const migratedOut = _migrateOutputNodeFromLegacy({ ...outSrc, type: 'output' })

    const mids = middles.map(n => ({
      ...n,
      schema: n.schema || nodeSchemas.value[n.schemaKey] || null
    }))

    const placed = [migratedIn, ...mids, migratedOut]
    applyHorizontalPipelineLayout(placed)
    migratedIn.schema = nodeSchemas.value[SCHEMA_DOCUMENT_INPUT]
    migratedOut.schema = nodeSchemas.value[SCHEMA_LIBRARY_OUTPUT]
    _applyDefaultOutputSpaceToNode(migratedOut)
    return placed
  }

  /** 输出节点未配置文档库时，沿用聊天页「输出文档库」或首个文档库空间 */
  function _applyDefaultOutputSpaceToNode(outNode) {
    if (!outNode?.configValues || outNode.configValues.targetSpaceId) return
    const fileStore = useFileStore()
    const libraryStore = useLibraryStore()
    const preferred = fileStore.outputSpaceId
    const fallback = libraryStore.spaces?.[0]?.id
    const spaceId = preferred || fallback
    if (spaceId && _normalizeOutputMode(outNode.configValues?.outputMode) === 'library') {
      outNode.configValues.targetSpaceId = spaceId
    }
  }

  function ensureDefaultOutputSpace() {
    const outNode = canvasNodes.value.find(n => n.type === 'output')
    if (!outNode) return
    _applyDefaultOutputSpaceToNode(outNode)
  }

  /** 输入节点支持的文件格式列表（兼容旧的 inputFileKind 单值） */
  const workflowInputFileKinds = computed(() => {
    const n = canvasNodes.value.find(x => x.type === 'input')
    const cv = n?.configValues || {}
    if (Array.isArray(cv.inputFileKinds) && cv.inputFileKinds.length > 0) {
      return cv.inputFileKinds
    }
    if (typeof cv.inputFileKind === 'string' && cv.inputFileKind) {
      return [cv.inputFileKind]
    }
    // 默认支持全部格式
    return ['pdf', 'txt', 'md', 'docx', 'xlsx']
  })

  /** 清空与当前支持格式不匹配的选择 */
  function pruneFilesForWorkflowKind() {
    const kinds = workflowInputFileKinds.value
    const matches = (name) => kinds.some(k => workflowFileMatchesKind(name, k))
    selectedDocs.value = selectedDocs.value.filter(d => matches(d.name))
    localFiles.value = localFiles.value.filter(f => matches(f.name))
  }

  // ==================== 执行状态 ====================

  const isExecuting = ref(false)
  const executionProgress = ref(0)
  const executionLogs = ref([])
  const outputFiles = ref([])
  const nodeProgress = ref([])
  const currentNodeId = ref('')
  const currentNodeName = ref('')
  /** running | completed | failed（与后端 status 对齐，idle 表示未在执行） */
  const executionStatus = ref('idle')
  const executionCurrentFileIndex = ref(0)
  const executionTotalFiles = ref(0)
  const executionCurrentFileName = ref('')
  /** 无输出节点时的结果内容（数据抽取/实体提取等直接展示） */
  const executionResultContent = ref('')

  // ==================== 计算属性 ====================

  const currentWorkflow = computed(() =>
    currentWorkflowId.value ? workflows.value[currentWorkflowId.value] : null
  )

  const workflowList = computed(() => {
    const list = Object.values(workflows.value)
    return list.sort((a, b) => {
      const ta = new Date(a.updated_at || a.created_at || 0).getTime()
      const tb = new Date(b.updated_at || b.created_at || 0).getTime()
      return tb - ta
    })
  })

  const selectedNode = computed(() =>
    canvasNodes.value.find(n => n.id === selectedNodeId.value)
  )

  // 文档总数（库选 + 本地）
  const totalDocCount = computed(() =>
    selectedDocs.value.length + localFiles.value.length
  )

  // ==================== API 加载 ====================

  async function loadWorkflows() {
    try {
      const res = await workflowApi.getWorkflows()
      const list = res?.workflows || []
      workflows.value = {}
      list.forEach(w => {
        workflows.value[w.id] = {
          id: w.id,
          name: w.name,
          icon: w.icon || '',
          time: _formatTime(w.updated_at || w.created_at),
          type: w.type || 'custom',
          nodes: w.nodes || [],           // 完整节点列表（含 configValues、schemaKey）
          config: w.config || {},
          created_at: w.created_at || '',
          updated_at: w.updated_at || '',
        }
      })
    } catch (e) {
      console.error('loadWorkflows error:', e)
    }
  }

  async function loadModels() {
    try {
      const res = await workflowApi.getModels()
      availableModels.value = Array.isArray(res) ? res : (res?.models || [])
    } catch (e) {
      console.error('loadModels error:', e)
    }
  }

  async function loadLanguages() {
    try {
      const res = await workflowApi.getLanguages()
      availableLanguages.value = (Array.isArray(res) ? res : []).map(item => ({
        code: item.code,
        label: item.name || item.code
      }))
    } catch (e) {
      console.error('loadLanguages error:', e)
    }
  }

  async function loadOutputFormats() {
    try {
      const res = await workflowApi.getOutputFormats()
      outputFormats.value = (Array.isArray(res) ? res : []).map(item => ({
        code: item.code,
        label: item.name || item.code
      }))
    } catch (e) {
      console.error('loadOutputFormats error:', e)
    }
  }

  // ==================== 工作流操作 ====================

  function selectWorkflow(workflowId) {
    isHydratingWorkflow = true
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
      autoSaveTimer = null
    }
    autoSaveStatus.value = 'idle'

    currentWorkflowId.value = workflowId
    const wf = workflows.value[workflowId]

    if (!wf) {
      workflowName.value = '未命名'
      canvasNodes.value = []
      selectedNodeId.value = null
      isHydratingWorkflow = false
      return
    }

    workflowApi.getWorkflow(workflowId).then(res => {
      const wfData = res || {}
      workflowName.value = wfData.name || wf.name || '未命名'
      canvasNodes.value = normalizeCanvasImportedNodes(wfData.nodes || [])
      selectedNodeId.value = null
    }).catch(() => {
      workflowName.value = wf.name || '未命名'
      canvasNodes.value = []
    }).finally(() => {
      isHydratingWorkflow = false
    })
  }

  async function createNewWorkflow() {
    const id = 'wf_' + Date.now()
    const name = '新建工作流'
    workflows.value[id] = {
      id,
      name,
      icon: '',
      time: '刚刚',
      type: 'custom',
      nodes: [],
      config: {},
    }
    currentWorkflowId.value = id
    workflowName.value = name
    canvasNodes.value = normalizeCanvasImportedNodes([])
    selectedNodeId.value = null
    workflows.value[id].nodes = canvasNodes.value.map(({ x, y, schema, ...rest }) => rest)
    // 立即保存到后端
    try {
      await workflowApi.saveWorkflow({
        id,
        name,
        icon: '',
        type: 'custom',
        nodes: workflows.value[id].nodes,
        config: {},
      })
    } catch (e) {
      console.error('createNewWorkflow save error:', e)
    }
  }

  async function persistCurrentWorkflow() {
    if (!currentWorkflowId.value) return
    const wf = workflows.value[currentWorkflowId.value]
    if (!wf) return
    wf.name = workflowName.value || wf.name
    // 节点要保存完整配置：id, type, title, icon, body, schemaKey, configValues
    wf.nodes = canvasNodes.value.map(({ x, y, schema, ...rest }) => rest)
    await workflowApi.saveWorkflow({
      id: wf.id,
      name: wf.name,
      icon: wf.icon || '',
      type: 'custom',
      nodes: wf.nodes,
      config: wf.config || {},
    })
    wf.time = '刚刚'
  }

  async function saveCurrentWorkflow() {
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
      autoSaveTimer = null
    }
    const gen = ++saveGeneration
    autoSaveStatus.value = 'saving'
    try {
      await persistCurrentWorkflow()
      if (gen === saveGeneration) {
        autoSaveStatus.value = 'saved'
        setTimeout(() => {
          if (autoSaveStatus.value === 'saved') autoSaveStatus.value = 'idle'
        }, 2000)
      }
    } catch (e) {
      console.error('saveCurrentWorkflow error:', e)
      if (gen === saveGeneration) autoSaveStatus.value = 'error'
      throw e
    }
  }

  async function deleteWorkflow(workflowId) {
    try {
      await workflowApi.deleteWorkflow(workflowId)
    } catch (e) {
      console.error('deleteWorkflow error:', e)
    }
    delete workflows.value[workflowId]
    if (currentWorkflowId.value === workflowId) {
      const keys = Object.keys(workflows.value)
      currentWorkflowId.value = keys.length > 0 ? keys[0] : null
      if (currentWorkflowId.value) {
        selectWorkflow(currentWorkflowId.value)
      } else {
        createNewWorkflow()
      }
    }
  }

  // ==================== 节点操作 ====================

  function selectNode(nodeId) {
    selectedNodeId.value = nodeId
  }

  function updateNodePosition(nodeId, x, y) {
    const node = canvasNodes.value.find(n => n.id === nodeId)
    if (node) {
      node.x = x
      node.y = y
    }
  }

  /** 执行顺序前移一格；首尾输入/输出不可移动，移动后整条流水线重新水平居中 */
  function moveNodeEarlier(nodeId) {
    const idx = canvasNodes.value.findIndex(n => n.id === nodeId)
    if (idx <= 1) return
    const node = canvasNodes.value[idx]
    if (!node || node.type === 'input' || node.type === 'output') return
    const list = canvasNodes.value
    const item = list[idx]
    list.splice(idx, 1)
    list.splice(idx - 1, 0, item)
    applyHorizontalPipelineLayout(list)
    scheduleAutoSave()
  }

  /** 执行顺序后移一格；首尾输入/输出不可移动，移动后整条流水线重新水平居中 */
  function moveNodeLater(nodeId) {
    const idx = canvasNodes.value.findIndex(n => n.id === nodeId)
    const node = canvasNodes.value[idx]
    if (!node || node.type === 'input' || node.type === 'output') return
    if (idx < 1 || idx >= canvasNodes.value.length - 2) return
    const list = canvasNodes.value
    const item = list[idx]
    list.splice(idx, 1)
    list.splice(idx + 1, 0, item)
    applyHorizontalPipelineLayout(list)
    scheduleAutoSave()
  }

  function updateNodeConfig(nodeId, key, value) {
    const node = canvasNodes.value.find(n => n.id === nodeId)
    if (node) {
      if (!node.configValues) node.configValues = {}
      node.configValues[key] = value

      if (key === 'inputFileKinds' || key === 'inputFileKind') {
        pruneFilesForWorkflowKind()
      }

      // 特殊处理：inputSource 变化时清空对应数据
      if (key === 'inputSource') {
        if (value === 'library') {
          node.configValues.localFiles = []
        } else {
          node.configValues.spaceId = null
          selectedDocs.value = []
        }
      }
      scheduleAutoSave()
    }
  }

  function addNode(toolboxItem) {
    if (!toolboxItem || toolboxItem.type === 'input' || toolboxItem.type === 'output') {
      return null
    }
    if (canvasNodes.value.length < 2) {
      canvasNodes.value = normalizeCanvasImportedNodes(canvasNodes.value)
    }
    const schema = nodeSchemas.value[toolboxItem.schemaKey] || null
    const id = 'n_' + Date.now()
    const insertAt = Math.max(1, canvasNodes.value.length - 1)
    const configValues = _defaultConfigForSchemaKey(toolboxItem.schemaKey)
    const newNode = {
      id,
      type: toolboxItem.type,
      icon: toolboxItem.icon,
      title: toolboxItem.title,
      body: toolboxItem.body,
      x: 0,
      y: 160,
      configValues,
      schemaKey: toolboxItem.schemaKey,
      schema
    }
    canvasNodes.value.splice(insertAt, 0, newNode)
    applyHorizontalPipelineLayout(canvasNodes.value)
    selectedNodeId.value = id
    scheduleAutoSave()
    return id
  }

  /** 在画布指定坐标放置节点（拖拽落点）；仅允许插入输入与输出之间 */
  function addNodeAt(toolboxItem, x, y) {
    if (!toolboxItem || toolboxItem.type === 'input' || toolboxItem.type === 'output') {
      return null
    }
    if (canvasNodes.value.length < 2) {
      canvasNodes.value = normalizeCanvasImportedNodes(canvasNodes.value)
    }
    const schema = nodeSchemas.value[toolboxItem.schemaKey] || null
    const id = 'n_' + Date.now()
    const INNER = 3000
    const NODE_PLACEHOLDER_W = 216
    const NODE_PLACEHOLDER_H = 100
    const cx = Math.round(Math.min(Math.max(8, x), INNER - NODE_PLACEHOLDER_W - 8))
    const cy = Math.round(Math.min(Math.max(8, y), INNER - NODE_PLACEHOLDER_H - 8))
    const configValues = _defaultConfigForSchemaKey(toolboxItem.schemaKey)
    const newNode = {
      id,
      type: toolboxItem.type,
      icon: toolboxItem.icon,
      title: toolboxItem.title,
      body: toolboxItem.body,
      x: cx,
      y: cy,
      configValues,
      schemaKey: toolboxItem.schemaKey,
      schema
    }
    const dropCenterX = cx + NODE_PLACEHOLDER_W / 2
    const listBefore = canvasNodes.value
    let insertAt = listBefore.length - 1
    for (let i = 1; i < listBefore.length; i++) {
      const prev = listBefore[i - 1]
      const curr = listBefore[i]
      const mid =
        (prev.x + NODE_PLACEHOLDER_W / 2 + curr.x + NODE_PLACEHOLDER_W / 2) / 2
      if (dropCenterX < mid) {
        insertAt = i
        break
      }
    }
    if (insertAt < 1) insertAt = 1
    if (insertAt > listBefore.length - 1) insertAt = listBefore.length - 1

    canvasNodes.value.splice(insertAt, 0, newNode)
    applyHorizontalPipelineLayout(canvasNodes.value)
    selectedNodeId.value = id
    scheduleAutoSave()
    return id
  }

  /** 新节点拖入画布时的默认配置，避免「处理类型」等依赖字段全空导致面板无内容 */
  function _defaultConfigForSchemaKey(schemaKey) {
    switch (schemaKey) {
      case 'schema-save-text':
        return { outputEncoding: 'utf-8', lineEnding: 'lf' }
      case 'schema-translate':
        return {
          targetLanguage: 'zh',
          prompt:
            '请将以下文档全文翻译为{target_language}，保持 Markdown/段落结构，仅输出译文。禁止输出英语，除非目标语言就是英语。',
        }
      default:
        return {}
    }
  }

  function deleteNode(nodeId) {
    const idx = canvasNodes.value.findIndex(n => n.id === nodeId)
    if (idx === -1) return
    if (idx === 0 || idx === canvasNodes.value.length - 1) return
    canvasNodes.value.splice(idx, 1)
    applyHorizontalPipelineLayout(canvasNodes.value)
    if (selectedNodeId.value === nodeId) {
      selectedNodeId.value = canvasNodes.value.length > 0
        ? canvasNodes.value[Math.min(idx, canvasNodes.value.length - 1)].id
        : null
    }
    scheduleAutoSave()
  }

  function clearCanvas() {
    canvasNodes.value = normalizeCanvasImportedNodes([])
    selectedNodeId.value = null
    scheduleAutoSave()
  }

  // ==================== 文档操作（从文档库） ====================

  function setSelectedDocs(docs) {
    selectedDocs.value = docs
  }

  function addSelectedDoc(doc) {
    if (!selectedDocs.value.find(d => d.id === doc.id)) {
      selectedDocs.value.push(doc)
    }
  }

  function removeSelectedDoc(docId) {
    selectedDocs.value = selectedDocs.value.filter(d => d.id !== docId)
  }

  function clearSelectedDocs() {
    selectedDocs.value = []
  }

  // ==================== 本地文件操作 ====================

  function addLocalFiles(files) {
    files.forEach(file => {
      if (!localFiles.value.find(f => f.name === file.name && f.size === file.size)) {
        localFiles.value.push({
          id: 'local_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
          name: file.name,
          size: file.size,
          file: file,
          type: file.type
        })
      }
    })
  }

  function removeLocalFile(fileId) {
    localFiles.value = localFiles.value.filter(f => f.id !== fileId)
  }

  function clearLocalFiles() {
    localFiles.value = []
  }

  // ==================== 工作流执行 ====================

  function _sanitizeConfigValue(value) {
    if (Array.isArray(value)) {
      return value
        .map(v => _sanitizeConfigValue(v))
        .filter(v => v !== null && v !== undefined)
    }

    if (value && typeof value === 'object') {
      if (Object.prototype.hasOwnProperty.call(value, 'value')) {
        return value.value
      }
      return value
    }

    if (value === '[object Object]') {
      return null
    }

    return value
  }

  function _sanitizeNodeConfigValues(configValues) {
    const src = configValues || {}
    const out = {}
    Object.keys(src).forEach(k => {
      out[k] = _sanitizeConfigValue(src[k])
    })
    return out
  }

  function _normalizeExecutionLog(log) {
    if (log == null) return { type: 'info', message: '' }
    if (typeof log === 'string') return { type: 'info', message: log }
    const rawType = String(log.type || 'info').toLowerCase()
    const type =
      rawType === 'success' || rawType === 'complete' ? 'done' : rawType === 'warning' ? 'warn' : rawType
    const allowed = ['info', 'done', 'warn', 'error']
    const t = allowed.includes(type) ? type : 'info'
    const msg =
      log.message != null
        ? String(log.message)
        : log.msg != null
          ? String(log.msg)
          : ''
    return { type: t, message: msg || JSON.stringify(log) }
  }

  /** 将服务端返回的完整 logs 中尚未追加的部分写入 executionLogs，返回新的游标 */
  function _appendNewLogsFromResponse(res, lastCount) {
    const raw = res?.logs
    if (!Array.isArray(raw) || raw.length <= lastCount) return lastCount
    for (let i = lastCount; i < raw.length; i++) {
      executionLogs.value.push(_normalizeExecutionLog(raw[i]))
    }
    return raw.length
  }

  function _applyExecutionSnapshot(res) {
    const idx = res?.current_file_index ?? res?.currentFileIndex ?? 0
    const total = res?.total_files ?? res?.totalFiles ?? 0
    const name = res?.current_file_name ?? res?.currentFileName ?? ''
    executionCurrentFileIndex.value = Number(idx) || 0
    executionTotalFiles.value = Number(total) || 0
    executionCurrentFileName.value = String(name || '')
    if (res?.progress != null && res.progress !== '') {
      const p = Number(res.progress)
      if (!Number.isNaN(p)) executionProgress.value = Math.min(100, Math.max(0, p))
    }
    nodeProgress.value = Array.isArray(res?.node_progress) ? res.node_progress : nodeProgress.value
    currentNodeId.value = res?.current_node_id ?? res?.currentNodeId ?? ''
    currentNodeName.value = res?.current_node_name ?? res?.currentNodeName ?? ''
  }

  async function executeWorkflow() {
    if (isExecuting.value) return
    isExecuting.value = true
    executionProgress.value = 0
    executionLogs.value = []
    outputFiles.value = []
    executionStatus.value = 'running'
    executionCurrentFileIndex.value = 0
    executionTotalFiles.value = 0
    executionCurrentFileName.value = ''
    executionResultContent.value = ''
    nodeProgress.value = canvasNodes.value.map((n, idx) => ({
      id: n.id,
      title: n.title,
      type: n.type,
      schemaKey: n.schemaKey,
      index: idx + 1,
      status: 'pending',
      progress: 0,
      message: ''
    }))
    currentNodeId.value = ''
    currentNodeName.value = ''

    try {
      const list = canvasNodes.value
      const kIn = list.filter(n => n.type === 'input')
      const kOut = list.filter(n => n.type === 'output')
      if (
        list.length < 2 ||
        kIn.length !== 1 ||
        kOut.length !== 1 ||
        list[0].type !== 'input' ||
        list[list.length - 1].type !== 'output'
      ) {
        executionLogs.value.push({
          type: 'error',
          message: '工作流必须为：1 个「文档输入」→ 可选中间步骤 → 1 个「文档输出」，且顺序不可倒置'
        })
        executionStatus.value = 'failed'
        return
      }
      const fks = workflowInputFileKinds.value
      const matchesAny = (name) => fks.some(k => workflowFileMatchesKind(name, k))
      const mismatchedLib = selectedDocs.value.filter(d => !matchesAny(d.name))
      if (mismatchedLib.length) {
        executionLogs.value.push({
          type: 'error',
          message: `以下文档格式不支持：${mismatchedLib.map(d => d.name).join('、')}`
        })
        executionStatus.value = 'failed'
        return
      }
      const mismatchedLoc = localFiles.value.filter(f => !matchesAny(f.name))
      if (mismatchedLoc.length) {
        executionLogs.value.push({
          type: 'error',
          message: `以下本地文件格式不支持：${mismatchedLoc.map(f => f.name).join('、')}`
        })
        executionStatus.value = 'failed'
        return
      }

      if (selectedDocs.value.length === 0 && localFiles.value.length === 0) {
        executionLogs.value.push({ type: 'error', message: '请至少选择一个输入文档（文档库或本地文件）' })
        executionStatus.value = 'failed'
        return
      }

      const outNode = canvasNodes.value.find(n => n.type === 'output')
      const outCv = outNode?.configValues || {}
      const outputMode = _normalizeOutputMode(outCv.outputMode)

      if (outputMode === 'library') {
        await useLibraryStore().loadSpaces().catch(() => {})
        ensureDefaultOutputSpace()
        if (!outCv.targetSpaceId) {
          executionLogs.value.push({ type: 'error', message: '保存到文档库时请选择输出文档库空间' })
          executionStatus.value = 'failed'
          return
        }
      }

      await flushPendingSave()

      const params = {
        workflowId: currentWorkflowId.value,
        nodes: canvasNodes.value.map(n => ({
          id: n.id,
          type: n.type,
          title: n.title,
          schemaKey: n.schemaKey,
          configValues: _sanitizeNodeConfigValues(n.configValues)
        })),
        docs: selectedDocs.value.map(d => d.id),
        localFiles: localFiles.value
          .filter(f => f.file?.path)
          .map(f => f.file.path)
      }

      const res = await workflowApi.execute(params)
      const executionId = res?.execution_id
      if (!executionId) {
        executionLogs.value.push({ type: 'error', message: '未返回 execution_id，无法轮询状态' })
        executionStatus.value = 'failed'
        return
      }

      // 轮询执行状态
      await pollExecution(executionId)
    } catch (e) {
      executionLogs.value.push({ type: 'error', message: e.message })
      executionStatus.value = 'failed'
    } finally {
      isExecuting.value = false
    }
  }

  async function pollExecution(executionId) {
    const pollIntervalMs = 2000
    const maxPollMs = 30 * 60 * 1000
    const maxPolls = Math.ceil(maxPollMs / pollIntervalMs)
    let polls = 0
    let lastLogCount = 0
    while (polls < maxPolls) {
      try {
        const res = await workflowApi.getExecutionStatus(executionId)
        const status = res?.status
        _applyExecutionSnapshot(res)
        lastLogCount = _appendNewLogsFromResponse(res, lastLogCount)

        if (status === 'completed' || status === 'partial') {
          executionProgress.value = 100
          executionStatus.value = status
          if (Array.isArray(res.output_files) && res.output_files.length > 0) {
            outputFiles.value = res.output_files
          }
          if (status === 'partial' && res?.error) {
            executionLogs.value.push({ type: 'warn', message: res.error })
          }
          break
        }
        if (status === 'failed') {
          executionStatus.value = 'failed'
          break
        }

        // running / pending 等：进度条优先用服务端 progress，否则按文件序号估算
        const tf = executionTotalFiles.value || 0
        const ci = executionCurrentFileIndex.value || 0
        if (res?.progress == null || res.progress === '') {
          if (tf > 0 && ci > 0) {
            executionProgress.value = Math.min(99, Math.max(0, Math.round((ci / tf) * 100)))
          }
        }
      } catch (e) {
        executionLogs.value.push({ type: 'error', message: e.message })
        executionStatus.value = 'failed'
        break
      }
      await new Promise(r => setTimeout(r, pollIntervalMs))
      polls++
    }
    if (polls >= maxPolls) {
      executionLogs.value.push({ type: 'error', message: '执行超时（超过 30 分钟仍未完成）' })
      executionStatus.value = 'failed'
    }
  }

  // ==================== 辅助方法 ====================

  function updateWorkflowName(name) {
    workflowName.value = name
    const wf = workflows.value[currentWorkflowId.value]
    if (wf) {
      wf.name = name
    }
    scheduleAutoSave()
  }

  // 根据 schemaKey 获取 schema（用于配置面板动态渲染）
  function getSchemaByKey(schemaKey) {
    return nodeSchemas.value[schemaKey] || null
  }

  function _formatTime(dateStr) {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now - date
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)
    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days === 1) return '昨天'
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN')
  }

  // ==================== 导出 ====================

  return {
    // 状态
    currentWorkflowId,
    workflowName,
    selectedDocs,
    localFiles,
    selectedNodeId,
    selectedNode,
    nodeConfigs,
    nodeSchemas,
    workflows,
    toolboxItems,
    canvasNodes,
    availableModels,
    availableLanguages,
    outputFormats,
    autoSaveStatus,
    isExecuting,
    executionProgress,
    executionLogs,
    outputFiles,
    nodeProgress,
    currentNodeId,
    currentNodeName,
    executionStatus,
    executionCurrentFileIndex,
    executionTotalFiles,
    executionCurrentFileName,
    executionResultContent,
    // 计算属性
    currentWorkflow,
    workflowList,
    totalDocCount,
    workflowInputFileKinds,
    // API 加载
    loadWorkflows,
    loadModels,
    loadLanguages,
    loadOutputFormats,
    // 工作流操作
    selectWorkflow,
    createNewWorkflow,
    saveCurrentWorkflow,
    flushPendingSave,
    deleteWorkflow,
    updateWorkflowName,
    // 节点操作
    selectNode,
    updateNodePosition,
    moveNodeEarlier,
    moveNodeLater,
    updateNodeConfig,
    addNode,
    addNodeAt,
    deleteNode,
    clearCanvas,
    getSchemaByKey,
    // 文档操作
    setSelectedDocs,
    addSelectedDoc,
    removeSelectedDoc,
    clearSelectedDocs,
    // 本地文件
    addLocalFiles,
    removeLocalFile,
    clearLocalFiles,
    // 执行
    ensureDefaultOutputSpace,
    executeWorkflow
  }
})
