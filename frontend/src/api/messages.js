import client from './client'

export default {
  list(sessionId, params = {}) {
    return client.get(`/messages/${sessionId}`, { params })
  },

  send(sessionId, data) {
    return client.post(`/messages/${sessionId}`, data)
  },

  connect(sessionId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const token = window.localStorage.getItem('access_token')
    const query = token ? `?token=${encodeURIComponent(token)}` : ''
    return new WebSocket(`${protocol}//${host}/api/messages/ws/${sessionId}${query}`)
  },
}
