import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { useLibraryStore } from './libraryStore'

const PICKER_SPACE_KEY = 'chat_picker_library_space_id'

/**
 * 聊天附件：仅从文档库勾选，发送时携带 library_doc_id，由后端解析路径。
 */
export const useFileStore = defineStore('file', () => {
  const libraryStore = useLibraryStore()

  const currentFileType = ref('data')
  const filesPanelCollapsed = ref(true)
  const searchQuery = ref('')
  const pickerSpaceId = ref(localStorage.getItem(PICKER_SPACE_KEY) || '')
  const isLoadingDocs = ref(false)

  const tempFiles = ref({
    data: [],
    template: [],
  })

  const currentFiles = computed(() => tempFiles.value[currentFileType.value])

  const hasDataFiles = computed(() => tempFiles.value.data.length > 0)
  const hasTemplateFiles = computed(() => tempFiles.value.template.length > 0)
  const hasFiles = computed(() => hasDataFiles.value || hasTemplateFiles.value)

  const dataCount = computed(() => tempFiles.value.data.filter((f) => f.is_selected).length)
  const templateCount = computed(() => tempFiles.value.template.filter((f) => f.is_selected).length)

  const selectedDataCount = computed(() => dataCount.value)
  const selectedTemplateCount = computed(() => templateCount.value)

  watch(pickerSpaceId, (id) => {
    if (id) localStorage.setItem(PICKER_SPACE_KEY, id)
    else localStorage.removeItem(PICKER_SPACE_KEY)
  })

  function switchFileType(type) {
    currentFileType.value = type
  }

  function parseSizeToBytes(sizeLabel) {
    if (typeof sizeLabel === 'number') return sizeLabel
    const s = String(sizeLabel || '').trim()
    const m = s.match(/^([\d.]+)\s*(B|KB|MB|GB)?$/i)
    if (!m) return 0
    const n = parseFloat(m[1])
    const unit = (m[2] || 'B').toUpperCase()
    const mult = { B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3 }
    return Math.round(n * (mult[unit] || 1))
  }

  function docToFileInfo(doc, type) {
    return {
      id: doc.id,
      library_doc_id: doc.id,
      file_name: doc.name,
      file_size: parseSizeToBytes(doc.size),
      file_type: type,
      space_id: pickerSpaceId.value,
      is_selected: true,
      created_at: doc.created_at || new Date().toISOString(),
    }
  }

  async function ensureSpacesLoaded() {
    if (!libraryStore.spaces.length) {
      await libraryStore.loadSpaces()
    }
    if (!pickerSpaceId.value && libraryStore.spaces.length) {
      pickerSpaceId.value = libraryStore.spaces[0].id
    }
  }

  async function setPickerSpace(spaceId) {
    pickerSpaceId.value = spaceId || ''
    await loadPickerDocs()
  }

  async function loadPickerDocs() {
    if (!pickerSpaceId.value) {
      return
    }
    isLoadingDocs.value = true
    try {
      await libraryStore.loadDocs(pickerSpaceId.value, true)
    } finally {
      isLoadingDocs.value = false
    }
  }

  function isDocInSelection(docId, type) {
    return tempFiles.value[type].some((f) => f.id === docId)
  }

  function toggleLibraryDoc(doc, type) {
    const t = type || currentFileType.value
    const idx = tempFiles.value[t].findIndex((f) => f.id === doc.id)
    if (idx > -1) {
      tempFiles.value[t].splice(idx, 1)
      return
    }
    tempFiles.value[t].push(docToFileInfo(doc, t))
  }

  async function addFile(type, file) {
    const tempId = `temp_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
    const fileUrl = URL.createObjectURL(file)
    tempFiles.value[type].push({
      id: tempId,
      file_name: file.name,
      file_size: file.size,
      file_type: type,
      file_url: fileUrl,
      original_file: file,
      is_selected: true,
      created_at: new Date().toISOString(),
    })
  }

  function removeFile(id, type) {
    const index = tempFiles.value[type].findIndex((f) => f.id === id)
    if (index > -1) {
      const fileInfo = tempFiles.value[type][index]
      const url = fileInfo?.file_url
      if (url && String(url).startsWith('blob:')) {
        try {
          URL.revokeObjectURL(url)
        } catch (_) {}
      }
      tempFiles.value[type].splice(index, 1)
    }
  }

  function toggleFileSelection(id, type, isSelected) {
    const tempIndex = tempFiles.value[type].findIndex((f) => f.id === id)
    if (tempIndex > -1) {
      tempFiles.value[type][tempIndex].is_selected = isSelected
    }
  }

  function getFileTypeLabel(filename) {
    const ext = filename.split('.').pop().toLowerCase()
    const map = {
      pdf: 'PDF',
      doc: 'DOC',
      docx: 'DOCX',
      xls: 'XLS',
      xlsx: 'XLSX',
      txt: 'TXT',
      md: 'MD',
      csv: 'CSV',
    }
    return map[ext] || ext.toUpperCase()
  }

  function toggleFilesPanel() {
    filesPanelCollapsed.value = !filesPanelCollapsed.value
  }

  const pickerDocs = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    const spaceId = pickerSpaceId.value
    const docs = spaceId
      ? (libraryStore.docsCache[spaceId] || [])
      : []
    if (!q) return docs
    return docs.filter((d) => d.name.toLowerCase().includes(q))
  })

  return {
    currentFileType,
    filesPanelCollapsed,
    searchQuery,
    pickerSpaceId,
    tempFiles,
    currentFiles,
    hasDataFiles,
    hasTemplateFiles,
    hasFiles,
    dataCount,
    templateCount,
    selectedDataCount,
    selectedTemplateCount,
    isLoadingDocs,
    pickerDocs,
    switchFileType,
    ensureSpacesLoaded,
    setPickerSpace,
    loadPickerDocs,
    isDocInSelection,
    toggleLibraryDoc,
    addFile,
    removeFile,
    toggleFileSelection,
    toggleFilesPanel,
    getFileTypeLabel,
    setSearchQuery: (q) => {
      searchQuery.value = q
    },
  }
})
