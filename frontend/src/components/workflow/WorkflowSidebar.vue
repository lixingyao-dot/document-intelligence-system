<script setup>
import { ref, onMounted } from 'vue'
import { Plus, GitBranch, Save, Workflow } from 'lucide-vue-next'
import { useWorkflowStore } from '../../stores/workflowStore'
import { resolveWorkflowIcon } from '../../utils/workflowIcons'

const workflowStore = useWorkflowStore()

const activeSection = ref('workflow') // 'workflow' | 'toolbox'
const isLoading = ref(false)
const isSaving = ref(false)

onMounted(async () => {
  isLoading.value = true
  try {
    await workflowStore.loadWorkflows()
    if (!workflowStore.currentWorkflowId && workflowStore.workflowList.length > 0) {
      workflowStore.selectWorkflow(workflowStore.workflowList[0].id)
    }
  } finally {
    isLoading.value = false
  }
})

function handleWorkflowClick(workflowId) {
  workflowStore.selectWorkflow(workflowId)
}

function handleNewWorkflow() {
  workflowStore.createNewWorkflow()
}

async function handleSaveWorkflow() {
  if (isSaving.value || !workflowStore.currentWorkflowId) return
  isSaving.value = true
  try {
    await workflowStore.saveCurrentWorkflow()
  } finally {
    isSaving.value = false
  }
}

function handleAddNode(item) {
  workflowStore.addNode(item)
}

function onToolboxDragStart(e, item) {
  const payload = JSON.stringify({
    schemaKey: item.schemaKey,
    type: item.type,
    icon: item.icon,
    title: item.title,
    body: item.body,
    name: item.name
  })
  try {
    e.dataTransfer.setData('application/x-workflow-node', payload)
  } catch (_) {
    /* 部分环境仅支持 text/plain */
  }
  e.dataTransfer.setData('text/plain', payload)
  e.dataTransfer.effectAllowed = 'copy'
}
</script>

<template>
  <aside class="workflow-sidebar">

    <!-- Loading Indicator -->
    <div v-if="isLoading" class="sidebar-loading">
      <div class="loading-dots">
        <span></span><span></span><span></span>
      </div>
    </div>

    <template v-else>
      <!-- Section Switcher -->
      <div class="sidebar-switcher">
        <button
          class="switcher-btn"
          :class="{ active: activeSection === 'workflow' }"
          @click="activeSection = 'workflow'"
        >
          工作流
        </button>
        <button
          class="switcher-btn"
          :class="{ active: activeSection === 'toolbox' }"
          @click="activeSection = 'toolbox'"
        >
          组件库
        </button>
      </div>

      <!-- ===================== 工作流面板 ===================== -->
      <template v-if="activeSection === 'workflow'">
        <!-- New Workflow -->
        <div class="sidebar-section">
          <button class="new-workflow-btn" @click="handleNewWorkflow">
            <Plus :size="18" :stroke-width="2" aria-hidden="true" />
            <span>新建工作流</span>
          </button>
        </div>

        <!-- 当前工作流：名称与保存 -->
        <div v-if="workflowStore.currentWorkflowId" class="sidebar-section wf-meta-panel">
          <label class="wf-meta-label" for="wf-name-input">工作流名称</label>
          <input
            id="wf-name-input"
            class="wf-name-input"
            type="text"
            :value="workflowStore.workflowName"
            placeholder="未命名工作流"
            @input="workflowStore.updateWorkflowName($event.target.value)"
          />
          <p class="wf-meta-hint">{{ workflowStore.canvasNodes.length }} 个节点</p>
          <button
            type="button"
            class="save-wf-btn"
            :class="{ saving: isSaving }"
            :disabled="isSaving"
            @click="handleSaveWorkflow"
          >
            <Save v-if="!isSaving" :size="16" :stroke-width="2" aria-hidden="true" />
            <span v-if="isSaving" class="save-spinner" aria-hidden="true"></span>
            <span>{{ isSaving ? '保存中...' : '保存工作流' }}</span>
          </button>
        </div>

        <!-- Workflow List -->
        <div class="sidebar-scroll">
          <div class="workflow-group" v-if="workflowStore.workflowList.length > 0">
            <div class="workflow-group-title">工作流</div>
            <div
              v-for="wf in workflowStore.workflowList"
              :key="wf.id"
              class="workflow-item"
              :class="{ active: workflowStore.currentWorkflowId === wf.id }"
              @click="handleWorkflowClick(wf.id)"
            >
              <component
                :is="Workflow"
                class="workflow-item-icon"
                :size="16"
                :stroke-width="2"
                aria-hidden="true"
              />
              <div class="workflow-info">
                <span class="workflow-name">{{ wf.name }}</span>
                <span class="workflow-time">{{ wf.time }}</span>
              </div>
            </div>
          </div>

          <!-- Empty State -->
          <div v-if="workflowStore.workflowList.length === 0" class="workflow-empty">
            <div class="workflow-empty-icon" aria-hidden="true">
              <GitBranch :size="26" :stroke-width="1.75" />
            </div>
            <div class="workflow-empty-text">暂无工作流</div>
            <button class="workflow-empty-btn" @click="handleNewWorkflow">创建第一个工作流</button>
          </div>
        </div>
      </template>

      <!-- ===================== 组件库面板 ===================== -->
      <template v-else>
        <!-- Toolbox：左侧可拖入画布，右侧 + 仍一键添加 -->
        <div class="sidebar-scroll">
          <div
            v-for="section in workflowStore.toolboxItems"
            :key="section.section"
            class="toolbox-section"
          >
            <div class="toolbox-section-title">{{ section.section }}</div>
            <div
              v-for="item in section.items"
              :key="section.section + '|' + item.schemaKey + '|' + item.name"
              class="toolbox-item"
            >
              <div
                class="toolbox-item-main"
                draggable="true"
                title="按住拖到画布"
                @dragstart="onToolboxDragStart($event, item)"
              >
                <component
                  :is="resolveWorkflowIcon(item.schemaKey, item.type)"
                  class="toolbox-item-icon-lucide"
                  :size="16"
                  :stroke-width="2"
                  aria-hidden="true"
                />
                <span class="toolbox-item-name">{{ item.name }}</span>
              </div>
              <button
                type="button"
                class="toolbox-item-add"
                draggable="false"
                title="添加到画布末尾"
                @click.stop="handleAddNode(item)"
              >
                <Plus :size="16" :stroke-width="2" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </template>
    </template>
  </aside>
