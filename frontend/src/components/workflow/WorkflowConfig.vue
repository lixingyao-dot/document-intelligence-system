<script setup>
import { ref, computed, onMounted } from 'vue'
import { MousePointerClick } from 'lucide-vue-next'
import { useWorkflowStore, workflowFileMatchesKind } from '../../stores/workflowStore'
import { useLibraryStore } from '../../stores/libraryStore'
import { resolveWorkflowIcon } from '../../utils/workflowIcons'
import { isElectronShell, pickOutputFolder } from '../../utils/desktopShell'

const workflowStore = useWorkflowStore()
const libraryStore = useLibraryStore()

const workflowSourceKind = computed(() => workflowStore.workflowInputFileKind)

function docMatchesWorkflowKind(docName) {
  return workflowFileMatchesKind(docName, workflowSourceKind.value)
}

const localFileAccept = computed(() => {
  const k = workflowSourceKind.value
  const m = {
    pdf: '.pdf',
    md: '.md,.markdown',
    txt: '.txt',
    docx: '.doc,.docx',
    xlsx: '.xls,.xlsx'
  }
  return m[k] || '.pdf,.md,.txt,.doc,.docx,.xls,.xlsx'
})

function kindLabelZh(kind) {
  const map = {
    pdf: 'PDF',
    md: 'Markdown',
    txt: 'TXT',
    docx: 'Word',
    xlsx: 'Excel'
  }
  return map[kind] || kind
}
const fileInputRef = ref(null)
const isLoadingLibrary = ref(false)
const newSpaceName = ref('')

// 加载文档库空间
onMounted(async () => {
  try {
    await Promise.all([
      libraryStore.loadSpaces(),
      workflowStore.loadModels(),
      workflowStore.loadLanguages(),
      workflowStore.loadOutputFormats(),
    ])
  } catch (e) {
    console.error('initial load error:', e)
  }
})

// ==================== 节点配置更新 ====================
function updateConfig(key, value) {
  const nodeId = workflowStore.selectedNodeId
  if (nodeId) {
    workflowStore.updateNodeConfig(nodeId, key, value)
  }
}

function toggleMulti(key, option, checked) {
  const nodeId = workflowStore.selectedNodeId
  if (!nodeId) return
  const cfg = workflowStore.selectedNode?.configValues
  if (!cfg) return
  const current = Array.isArray(cfg[key]) ? [...cfg[key]] : []
  if (checked) {
    if (!current.includes(option)) current.push(option)
  } else {
    const idx = current.indexOf(option)
    if (idx > -1) current.splice(idx, 1)
  }
  updateConfig(key, current)
}

// ==================== 获取字段值 ====================
function getFieldValue(field, node) {
  if (!node || !node.configValues) return null
  return node.configValues[field.key] ?? null
}

function optionValue(opt) {
  if (opt && typeof opt === 'object') return opt.value ?? opt.label ?? ''
  return opt
}

function optionLabel(opt) {
  if (opt && typeof opt === 'object') return opt.label ?? opt.value ?? ''
  return opt
}

function normalizeFieldValue(value) {
  if (value && typeof value === 'object') return value.value ?? value.label ?? null
  return value
}

function getMultiFieldValues(field, node) {
  const raw = getFieldValue(field, node)
  if (!Array.isArray(raw)) return []
  return raw.map(v => normalizeFieldValue(v))
}

// ==================== Schema 获取 ====================
function getNodeSchema(node) {
  if (!node) return null
  return node.schema || workflowStore.nodeSchemas[node.schemaKey] || null
}

// ==================== 文档库选择相关 ====================

function normalizeOutputMode(raw) {
  const m = String(raw || 'library').toLowerCase()
  return m === 'external' || m === 'download' ? 'external' : 'library'
}

function handleOutputModeChange(value) {
  const mode = value === 'library' ? 'library' : 'external'
  updateConfig('outputMode', mode)
  if (mode === 'external') {
    updateConfig('targetSpaceId', null)
  } else {
    updateConfig('savePath', '')
  }
}

async function pickExternalOutputFolder() {
  const folder = await pickOutputFolder()
  if (folder) updateConfig('savePath', folder)
}

async function handleCreateNewSpace() {
  const name = newSpaceName.value.trim()
  if (!name) return
  try {
    const space = await libraryStore.createSpace(name)
    updateConfig('targetSpaceId', space.id)
    newSpaceName.value = ''
  } catch (e) {
    console.error('createSpace error:', e)
  }
}

