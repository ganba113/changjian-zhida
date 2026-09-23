/** 消息角色 */
export type MessageRole = 'user' | 'assistant'

/** 附件（文档） */
export interface Attachment {
  filename: string
  content: string
}

/** 单条对话消息 */
export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  /** 用户消息可携带附件（文档） */
  attachments?: Attachment[]
  /** 是否正在流式输出中 */
  streaming?: boolean
  /** RAG 召回片段（选知识库问答时） */
  retrieval?: KbSearchResult[]
  createTime: number
}

/** 一场会话（左侧列表中的一条历史对话） */
export interface Conversation {
  id: string
  title: string
  messages: ChatMessage[]
  createTime: number
  updateTime: number
}

/** 热门智能体卡片 */
export interface AgentCard {
  id: string
  name: string
  description: string
  icon: string
  color: string
}

/** 左侧导航项 */
export interface NavItem {
  path: string
  title: string
  icon: string
}

/** 智能体（后端下发） */
export interface Agent {
  id: string
  name: string
  description: string
}

/** 知识库（部门库） */
export interface KbLibrary {
  id: string
  name: string
  docCount: number
  createTime: number
}

/** 知识库文档 */
export interface KbDocument {
  id: string
  filename: string
  charCount: number
  chunkCount: number
  createTime: number
}

/** 知识库文档详情（含完整内容，点击查看用） */
export interface KbDocumentDetail extends KbDocument {
  libraryId: string
  content: string
}

/** 知识库检索结果片段 */
export interface KbSearchResult {
  docId: string
  filename: string
  library: string
  content: string
  score: number
}

/** 系统统计概览 */
export interface AdminStats {
  users: number
  conversations: number
  messages: number
  kbDocuments: number
  kbChunks: number
  weekConversations: number
  dailyActive: number[]
  totalTokens: number
  feedbackGood: number
  feedbackBad: number
}

/** 系统运行配置 */
export interface SystemConfig {
  VLLM_BASE_URL: string
  VLLM_MODEL: string
  TEMPERATURE: number
  MAX_TOKENS: number
  ENABLE_THINKING: boolean
}

/** 管理端会话记录 */
export interface AdminConversation {
  id: string
  userId: string
  title: string
  createTime: number
  updateTime: number
}

/** OCR 识别结果 */
export interface OcrResult {
  filename: string
  text: string
  engine: string
  chars: number
}

/** OCR 引擎状态 */
export interface OcrStatus {
  available: boolean
  engine: string | null
}

/** 知识库索引状态（单文档） */
export interface KbIndexDoc {
  id: string
  filename: string
  library_id: string
  lib_name: string
  chunk_count: number
  vec_count: number
}

/** 知识库索引状态（汇总） */
export interface KbIndexStatus {
  totalChunks: number
  indexedChunks: number
  documents: KbIndexDoc[]
}

/** vLLM 模型服务健康状态 */
export interface VllmHealth {
  online: boolean
  latencyMs: number
  model?: string
  detail?: string
}

/** 管理端会话完整消息 */
export interface AdminMessage {
  id: string
  role: string
  content: string
  attachments: string | null
  createTime: number
}

/** 管理端会话详情（含消息） */
export interface ConversationDetail {
  id: string
  userId: string
  title: string
  createTime: number
  updateTime: number
  messages: AdminMessage[]
}

/** 可编辑的提示词模板 */
export interface PromptTemplates {
  system_prompt_default: string
  identity_notice: string
  output_format_notice: string
}
