import axios from 'axios'
import type {
  Attachment,
  AdminConversation,
  AdminStats,
  Conversation,
  ConversationDetail,
  KbDocument,
  KbDocumentDetail,
  KbIndexStatus,
  KbLibrary,
  KbSearchResult,
  OcrResult,
  OcrStatus,
  PromptTemplates,
  SystemConfig,
  VllmHealth,
  YsScreenResult,
} from '@/types'

/**
 * HTTP 客户端
 * 统一请求前缀：开发环境走 Vite 代理 /api，生产环境由后端同源提供
 */
const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api'

/** 获取/生成当前用户标识（存 localStorage，同一浏览器视为同一用户） */
function getUserId(): string {
  let id = localStorage.getItem('cj_user_id')
  if (!id) {
    id = `u_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
    localStorage.setItem('cj_user_id', id)
  }
  return id
}

export const http = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
  headers: { 'X-User-Id': getUserId() },
})

/**
 * 发送消息并接收 AI 流式回答（SSE）。
 * 使用 fetch + ReadableStream 解析 SSE；支持 AbortSignal 终止。
 */
/**
 * 发送消息并接收 AI 流式回答（SSE）。
 * 使用 fetch + ReadableStream 解析 SSE；支持 AbortSignal 终止。
 */
export interface StreamCallbacks {
  /** 回答正文增量 */
  onChunk: (chunk: string) => void
  /** RAG 召回片段（选知识库问答时，在正文前一次性回调） */
  onRetrieval?: (hits: KbSearchResult[]) => void
}

export async function sendMessageStream(
  conversationId: string,
  question: string,
  attachments: Attachment[],
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  libraryId?: string,
): Promise<void> {
  const res = await fetch(`${BASE_URL}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getUserId(),
    },
    body: JSON.stringify({
      conversation_id: conversationId,
      message: question,
      attachments: attachments.length ? attachments : undefined,
      library_id: libraryId || undefined,
    }),
    signal,
  })

  if (!res.ok || !res.body) {
    throw new Error(`请求失败：HTTP ${res.status}`)
  }
  await consumeSseStream(res, callbacks)
}

/** 通用：读取 SSE 响应流，解析 retrieval/delta/error 事件 */
async function consumeSseStream(
  res: Response,
  callbacks: StreamCallbacks,
): Promise<void> {
  const reader = res.body!.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''

    for (const block of blocks) {
      for (const line of block.split('\n')) {
        const s = line.trim()
        if (!s.startsWith('data:')) continue
        const data = s.slice(5).trim()
        if (!data || data === '[DONE]') continue

        let obj: {
          delta?: string
          error?: string
          retrieval?: KbSearchResult[]
        }
        try {
          obj = JSON.parse(data)
        } catch {
          continue
        }
        if (obj.error) throw new Error(obj.error)
        if (obj.retrieval) callbacks.onRetrieval?.(obj.retrieval)
        if (obj.delta) callbacks.onChunk(obj.delta)
      }
    }
  }
}

/** 上传文档，后端提取文本 */
export async function uploadFile(file: File): Promise<Attachment> {
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await http.post('/upload', form)
    return { filename: res.data.filename, content: res.data.content }
  } catch (e) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    throw new Error(typeof detail === 'string' ? detail : '上传失败，请检查文件格式')
  }
}

/** 获取会话列表（当前用户） */
export async function fetchConversations(): Promise<Conversation[]> {
  const res = await http.get('/conversations')
  return res.data?.data ?? []
}

/** 获取单个会话详情（含消息） */
export async function fetchConversation(id: string): Promise<Conversation> {
  const res = await http.get(`/conversations/${id}`)
  return res.data
}

/** 删除会话 */
export async function removeConversationRemote(id: string): Promise<void> {
  await http.delete(`/conversations/${id}`)
}

// ---------------------------------------------------------------------------
// 知识库（部门库）
// ---------------------------------------------------------------------------

