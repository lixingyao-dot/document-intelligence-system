<script setup>
import { ref, onMounted } from 'vue'
import {
  BookOpen,
  Folder,
  Table2,
  FlaskConical,
  FolderKanban,
  ScrollText,
  Newspaper,
  Microscope,
  Briefcase,
  Building2,
  FileSpreadsheet,
  GraduationCap,
  BookMarked,
  Library,
  Boxes,
  AlertCircle,
  TriangleAlert,
} from 'lucide-vue-next'
import { useLibraryStore } from '../../stores/libraryStore'

const libraryStore = useLibraryStore()

const SPACE_ICON_KEYS = [
  'BookOpen',
  'Folder',
  'Table2',
  'FlaskConical',
  'FolderKanban',
  'ScrollText',
  'Newspaper',
  'Microscope',
  'Briefcase',
  'Building2',
  'FileSpreadsheet',
  'GraduationCap',
  'BookMarked',
  'Library',
  'Boxes',
]

const spaceIconByKey = {
  BookOpen,
  Folder,
  Table2,
  FlaskConical,
  FolderKanban,
  ScrollText,
  Newspaper,
  Microscope,
  Briefcase,
  Building2,
  FileSpreadsheet,
  GraduationCap,
  BookMarked,
  Library,
  Boxes,
}

/** 兼容旧版单字图标存库 */
const LEGACY_SPACE_ICONS = {
  书: 'BookOpen',
  档: 'Folder',
  表: 'Table2',
  研: 'FlaskConical',
  项: 'FolderKanban',
  卷: 'ScrollText',
  刊: 'Newspaper',
  验: 'Microscope',
  案: 'Briefcase',
  司: 'Building2',
  报: 'FileSpreadsheet',
  课: 'GraduationCap',
  例: 'BookMarked',
  库: 'Library',
  组: 'Boxes',
}

function resolveSpaceIconKey(stored) {
  if (stored && spaceIconByKey[stored]) return stored
  if (stored && LEGACY_SPACE_ICONS[stored]) return LEGACY_SPACE_ICONS[stored]
  return 'BookOpen'
}

// ==================== 组件挂载 ====================
onMounted(() => {
  libraryStore.loadSpaces()
})

// ==================== 空间选择 ====================
function handleSpaceClick(spaceId) {
  libraryStore.selectSpace(spaceId)
}

// ==================== 新建空间 ====================
const showCreateModal = ref(false)
const createForm = ref({ name: '', icon: 'BookOpen' })
const isCreating = ref(false)
const createError = ref('')

const iconOptions = SPACE_ICON_KEYS

async function handleCreateSpace() {
  const { name } = createForm.value
  if (!name.trim()) {
    createError.value = '请输入空间名称'
    return
  }
  isCreating.value = true
  createError.value = ''
  try {
    await libraryStore.createSpace(name.trim(), createForm.value.icon)
    showCreateModal.value = false
    createForm.value = { name: '', icon: 'BookOpen' }
  } catch (e) {
    createError.value = e.message || '创建失败，请重试'
  } finally {
    isCreating.value = false
  }
}

function openCreateModal() {
  createForm.value = { name: '', icon: 'BookOpen' }
  createError.value = ''
  showCreateModal.value = true
}

function closeCreateModal() {
  showCreateModal.value = false
}

// ==================== 删除空间 ====================
const showDeleteModal = ref(false)
const deleteTargetSpace = ref(null)
const isDeleting = ref(false)
const deleteError = ref('')

function openDeleteModal(space, event) {
  event.stopPropagation()
  deleteTargetSpace.value = space
  deleteError.value = ''
  showDeleteModal.value = true
}

async function handleDeleteSpace() {
  if (!deleteTargetSpace.value) return
  isDeleting.value = true
  deleteError.value = ''
  try {
    await libraryStore.deleteSpace(deleteTargetSpace.value.id)
    showDeleteModal.value = false
    deleteTargetSpace.value = null
  } catch (e) {
    deleteError.value = e.message || '删除失败，请重试'
  } finally {
    isDeleting.value = false
  }
}

function closeDeleteModal() {
  showDeleteModal.value = false
  deleteTargetSpace.value = null
}
</script>

