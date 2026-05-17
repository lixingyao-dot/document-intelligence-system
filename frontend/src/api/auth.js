import client from './client'

const TOKEN_KEY = 'access_token'

function setAccessToken(token) {
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token)
  }
}

function clearAccessToken() {
  window.localStorage.removeItem(TOKEN_KEY)
}

export function getAccessToken() {
  return window.localStorage.getItem(TOKEN_KEY)
}

function parseJwtPayload(token) {
  try {
    const parts = token.split('.')
    if (parts.length !== 2) return null
    let payload = parts[0]
    const padding = '='.repeat((4 - (payload.length % 4)) % 4)
    payload = (payload + padding).replace(/-/g, '+').replace(/_/g, '/')
    const decoded = JSON.parse(window.atob(payload))
    return decoded
  } catch {
    return null
  }
}

export function getUserFromToken() {
  const token = getAccessToken()
  if (!token) return null
  const payload = parseJwtPayload(token)
  if (!payload) return null
  const exp = payload.exp
  if (exp && Date.now() / 1000 > exp) {
    return null
  }
  return {
    id: payload.sub,
    phone: payload.phone,
    display_name: payload.display_name,
    status: payload.status || 'active',
  }
}

export default {
  register(data) {
    return client.post('/auth/register', data).then((res) => {
      if (res?.access_token) {
        setAccessToken(res.access_token)
      }
      return res
    })
  },

  login(data) {
    return client.post('/auth/login', data).then((res) => {
      if (res?.access_token) {
        setAccessToken(res.access_token)
      }
      return res
    })
  },

  me() {
    return client.get('/auth/me')
  },

  logout() {
    return client.post('/auth/logout').finally(() => {
      clearAccessToken()
    })
  },

  clearAccessToken,
  setAccessToken,
}