/** 获取知识库列表 */
export async function fetchKbLibraries(): Promise<KbLibrary[]> {
  const res = await http.get('/kb/libraries')
  return res.data?.data ?? []
}

/** 新建知识库（isPublic=false 时仅创建者可见） */
export async function createKbLibrary(name: string, isPublic = true): Promise<KbLibrary> {
  const res = await http.post('/kb/libraries', { name, is_public: isPublic })
  return res.data
}

/** 删除知识库 */
export async function removeKbLibrary(id: string, password: string): Promise<void> {
  await http.delete(`/kb/libraries/${id}`, {
    headers: { 'X-Admin-Password': password },
  })
}

/** 上传文档到指定知识库 */
export async function uploadKbDocument(
  libraryId: string,
  file: File,
): Promise<KbDocument> {
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await http.post(`/kb/libraries/${libraryId}/documents`, form)
    return res.data
  } catch (e) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    throw new Error(typeof detail === 'string' ? detail : '上传失败，请检查文件格式')
  }
}

/** 获取指定知识库的文档列表 */
export async function fetchKbDocuments(libraryId: string): Promise<KbDocument[]> {
  const res = await http.get(`/kb/libraries/${libraryId}/documents`)
  return res.data?.data ?? []
}

/** 删除知识库文档 */
export async function removeKbDocument(id: string): Promise<void> {
  await http.delete(`/kb/documents/${id}`)
}

/** 获取单个知识库文档完整内容 */
export async function fetchKbDocument(id: string): Promise<KbDocumentDetail> {
  const res = await http.get(`/kb/documents/${id}`)
  return res.data
}

/** 检索知识库（libraryId 为空则检索全部库） */
export async function searchKb(
  query: string,
  libraryId?: string,
  topK?: number,
): Promise<KbSearchResult[]> {
  const res = await http.post('/kb/search', {
    query,
    library_id: libraryId || undefined,
    top_k: topK,
  })
  return res.data?.data ?? []
}

export async function reindexKb(password: string): Promise<{
  total: number
  indexed: number
  failed: number
}> {
  const res = await http.post('/kb/reindex', undefined, {
    headers: { 'X-Admin-Password': password },
  })
  return res.data?.data ?? { total: 0, indexed: 0, failed: 0 }
}

// ===== 系统管理（需管理员密码，X-Admin-Password 请求头） =====

/** 管理员密码存 sessionStorage（会话级，关闭浏览器标签页失效） */
export function getAdminPwd(): string {
  return sessionStorage.getItem('cj_admin_pwd') ?? ''
}

export function setAdminPwd(pwd: string): void {
  sessionStorage.setItem('cj_admin_pwd', pwd)
}

export function clearAdminPwd(): void {
  sessionStorage.removeItem('cj_admin_pwd')
}

export async function fetchAdminStats(): Promise<AdminStats> {
  const res = await http.get('/admin/stats', {
    headers: { 'X-Admin-Password': getAdminPwd() },
  })
  return res.data
}

export async function fetchAdminConversations(limit = 50): Promise<AdminConversation[]> {
  const res = await http.get('/admin/conversations', {
    params: { limit },
    headers: { 'X-Admin-Password': getAdminPwd() },
  })
  return res.data?.data ?? []
}

export async function fetchAdminConfig(): Promise<SystemConfig> {
  const res = await http.get('/admin/config', {
    headers: { 'X-Admin-Password': getAdminPwd() },
  })
  return res.data?.data
}

export async function updateAdminConfig(payload: {
  temperature?: number
  max_tokens?: number
}): Promise<SystemConfig> {
  const res = await http.post('/admin/config', payload, {
    headers: { 'X-Admin-Password': getAdminPwd() },
  })
  return res.data?.data
}

/** 提交回答质量反馈（点赞/点踩） */
export async function submitFeedback(
  messageId: string,
  conversationId: string,
  rating: 1 | -1,
): Promise<void> {
  await http.post('/feedback', {
    message_id: messageId,
    conversation_id: conversationId,
    rating,
  })
}

