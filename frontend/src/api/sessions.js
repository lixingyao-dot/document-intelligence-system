import client from './client'

export default {
  list(params = {}) {
    return client.get('/sessions', { params })
  },

  get(sessionId) {
    return client.get(`/sessions/${sessionId}`)
  },

  create(data = {}) {
    return client.post('/sessions', data)
  },

  update(sessionId, data) {
    return client.patch(`/sessions/${sessionId}`, data)
  },

  delete(sessionId) {
    return client.delete(`/sessions/${sessionId}`)
  },
}
