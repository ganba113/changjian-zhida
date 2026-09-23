<script setup lang="ts">
/**
 * 底部输入区（固定在主内容区底部）
 * - textarea 自适应高度，Enter 发送、Shift+Enter 换行
 * - 支持上传附件（文档），随消息一起发送
 * - 生成中显示「停止」按钮，可随时终止并开始新对话
 */
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { Promotion, Paperclip, Close, VideoPause } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import { uploadFile, fetchKbLibraries } from '@/api/chat'
import type { Attachment, KbLibrary } from '@/types'

const chatStore = useChatStore()
const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

const attachments = ref<Attachment[]>([])
const uploading = ref(false)

/** 知识库列表（RAG 问答选择） */
const libraries = ref<KbLibrary[]>([])
/** 下拉选择的知识库：直接读写 store，保证欢迎页/消息视图两个实例状态一致 */
const selectedLib = computed<string | null>({
  get: () => chatStore.activeLibraryId,
  set: (v) => chatStore.setActiveLibrary(v ?? null),
})

async function loadLibraries() {
  try {
    libraries.value = await fetchKbLibraries()
  } catch (e) {
    console.error('加载知识库列表失败', e)
  }
}

/** 触发文件选择 */
function triggerUpload() {
  fileInputRef.value?.click()
}

/** 文件选择后上传 */
async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || !files.length) return
  uploading.value = true
  try {
    for (const f of Array.from(files)) {
      const att = await uploadFile(f)
      attachments.value.push(att)
    }
    ElMessage.success(`已上传 ${files.length} 个文件`)
  } catch (err) {
    ElMessage.error('上传失败：' + (err as Error).message)
  } finally {
    uploading.value = false
    input.value = ''
  }
}

/** 移除附件 */
function removeAttachment(idx: number) {
  attachments.value.splice(idx, 1)
}

/** 发送消息 */
function handleSend() {
  const text = inputText.value.trim()
  if ((!text && !attachments.value.length) || chatStore.generating) return
  const atts = [...attachments.value]
  const question = text || '请根据附件内容进行分析'
  inputText.value = ''
  attachments.value = []
  resizeTextarea()
  chatStore.sendUserMessage(question, atts)
}

/** 键盘事件：Enter 发送，Shift+Enter 换行 */
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    handleSend()
  }
}

/** textarea 高度自适应（约 9 行封顶） */
function resizeTextarea() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 288) + 'px'
}

/** 全局快捷键：Ctrl/Cmd + K 聚焦输入框 */
function globalKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    textareaRef.value?.focus()
  }
}

onMounted(async () => {
  window.addEventListener('keydown', globalKeydown)
  loadLibraries()
  await nextTick()
  textareaRef.value?.focus()
})

onUnmounted(() => {
  window.removeEventListener('keydown', globalKeydown)
})
</script>

<template>
  <div class="chat-input">
    <div class="input-box">
      <!-- 已选附件展示 -->
      <div v-if="attachments.length" class="attach-list">
        <div v-for="(att, idx) in attachments" :key="att.filename + idx" class="attach-item">
          <el-icon :size="14"><Paperclip /></el-icon>
          <span class="attach-name">{{ att.filename }}</span>
          <el-icon class="attach-remove" :size="13" @click="removeAttachment(idx)"><Close /></el-icon>
        </div>
      </div>

      <textarea
        ref="textareaRef"
        v-model="inputText"
        class="input-textarea"
        rows="3"
        placeholder="请输入您的问题，Enter 发送，Shift + Enter 换行；可上传文档进行对话"
        @keydown="handleKeydown"
        @input="resizeTextarea"
      ></textarea>

      <div class="input-actions">
        <div class="input-left">
          <!-- 上传附件按钮 -->
          <el-tooltip content="上传文档" placement="top">
            <el-button
              class="attach-btn"
              :loading="uploading"
              circle
              text
              @click="triggerUpload"
            >
              <el-icon :size="18"><Paperclip /></el-icon>
            </el-button>
          </el-tooltip>
          <!-- 知识库选择（RAG 问答） -->
          <el-select
            v-model="selectedLib"
            clearable
            placeholder="知识库（可选）"
            size="small"
            class="lib-select"
          >
            <el-option
              v-for="lib in libraries"
              :key="lib.id"
              :label="lib.name"
              :value="lib.id"
            />
          </el-select>
          <span class="input-hint">Ctrl + K 快速聚焦</span>
        </div>

        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept=".txt,.md,.csv,.json,.pdf,.docx,.doc,.wps,.xlsx,.xls,.html,.log"
          style="display: none"
          @change="onFileChange"
        />

        <!-- 发送 / 停止按钮 -->
        <el-button
          v-if="!chatStore.generating"
          type="primary"
          class="send-btn"
          :disabled="(!inputText.trim() && !attachments.length) || uploading"
          @click="handleSend"
        >
          <el-icon style="margin-right: 4px"><Promotion /></el-icon>
          发送
        </el-button>
        <el-button
          v-else
          type="danger"
          class="send-btn"
          @click="chatStore.stopGeneration()"
        >
          <el-icon style="margin-right: 4px"><VideoPause /></el-icon>
          停止
        </el-button>
      </div>
    </div>

    <p class="input-disclaimer">内容由 AI 生成，仅供参考，请以法律法规及办案规范为准</p>
  </div>
</template>

<style scoped>
.chat-input {
  flex-shrink: 0;
  padding: 8px 24px 10px;
}

.input-box {
  max-width: 860px;
  margin: 0 auto;
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 14px;
  padding: 10px 12px 8px;
  box-shadow: 0 4px 16px rgba(31, 45, 61, 0.06);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.input-box:focus-within {
  border-color: var(--cj-primary-light);
  box-shadow: 0 4px 20px rgba(30, 79, 163, 0.16);
}

/* 附件列表 */
.attach-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
}
.attach-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--cj-hover-bg);
  border: 1px solid var(--cj-border);
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 12px;
  color: var(--cj-text-main);
  max-width: 260px;
}
.attach-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attach-remove {
  color: var(--cj-text-sub);
  cursor: pointer;
}
.attach-remove:hover {
  color: #e5484d;
}

.input-textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  line-height: 1.7;
  font-family: inherit;
  color: var(--cj-text-main);
  background: transparent;
  max-height: 288px;
}

.input-textarea::placeholder {
  color: #b0bccd;
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}
.input-left {
  display: flex;
  align-items: center;
  gap: 6px;
}
.attach-btn {
  color: var(--cj-text-sub);
  padding: 4px;
}
.attach-btn:hover {
  color: var(--cj-primary);
  background: var(--cj-hover-bg);
}
.input-hint {
  font-size: 12px;
  color: #b0bccd;
}
.lib-select {
  width: 168px;
}

.send-btn {
  border-radius: 8px;
  padding: 7px 18px;
}

.input-disclaimer {
  max-width: 860px;
  margin: 8px auto 0;
  text-align: center;
  font-size: 12px;
  color: #b0bccd;
}
</style>