/** 通用文件下载（管理员接口，带密码） */
async function downloadFile(url: string, filename: string): Promise<void> {
  const res = await http.get(url, {
    responseType: 'blob',
    headers: { 'X-Admin-Password': getAdminPwd() },
  })
  const blob = new Blob([res.data])
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

/** 下载数据库备份 */
export async function downloadBackup(): Promise<void> {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  const name = `changjian-zhida-backup-${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}.db`
  await downloadFile('/admin/backup', name)
}

/** 知识库索引状态 */
export async function fetchKbIndexStatus(): Promise<KbIndexStatus> {
  const res = await http.get('/admin/kb-index-status', {
    headers: { 'X-Admin-Password': getAdminPwd() },
  })
  return res.data?.data ?? { totalChunks: 0, indexedChunks: 0, documents: [] }
}

/** vLLM 模型服务健康状态 */
export async function fetchVllmHealth(): Promise<VllmHealth> {
  const res = await http.get('/admin/vllm-health', {
    headers: { 'X-Admin-Password': getAdminPwd() },
  })
  return res.data ?? { online: false, latencyMs: 0 }
}

/** 查看会话完整对话 */
export async function fetchConversationMessages(id: string): Promise<ConversationDetail> {
  const res = await http.get(`/admin/conversations/${id}/messages`, {
    headers: { 'X-Admin-Password': getAdminPwd() },
  })
  return res.data?.data
}

/** 导出会话为文本文件 */
export async function exportConversation(id: string): Promise<void> {
  await downloadFile(`/admin/conversations/${id}/export`, `conversation-${id.slice(0, 8)}.txt`)
}

/** 批量删除会话 */
export async function batchDeleteConversations(ids: string[]): Promise<void> {
  await http.post(
    '/admin/conversations/batch-delete',
    { ids },
    { headers: { 'X-Admin-Password': getAdminPwd() } },
  )
}

/** 读取提示词模板 */
export async function fetchPrompts(): Promise<PromptTemplates> {
  const res = await http.get('/admin/prompts', {
    headers: { 'X-Admin-Password': getAdminPwd() },
  })
  return res.data?.data
}

/** 更新提示词模板 */
export async function updatePrompts(payload: Partial<PromptTemplates>): Promise<PromptTemplates> {
  const res = await http.post('/admin/prompts', payload, {
    headers: { 'X-Admin-Password': getAdminPwd() },
  })
  return res.data?.data
}

// ===== OCR 识别 =====

/** 查询 OCR 引擎可用状态 */
export async function fetchOcrStatus(): Promise<OcrStatus> {
  const res = await http.get('/ocr/status')
  return res.data ?? { available: false, engine: null }
}

/** 上传图片进行 OCR 识别 */
export async function recognizeOcr(file: File): Promise<OcrResult> {
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await http.post('/ocr', form, { timeout: 120000 })
    return res.data
  } catch (e) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    throw new Error(typeof detail === 'string' ? detail : '识别失败，请稍后重试')
  }
}

// ===== 检护营商智能体（食品安全处罚监督筛查）=====

/** 查询主体碰撞数据量 */
export async function fetchYsStatus(): Promise<{ collisionCount: number }> {
  const res = await http.get('/agent/yingshang/status')
  return res.data ?? { collisionCount: 0 }
}

/** 导入市监局许可/备案表（主体碰撞数据） */
export async function importYsCollision(file: File): Promise<{ imported: number }> {
  const form = new FormData()
  form.append('file', file)
  const res = await http.post('/agent/yingshang/import-collision', form, { timeout: 300000 })
  return res.data
}

/** 筛查：上传字段表(xlsx)/文书文件，或粘贴文书文本 */
export async function screenYs(payload: { file?: File; text?: string }): Promise<YsScreenResult> {
  const form = new FormData()
  if (payload.file) form.append('file', payload.file)
  if (payload.text) form.append('text', payload.text)
  const res = await http.post('/agent/yingshang/screen', form, { timeout: 300000 })
  return res.data?.data ?? { total: 0, hintCount: 0, hints: [] }
}
