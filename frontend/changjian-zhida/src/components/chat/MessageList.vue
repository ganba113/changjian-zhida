<script setup lang="ts">
/**
 * 消息列表：渲染当前会话的全部消息
 * 用户消息右对齐（蓝色气泡），AI 消息左对齐（白色气泡 + 头像）
 * 每条消息气泡下方带纯图标操作栏：复制 / 点赞(上拇指) / 点踩(下拇指)
 */
import { computed, ref } from 'vue'
import { Promotion, User, Paperclip } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import { copyText } from '@/utils/clipboard'
import { submitFeedback } from '@/api/chat'
import type { ChatMessage } from '@/types'

const chatStore = useChatStore()
const messages = computed(() => chatStore.activeMessages)

/** 已反馈状态：message_id -> 1 | -1 */
const feedbackState = ref<Record<string, 1 | -1>>({})

/** 复制消息内容 */
async function copyMessage(msg: ChatMessage) {
  const ok = await copyText(msg.content)
  if (ok) ElMessage.success('已复制')
  else ElMessage.error('复制失败，请手动选择复制')
}

/** 提交回答质量反馈（点赞/点踩） */
async function rateMessage(msg: ChatMessage, rating: 1 | -1) {
  const convId = chatStore.activeConversationId
  if (!convId) return
  try {
    await submitFeedback(msg.id, convId, rating)
    feedbackState.value[msg.id] = rating
    ElMessage.success(rating === 1 ? '感谢反馈' : '已记录')
  } catch {
    ElMessage.error('反馈失败')
  }
}
</script>

<template>
  <div class="message-list">
    <div
      v-for="msg in messages"
      :key="msg.id"
      class="msg-row"
      :class="msg.role"
    >
      <div class="msg-main" :class="msg.role">
        <!-- 头像 -->
        <div class="avatar" :class="msg.role">
          <el-icon v-if="msg.role === 'assistant'" :size="18" color="#fff"><Promotion /></el-icon>
          <el-icon v-else :size="18" color="#fff"><User /></el-icon>
        </div>

        <!-- 气泡内容 -->
        <div class="bubble" :class="msg.role">
          <!-- 用户消息的附件标记 -->
          <div v-if="msg.role === 'user' && msg.attachments?.length" class="msg-attachments">
            <div v-for="att in msg.attachments" :key="att.filename" class="msg-attach">
              <el-icon :size="13"><Paperclip /></el-icon>
              <span>{{ att.filename }}</span>
            </div>
          </div>

          <!-- 正文 -->
          <span class="msg-text">{{ msg.content }}</span>
          <span v-if="msg.streaming" class="cj-cursor"></span>
          <span v-else-if="msg.role === 'assistant' && !msg.content" class="thinking">
            正在思考…
          </span>

          <!-- RAG 召回引用来源（AI，折叠框） -->
          <details
            v-if="msg.role === 'assistant' && msg.retrieval?.length"
            class="retrieval-fold"
          >
            <summary>引用来源（{{ msg.retrieval.length }}）</summary>
            <div class="retrieval-list">
              <div v-for="(r, i) in msg.retrieval" :key="i" class="retrieval-item">
                <div class="retrieval-meta">#{{ i + 1 }} · {{ r.filename }}</div>
                <div class="retrieval-content">{{ r.content }}</div>
              </div>
            </div>
          </details>
        </div>
      </div>

      <!-- 气泡下方操作栏（纯图标） -->
      <div v-if="msg.content && !msg.streaming" class="msg-actions" :class="msg.role">
        <el-tooltip content="复制" placement="top">
          <span class="action-icon" @click="copyMessage(msg)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
          </span>
        </el-tooltip>
        <template v-if="msg.role === 'assistant'">
          <el-tooltip content="有帮助" placement="top">
            <span
              class="action-icon good"
              :class="{ rated: feedbackState[msg.id] === 1 }"
              @click="rateMessage(msg, 1)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3z" />
                <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
              </svg>
            </span>
          </el-tooltip>
          <el-tooltip content="有问题" placement="top">
            <span
              class="action-icon bad"
              :class="{ rated: feedbackState[msg.id] === -1 }"
              @click="rateMessage(msg, -1)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z" />
                <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
              </svg>
            </span>
          </el-tooltip>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-bottom: 20px;
}

.msg-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.msg-row.user {
  align-items: flex-end;
}

.msg-main {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  max-width: 100%;
}
.msg-main.user {
  flex-direction: row-reverse;
}

.avatar {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.avatar.assistant {
  background: var(--cj-primary-gradient);
}
.avatar.user {
  background: #6b7a90;
}

.bubble {
  max-width: 78%;
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble.assistant {
  background: #fff;
  border: 1px solid var(--cj-border);
  border-top-left-radius: 4px;
}
.bubble.user {
  background: var(--cj-primary);
  color: #fff;
  border-top-right-radius: 4px;
}

/* 等待首字输出时的占位 */
.thinking {
  color: var(--cj-text-sub);
}

/* 用户消息里的附件标记 */
.msg-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}
.msg-attach {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 12px;
  max-width: 220px;
}
.msg-attach span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* RAG 召回引用来源（折叠框） */
.retrieval-fold {
  margin-top: 8px;
  border: 1px solid var(--cj-border);
  border-radius: 8px;
  background: #fafbfe;
  overflow: hidden;
}
.retrieval-fold summary {
  cursor: pointer;
  padding: 7px 12px;
  font-size: 12px;
  color: var(--cj-primary);
  font-weight: 600;
  list-style: none;
  user-select: none;
}
.retrieval-fold summary::before {
  content: '▸ ';
}
.retrieval-fold[open] summary::before {
  content: '▾ ';
}
.retrieval-list {
  padding: 4px 12px 10px;
}
.retrieval-item {
  padding: 8px 0;
  border-top: 1px dashed var(--cj-border);
}
.retrieval-meta {
  font-size: 12px;
  color: var(--cj-primary);
  margin-bottom: 3px;
  font-weight: 600;
}
.retrieval-content {
  font-size: 12px;
  line-height: 1.7;
  color: var(--cj-text-sub);
  white-space: pre-wrap;
  word-break: break-word;
}

/* 气泡下方操作栏（纯图标） */
.msg-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-left: 44px; /* 头像 34 + gap 10，对齐气泡左缘 */
  user-select: none;
}
.msg-actions.user {
  padding-left: 0;
  padding-right: 44px;
}

.action-icon {
  cursor: pointer;
  color: #9aa5b5;
  font-size: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 5px;
  border-radius: 6px;
  transition: color 0.15s, background 0.15s;
}
.action-icon svg {
  width: 18px;
  height: 18px;
}
.action-icon:hover {
  color: var(--cj-primary, #1e4fa3);
  background: #f0f3f8;
}
.action-icon.good.rated {
  color: #18a058;
}
.action-icon.bad.rated {
  color: #d03050;
}
</style>
