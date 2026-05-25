<script setup>
import { ref } from 'vue'
import {
  FileText,
  FolderOpen,
  MessagesSquare,
  GitBranch,
  Settings,
} from 'lucide-vue-next'
import { useTabStore } from '../stores/tabStore'
import SettingsModal from './SettingsModal.vue'

const tabStore = useTabStore()
const showSettings = ref(false)

const tabIcons = {
  library: FolderOpen,
  chat: MessagesSquare,
  workflow: GitBranch,
}

function tabIcon(tabId) {
  return tabIcons[tabId] || FileText
}

function handleTabClick(tabId) {
  tabStore.switchTab(tabId)
}
</script>

<template>
  <aside class="app-sidebar" aria-label="主导航">
    <div class="sidebar-brand">
      <div class="logo">
        <div class="logo-icon" aria-hidden="true">
          <FileText :size="20" :stroke-width="2" />
        </div>
      </div>
      <span class="sidebar-brand-title">文档智能</span>
      <span class="sidebar-brand-badge">本地版</span>
    </div>

    <nav class="sidebar-nav main-nav" aria-label="功能模块">
      <button
        v-for="tab in tabStore.tabs"
        :key="tab.id"
        type="button"
        class="nav-tab"
        :class="{ active: tabStore.currentTab === tab.id }"
        :data-tab="tab.id"
        @click="handleTabClick(tab.id)"
      >
        <component
          :is="tabIcon(tab.id)"
          class="nav-tab-icon"
          :size="20"
          :stroke-width="2"
          aria-hidden="true"
        />
        <span>{{ tab.label }}</span>
      </button>
    </nav>

    <div class="sidebar-footer">
      <button type="button" class="settings-btn" @click="showSettings = true">
        <Settings :size="18" :stroke-width="2" aria-hidden="true" />
        <span>API 与模型设置</span>
      </button>
    </div>

    <SettingsModal v-if="showSettings" @close="showSettings = false" />
  </aside>
</template>

<style scoped>
.sidebar-brand-badge {
  font-size: 10px;
  font-weight: 600;
  color: var(--accent-primary);
  background: rgba(125, 211, 252, 0.15);
  border: 1px solid var(--glass-border-soft);
  border-radius: 8px;
  padding: 2px 6px;
  margin-top: 2px;
}

.settings-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 8px;
  background: var(--glass-panel-strong);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--glass-radius-sm);
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.settings-btn:hover {
  background: var(--glass-panel-hover);
  color: var(--text-primary);
  border-color: var(--glass-border);
}
</style>
