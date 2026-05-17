import client from './client'

export default {
  // ==================== 空间管理 ====================

  /** 获取所有文档空间 */
  getSpaces() {
    return client.get('/library/spaces')
  },

  /** 创建文档空间 */
  createSpace(data) {
    return client.post('/library/spaces', data)
  },

  /** 更新文档空间 */
  updateSpace(spaceId, data) {
    return client.put(`/library/spaces/${spaceId}`, data)
  },

  /** 删除文档空间 */
  deleteSpace(spaceId) {
    return client.delete(`/library/spaces/${spaceId}`)
  },

  // ==================== 文档管理 ====================

  /** 获取空间下的所有文档 */
  getDocs(spaceId) {
    return client.get(`/library/spaces/${spaceId}/docs`)
  },

  /** 上传文档到指定空间 */
  uploadDoc(spaceId, file) {
    const formData = new FormData()
    formData.append('file', file)
    return client.post(`/library/spaces/${spaceId}/docs`, formData)
  },

  /** 删除单个文档 */
  deleteDoc(docId) {
    return client.delete(`/library/docs/${docId}`)
  },

  /** 批量删除文档 */
  deleteDocsBatch(docIds) {
    return client.post('/library/docs/delete-batch', { doc_ids: docIds })
  },

  /** 下载文档（带鉴权） */
  async downloadDoc(docId, fileName) {
    const token = localStorage.getItem('auth_token') || ''
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(`${base}/api/library/docs/${docId}/download`, {
      headers: token ? { Authorization: token } : {},
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(text || `下载失败 (${res.status})`)
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName || 'download'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },

  /**
   * 批量导出为 ZIP
   * @param {string[]} docIds
   * @param {string} [archiveName] 不含 .zip 亦可
   */
  async exportDocsBatch(docIds, archiveName = 'documents') {
    const token = localStorage.getItem('auth_token') || ''
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(`${base}/api/library/docs/export-batch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: token } : {}),
      },
      body: JSON.stringify({
        doc_ids: docIds,
        archive_name: archiveName,
      }),
    })
    if (!res.ok) {
      let message = `导出失败 (${res.status})`
      try {
        const data = await res.json()
        message = data.detail || data.message || message
        if (Array.isArray(message)) message = message.join('；')
      } catch {
        const text = await res.text().catch(() => '')
        if (text) message = text
      }
      throw new Error(message)
    }
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition') || ''
    let filename = `${archiveName}.zip`
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
    if (utf8Match) {
      filename = decodeURIComponent(utf8Match[1])
    } else {
      const plainMatch = disposition.match(/filename="?([^";]+)"?/i)
      if (plainMatch) filename = plainMatch[1]
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    return { filename, size: blob.size }
  },
}