</template>

<style scoped>
.sidebar-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 120px;
}

.loading-dots {
  display: flex;
  gap: 6px;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  background: var(--accent-primary);
  border-radius: 0;
  animation: pulse-dot 1.4s ease-in-out infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

.template-quick-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.1), rgba(59, 130, 246, 0.06));
  border: 1px solid rgba(37, 99, 235, 0.22);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;
}

.template-quick-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.08), rgba(59, 130, 246, 0.04));
  opacity: 0;
  transition: opacity 0.2s;
}

.template-quick-card:hover {
  border-color: rgba(37, 99, 235, 0.4);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.15);
}

.template-quick-card:hover::before {
  opacity: 1;
}

.template-quick-icon {
  width: 40px;
  height: 40px;
  background: var(--gradient-primary);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-inverse);
}

.template-quick-info {
  flex: 1;
  min-width: 0;
}

.template-quick-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.template-quick-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.template-quick-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-primary);
  background: rgba(37, 99, 235, 0.12);
  padding: 2px 8px;
  border-radius: 0;
  flex-shrink: 0;
}

.workflow-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  gap: 8px;
}

.workflow-empty-icon {
  width: 48px;
  height: 48px;
  border-radius: 0;
  background: rgba(37, 99, 235, 0.06);
  border: 2px dashed rgba(37, 99, 235, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-primary);
}

.workflow-empty-text {
  font-size: 14px;
  color: var(--text-muted);
}

.workflow-empty-btn {
  margin-top: 8px;
  padding: 8px 16px;
  background: rgba(37, 99, 235, 0.1);
  border: 1px solid rgba(37, 99, 235, 0.25);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--accent-primary);
  cursor: pointer;
  transition: all 0.2s;
}

.workflow-empty-btn:hover {
  background: rgba(37, 99, 235, 0.16);
  border-color: var(--accent-primary);
}

.toolbox-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: grab;
}

.toolbox-item-main:active {
  cursor: grabbing;
}

.wf-meta-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
}

.wf-meta-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.wf-name-input {
  width: 100%;
  padding: 9px 11px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  font-size: 13px;
  color: var(--text-primary);
  outline: none;
}

.wf-name-input:focus {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(66, 99, 235, 0.15);
}

.wf-meta-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
}

.wf-meta-hint--muted {
  font-style: italic;
}

.save-wf-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 14px;
  margin-top: 4px;
  background: var(--gradient-primary);
  border: none;
  font-size: 13px;
  font-weight: 600;
  color: white;
  cursor: pointer;
  transition: all 0.2s;
}

.save-wf-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(66, 99, 235, 0.35);
}

.save-wf-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.save-wf-btn.saving {
  background: var(--bg-hover);
  color: var(--text-muted);
}

.save-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: white;
  animation: wf-save-spin 0.8s linear infinite;
}

@keyframes wf-save-spin {
  to { transform: rotate(360deg); }
}
</style>
