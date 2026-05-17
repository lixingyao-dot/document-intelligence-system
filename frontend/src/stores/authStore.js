import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import authApi from '../api/auth'
import { getUserFromToken } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const currentUser = ref(null)
  const isInitializing = ref(true)
  const isAuthenticated = computed(() => !!currentUser.value)

  const userDisplayName = computed(() => {
    if (!currentUser.value) return ''
    return currentUser.value.display_name || currentUser.value.phone || '用户'
  })

  const userAvatar = computed(() => {
    if (!currentUser.value) return '?'
    const name = userDisplayName.value
    return name.charAt(0).toUpperCase()
  })

  function init() {
    isInitializing.value = true
    const user = getUserFromToken()
    if (user) {
      currentUser.value = user
    }
    isInitializing.value = false
  }

  async function login(phone, password) {
    const res = await authApi.login({ phone, password })
    const user = getUserFromToken()
    if (user) {
      currentUser.value = user
    }
    return res
  }

  async function register(phone, password, displayName = null) {
    const res = await authApi.register({
      phone,
      password,
      display_name: displayName,
    })
    const user = getUserFromToken()
    if (user) {
      currentUser.value = user
    }
    return res
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch (e) {
      // 忽略登出错误
    }
    currentUser.value = null
    authApi.clearAccessToken()
  }

  return {
    currentUser,
    isInitializing,
    isAuthenticated,
    userDisplayName,
    userAvatar,
    init,
    login,
    register,
    logout,
  }
})
