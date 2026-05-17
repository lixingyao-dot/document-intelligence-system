import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import libraryApi from '../api/library'

export const useLibraryStore = defineStore('library', () => {
  // 状态
  const spaces = ref([])
  const docsCache = ref({})        // spaceId -> docs[]
  const currentSpaceId = ref(null)
  const currentDocs = ref([])      // 当前空间的文档（来自缓存或API）
  const searchQuery = ref('')
  const selectedDocIds = ref(new Set())
  const isLoading = ref(false)
  const isUploading = ref(false)
  const uploadProgress = ref(0)
  const isExporting = ref(false)
  const error = ref(null)

  // 计算属性
  const currentSpace = computed(() => spaces.value.find(s => s.id === currentSpaceId.value) || null)
  const selectedCount = computed(() => selectedDocIds.value.size)
  const filteredDocs = computed(() => {
    if (!searchQuery.value.trim()) return currentDocs.value
    const q = searchQuery.value.toLowerCase()
    return currentDocs.value.filter(d => d.name.toLowerCase().includes(q))
  })

  // ==================== 空间操作 ====================

  async function loadSpaces() {
    isLoading.value = true
    error.value = null
    try {
      const res = await libraryApi.getSpaces()
      spaces.value = (res?.spaces || []).map(s => ({
        id: s.id,
        name: s.name,
        icon: s.icon || '',
        description: s.description,
        doc_count: s.doc_count || 0,
        created_at: s.created_at,
        updated_at: s.updated_at,
      }))
      // 左侧 doc_count 来自服务端；若仍用本地 docs 缓存，列表会与数字不一致（如工作流入库后）
      docsCache.value = {}
      if (spaces.value.length === 0) {
        currentSpaceId.value = null
        currentDocs.value = []
      } else {
        if (!currentSpaceId.value) {
          clearSelection()
          currentSpaceId.value = spaces.value[0].id
        }
        await loadDocs(currentSpaceId.value, true)
      }
    } catch (e) {
      error.value = e.message || '加载空间列表失败'
      console.error('loadSpaces error:', e)
    } finally {
      isLoading.value = false
    }
  }

  async function createSpace(name, icon = '', description = '') {
    error.value = null
    try {
      const res = await libraryApi.createSpace({ name, icon, description })
      const s = res
      spaces.value.unshift({
        id: s.id,
        name: s.name,
        icon: s.icon || icon,
        description: s.description,
        doc_count: 0,
        created_at: s.created_at,
        updated_at: s.updated_at,
      })
      selectSpace(s.id)
      return s
    } catch (e) {
      error.value = e.message || '创建空间失败'
      throw e
    }
  }

  async function deleteSpace(spaceId) {
    error.value = null
    try {
      await libraryApi.deleteSpace(spaceId)
      spaces.value = spaces.value.filter(s => s.id !== spaceId)
      delete docsCache.value[spaceId]
      if (currentSpaceId.value === spaceId) {
        clearSelection()
        currentDocs.value = []
        currentSpaceId.value = spaces.value.length > 0 ? spaces.value[0].id : null
        if (currentSpaceId.value) {
          selectSpace(currentSpaceId.value)
        }
      }
    } catch (e) {
      error.value = e.message || '删除空间失败'
      throw e
    }
  }

  function selectSpace(spaceId, forceRefresh = false) {
    if (currentSpaceId.value === spaceId && !forceRefresh) return
    currentSpaceId.value = spaceId
    clearSelection()
    if (docsCache.value[spaceId] && !forceRefresh) {
      currentDocs.value = docsCache.value[spaceId]
      isLoading.value = false
    } else {
      loadDocs(spaceId)
    }
  }

  // ==================== 文档操作 ====================

  async function loadDocs(spaceId, forceRefresh = false) {
    if (!spaceId) return
    // 如果有缓存且不是强制刷新，直接用缓存
    if (docsCache.value[spaceId] && !forceRefresh) {
      currentDocs.value = docsCache.value[spaceId]
      isLoading.value = false
      return
    }
    isLoading.value = true
    error.value = null
    try {
      const res = await libraryApi.getDocs(spaceId)
      const docs = (res?.docs || []).map(d => ({
        id: d.id,
        name: d.file_name,
        size: _formatSize(d.file_size),
        size_bytes: d.file_size,
        time: _formatTime(d.created_at),
        mime_type: d.mime_type,
        file_extension: d.file_extension,
        storage_key: d.storage_key,
        blob_url: d.blob_url,
        created_at: d.created_at,
        updated_at: d.updated_at,
      }))
      // 更新缓存和当前文档
      docsCache.value[spaceId] = docs
      if (currentSpaceId.value === spaceId) {
        currentDocs.value = docs
      }
    } catch (e) {
      error.value = e.message || '加载文档列表失败'
      console.error('loadDocs error:', e)
    } finally {
      isLoading.value = false
    }
  }

  async function uploadDocs(spaceId, files) {
    if (!files || files.length === 0) return
    isUploading.value = true
    uploadProgress.value = 0
    error.value = null

    const total = files.length
    let completed = 0

    try {
      for (const file of files) {
        await libraryApi.uploadDoc(spaceId, file)
        completed++
        uploadProgress.value = Math.round((completed / total) * 100)
      }
      // 重新加载文档列表（强制刷新，跳过缓存）
      await loadDocs(spaceId, true)
      // 更新空间文档数量
      const space = spaces.value.find(s => s.id === spaceId)
      if (space) {
        space.doc_count = currentDocs.value.length
      }
    } catch (e) {
      error.value = e.message || '上传文件失败'
      throw e
    } finally {
      isUploading.value = false
      uploadProgress.value = 0
    }
  }

  async function deleteDoc(docId) {
    error.value = null
    try {
      await libraryApi.deleteDoc(docId)
      currentDocs.value = currentDocs.value.filter(d => d.id !== docId)
      selectedDocIds.value.delete(docId)
      // 更新空间文档数量
      if (currentSpace.value) {
        currentSpace.value.doc_count = currentDocs.value.length
      }
    } catch (e) {
      error.value = e.message || '删除文档失败'
      throw e
    }
  }

  async function deleteSelectedDocs() {
    const ids = Array.from(selectedDocIds.value)
    if (ids.length === 0) return
    error.value = null
    try {
      await libraryApi.deleteDocsBatch(ids)
      currentDocs.value = currentDocs.value.filter(d => !ids.includes(d.id))
      selectedDocIds.value.clear()
      // 更新空间文档数量
      if (currentSpace.value) {
        currentSpace.value.doc_count = currentDocs.value.length
      }
    } catch (e) {
      error.value = e.message || '批量删除失败'
      throw e
    }
  }

  async function exportSelectedDocs() {
    const ids = Array.from(selectedDocIds.value)
    if (ids.length === 0) return
    isExporting.value = true
    error.value = null
    const spaceName = (currentSpace.value?.name || 'documents').replace(/[\\/:*?"<>|]/g, '_')
    const archiveName = `${spaceName}_${ids.length}files`
    try {
      await libraryApi.exportDocsBatch(ids, archiveName)
    } catch (e) {
      error.value = e.message || '批量导出失败'
      throw e
    } finally {
      isExporting.value = false
    }
  }

  // ==================== 选择操作 ====================

  function toggleDocSelect(docId) {
    if (selectedDocIds.value.has(docId)) {
      selectedDocIds.value.delete(docId)
    } else {
      selectedDocIds.value.add(docId)
    }
  }

  function isDocSelected(docId) {
    return selectedDocIds.value.has(docId)
  }

  function clearSelection() {
    selectedDocIds.value.clear()
  }

  function setSearchQuery(query) {
    searchQuery.value = query
  }

  async function refreshDocs() {
    if (currentSpaceId.value) {
      await loadDocs(currentSpaceId.value, true)
    }
  }

  function _formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
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
    if (days < 30) return `${Math.floor(days / 7)}周前`
    if (days < 365) return `${Math.floor(days / 30)}个月前`
    return `${Math.floor(days / 365)}年前`
  }

  // ==================== 导出 ====================

  return {
    // 状态
    spaces,
    docsCache,
    currentDocs,
    currentSpaceId,
    searchQuery,
    selectedDocIds,
    isLoading,
    isUploading,
    uploadProgress,
    isExporting,
    error,
    // 计算属性
    currentSpace,
    selectedCount,
    filteredDocs,
    // 空间操作
    loadSpaces,
    createSpace,
    deleteSpace,
    selectSpace,
    // 文档操作
    loadDocs,
    refreshDocs,
    uploadDocs,
    deleteDoc,
    deleteSelectedDocs,
    exportSelectedDocs,
    // 选择操作
    toggleDocSelect,
    isDocSelected,
    clearSelection,
    setSearchQuery,
  }
})