<template>
  <div class="library-sidebar">
    <!-- Spaces Section -->
    <div class="space-section">
      <div class="space-header">
        <span class="space-title">文档空间</span>
        <button class="space-action" title="新建空间" @click="openCreateModal">+</button>
      </div>

      <!-- 加载中 -->
      <div v-if="libraryStore.isLoading && libraryStore.spaces.length === 0" class="spaces-loading">
        <div class="loading-dots">
          <span></span><span></span><span></span>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!libraryStore.isLoading && libraryStore.spaces.length === 0" class="spaces-empty">
        <p>暂无空间</p>
        <button class="empty-create-btn" @click="openCreateModal">+ 创建第一个空间</button>
      </div>

      <!-- 空间列表 -->
      <div
        v-for="space in libraryStore.spaces"
        :key="space.id"
        class="space-item"
        :class="{ active: libraryStore.currentSpaceId === space.id }"
        @click="handleSpaceClick(space.id)"
      >
        <span class="space-item-icon" aria-hidden="true">
          <component :is="spaceIconByKey[resolveSpaceIconKey(space.icon)]" :size="16" :stroke-width="2" />
        </span>
        <span class="space-name">{{ space.name }}</span>
        <span class="space-count">{{ space.doc_count }}</span>
        <button
          class="space-delete-btn"
          title="删除空间"
          @click="openDeleteModal(space, $event)"
        >
          ×
        </button>
      </div>
    </div>

    <!-- ==================== 创建空间弹窗 ==================== -->
    <Teleport to="body">
      <div class="modal-overlay" :class="{ active: showCreateModal }" @click.self="closeCreateModal">
        <div class="modal">
          <div class="modal-header">
            <span class="modal-title">创建文档空间</span>
            <button class="modal-close" @click="closeCreateModal">×</button>
          </div>

          <div class="modal-body">
            <!-- 错误提示 -->
            <div v-if="createError" class="modal-error">
              <span class="error-icon" aria-hidden="true">
                <AlertCircle :size="16" :stroke-width="2" />
              </span>
              <span>{{ createError }}</span>
            </div>

            <!-- 空间名称 -->
            <div class="form-field">
              <label class="form-label">空间名称</label>
              <input
                v-model="createForm.name"
                class="form-input"
                placeholder="例如：论文研究"
                maxlength="50"
                @keyup.enter="handleCreateSpace"
                @input="createError = ''"
              />
            </div>

            <!-- 选择图标 -->
            <div class="form-field">
              <label class="form-label">选择图标</label>
              <div class="icon-grid">
                <button
                  v-for="key in iconOptions"
                  :key="key"
                  type="button"
                  class="icon-btn"
                  :class="{ selected: createForm.icon === key }"
                  :title="key"
                  @click="createForm.icon = key"
                >
                  <component :is="spaceIconByKey[key]" :size="20" :stroke-width="2" />
                </button>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button class="modal-btn cancel" @click="closeCreateModal">取消</button>
            <button
              class="modal-btn primary"
              :disabled="isCreating"
              @click="handleCreateSpace"
            >
              <span v-if="isCreating" class="btn-spinner"></span>
              <span v-else>创建</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ==================== 删除空间确认弹窗 ==================== -->
    <Teleport to="body">
      <div class="modal-overlay" :class="{ active: showDeleteModal }" @click.self="closeDeleteModal">
        <div class="modal">
          <div class="modal-header">
            <span class="modal-title">删除文档空间</span>
            <button class="modal-close" @click="closeDeleteModal">×</button>
          </div>

          <div class="modal-body">
            <!-- 错误提示 -->
            <div v-if="deleteError" class="modal-error">
              <span class="error-icon" aria-hidden="true">
                <AlertCircle :size="16" :stroke-width="2" />
              </span>
              <span>{{ deleteError }}</span>
            </div>

            <!-- 确认内容 -->
            <div class="confirm-box">
              <div class="confirm-icon" aria-hidden="true">
                <TriangleAlert :size="28" :stroke-width="1.75" />
              </div>
              <p class="confirm-text">
                确定要删除空间 <strong>"{{ deleteTargetSpace?.name }}"</strong> 吗？
              </p>
              <p class="confirm-subtext">
                此操作将同时删除该空间下的所有文档，且无法恢复。
              </p>
            </div>
          </div>

          <div class="modal-footer">
            <button class="modal-btn cancel" @click="closeDeleteModal">取消</button>
            <button
              class="modal-btn danger"
              :disabled="isDeleting"
              @click="handleDeleteSpace"
            >
              <span v-if="isDeleting" class="btn-spinner"></span>
              <span v-else>确认删除</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* Sidebar */