function handleInputSourceChange(value) {
  updateConfig('inputSource', 'library')
  if (value !== 'library') {
    workflowStore.clearSelectedDocs()
    workflowStore.clearLocalFiles()
  }
}

// 下载输出文件
function downloadFile(file) {
  let url
  if (file.blob_name) {
    url = `/api/files/download-by-blob?blob_name=${encodeURIComponent(file.blob_name)}`
  } else {
    url = `/api/files/download?path=${encodeURIComponent(file.path)}`
  }
  const a = document.createElement('a')
  a.href = url
  a.download = file.name
  a.click()
}

// 选择文档库空间
function handleSpaceChange(spaceId) {
  updateConfig('spaceId', spaceId)
  if (spaceId) {
    loadDocsForSpace(spaceId)
  } else {
    workflowStore.clearSelectedDocs()
  }
}

async function loadDocsForSpace(spaceId) {
  isLoadingLibrary.value = true
  try {
    await libraryStore.loadDocs(spaceId)
    workflowStore.setSelectedDocs(
      libraryStore.currentDocs.filter(d => workflowFileMatchesKind(d.name, workflowStore.workflowInputFileKind))
    )
  } finally {
    isLoadingLibrary.value = false
  }
}

// 切换文档选中
function handleDocToggle(docId) {
  const doc = libraryStore.currentDocs.find(d => d.id === docId)
  if (!doc || !docMatchesWorkflowKind(doc.name)) return
  if (workflowStore.selectedDocs.find(d => d.id === docId)) {
    workflowStore.removeSelectedDoc(docId)
  } else {
    workflowStore.addSelectedDoc(doc)
  }
}

// ==================== 本地上传 ====================
function handleFileSelect(event) {
  const files = Array.from(event.target.files || [])
  const kind = workflowStore.workflowInputFileKind
  const matched = files.filter(f => workflowFileMatchesKind(f.name, kind))
  if (matched.length > 0) {
    workflowStore.addLocalFiles(matched)
  }
  // 清空 input 以便重复选择同一文件
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function handleDrop(event) {
  event.preventDefault()
  const files = Array.from(event.dataTransfer?.files || [])
  const kind = workflowStore.workflowInputFileKind
  const allowed = files.filter(f => workflowFileMatchesKind(f.name, kind))
  if (allowed.length > 0) {
    workflowStore.addLocalFiles(allowed)
  }
}

function handleDragOver(event) {
  event.preventDefault()
}

// ==================== 语言/格式选择 ====================
function handleLanguageChange(langCode) {
  updateConfig('targetLanguage', langCode)
}

function handleFormatChange(formatCode) {
  updateConfig('outputFormat', formatCode)
}

function _formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

// ==================== 目标文档库选择 ====================
function handleTargetSpaceChange(spaceId) {
  if (spaceId === '__new__') {
    // 显示新建表单，清空选择
    updateConfig('targetSpaceId', null)
    return
  }
  updateConfig('targetSpaceId', spaceId)
}

// ==================== 执行工作流 ====================
async function handleExecute() {
  await workflowStore.executeWorkflow()
}

// 当前选中的文档（来自 store）
const displayedDocs = computed(() => workflowStore.selectedDocs)
const displayedLocalFiles = computed(() => workflowStore.localFiles)
const currentInputSource = computed(() => 'library')

const currentSpaceId = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return null
  return getFieldValue({ key: 'spaceId' }, node) || null
})

const currentOutputMode = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return 'library'
  return normalizeOutputMode(getFieldValue({ key: 'outputMode' }, node)) === 'external' ? 'download' : 'library'
})

const currentTargetSpaceId = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return null
  return getFieldValue({ key: 'targetSpaceId' }, node) || null
})

const currentLanguage = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return null
  return getFieldValue({ key: 'targetLanguage' }, node) || null
})

const currentFormat = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return null
  return getFieldValue({ key: 'outputFormat' }, node) || workflowStore.outputFormats[0]?.code
})

