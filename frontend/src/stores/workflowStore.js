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
  // ==================== 节点 Schema（无硬编码值，所有选项由 API 决定） ====================

  const nodeSchemas = ref({
    [SCHEMA_DOCUMENT_INPUT]: {
      icon: '', iconClass: 'input',
      title: '文档输入', subtitle: '统一输入',
      fields: [
        { key: '_hint_in', type: 'static', text: '请先选择源文件格式，并从文档库勾选待处理文档（上传请至左侧「文档库」页）。' },
        { key: 'inputFileKind', label: '源文件格式', type: 'select',
          options: [
            { value: 'pdf', label: 'PDF (.pdf)' },
            { value: 'md', label: 'Markdown (.md)' },
            { value: 'txt', label: '纯文本 (.txt)' },
            { value: 'docx', label: 'Word (.docx / .doc)' },
            { value: 'xlsx', label: 'Excel (.xlsx / .xls)' }
          ] },
        { key: 'spaceId', label: '输入文档库', type: 'library-selector' },
        { key: 'skipExisting', label: '跳过已处理文档（有同名输出则跳过）', type: 'toggle', dependsOn: { field: 'inputFileKind', value: 'pdf' } }
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
        { key: 'dataFormat', label: '输出格式', type: 'select',
          options: [{ value: 'json', label: 'JSON' }, { value: 'csv', label: 'CSV' }, { value: 'table', label: '表格' }] },
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
    'schema-convert-format': {
      icon: '', iconClass: 'ai',
      title: '格式转换', subtitle: '转换节点',
      fields: [
        { key: '_hint_cf', type: 'static', text: '选择目标格式及转换选项；配置将保存在节点 config 供执行端解析。' },
        { key: 'targetFormat', label: '目标格式', type: 'select',
          options: [
            { value: 'markdown', label: 'Markdown' },
            { value: 'html', label: 'HTML' },
            { value: 'plaintext', label: '纯文本' },
            { value: 'pdf', label: 'PDF' },
            { value: 'docx', label: 'Word (DOCX)' },
            { value: 'json', label: 'JSON' }
          ] },
        { key: 'conversionOptions', label: '转换选项', type: 'select-multiple',
          options: [
            { value: 'keep_layout', label: '尽量保留版面' },
            { value: 'extract_tables', label: '优先提取表格' },
            { value: 'embed_images', label: '保留内嵌图片' },
            { value: 'code_as_text', label: '代码块转纯文本' },
            { value: 'sanitize_html', label: 'HTML 安全清洗' }
          ] },
        { key: 'preserveFormatting', label: '保留原格式标记', type: 'toggle' },
        { key: 'preserveStructure', label: '保留文档结构', type: 'toggle' },
        { key: 'prompt', label: '自定义转换规则', type: 'textarea' }
      ]
    },
    'schema-split-document': {
      icon: '', iconClass: 'ai',
      title: '文档分割', subtitle: '分割节点',
      fields: [
        { key: 'splitMethod', label: '分割方式', type: 'select',
          options: [{ value: 'section', label: '按章节' }, { value: 'paragraph', label: '按段落' }, { value: 'size', label: '按大小' }, { value: 'page', label: '按页数' }] },
        { key: 'splitSize', label: '分割参数', type: 'input', placeholder: '如大小:字符数或页数' },
        { key: 'preserveContext', label: '保留上下文', type: 'toggle' },
        { key: 'prompt', label: '自定义分割规则', type: 'textarea' }
      ]
    },
    'schema-keyword-highlight': {
      icon: '', iconClass: 'ai',
      title: '关键词高亮', subtitle: '增强节点',
      fields: [
        { key: 'topK', label: '关键词数量', type: 'input', placeholder: '默认 10' },
        { key: 'marker', label: '高亮标记符', type: 'input', placeholder: '默认 **' },
        { key: 'prompt', label: '自定义规则', type: 'textarea' }
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
    'schema-term-normalize': {
      icon: '', iconClass: 'ai',
      title: '术语统一替换', subtitle: '规范节点',
      fields: [
        { key: 'termDictionary', label: '术语词典', type: 'textarea', placeholder: '示例：A=>标准术语A; B=>标准术语B' },
        { key: 'prompt', label: '自定义规则', type: 'textarea' }
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
    'schema-sentiment-enhanced': {
      icon: '', iconClass: 'ai',
      title: '情感倾向分析', subtitle: '分析节点',
      fields: [
        { key: 'prompt', label: '自定义分析规则', type: 'textarea' }
      ]
    },
    'schema-timeline-extract': {
      icon: '', iconClass: 'ai',
      title: '时间线抽取', subtitle: '抽取节点',
      fields: [
        { key: 'prompt', label: '自定义抽取规则', type: 'textarea' }
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
    'schema-data-process': {
      icon: '', iconClass: 'ai',
      title: '数据处理', subtitle: '表格类操作',
      fields: [
        { key: '_hint_dp', type: 'static', text: '针对表格数据：先选择处理类型，再填写对应参数（与《节点处理》数据处理章节一致）。' },
        { key: 'processKind', label: '处理类型', type: 'select',
          options: [
            { value: 'sort', label: '排序' },
            { value: 'filter', label: '筛选' },
            { value: 'aggregate', label: '汇总' },
            { value: 'dedupe', label: '去重' },
            { value: 'fill_null', label: '填充空值' },
            { value: 'computed_column', label: '新增计算列' },
            { value: 'merge_columns', label: '合并列' },
            { value: 'split_column', label: '拆分列' }
          ] },
        { key: 'sortColumn', label: '排序列（列名）', type: 'input', placeholder: '例如：金额 或 D', dependsOn: { field: 'processKind', value: 'sort' } },
        { key: 'sortOrder', label: '升降序', type: 'select',
          options: [{ value: 'asc', label: '升序' }, { value: 'desc', label: '降序' }],
          dependsOn: { field: 'processKind', value: 'sort' } },
        { key: 'filterExpr', label: '筛选条件', type: 'textarea', placeholder: '例：列「状态」= 已完成；或简短表达式说明', dependsOn: { field: 'processKind', value: 'filter' } },
        { key: 'aggregateColumn', label: '汇总列', type: 'input', placeholder: '要汇总的列名', dependsOn: { field: 'processKind', value: 'aggregate' } },
        { key: 'aggregateOp', label: '汇总方式', type: 'select',
          options: [
            { value: 'sum', label: '求和' },
            { value: 'count', label: '计数' },
            { value: 'avg', label: '平均值' },
            { value: 'min', label: '最小' },
            { value: 'max', label: '最大' }
          ],
          dependsOn: { field: 'processKind', value: 'aggregate' } },
        { key: 'groupByColumns', label: '分组列（可选）', type: 'input', placeholder: '逗号分隔，留空表示全文一条汇总', dependsOn: { field: 'processKind', value: 'aggregate' } },
        { key: 'dedupeColumns', label: '去重依据列', type: 'input', placeholder: '逗号分隔列名，留空表示整行去重', dependsOn: { field: 'processKind', value: 'dedupe' } },
        { key: 'fillColumns', label: '填充列', type: 'input', placeholder: '要填充的列，逗号分隔', dependsOn: { field: 'processKind', value: 'fill_null' } },
        { key: 'fillValue', label: '填充值', type: 'input', placeholder: '例如：0 或 N/A', dependsOn: { field: 'processKind', value: 'fill_null' } },
        { key: 'computedFormula', label: '计算表达式', type: 'textarea', placeholder: '例：=[金额]*[数量] 或列运算说明', dependsOn: { field: 'processKind', value: 'computed_column' } },
        { key: 'computedColumnName', label: '新列名', type: 'input', placeholder: '结果写入的列标题', dependsOn: { field: 'processKind', value: 'computed_column' } },
        { key: 'mergeSourceColumns', label: '待合并列', type: 'input', placeholder: '逗号分隔', dependsOn: { field: 'processKind', value: 'merge_columns' } },
        { key: 'mergeSeparator', label: '连接符', type: 'input', placeholder: '默认空格', dependsOn: { field: 'processKind', value: 'merge_columns' } },
        { key: 'mergeTargetColumn', label: '目标列名', type: 'input', dependsOn: { field: 'processKind', value: 'merge_columns' } },
        { key: 'splitSourceColumn', label: '待拆分列', type: 'input', dependsOn: { field: 'processKind', value: 'split_column' } },
        { key: 'splitDelimiter', label: '分隔符', type: 'input', placeholder: '如：,、;、|', dependsOn: { field: 'processKind', value: 'split_column' } },
        { key: 'splitIntoColumns', label: '拆成列名', type: 'input', placeholder: '逗号分隔多列标题', dependsOn: { field: 'processKind', value: 'split_column' } },
        { key: 'prompt', label: '补充说明', type: 'textarea' }
      ]
    },
    'schema-data-clean': {
      icon: '', iconClass: 'ai',
      title: '数据清洗', subtitle: '规则与规范化',
      fields: [
        { key: '_hint_dc', type: 'static', text: '可多选下方规则；实际清洗与预览在执行阶段由服务端/执行引擎应用（可先保存配置再联调）。' },
        { key: 'cleanRules', label: '清洗规则', type: 'select-multiple',
          options: [
            { value: 'trim_spaces', label: '去除首尾空格' },
            { value: 'normalize_date', label: '统一日期格式' },
            { value: 'normalize_number', label: '统一数字格式' },
            { value: 'handle_outliers', label: '处理异常值' },
            { value: 'expand_merged_cells', label: '合并单元格展开' },
            { value: 'fix_format_errors', label: '修正格式错误' }
          ] },
        { key: 'dateFormatPattern', label: '目标日期格式', type: 'input', placeholder: '例：YYYY-MM-DD（勾选「统一日期格式」后可填）',
          dependsOn: { field: 'cleanRules', arrayIncludes: 'normalize_date' } },
        { key: 'numberDecimalPlaces', label: '小数位数', type: 'input', placeholder: '可选，如：2',
          dependsOn: { field: 'cleanRules', arrayIncludes: 'normalize_number' } },
        { key: 'prompt', label: '补充规则说明', type: 'textarea' },
      ]
    },
    'schema-table-extract': {
      icon: '', iconClass: 'ai',
      title: '表格提取', subtitle: '从文档中抽取表格',
      fields: [
        { key: 'tableStrategy', label: '提取策略', type: 'select',
          options: [
            { value: 'first', label: '第一个表格' },
            { value: 'all', label: '全部表格' },
            { value: 'by_index', label: '按序号' }
          ] },
        { key: 'tableIndex', label: '表格序号（从 1 开始）', type: 'input', placeholder: '当策略为「按序号」',
          dependsOn: { field: 'tableStrategy', value: 'by_index' } },
        { key: 'prompt', label: '补充说明', type: 'textarea' }
      ]
    },
    'schema-data-rollup': {
      icon: '', iconClass: 'ai',
      title: '数据汇总', subtitle: '统计汇总',
      fields: [
        { key: 'rollupDims', label: '分类维度（列）', type: 'textarea', placeholder: '逗号或换行分隔' },
        { key: 'rollupMetrics', label: '指标与聚合', type: 'textarea', placeholder: '例：销售额:sum; 数量:count' },
        { key: 'prompt', label: '补充说明', type: 'textarea' }
      ]
    },
    'schema-save-excel': {
      icon: '', iconClass: 'output',
      title: '保存 Excel', subtitle: '输出节点',
      fields: [
        { key: 'savePath', label: '相对路径或文件名前缀', type: 'input', placeholder: '可选' },
        { key: 'sheetName', label: '工作表名称', type: 'input', placeholder: '默认 Sheet1' },
        { key: 'prompt', label: '备注', type: 'textarea' }
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
          icon: '', name: '数据处理', type: 'ai', title: '数据处理', body: '表格排序、筛选、汇总、去重与列变换',
          schemaKey: 'schema-data-process',
          schema: null
        },
        {
          icon: '', name: '数据清洗', type: 'ai', title: '数据清洗', body: '去空格、格式统一与脏数据规范化',
          schemaKey: 'schema-data-clean',
          schema: null
        },
        {
          icon: '', name: '表格提取', type: 'ai', title: '表格提取', body: '从 PDF/Word 等文档中提取表格结构',
          schemaKey: 'schema-table-extract',
          schema: null
        },
        {
          icon: '', name: '数据汇总', type: 'ai', title: '数据汇总', body: '按维度统计汇总指标',
          schemaKey: 'schema-data-rollup',
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
          icon: '', name: '格式转换', type: 'ai', title: '格式转换', body: '在多种格式间智能转换',
          schemaKey: 'schema-convert-format',
          schema: null
        },
        {
          icon: '', name: '文档分割', type: 'ai', title: '文档分割', body: '智能分割文档为多个部分',
          schemaKey: 'schema-split-document',
          schema: null
        },
        {
          icon: '', name: '关键词高亮', type: 'ai', title: '关键词高亮', body: '提取关键词并在结果中标注高亮',
          schemaKey: 'schema-keyword-highlight',
          schema: null
        },
        {
          icon: '', name: '敏感信息脱敏', type: 'ai', title: '敏感信息脱敏', body: '手机号/身份证/邮箱等自动掩码',
          schemaKey: 'schema-sensitive-masking',
          schema: null
        },
        {
          icon: '', name: '术语统一替换', type: 'ai', title: '术语统一替换', body: '按词典规范化术语表达',
          schemaKey: 'schema-term-normalize',
          schema: null
        },
        {
          icon: '', name: '结构化提纲生成', type: 'ai', title: '结构化提纲生成', body: '按层级输出目录提纲',
          schemaKey: 'schema-outline-generate',
          schema: null
        },
        {
          icon: '', name: '情感倾向分析', type: 'ai', title: '情感倾向分析', body: '输出打分、标签和依据',
          schemaKey: 'schema-sentiment-enhanced',
          schema: null
        },
        {
          icon: '', name: '时间线抽取', type: 'ai', title: '时间线抽取', body: '提取事件并按时间排序',
          schemaKey: 'schema-timeline-extract',
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
      body: '选择下载或入库及目标格式（含 xlsx / txt / md 等）',
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
    if (sk === 'schema-save-excel') {
      return {
        ...node,
        title: '文档输出',
        body: '选择下载或入库及目标格式（含 xlsx / txt / md 等）',
        schemaKey: SCHEMA_LIBRARY_OUTPUT,
        schema: nodeSchemas.value[SCHEMA_LIBRARY_OUTPUT],
        configValues: {
          ..._defaultOutputConfigValues(),
          outputFormat: 'xlsx',
          sheetName: cv.sheetName,
          savePath: cv.savePath,
          outputMode: 'library'
        }
      }
    }
    if (sk === 'schema-save-text') {
      return {
        ...node,
        title: '文档输出',
        body: '选择下载或入库及目标格式（含 xlsx / txt / md 等）',
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
        body: '选择下载或入库及目标格式（含 xlsx / txt / md 等）',
        configValues: merged,
        schema: nodeSchemas.value[SCHEMA_LIBRARY_OUTPUT]
      }
    }
    return {
      ...node,
      title: '文档输出',
      body: '选择下载或入库及目标格式（含 xlsx / txt / md 等）',
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

  /** 首个输入节点的源格式（用于文件校验） */
  const workflowInputFileKind = computed(() => {
    const n = canvasNodes.value.find(x => x.type === 'input')
    const k = n?.configValues?.inputFileKind
    return typeof k === 'string' && k ? k : 'pdf'
  })

  /** 清空与当前源格式不匹配的选择 */
  function pruneFilesForWorkflowKind(kind) {
    selectedDocs.value = selectedDocs.value.filter(d => workflowFileMatchesKind(d.name, kind))
    localFiles.value = localFiles.value.filter(f => workflowFileMatchesKind(f.name, kind))
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
    currentWorkflowId.value = workflowId
    const wf = workflows.value[workflowId]

    if (!wf) {
      workflowName.value = '未命名'
      canvasNodes.value = []
      selectedNodeId.value = null
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

  async function saveCurrentWorkflow() {
    if (!currentWorkflowId.value) return
    const wf = workflows.value[currentWorkflowId.value]
    if (!wf) return
    // 节点要保存完整配置：id, type, title, icon, body, schemaKey, configValues
    wf.nodes = canvasNodes.value.map(({ x, y, schema, ...rest }) => rest)
    try {
      await workflowApi.saveWorkflow({
        id: wf.id,
        name: wf.name,
        icon: wf.icon || '',
        type: 'custom',
        nodes: wf.nodes,
        config: wf.config || {},
      })
      wf.time = '刚刚'
    } catch (e) {
      console.error('saveCurrentWorkflow error:', e)
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
  }

  function updateNodeConfig(nodeId, key, value) {
    const node = canvasNodes.value.find(n => n.id === nodeId)
    if (node) {
      if (!node.configValues) node.configValues = {}
      node.configValues[key] = value

      if (key === 'inputFileKind' && typeof value === 'string') {
        pruneFilesForWorkflowKind(value)
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
    return id
  }

  /** 新节点拖入画布时的默认配置，避免「处理类型」等依赖字段全空导致面板无内容 */
  function _defaultConfigForSchemaKey(schemaKey) {
    switch (schemaKey) {
      case 'schema-data-process':
        return { processKind: 'sort', sortOrder: 'asc' }
      case 'schema-data-clean':
        return { cleanRules: ['trim_spaces'] }
      case 'schema-table-extract':
        return { tableStrategy: 'first' }
      case 'schema-save-text':
        return { outputEncoding: 'utf-8', lineEnding: 'lf' }
      case 'schema-convert-format':
        return { targetFormat: 'markdown', conversionOptions: [] }
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
  }

  function clearCanvas() {
    canvasNodes.value = normalizeCanvasImportedNodes([])
    selectedNodeId.value = null
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
      const fk = workflowInputFileKind.value
      const mismatchedLib = selectedDocs.value.filter(d => !workflowFileMatchesKind(d.name, fk))
      if (mismatchedLib.length) {
        executionLogs.value.push({
          type: 'error',
          message: `以下文档与当前源格式（${fk}）不匹配：${mismatchedLib.map(d => d.name).join('、')}`
        })
        executionStatus.value = 'failed'
        return
      }
      const mismatchedLoc = localFiles.value.filter(f => !workflowFileMatchesKind(f.name, fk))
      if (mismatchedLoc.length) {
        executionLogs.value.push({
          type: 'error',
          message: `以下本地文件与当前源格式（${fk}）不匹配：${mismatchedLoc.map(f => f.name).join('、')}`
        })
        executionStatus.value = 'failed'
        return
      }

      if (selectedDocs.value.length === 0) {
        executionLogs.value.push({ type: 'error', message: '请从文档库选择至少一个输入文档' })
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
        localFiles: []
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
    // 计算属性
    currentWorkflow,
    workflowList,
    totalDocCount,
    workflowInputFileKind,
    // API 加载
    loadWorkflows,
    loadModels,
    loadLanguages,
    loadOutputFormats,
    // 工作流操作
    selectWorkflow,
    createNewWorkflow,
    saveCurrentWorkflow,
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
