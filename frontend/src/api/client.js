import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 30 * 60 * 1000,
})

function extractAxiosErrorMessage(error) {
  const res = error.response
  const data = res?.data
  if (data && typeof data === 'object') {
    const em = data.error?.message
    if (typeof em === 'string' && em.trim()) return em
    const d = data.detail
    if (typeof d === 'string' && d.trim()) return d
  }
  if (typeof data === 'string' && data.trim()) return data
  return error.message
}

client.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body && typeof body === 'object' && body.success === true && 'data' in body) {
      return body.data
    }
    return body
  },
  (error) => Promise.reject(new Error(extractAxiosErrorMessage(error)))
)

export default client