/** 是否显示该 schema 字段（支持 conditionField、dependsOn、arrayIncludes） */
function isFieldVisible(field, node) {
  if (!node) return false
  if (field.conditionField != null && field.conditionValue !== undefined) {
    let actual = getFieldValue({ key: field.conditionField }, node)
    if (field.conditionField === 'outputMode') {
      actual = normalizeOutputMode(actual)
    }
    if (actual !== field.conditionValue) return false
  }
  const raw = field.dependsOn
  if (!raw) return true
  const deps = Array.isArray(raw) ? raw : [raw]
  for (const dep of deps) {
    const val = getFieldValue({ key: dep.field }, node)
    if (dep.arrayIncludes != null) {
      const arr = Array.isArray(val) ? val : val != null ? [val] : []
      if (!arr.includes(dep.arrayIncludes)) return false
    } else if (dep.value !== undefined && val !== dep.value) {
      return false
    }
  }
  return true
}

const filteredFields = computed(() => {
  const schema = getNodeSchema(workflowStore.selectedNode)
  if (!schema?.fields) return []
  return schema.fields.filter(f => isFieldVisible(f, workflowStore.selectedNode))
})

/** 当前选中节点在执行顺序（canvasNodes 序列）中的索引 */
const selectedStepOrderIndex = computed(() => {
  const id = workflowStore.selectedNodeId
  if (!id) return -1
  return workflowStore.canvasNodes.findIndex(n => n.id === id)
})

/** 侧栏「前移 / 后移」：仅切换选中节点，不改变画布节点顺序与坐标 */
function selectPrevNodeInOrder() {
  const i = selectedStepOrderIndex.value
  if (i <= 0) return
  const prev = workflowStore.canvasNodes[i - 1]
  if (prev) workflowStore.selectNode(prev.id)
}

function selectNextNodeInOrder() {
  const i = selectedStepOrderIndex.value
  const nodes = workflowStore.canvasNodes
  if (i < 0 || i >= nodes.length - 1) return
  const next = nodes[i + 1]
  if (next) workflowStore.selectNode(next.id)
}

const executionButtonText = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return '执行'
  
  const title = node.title || node.type
  
  // 根据节点标题生成对应的按钮文本
  const verbMap = {
    'AI 翻译': '翻译',
    '内容提取': '提取',
    '数据抽取': '抽取',
    '实体提取': '提取',
    '数据处理': '处理',
    '数据清洗': '清洗',
    '表格提取': '提取',
    '数据汇总': '汇总',
    '内容分析': '分析',
    '文本增强': '增强',
    '格式转换': '转换',
    '文档分割': '分割',
    '保存 Excel': '导出',
    '保存文本': '保存'
  }
  
  const verb = verbMap[title] || '处理'
  return `开始${verb}`
})

function nodeStatusText(status) {
  const map = {
    pending: '等待中',
    running: '执行中',
    completed: '已完成',
    partial: '部分完成',
    failed: '失败'
  }
  return map[status] || '未开始'
}
</script>

