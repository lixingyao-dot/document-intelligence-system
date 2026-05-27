<script setup>
import {
  FileText,
  FolderOpen,
  MessagesSquare,
  GitBranch,
  Settings,
} from 'lucide-vue-next'
import { useTabStore } from '../stores/tabStore'
const emit = defineEmits(['open-settings'])

const tabStore = useTabStore()

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
      <button
        type="button"
        class="settings-btn"
        title="API 与模型设置"
        @click.stop="emit('open-settings')"
      >
        <Settings :size="18" :stroke-width="2" aria-hidden="true" />
        <span>模型设置</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.settings-btn {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px 4px;
  background: var(--glass-panel-strong);
  border: 1px solid var(--glass-border-soft);
  border-radius: var(--glass-radius-sm);
  font-size: 10px;
  font-weight: 600;
  line-height: 1.25;
  text-align: center;
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
