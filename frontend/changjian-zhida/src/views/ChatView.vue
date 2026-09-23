<script setup lang="ts">
/**
 * AI 对话主视图
 * 无消息时：标题 + 输入框居中聚合
 * 有消息时：滚动消息列表 + 底部固定输入区
 */
import { nextTick, onMounted, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import WelcomePanel from '@/components/chat/WelcomePanel.vue'
import MessageList from '@/components/chat/MessageList.vue'
import ChatInput from '@/components/chat/ChatInput.vue'

const chatStore = useChatStore()

/** 消息列表滚动容器，用于自动滚到底部 */
let scrollEl: HTMLElement | null = null
function setScrollEl(el: unknown) {
  scrollEl = (el as HTMLElement) ?? null
}

/** 滚动到消息底部 */
async function scrollToBottom() {
  await nextTick()
  if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight
}

// 消息变化（发送/流式输出）时自动滚动
watch(
  () => chatStore.activeMessages.map((m) => m.content.length).join(','),
  scrollToBottom,
)

onMounted(scrollToBottom)
</script>

<template>
  <div class="chat-view">
    <!-- 空状态：标题 + 输入框居中聚合 -->
    <div v-if="chatStore.isEmptyChat" class="empty-center">
      <WelcomePanel />
      <div class="empty-input">
        <ChatInput />
      </div>
    </div>

    <!-- 有消息时：滚动消息列表 + 底部固定输入 -->
    <template v-else>
      <div class="chat-scroll" :ref="setScrollEl">
        <MessageList class="chat-inner" />
      </div>
      <ChatInput />
    </template>
  </div>
</template>

<style scoped>
.chat-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 空状态：标题下移，输入框上移，整体在可视区域中间聚合 */
.empty-center {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 24px 15vh;
  overflow-y: auto;
}

.empty-input {
  width: 100%;
  max-width: 860px;
  margin-top: 36px;
}

.chat-scroll {
  flex: 1;
  overflow-y: auto;
}

.chat-inner {
  max-width: 860px;
  margin: 0 auto;
  padding: 24px 24px 8px;
}
</style>