.library-sidebar {
  width: 100%;
  height: 100%;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.space-section {
  margin-bottom: 24px;
}

.space-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.space-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-muted);
}

.space-action {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 0;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 18px;
  font-weight: 400;
  transition: all 0.2s;
}

.space-action:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* Space Item */
.space-item-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-muted);
}

.space-item.active .space-item-icon {
  color: var(--accent-primary);
}

.space-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s;
  color: var(--text-secondary);
  margin-bottom: 2px;
  position: relative;
}

.space-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.space-item.active {
  background: rgba(37, 99, 235, 0.1);
  color: var(--accent-primary);
}

.space-item:hover .space-delete-btn {
  opacity: 1;
}

.space-name {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.space-count {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 0;
  flex-shrink: 0;
}

.space-delete-btn {
  opacity: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 0;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 16px;
  font-weight: 400;
  transition: all 0.2s;
  flex-shrink: 0;
}

.space-delete-btn:hover {
  background: rgba(239, 68, 68, 0.15);
  color: var(--accent-danger);
}

/* Loading & Empty */
.spaces-loading {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

.loading-dots {
  display: flex;
  gap: 6px;
}

.loading-dots span {
  width: 6px;
  height: 6px;
  background: var(--accent-primary);
  border-radius: 0;
  animation: bounce-dot 1.4s ease-in-out infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce-dot {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.spaces-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 0;
  color: var(--text-muted);
}

.spaces-empty .empty-icon {
  font-size: 32px;
  opacity: 0.5;
}

.spaces-empty p {
  font-size: 13px;
  margin: 0;
}

.empty-create-btn {
  margin-top: 8px;
  padding: 8px 16px;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--accent-primary);
  cursor: pointer;
  transition: all 0.2s;
}

.empty-create-btn:hover {
  background: rgba(99, 102, 241, 0.2);
}

/* ============ 弹窗样式 ============ */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  opacity: 0;
  visibility: hidden;
  transition: all 0.3s ease;
}

.modal-overlay.active {
  opacity: 1;
  visibility: visible;
}

.modal {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xl);
  width: 480px;
  max-width: 90vw;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  transform: scale(0.9) translateY(20px);
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.6);
}

.modal-overlay.active .modal {
  transform: scale(1) translateY(0);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.modal-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
}

.modal-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 22px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
  line-height: 1;
}

.modal-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.modal-body {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}

.modal-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: #ef4444;
  margin-bottom: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}

/* Form Styles */
.form-field {
  margin-bottom: 20px;
}

.form-field:last-child {
  margin-bottom: 0;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.form-input {
  width: 100%;
  padding: 11px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  transition: all 0.2s;
  font-family: inherit;
}

.form-input::placeholder {
  color: var(--text-muted);
}

.form-input:focus {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

/* Icon Grid */
.icon-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 6px;
}

.icon-btn {
  width: 100%;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: 2px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.icon-btn:hover {
  background: var(--bg-hover);
  border-color: var(--border-color-hover);
  transform: scale(1.1);
}

.icon-btn.selected {
  background: rgba(37, 99, 235, 0.12);
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
  color: var(--accent-primary);
}

/* Confirm Box */
.confirm-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.confirm-icon {
  width: 56px;
  height: 56px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-danger);
}

.modal-error .error-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 0;
  background: rgba(220, 38, 38, 0.12);
  color: var(--accent-danger);
  flex-shrink: 0;
}

.confirm-text {
  font-size: 15px;
  color: var(--text-primary);
  line-height: 1.6;
}

.confirm-text strong {
  color: var(--accent-primary);
}

.confirm-subtext {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.6;
}

/* Modal Buttons */
.modal-btn {
  padding: 10px 24px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
  min-width: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.modal-btn.cancel {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
}

.modal-btn.cancel:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.modal-btn.primary {
  background: var(--gradient-primary);
  border: none;
  color: white;
}

.modal-btn.primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4);
}

.modal-btn.primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.modal-btn.danger {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.modal-btn.danger:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.25);
  transform: translateY(-2px);
}

.modal-btn.danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Spinner */
.btn-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 0;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