<template>
  <div class="workflow-config-panel">

    <div class="config-content">

      <div v-if="workflowStore.selectedNode" class="config-section node-config-anim">

        <!-- Step Indicator -->
        <div class="step-indicator">
          <div
            v-for="(node, i) in workflowStore.canvasNodes"
            :key="node.id"
            class="step-dot-wrap"
          >
            <div
              class="step-dot"
              :class="{
                'step-done': i < workflowStore.canvasNodes.findIndex(n => n.id === workflowStore.selectedNodeId),
                'step-active': workflowStore.selectedNodeId === node.id
              }"
            ></div>
            <div v-if="i < workflowStore.canvasNodes.length - 1" class="step-connector"></div>
          </div>
        </div>

        <!-- Node Header -->
        <div class="node-config-header">
          <div
            class="node-config-icon-wrap node-config-icon-wrap--schema"
            :class="workflowStore.selectedNode.type"
            aria-hidden="true"
          >
            <component
              :is="resolveWorkflowIcon(workflowStore.selectedNode.schemaKey, workflowStore.selectedNode.type)"
              :size="20"
              :stroke-width="2"
            />
          </div>
          <div>
            <div class="node-config-title">{{ workflowStore.selectedNode.title }}</div>
            <div class="node-config-subtitle">{{ getNodeSchema(workflowStore.selectedNode)?.subtitle }}</div>
          </div>
        </div>

        <!-- 侧栏内切换查看节点；画布顺序与位置由画布上操作或拖拽决定 -->
        <div v-if="workflowStore.canvasNodes.length > 1" class="config-group step-order-group">
          <div class="config-group-label">节点切换</div>
          <p class="step-order-hint">
            「前移 / 后移」仅在侧栏内切换到上一 / 下一节点，不改变画布上节点位置与连线。
          </p>
          <div class="step-order-row">
            <button
              type="button"
              class="step-order-btn"
              :disabled="selectedStepOrderIndex <= 0"
              title="切换到上一节点"
              @click="selectPrevNodeInOrder"
            >前移</button>
            <span class="step-order-pos">第 {{ selectedStepOrderIndex + 1 }} / {{ workflowStore.canvasNodes.length }} 步</span>
            <button
              type="button"
              class="step-order-btn"
              :disabled="selectedStepOrderIndex < 0 || selectedStepOrderIndex >= workflowStore.canvasNodes.length - 1"
              title="切换到下一节点"
              @click="selectNextNodeInOrder"
            >后移</button>
          </div>
        </div>

        <!-- Fields -->
        <div class="config-group">
          <div class="config-group-label">参数配置</div>

          <template v-for="(field, fIdx) in filteredFields" :key="field.key || ('static-' + fIdx)">

            <!-- ===== 静态说明 ===== -->
            <div v-if="field.type === 'static'" class="field field-static-row">
              <p class="field-static-text">{{ field.text }}</p>
            </div>

            <!-- ===== 输出模式选择 ===== -->
            <div v-else-if="field.type === 'output-mode-select'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div class="source-tabs">
                <button
                  class="source-tab"
                  :class="{ active: currentOutputMode === 'download' }"
                  @click="handleOutputModeChange('download')"
                >仅输出（可下载）</button>
                <button
                  class="source-tab"
                  :class="{ active: currentOutputMode === 'library' }"
                  @click="handleOutputModeChange('library')"
                >保存到文档库</button>
              </div>
            </div>

            <!-- ===== 输入来源选择 ===== -->
            <div v-else-if="field.type === 'select-source'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div class="source-tabs">
                <button
                  v-for="opt in field.options"
                  :key="opt.value"
                  class="source-tab"
                  :class="{ active: currentInputSource === opt.value }"
                  @click="handleInputSourceChange(opt.value)"
                >{{ opt.label }}</button>
              </div>
            </div>

            <!-- ===== 文档库选择器 ===== -->
            <div v-else-if="field.type === 'library-selector'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <select
                class="config-select"
                :value="field.key === 'targetSpaceId' ? currentTargetSpaceId : currentSpaceId"
                @change="field.key === 'targetSpaceId' ? handleTargetSpaceChange($event.target.value) : handleSpaceChange($event.target.value)"
              >
                <option value="">-- 选择文档库 --</option>
                <option
                  v-for="space in libraryStore.spaces"
                  :key="space.id"
                  :value="space.id"
                >{{ space.name }}</option>
                <option value="__new__">新建文档库…</option>
              </select>
              <div v-if="field.key === 'targetSpaceId' && currentTargetSpaceId === '__new__'" class="new-space-form">
                <input
                  v-model="newSpaceName"
                  class="config-input"
                  placeholder="输入新文档库名称"
                  style="margin-top: 8px;"
                />
                <button
                  class="btn-sm btn-primary"
                  style="margin-top: 6px;"
                  @click="handleCreateNewSpace"
                >确认创建</button>
              </div>
            </div>

            <!-- ===== 语言选择器 ===== -->
            <div v-else-if="field.type === 'language-selector'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div class="language-grid">
                <button
                  v-for="lang in workflowStore.availableLanguages"
                  :key="lang.code"
                  class="lang-chip"
                  :class="{ active: currentLanguage === lang.code }"
                  @click="handleLanguageChange(lang.code)"
                >{{ lang.label }}</button>
              </div>
            </div>

            <!-- ===== 格式选择器 ===== -->
            <div v-else-if="field.type === 'format-selector'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div class="format-grid">
                <button
                  v-for="fmt in workflowStore.outputFormats"
                  :key="fmt.code"
                  class="format-chip"
                  :class="{ active: currentFormat === fmt.code }"
                  @click="handleFormatChange(fmt.code)"
                >{{ fmt.label }}</button>
              </div>
            </div>

            <!-- ===== Select ===== -->
            <div v-else-if="field.type === 'select'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <select
                class="config-select"
                :value="normalizeFieldValue(getFieldValue(field, workflowStore.selectedNode))"
                @change="updateConfig(field.key, $event.target.value)"
              >
                <option
                  v-for="opt in (field.options || [])"
                  :key="optionValue(opt)"
                  :value="optionValue(opt)"
                >{{ optionLabel(opt) }}</option>
              </select>
            </div>

            <!-- ===== Input ===== -->
            <div v-else-if="field.type === 'input'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div v-if="field.key === 'savePath'" class="path-input-row">
                <input
                  class="config-input"
                  type="text"
                  :placeholder="field.placeholder || ''"
                  :value="getFieldValue(field, workflowStore.selectedNode)"
                  @input="updateConfig(field.key, $event.target.value)"
                />
                <button
                  v-if="isElectronShell()"
                  type="button"
                  class="btn-sm btn-secondary path-pick-btn"
                  @click="pickExternalOutputFolder"
                >选择文件夹</button>
              </div>
              <input
                v-else
                class="config-input"
                type="text"
                :placeholder="field.placeholder || ''"
                :value="getFieldValue(field, workflowStore.selectedNode)"
                @input="updateConfig(field.key, $event.target.value)"
              />
            </div>

            <!-- ===== Textarea ===== -->
            <div v-else-if="field.type === 'textarea'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <textarea
                class="config-textarea"
                :value="getFieldValue(field, workflowStore.selectedNode)"
                @input="updateConfig(field.key, $event.target.value)"
              ></textarea>
            </div>

            <!-- ===== Range ===== -->
            <div v-else-if="field.type === 'range'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div class="range-row">
                <input
                  type="range"
                  class="range-input"
                  :min="field.min"
                  :max="field.max"
                  :value="getFieldValue(field, workflowStore.selectedNode)"
                  @input="updateConfig(field.key, Number($event.target.value))"
                  />
                <span class="range-val">{{ getFieldValue(field, workflowStore.selectedNode) || field.min }} {{ field.unit }}</span>
              </div>
            </div>

            <!-- ===== Toggle ===== -->
            <div v-else-if="field.type === 'toggle'" class="field field-toggle-row">
              <label class="field-label">{{ field.label }}</label>
              <div
                class="toggle-switch"
                :class="{ on: getFieldValue(field, workflowStore.selectedNode) }"
                @click="updateConfig(field.key, !getFieldValue(field, workflowStore.selectedNode)); $event.target.classList.toggle('on')"
              ></div>
            </div>

            <!-- ===== Multi-select tags ===== -->
            <div v-else-if="field.type === 'multiselect' || field.type === 'select-multiple'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div class="tag-grid">
                <div
                  v-for="opt in (field.options || [])"
                  :key="optionValue(opt)"
                  class="tag-chip"
                  :class="{ active: getMultiFieldValues(field, workflowStore.selectedNode).includes(optionValue(opt)) }"
                  @click="toggleMulti(field.key, optionValue(opt), !getMultiFieldValues(field, workflowStore.selectedNode).includes(optionValue(opt)))"
                >{{ optionLabel(opt) }}</div>
              </div>
            </div>

          </template>
        </div>

        <!-- ===== 文档选择区域（仅输入节点显示） ===== -->
        <div v-if="workflowStore.selectedNode.type === 'input'" class="config-group">
          <div class="config-group-label">
            待处理文档
            <span class="doc-count-badge">{{ displayedDocs.length }} 个</span>
          </div>

          <p class="doc-source-format-hint" style="margin-bottom: 8px;">
            输入仅来自文档库；请在「参数配置」中选择输入文档库并勾选文件。
          </p>

          <div class="doc-library-section">
            <div v-if="isLoadingLibrary" class="doc-loading">
              <span class="loading-dots-sm"><span></span><span></span><span></span></span> 加载文档...
            </div>
            <div v-else-if="!currentSpaceId" class="doc-empty-hint">
              请先在「参数配置」中选择一个文档库
            </div>
            <template v-else>
              <div class="doc-source-format-hint">
                文档库中与当前源格式（{{ kindLabelZh(workflowSourceKind) }}）不符的条目不可勾选
              </div>
              <div v-if="libraryStore.currentDocs.length === 0" class="doc-empty-hint">
                该文档库暂无文档
              </div>
              <div v-else class="doc-list">
                <div
                  v-for="doc in libraryStore.currentDocs"
                  :key="doc.id"
                  class="doc-list-item"
                  :class="{
                    selected: workflowStore.selectedDocs.find(d => d.id === doc.id),
                    'doc-kind-mismatch': !docMatchesWorkflowKind(doc.name)
                  }"
                  @click="handleDocToggle(doc.id)"
                >
                  <div class="doc-list-check">
                    <span v-if="workflowStore.selectedDocs.find(d => d.id === doc.id)" class="check-mark" />
                  </div>
                  <span class="doc-list-icon" aria-hidden="true" />
                  <span class="doc-list-name">{{ doc.name }}</span>
                  <span class="doc-list-size">{{ doc.size }}</span>
                </div>
              </div>
            </template>
          </div>

          <!-- 本地上传区域 -->
          <div v-if="false" class="doc-local-section">
            <div
              class="upload-zone"
              @click="fileInputRef?.click()"
              @drop="handleDrop"
              @dragover="handleDragOver"
            >
              <input
                ref="fileInputRef"
                type="file"
                :accept="localFileAccept"
                multiple
                style="display:none"
                @change="handleFileSelect"
              />
              <div class="upload-zone-icon" aria-hidden="true" />
              <div class="upload-zone-text">点击或拖拽文件到此处</div>
              <div class="upload-zone-hint">须与上文「源文件格式」一致（当前：{{ kindLabelZh(workflowSourceKind) }}）</div>
            </div>

            <!-- 已选本地文件 -->
            <div v-if="displayedLocalFiles.length > 0" class="local-files-list">
              <div
                v-for="file in displayedLocalFiles"
                :key="file.id"
                class="local-file-item"
              >
                <span class="local-file-icon" aria-hidden="true" />
                <span class="local-file-name">{{ file.name }}</span>
                <span class="local-file-size">{{ _formatSize(file.size) }}</span>
                <button
                  class="local-file-remove"
                  @click="workflowStore.removeLocalFile(file.id)"
                >×</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Selected Docs Summary (for non-input nodes) -->
        <div v-if="workflowStore.selectedNode.type !== 'input' && displayedDocs.length > 0" class="config-group">
          <div class="config-group-label">
            已选文档 <span class="doc-count-badge">{{ displayedDocs.length }} 个</span>
          </div>
          <div class="selected-docs-list">
            <div
              v-for="doc in displayedDocs"
              :key="doc.id"
              class="selected-doc-item"
            >
              <span class="selected-doc-icon" aria-hidden="true" />
              <span class="selected-doc-name">{{ doc.name }}</span>
              <span class="selected-doc-size">{{ doc.size }}</span>
            </div>
          </div>
        </div>

        <!-- Action Button -->
        <button
          class="config-btn"
          :class="{ executing: workflowStore.isExecuting }"
          @click="handleExecute"
          :disabled="workflowStore.isExecuting"
        >
          <span v-if="workflowStore.isExecuting" class="btn-spinner"></span>
          <span v-else>▶</span>
          <span>{{ workflowStore.isExecuting ? `处理中 ${workflowStore.executionProgress}%` : executionButtonText }}</span>
        </button>

        <!-- Execution Progress -->
        <div v-if="workflowStore.isExecuting || workflowStore.executionLogs.length > 0" class="execution-status">
          <div class="exec-progress-bar">
            <div class="exec-progress-fill" :style="{ width: workflowStore.executionProgress + '%' }"></div>
          </div>
          <div v-if="workflowStore.nodeProgress.length > 0" class="node-progress-list">
            <div
              v-for="item in workflowStore.nodeProgress"
              :key="item.id"
              class="node-progress-item"
              :class="'node-progress-' + item.status"
            >
              <div class="node-progress-main">
                <span class="node-progress-index">{{ item.index }}</span>
                <span class="node-progress-title">{{ item.title }}</span>
                <span class="node-progress-state">{{ nodeStatusText(item.status) }}</span>
              </div>
              <div class="node-progress-track">
                <div class="node-progress-fill" :style="{ width: (item.progress || 0) + '%' }"></div>
              </div>
            </div>
          </div>
          <div class="exec-logs">
            <div
              v-for="(log, i) in workflowStore.executionLogs"
              :key="i"
              class="exec-log-item"
              :class="'log-' + log.type"
            >{{ log.message }}</div>
          </div>
        </div>

        <!-- Output Files Download -->
        <div v-if="workflowStore.outputFiles.length > 0 && !workflowStore.isExecuting" class="output-files-section">
          <div class="output-files-title">输出文件</div>
          <div
            v-for="f in workflowStore.outputFiles"
            :key="f.path"
            class="output-file-item"
          >
            <span class="output-file-name">{{ f.name }}</span>
            <span class="output-file-size">{{ (f.size / 1024).toFixed(1) }} KB</span>
            <button class="output-download-btn" @click="downloadFile(f)">下载</button>
          </div>
        </div>
      </div>

      <!-- ======== 无选中节点 — 空状态 ======== -->
      <div v-else class="config-empty-state">
        <div class="empty-icon empty-icon-shape" aria-hidden="true">
          <MousePointerClick :size="28" :stroke-width="1.75" />
        </div>
        <div class="empty-title">点击节点以配置</div>
        <div class="empty-desc">在画布上点击任意节点<br/>右侧将切换显示该节点的专属配置</div>
        <div class="empty-nodes-hint" v-if="workflowStore.canvasNodes.length > 0">
          <div class="empty-nodes-title">工作流节点</div>
          <div
            v-for="(node, i) in workflowStore.canvasNodes"
            :key="node.id"
            class="empty-node-item"
            :class="{ done: workflowStore.selectedNodeId && i < workflowStore.canvasNodes.findIndex(n => n.id === workflowStore.selectedNodeId) }"
            @click="workflowStore.selectNode(node.id)"
          >
            <span class="empty-node-icon" :class="node.type" aria-hidden="true" />
            <span>{{ node.title }}</span>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.source-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  padding: 3px;
}

