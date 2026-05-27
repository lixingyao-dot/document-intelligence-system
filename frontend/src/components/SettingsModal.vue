<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { X } from 'lucide-vue-next'
import settingsApi from '../api/settings'

const emit = defineEmits(['close'])

const PROVIDERS = [
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'zhipu', label: '智谱 GLM' },
  { id: 'openai', label: 'OpenAI 兼容' },
]

const activeProvider = ref('deepseek')
const providerMeta = ref({})
const draft = ref({ model: '', base_url: '', api_key: '' })
const loading = ref(false)
const saving = ref(false)
const message = ref('')
const uiBuildId = typeof __UI_BUILD_ID__ !== 'undefined' ? __UI_BUILD_ID__ : ''
const appVersion = typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : ''

const currentMeta = computed(() => providerMeta.value[activeProvider.value] || {})

const keyPlaceholder = computed(() => {
  const masked = currentMeta.value.api_key_masked
  return masked ? `已配置 ${masked}（留空不修改）` : '输入 API Key'
})

function providerOptionLabel(id) {
  const p = PROVIDERS.find((x) => x.id === id)
  const meta = providerMeta.value[id]
  const name = p?.label || id
  return meta?.has_api_key ? `${name}（已配置 Key）` : name
}

function draftFromProvider(providerId) {
  const p = providerMeta.value[providerId] || {}
  return {
    model: (p.model || p.default_model || '').trim(),
    base_url: p.base_url || '',
    api_key: '',
  }
}

function applyDraftFromServer(data) {
  activeProvider.value = data.active_provider || 'deepseek'
  providerMeta.value = data.providers || {}
  draft.value = draftFromProvider(activeProvider.value)
}

watch(activeProvider, (id) => {
  draft.value = draftFromProvider(id)
})

onMounted(async () => {
  loading.value = true
  try {
    const data = await settingsApi.get()
    applyDraftFromServer(data)
  } catch (e) {
    message.value = e.message || '加载设置失败'
  } finally {
    loading.value = false
  }
})

async function handleSave() {
  saving.value = true
  message.value = ''
  try {
    const payload = {
      active_provider: activeProvider.value,
      provider: activeProvider.value,
      model: draft.value.model.trim(),
      base_url: draft.value.base_url.trim(),
    }
    if (draft.value.api_key.trim()) {
      payload.api_key = draft.value.api_key.trim()
    }
    const data = await settingsApi.save(payload)
    applyDraftFromServer(data)
    message.value = '已保存，新配置将在下次对话/工作流中生效'
  } catch (e) {
    message.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="settings-overlay" @click.self="emit('close')">
    <div class="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header class="settings-header">
        <div>
          <h2 id="settings-title">API 与模型设置</h2>
          <p class="settings-subtitle">按供应商分别保存模型与密钥，切换后互不影响</p>
        </div>
        <button type="button" class="icon-btn" aria-label="关闭" @click="emit('close')">
          <X :size="20" :stroke-width="2" />
        </button>
      </header>

      <p v-if="loading" class="settings-hint">加载中...</p>
      <form v-else class="settings-form" @submit.prevent="handleSave">
        <section class="provider-panel">
          <label class="field">
            <span>模型提供商</span>
            <select v-model="activeProvider">
              <option v-for="p in PROVIDERS" :key="p.id" :value="p.id">
                {{ providerOptionLabel(p.id) }}
              </option>
            </select>
          </label>

          <label class="field">
            <span>模型名称</span>
            <input
              v-model="draft.model"
              :placeholder="currentMeta.default_model || '留空使用默认模型'"
            />
          </label>

          <label class="field">
            <span>API Base URL</span>
            <input
              v-model="draft.base_url"
              :placeholder="currentMeta.default_base_url || '留空使用默认地址'"
            />
          </label>

          <label class="field">
            <span>{{ currentMeta.label || 'API' }} Key</span>
            <input
              v-model="draft.api_key"
              type="password"
              autocomplete="off"
              :placeholder="keyPlaceholder"
            />
          </label>
        </section>

        <p v-if="message" class="settings-message" :class="{ error: message.includes('失败') }">
          {{ message }}
        </p>

        <p v-if="uiBuildId" class="settings-build-id">
          界面 v{{ appVersion }} · 构建 {{ uiBuildId }}
        </p>

        <footer class="settings-footer">
          <button type="button" class="btn-secondary" @click="emit('close')">取消</button>
          <button type="submit" class="btn-primary" :disabled="saving">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </footer>
      </form>
    </div>
  </div>
</template>

<style scoped>
.settings-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  margin: 0;
  padding: 0;
  background: rgba(15, 23, 42, 0.28);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 200000;
  box-sizing: border-box;
}

.settings-modal {
  position: fixed;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: min(520px, calc(100vw - 48px));
  max-height: min(86vh, 720px);
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(28px) saturate(180%);
  -webkit-backdrop-filter: blur(28px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.55);
  border-radius: var(--glass-radius, 18px);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.2);
  padding: 22px 24px 20px;
  color: var(--text-primary);
  box-sizing: border-box;
}

.settings-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.settings-header h2 {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
  color: var(--text-primary);
}

.settings-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.icon-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 4px;
  flex-shrink: 0;
}

.settings-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.provider-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: var(--glass-radius-sm, 14px);
  background: rgba(255, 255, 255, 0.1);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.field span {
  font-weight: 600;
}

.field input,
.field select {
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.18);
  font-size: 13px;
  color: var(--text-form);
}

.field select option {
  background: #1a1a22;
  color: #ffffff;
}

.field input:focus,
.field select:focus {
  outline: none;
  border-color: var(--accent-primary);
}

.field select {
  cursor: pointer;
}

.settings-message {
  font-size: 13px;
  color: var(--accent-success);
  margin: 0;
}

.settings-message.error {
  color: var(--accent-danger, #c0392b);
}

.settings-build-id {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--text-muted);
  font-family: ui-monospace, monospace;
  word-break: break-all;
}

.settings-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}

.btn-primary,
.btn-secondary {
  padding: 9px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--border-color);
  border-radius: 12px;
}

.btn-primary {
  background: var(--gradient-primary);
  color: var(--text-on-accent);
  border: none;
}

.btn-primary:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.5);
  color: var(--text-primary);
  border: 1px solid var(--glass-border-soft);
}

.settings-hint {
  font-size: 13px;
  color: var(--text-muted);
}
</style>
