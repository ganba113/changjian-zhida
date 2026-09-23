import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Conversation, ChatMessage, Attachment } from '@/types'
import {
  sendMessageStream,
  fetchConversations,
  fetchConversation,
  removeConversationRemote,
} from '@/api/chat'

/** 生成唯一 id */
function genId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/**
 * 对话状态：会话列表 + 当前会话 + 消息流式输出
 * 会话与消息均由后端持久化，按用户隔离。
 * 支持多会话并发：每个会话独立跟踪生成状态，互不阻塞。
 */
export const useChatStore = defineStore('chat', () => {
  // ---------- state ----------
  const conversations = ref<Conversation[]>([])
  const activeConversationId = ref<string | null>(null)
  /** 会话列表是否已加载 */
  const loaded = ref(false)
  /** 每个会话的 AbortController（用于终止各自的生成） */
  const abortMap = new Map<string, AbortController>()
  /** 当前选中的知识库（RAG 问答用，null 表示不指定知识库） */
  const activeLibraryId = ref<string | null>(null)

  // ---------- getters ----------
  const activeConversation = computed<Conversation | null>(
    () => conversations.value.find((c) => c.id === activeConversationId.value) ?? null,
  )

  const activeMessages = computed<ChatMessage[]>(
    () => activeConversation.value?.messages ?? [],
  )

  const isEmptyChat = computed(() => activeMessages.value.length === 0)

  /** 当前激活会话是否正在生成（不再是全局锁，允许多会话并发） */
  const generating = computed(() => activeMessages.value.some((m) => m.streaming))

  // ---------- actions ----------
  /** 从后端加载会话列表 */
  async function loadConversations() {
    try {
      const list = await fetchConversations()
      // 保留已加载会话的消息，避免切页回来丢失当前会话内容
      const prevMessages = new Map(conversations.value.map((c) => [c.id, c.messages]))
      conversations.value = list.map((c) => ({
        ...c,
        messages: prevMessages.get(c.id) ?? [],
      }))
      loaded.value = true
    } catch (e) {
      console.error('加载会话列表失败', e)
    }
  }

  /** 新建对话：清空当前选择，回到欢迎页；重置知识库选择 */
  function newConversation() {
    activeConversationId.value = null
    activeLibraryId.value = null
  }

  /** 选择历史对话：若消息尚未加载则从后端拉取 */
  async function selectConversation(id: string) {
    if (activeConversationId.value === id) return
    activeConversationId.value = id
    const conv = conversations.value.find((c) => c.id === id)
    if (conv && conv.messages.length === 0) {
      try {
        const detail = await fetchConversation(id)
        conv.messages = detail.messages
      } catch (e) {
        console.error('加载会话消息失败', e)
      }
    }
  }

  /** 删除对话（本地乐观删除 + 后端删除） */
  async function removeConversation(id: string) {
    const idx = conversations.value.findIndex((c) => c.id === id)
    if (idx > -1) conversations.value.splice(idx, 1)
    if (activeConversationId.value === id) {
      activeConversationId.value = null
    }
    try {
      await removeConversationRemote(id)
    } catch (e) {
      console.error('删除会话失败', e)
    }
  }

  /** 终止「当前会话」正在生成的回答 */
  function stopGeneration() {
    const id = activeConversationId.value
    if (id) abortMap.get(id)?.abort()
  }

  /**
   * 发送用户消息并接收 AI 流式回答
   * 若当前无激活会话则自动创建一条新会话（同步到后端）
   * 允许多个会话同时生成（不设全局锁）
   */
  async function sendUserMessage(content: string, attachments: Attachment[] = []) {
    const text = content.trim()
    if (!text) return

    if (!activeConversation.value) {
      const conv: Conversation = {
        id: genId(),
        title: text.slice(0, 20),
        messages: [],
        createTime: Date.now(),
        updateTime: Date.now(),
      }
      conversations.value.unshift(conv)
      activeConversationId.value = conv.id
    }

    const conv = activeConversation.value!

    conv.messages.push({
      id: genId(),
      role: 'user',
      content: text,
      attachments: attachments.length ? attachments : undefined,
      createTime: Date.now(),
    })
    conv.updateTime = Date.now()

    conv.messages.push({
      id: genId(),
      role: 'assistant',
      content: '',
      streaming: true,
      createTime: Date.now(),
    })
    const aiMsg = conv.messages[conv.messages.length - 1]

    const controller = new AbortController()
    abortMap.set(conv.id, controller)

    try {
      await sendMessageStream(
        conv.id,
        text,
        attachments,
        {
          onChunk: (chunk) => {
            aiMsg.content += chunk
          },
          onRetrieval: (hits) => {
            aiMsg.retrieval = hits
          },
        },
        controller.signal,
        undefined,
        activeLibraryId.value ?? undefined,
      )
    } catch (e) {
      const name = (e as Error)?.name
      if (name === 'AbortError') {
        // 用户主动终止：保留已生成内容
        if (!aiMsg.content) aiMsg.content = '（已终止）'
      } else {
        aiMsg.content += `\n\n[出错了：${(e as Error).message}]`
      }
    } finally {
      aiMsg.streaming = false
      abortMap.delete(conv.id)
      conv.updateTime = Date.now()
    }
  }

  /** 设置当前选中的知识库（RAG 问答，null 表示不指定） */
  function setActiveLibrary(id: string | null) {
    activeLibraryId.value = id
  }

  return {
    conversations,
    activeConversationId,
    generating,
    loaded,
    activeConversation,
    activeMessages,
    isEmptyChat,
    activeLibraryId,
    loadConversations,
    newConversation,
    selectConversation,
    removeConversation,
    stopGeneration,
    sendUserMessage,
    setActiveLibrary,
  }
})