.source-tab {
  flex: 1;
  padding: 8px 12px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.source-tab:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.source-tab.active {
  background: var(--bg-card);
  border-color: rgba(125, 211, 252, 0.3);
  color: var(--accent-primary);
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(125, 211, 252, 0.12);
}

.doc-count-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-primary);
  background: rgba(125, 211, 252, 0.12);
  padding: 2px 8px;
  border-radius: 0;
  margin-left: 8px;
}

.doc-library-section {
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.doc-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-muted);
  font-size: 13px;
}

.loading-dots-sm {
  display: flex;
  gap: 4px;
}

.loading-dots-sm span {
  width: 6px;
  height: 6px;
  background: var(--accent-purple);
  border-radius: 0;
  animation: pulse-dot 1.4s ease-in-out infinite;
}

.loading-dots-sm span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots-sm span:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

.doc-empty-hint {
  padding: 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.doc-source-format-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
  line-height: 1.45;
}

.doc-kind-mismatch {
  opacity: 0.45;
  cursor: not-allowed;
}

.doc-list {
  max-height: 220px;
  overflow-y: auto;
}

.doc-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 13px;
  border-bottom: 1px solid var(--border-color);
}

.doc-list-item:last-child {
  border-bottom: none;
}

.doc-list-item:hover {
  background: var(--bg-hover);
}

