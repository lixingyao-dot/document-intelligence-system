<script setup>
import { ref, onMounted } from 'vue'
import { Plus, GitBranch, Workflow, Trash2 } from 'lucide-vue-next'
import { useWorkflowStore } from '../../stores/workflowStore'
import { resolveWorkflowIcon } from '../../utils/workflowIcons'

const workflowStore = useWorkflowStore()

const activeSection = ref('workflow') // 'workflow' | 'toolbox'
const isLoading = ref(false)

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

const showDeleteConfirm = ref(false)
const deleteTargetId = ref(null)

function handleDeleteWorkflow(e, workflowId) {
  e.stopPropagation()
  deleteTargetId.value = workflowId
  showDeleteConfirm.value = true
}

async function confirmDelete() {
  if (deleteTargetId.value) {
    await workflowStore.deleteWorkflow(deleteTargetId.value)
  }
  showDeleteConfirm.value = false
  deleteTargetId.value = null
}

function cancelDelete() {
  showDeleteConfirm.value = false
  deleteTargetId.value = null
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
              <button
                class="workflow-delete-btn"
                title="删除工作流"
                @click="(e) => handleDeleteWorkflow(e, wf.id)"
              >
                <Trash2 :size="14" :stroke-width="2" />
              </button>
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

  <!-- 自定义删除确认弹窗 -->
  <Teleport to="body">
    <div v-if="showDeleteConfirm" class="wf-modal-overlay" @click.self="cancelDelete">
      <div class="wf-modal-dialog">
        <div class="wf-modal-title">删除工作流</div>
        <div class="wf-modal-body">确定要删除该工作流吗？此操作无法撤销。</div>
        <div class="wf-modal-actions">
          <button class="wf-modal-btn wf-modal-btn-cancel" @click="cancelDelete">取消</button>
          <button class="wf-modal-btn wf-modal-btn-confirm" @click="confirmDelete">确定</button>
        </div>
      </div>
    </div>
  </Teleport>
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

.workflow-delete-btn {
  opacity: 0;
  background: none;
  border: none;
  padding: 4px;
  cursor: pointer;
  color: var(--text-muted);
  border-radius: 4px;
  transition: all 0.15s;
  flex-shrink: 0;
  margin-left: auto;
}

.workflow-item:hover .workflow-delete-btn {
  opacity: 1;
}

.workflow-delete-btn:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.12);
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

/* 删除确认弹窗 */
.wf-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.wf-modal-dialog {
  background: var(--bg-card, #1e1e2e);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 24px 28px;
  min-width: 340px;
  max-width: 420px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}
.wf-modal-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #fff);
  margin-bottom: 10px;
}
.wf-modal-body {
  font-size: 14px;
  color: var(--text-secondary, #aaa);
  line-height: 1.6;
  margin-bottom: 22px;
}
.wf-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.wf-modal-btn {
  padding: 8px 22px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s;
}
.wf-modal-btn-cancel {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary, #aaa);
  border-color: rgba(255, 255, 255, 0.1);
}
.wf-modal-btn-cancel:hover {
  background: rgba(255, 255, 255, 0.1);
}
.wf-modal-btn-confirm {
  background: #e5484d;
  color: #fff;
}
.wf-modal-btn-confirm:hover {
  background: #d63a3f;
}
</style>
