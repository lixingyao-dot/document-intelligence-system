import client from './client'

export default {
  getCapabilities() {
    return client.get('/agents/capabilities')
  },

  execute(task) {
    return client.post('/agents/execute', task)
  },

  mixedFill(payload) {
    return client.post('/agents/mixed-fill', payload)
  },
}
