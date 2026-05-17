import client from './client'

export default {
  list(sessionId) {
    return client.get(`/sessions/${sessionId}/files`)
  },

  upload(sessionId, file, fileType) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('file_type', fileType)
    return client.post(`/sessions/${sessionId}/files`, formData)
  },

  uploadTemp(sessionId, file, fileType) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('file_type', fileType)
    return client.post(`/sessions/${sessionId}/temp-files/upload`, formData)
  },

  deleteTempFile(sessionId, filePath) {
    return client.delete(`/sessions/${sessionId}/temp-files/${encodeURIComponent(filePath)}`)
  },

  updateSelection(sessionId, selections) {
    return client.patch(`/sessions/${sessionId}/files/selection`, selections, {
      headers: { 'Content-Type': 'application/json' }
    })
  },

  delete(sessionId, fileId) {
    return client.delete(`/sessions/${sessionId}/files/${fileId}`)
  },
}
