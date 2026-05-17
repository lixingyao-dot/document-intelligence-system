<script setup>
import { ref, computed } from 'vue'
import { Sparkles, AlertCircle } from 'lucide-vue-next'
import { useAuthStore } from '../stores/authStore'

const authStore = useAuthStore()

const activeTab = ref('login')
const loading = ref(false)
const errorText = ref('')

// 登录表单
const loginPhone = ref('')
const loginPassword = ref('')

// 注册表单
const registerPhone = ref('')
const registerPassword = ref('')
const registerDisplayName = ref('')

const canLogin = computed(() => loginPhone.value.trim() && loginPassword.value)
const canRegister = computed(() => registerPhone.value.trim() && registerPassword.value.length >= 6)

async function handleLogin() {
  if (!canLogin.value) return
  loading.value = true
  errorText.value = ''
  try {
    await authStore.login(loginPhone.value.trim(), loginPassword.value)
  } catch (e) {
    errorText.value = e?.message || '登录失败'
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  if (!canRegister.value) return
  loading.value = true
  errorText.value = ''
  try {
    await authStore.register(
      registerPhone.value.trim(),
      registerPassword.value,
      registerDisplayName.value.trim() || null
    )
  } catch (e) {
    errorText.value = e?.message || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-shell">
    <!-- 背景装饰 -->
    <div class="auth-bg-gradient"></div>
    <div class="auth-particles">
      <div class="particle particle-1"></div>
      <div class="particle particle-2"></div>
      <div class="particle particle-3"></div>
      <div class="particle particle-4"></div>
    </div>

    <!-- 登录卡片 -->
    <div class="auth-card">
      <!-- Logo区域 -->
      <div class="auth-header">
        <div class="auth-logo">
          <div class="auth-logo-icon" aria-hidden="true">
            <Sparkles :size="28" :stroke-width="1.75" />
          </div>
          <div class="auth-logo-glow"></div>
        </div>
        <h1 class="auth-title">文档智能系统</h1>
        <p class="auth-subtitle">智能文档处理 · 开启高效工作</p>
      </div>

      <!-- 错误提示 -->
      <div v-if="errorText" class="auth-error">
        <span class="auth-error-icon" aria-hidden="true">
          <AlertCircle :size="18" :stroke-width="2" />
        </span>
        <span>{{ errorText }}</span>
      </div>

      <!-- 登录/注册切换 -->
      <div class="auth-tabs">
        <button
          class="auth-tab"
          :class="{ active: activeTab === 'login' }"
          @click="activeTab = 'login'"
        >
          登录
        </button>
        <button
          class="auth-tab"
          :class="{ active: activeTab === 'register' }"
          @click="activeTab = 'register'"
        >
          注册
        </button>
        <div
          class="auth-tab-indicator"
          :style="{ left: activeTab === 'login' ? '4px' : '50%' }"
        ></div>
      </div>

      <!-- 登录表单 -->
      <form v-if="activeTab === 'login'" class="auth-form" @submit.prevent="handleLogin">
        <div class="auth-field">
          <label class="auth-label">
            手机号
          </label>
          <input
            v-model="loginPhone"
            type="tel"
            class="auth-input"
            placeholder="请输入手机号"
            autocomplete="tel"
          />
        </div>

        <div class="auth-field">
          <label class="auth-label">
            密码
          </label>
          <input
            v-model="loginPassword"
            type="password"
            class="auth-input"
            placeholder="请输入密码"
            autocomplete="current-password"
          />
        </div>

        <button
          type="submit"
          class="auth-submit"
          :class="{ loading }"
          :disabled="!canLogin || loading"
        >
          <span v-if="!loading">登录</span>
          <span v-else class="auth-spinner"></span>
        </button>
      </form>

      <!-- 注册表单 -->
      <form v-else class="auth-form" @submit.prevent="handleRegister">
        <div class="auth-field">
          <label class="auth-label">
            手机号
          </label>
          <input
            v-model="registerPhone"
            type="tel"
            class="auth-input"
            placeholder="请输入手机号"
            autocomplete="tel"
          />
        </div>

        <div class="auth-field">
          <label class="auth-label">
            昵称
          </label>
          <input
            v-model="registerDisplayName"
            type="text"
            class="auth-input"
            placeholder="昵称（可选）"
            autocomplete="name"
          />
        </div>

        <div class="auth-field">
          <label class="auth-label">
            密码
          </label>
          <input
            v-model="registerPassword"
            type="password"
            class="auth-input"
            placeholder="至少 6 位"
            autocomplete="new-password"
          />
        </div>

        <button
          type="submit"
          class="auth-submit"
          :class="{ loading }"
          :disabled="!canRegister || loading"
        >
          <span v-if="!loading">注册并登录</span>
          <span v-else class="auth-spinner"></span>
        </button>
      </form>

      <!-- 底部提示 -->
      <div class="auth-footer">
        <span class="auth-footer-text">登录后可使用会话历史与文件持久化能力</span>
      </div>
    </div>
  </div>
</template>
