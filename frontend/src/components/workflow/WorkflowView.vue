<script setup>
import { computed, ref } from 'vue'
import { Save } from 'lucide-vue-next'
import WorkflowSidebar from './WorkflowSidebar.vue'
import WorkflowCanvas from './WorkflowCanvas.vue'
import WorkflowConfig from './WorkflowConfig.vue'
import SidebarToggle from '../common/SidebarToggle.vue'
import { useWorkflowStore } from '../../stores/workflowStore'

const workflowStore = useWorkflowStore()
const leftCollapsed = ref(false)
const rightCollapsed = ref(false)

const autoSaveLabel = computed(() => {
  switch (workflowStore.autoSaveStatus) {
    case 'pending':
      return '等待保存…'
    case 'saving':
      return '保存中…'
    case 'saved':
      return '已自动保存'
    case 'error':
      return '保存失败'
    default:
      return '修改后自动保存'
  }
})

const isSaving = computed(() =>
  workflowStore.autoSaveStatus === 'saving' || workflowStore.autoSaveStatus === 'pending'
)

async function handleSaveWorkflow() {
  if (isSaving.value || !workflowStore.currentWorkflowId) return
  try {
    await workflowStore.saveCurrentWorkflow()
  } catch {
    /* 状态由 store 维护 */
  }
}
</script>

<template>
  <div class="workflow-view" :class="{ 'left-collapsed': leftCollapsed, 'right-collapsed': rightCollapsed }">

    <!-- 顶部工具栏 -->
    <div v-if="workflowStore.currentWorkflowId" class="workflow-topbar">
      <div class="topbar-left">
        <label class="topbar-label" for="wf-name-input">工作流名称</label>
        <input
          id="wf-name-input"
          class="topbar-name-input"
          type="text"
          :value="workflowStore.workflowName"
          placeholder="未命名工作流"
          @input="workflowStore.updateWorkflowName($event.target.value)"
        />
      </div>
      <div class="topbar-right">
        <span class="topbar-meta">{{ workflowStore.canvasNodes.length }} 个节点</span>
        <span
          class="topbar-autosave"
          :class="{
            saving: workflowStore.autoSaveStatus === 'saving' || workflowStore.autoSaveStatus === 'pending',
            saved: workflowStore.autoSaveStatus === 'saved',
            error: workflowStore.autoSaveStatus === 'error',
          }"
        >
          {{ autoSaveLabel }}
        </span>
        <button
          v-if="workflowStore.autoSaveStatus === 'error'"
          type="button"
          class="topbar-save-btn"
          :class="{ saving: isSaving }"
          :disabled="isSaving"
          @click="handleSaveWorkflow"
        >
          <Save v-if="!isSaving" :size="15" :stroke-width="2" aria-hidden="true" />
          <span v-if="isSaving" class="save-spinner" aria-hidden="true"></span>
          <span>{{ isSaving ? '保存中...' : '重试保存' }}</span>
        </button>
      </div>
    </div>

    <!-- 三栏主区域 -->
    <div class="workflow-body">
      <div class="sidebar-panel left-sidebar" :class="{ collapsed: leftCollapsed }">
        <WorkflowSidebar />
        <SidebarToggle
          side="left"
          :collapsed="leftCollapsed"
          collapse-title="收起左侧栏"
          expand-title="展开左侧栏"
          @toggle="leftCollapsed = !leftCollapsed"
        />
      </div>

      <WorkflowCanvas />

      <div class="sidebar-panel right-sidebar" :class="{ collapsed: rightCollapsed }">
        <WorkflowConfig />
        <SidebarToggle
          side="right"
          :collapsed="rightCollapsed"
          collapse-title="收起右侧栏"
          expand-title="展开右侧栏"
          @toggle="rightCollapsed = !rightCollapsed"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.workflow-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.workflow-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ====== 顶部工具栏 ====== */
.workflow-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-card, rgba(15, 15, 21, 0.92));
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.topbar-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.topbar-name-input {
  flex: 1;
  min-width: 0;
  max-width: 260px;
  padding: 6px 10px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  outline: none;
  transition: border-color 0.15s;
}

.topbar-name-input:focus {
  border-color: var(--accent-primary);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
}

.topbar-meta {
  font-size: 12px;
  color: var(--text-muted);
}

.topbar-autosave {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}

.topbar-autosave.saving {
  color: var(--text-secondary);
}

.topbar-autosave.saved {
  color: #34d399;
}

.topbar-autosave.error {
  color: #f87171;
}

.topbar-save-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  background: var(--accent-primary);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.15s;
  white-space: nowrap;
}

.topbar-save-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 2px 10px rgba(37, 99, 235, 0.35);
}

.topbar-save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.topbar-save-btn.saving {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.save-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.25);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ====== 侧栏通用 ====== */
.sidebar-panel {
  position: relative;
  overflow: hidden;
  transition: width 0.25s ease;
}

.sidebar-panel.collapsed {
  width: 0 !important;
}
</style>
