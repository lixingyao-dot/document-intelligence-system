import client from './client'

export default {
  get() {
    return client.get('/settings')
  },
  save(payload) {
    return client.put('/settings', payload)
  },
}