.doc-list-item.selected {
  background: rgba(125, 211, 252, 0.08);
}

.doc-list-check {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border-color);
  border-radius: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s;
}

.doc-list-item.selected .doc-list-check {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
}

.doc-list-item.selected .check-mark {
  border-color: #fff;
}

.check-mark {
  display: block;
  width: 5px;
  height: 9px;
  border: solid transparent;
  border-width: 0 2px 2px 0;
  border-color: var(--accent-primary);
  transform: rotate(45deg);
  margin-bottom: 2px;
}

.doc-list-icon {
  width: 3px;
  height: 22px;
  border-radius: 0;
  background: rgba(125, 211, 252, 0.22);
  flex-shrink: 0;
}

.doc-list-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
}

.doc-list-size {
  color: var(--text-muted);
  font-size: 12px;
  flex-shrink: 0;
}

/* Local upload section */
.doc-local-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.upload-zone {
  border: 2px dashed var(--border-color);
  border-radius: var(--radius-md);
  padding: 24px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-tertiary);
}

.upload-zone:hover {
  border-color: rgba(125, 211, 252, 0.45);
  background: rgba(125, 211, 252, 0.04);
}

.upload-zone-icon {
  width: 40px;
  height: 40px;
  margin: 0 auto 8px;
  border-radius: 0;
  border: 2px dashed rgba(125, 211, 252, 0.28);
  background: rgba(125, 211, 252, 0.05);
}

.upload-zone-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.upload-zone-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.local-files-list {
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.local-file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  font-size: 13px;
  border-bottom: 1px solid var(--border-color);
}

.local-file-item:last-child {
  border-bottom: none;
}

.local-file-icon {
  width: 3px;
  height: 22px;
  border-radius: 0;
  background: rgba(125, 211, 252, 0.22);
  flex-shrink: 0;
}

.local-file-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
}

.local-file-size {
  color: var(--text-muted);
  font-size: 12px;
  flex-shrink: 0;
}

.local-file-remove {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 0;
  font-size: 16px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.local-file-remove:hover {
  background: rgba(239, 68, 68, 0.15);
  color: var(--accent-danger);
}

/* Language grid */
.language-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.lang-chip {
  padding: 6px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.lang-chip:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}

.lang-chip.active {
  background: rgba(6, 182, 212, 0.15);
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
  font-weight: 600;
}

/* Format grid */
.format-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.format-chip {
  padding: 6px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.format-chip:hover {
  border-color: var(--accent-warning);
  color: var(--accent-warning);
}

.format-chip.active {
  background: rgba(245, 158, 11, 0.15);
  border-color: var(--accent-warning);
  color: var(--accent-warning);
  font-weight: 600;
}

.field-hint {
  margin-top: 6px;
}

.field-static-row {
  margin: 0 0 10px;
}

.field-static-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
  padding: 10px 12px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}

.step-order-group {
  margin-bottom: 4px;
}

.step-order-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.45;
}

.step-order-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.step-order-btn {
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.step-order-btn:hover:not(:disabled) {
  border-color: var(--accent-purple);
  color: var(--accent-purple);
}

.step-order-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.step-order-pos {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.field-badge {
  display: inline-block;
  margin: 4px 0 8px;
  padding: 2px 8px;
  border-radius: 0;
  font-size: 11px;
  font-weight: 600;
}

.field-badge-warning {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.28);
}

.hint-loading {
  font-size: 12px;
  color: var(--text-muted);
}

/* Execute button */
.config-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px;
  background: var(--gradient-success);
  border: none;
  border-radius: var(--radius-md);
  font-size: 15px;
  font-weight: 600;
  color: white;
  cursor: pointer;
  transition: all 0.2s;
  margin-top: 8px;
}

.config-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(16, 185, 129, 0.4);
}

.config-btn.executing {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  cursor: default;
}

.config-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.btn-spinner {
  display: inline-block;
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 0;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Execution status */
.execution-status {
  margin-top: 16px;
  padding: 14px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.exec-progress-bar {
  height: 6px;
  background: var(--bg-secondary);
  border-radius: 0;
  overflow: hidden;
  margin-bottom: 12px;
}

.exec-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-success), var(--accent-cyan));
  border-radius: 0;
  transition: width 0.5s ease;
}

.node-progress-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.node-progress-item {
  padding: 8px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.node-progress-main {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.node-progress-index {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
}

.node-progress-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.node-progress-state {
  color: var(--text-muted);
  font-size: 11px;
}

.node-progress-track {
  height: 4px;
  overflow: hidden;
  border-radius: 0;
  background: var(--bg-tertiary);
}

.node-progress-fill {
  height: 100%;
  width: 0;
  border-radius: 0;
  background: var(--text-muted);
  transition: width 0.35s ease;
}

.node-progress-running .node-progress-index,
.node-progress-running .node-progress-fill {
  background: var(--accent-cyan);
  color: #06202a;
}

.node-progress-completed .node-progress-index,
.node-progress-completed .node-progress-fill {
  background: var(--accent-success);
  color: white;
}

.node-progress-failed .node-progress-index,
.node-progress-failed .node-progress-fill {
  background: #ef4444;
  color: white;
}

.exec-logs {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 120px;
  overflow-y: auto;
}

.output-files-section {
  margin-top: 16px;
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}

.output-files-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.output-file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 0;
  background: var(--bg-tertiary);
  margin-bottom: 6px;
}

.output-file-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.output-file-size {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

.output-download-btn {
  padding: 4px 12px;
  border-radius: 0;
  background: var(--accent-primary);
  color: #fff;
  border: none;
  font-size: 12px;
  cursor: pointer;
  transition: opacity 0.2s;
  white-space: nowrap;
}

.output-download-btn:hover {
  opacity: 0.85;
}

.exec-log-item {
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0;
  border-bottom: 1px solid var(--border-color);
}

.exec-log-item:last-child {
  border-bottom: none;
}

.path-input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.path-input-row .config-input {
  flex: 1;
  min-width: 0;
}

.path-pick-btn {
  flex-shrink: 0;
  white-space: nowrap;
}

.exec-log-item.log-done {
  color: var(--accent-success);
}

.exec-log-item.log-error {
  color: var(--accent-danger);
}

</style>
