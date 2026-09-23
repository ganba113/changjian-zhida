<script setup lang="ts">
/**
 * 系统管理模块：需管理员密码验证后才能进入
 * 功能：统计概览 / 近7天活跃 / 知识库索引状态 / 会话管理（查看/导出/批量删除）
 *      模型配置 / 提示词模板编辑 / 数据备份 / vLLM 健康监控
 */
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Lock,
  Refresh,
  User,
  ChatDotRound,
  Message,
  Document,
  Files,
  TrendCharts,
  Download,
  View,
  Star,
  CircleClose,
  Coin,
  CircleCheckFilled,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  fetchAdminStats,
  fetchAdminConversations,
  fetchAdminConfig,
  updateAdminConfig,
  getAdminPwd,
  setAdminPwd,
  clearAdminPwd,
  downloadBackup,
  fetchKbIndexStatus,
  fetchVllmHealth,
  fetchConversationMessages,
  exportConversation,
  batchDeleteConversations,
  fetchPrompts,
  updatePrompts,
} from '@/api/chat'
import type {
  AdminStats,
  AdminConversation,
  SystemConfig,
  KbIndexStatus,
  VllmHealth,
  ConversationDetail,
  PromptTemplates,
} from '@/types'

const unlocked = ref(false)
const loading = ref(false)

const stats = ref<AdminStats | null>(null)
const conversations = ref<AdminConversation[]>([])
const config = ref<SystemConfig | null>(null)
const vllm = ref<VllmHealth | null>(null)
const indexStatus = ref<KbIndexStatus | null>(null)
const prompts = ref<PromptTemplates | null>(null)

/** 配置表单（temperature / max_tokens） */
const configForm = reactive({ temperature: 0.7, max_tokens: 2048 })
const savingConfig = ref(false)

/** 提示词模板表单 */
const promptsForm = reactive({
  system_prompt_default: '',
  identity_notice: '',
  output_format_notice: '',
})
const savingPrompts = ref(false)

/** 会话多选 + 详情弹窗 */
const selectedIds = ref<string[]>([])
const convDetail = ref<ConversationDetail | null>(null)
const convDialogVisible = ref(false)
const convLoading = ref(false)
const backingUp = ref(false)

function isPwdError(e: unknown): boolean {
  const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return detail === '管理员密码错误'
}

/** 加载全部管理数据 */
async function loadAll() {
  loading.value = true
  try {
    const [s, c, p, idx, convs, v] = await Promise.all([
      fetchAdminStats(),
      fetchAdminConfig(),
      fetchPrompts(),
      fetchKbIndexStatus(),
      fetchAdminConversations(100),
      fetchVllmHealth(),
    ])
    stats.value = s
    config.value = c
    configForm.temperature = c.TEMPERATURE
    configForm.max_tokens = c.MAX_TOKENS
    prompts.value = p
    promptsForm.system_prompt_default = p.system_prompt_default
    promptsForm.identity_notice = p.identity_notice
    promptsForm.output_format_notice = p.output_format_notice
    indexStatus.value = idx
    conversations.value = convs
    vllm.value = v
  } finally {
    loading.value = false
  }
}

async function unlock() {
  let pwd = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入管理员密码', '系统管理', {
      inputType: 'password',
      confirmButtonText: '进入',
      cancelButtonText: '取消',
      inputValidator: (v: string) => (v && v.trim() ? true : '密码不能为空'),
    })
    pwd = value.trim()
  } catch {
    return
  }
  setAdminPwd(pwd)
  try {
    await loadAll()
    unlocked.value = true
  } catch (e) {
    clearAdminPwd()
    if (isPwdError(e)) ElMessage.error('管理员密码错误')
    else ElMessage.error('加载失败：' + (e as Error).message)
  }
}

function logout() {
  clearAdminPwd()
  unlocked.value = false
  stats.value = null
  conversations.value = []
  config.value = null
  vllm.value = null
  indexStatus.value = null
  prompts.value = null
}

async function refresh() {
  try {
    await loadAll()
    ElMessage.success('已刷新')
  } catch (e) {
    if (isPwdError(e)) {
      ElMessage.error('登录已失效，请重新输入密码')
      logout()
    } else ElMessage.error('刷新失败：' + (e as Error).message)
  }
}

async function saveConfig() {
  savingConfig.value = true
  try {
    const updated = await updateAdminConfig({
      temperature: configForm.temperature,
      max_tokens: configForm.max_tokens,
    })
    config.value = updated
    ElMessage.success('配置已保存（热更新，立即生效）')
  } catch (e) {
    if (isPwdError(e)) {
      ElMessage.error('登录已失效，请重新输入密码')
      logout()
    } else ElMessage.error('保存失败：' + (e as Error).message)
  } finally {
    savingConfig.value = false
  }
}

async function savePrompts() {
  savingPrompts.value = true
  try {
    const updated = await updatePrompts({
      system_prompt_default: promptsForm.system_prompt_default,
      identity_notice: promptsForm.identity_notice,
      output_format_notice: promptsForm.output_format_notice,
    })
    prompts.value = updated
    ElMessage.success('提示词已保存（立即生效）')
  } catch (e) {
    if (isPwdError(e)) {
      ElMessage.error('登录已失效，请重新输入密码')
      logout()
    } else ElMessage.error('保存失败：' + (e as Error).message)
  } finally {
    savingPrompts.value = false
  }
}

async function handleBackup() {
  backingUp.value = true
  try {
    await downloadBackup()
    ElMessage.success('备份已开始下载')
  } catch (e) {
    if (isPwdError(e)) {
      ElMessage.error('登录已失效，请重新输入密码')
      logout()
    } else ElMessage.error('备份失败：' + (e as Error).message)
  } finally {
    backingUp.value = false
  }
}

/** 查看会话详情 */
async function viewConversation(row: AdminConversation) {
  convLoading.value = true
  convDialogVisible.value = true
  convDetail.value = null
  try {
    convDetail.value = await fetchConversationMessages(row.id)
  } catch (e) {
    if (isPwdError(e)) ElMessage.error('登录已失效，请重新输入密码')
    else ElMessage.error('加载失败：' + (e as Error).message)
    convDialogVisible.value = false
  } finally {
    convLoading.value = false
  }
}

async function handleExport(row: AdminConversation) {
  try {
    await exportConversation(row.id)
    ElMessage.success('已导出')
  } catch (e) {
    ElMessage.error('导出失败：' + (e as Error).message)
  }
}

async function handleBatchDelete() {
  if (!selectedIds.value.length) {
    ElMessage.warning('请先勾选要删除的会话')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedIds.value.length} 个会话吗？其消息与反馈将一并删除，且不可恢复。`,
      '批量删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await batchDeleteConversations(selectedIds.value)
    ElMessage.success(`已删除 ${selectedIds.value.length} 个会话`)
    selectedIds.value = []
    await loadAll()
  } catch (e) {
    if (isPwdError(e)) ElMessage.error('登录已失效，请重新输入密码')
    else ElMessage.error('删除失败：' + (e as Error).message)
  }
}

function fmtTime(ms: number): string {
  if (!ms) return '-'
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function fmtTokens(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

const dayLabels = computed(() => {
  const labels: string[] = []
  const now = new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 86400000)
    labels.push(`${d.getMonth() + 1}/${d.getDate()}`)
  }
  return labels
})

const dailyBars = computed(() => {
  const arr = stats.value?.dailyActive ?? []
  const max = Math.max(1, ...arr)
  return arr.map((v) => ({ value: v, height: Math.round((v / max) * 100) }))
})

const indexPercent = computed(() => {
  const total = indexStatus.value?.totalChunks ?? 0
  if (!total) return 0
  return Math.round(((indexStatus.value?.indexedChunks ?? 0) / total) * 100)
})

function onSelectionChange(rows: AdminConversation[]) {
  selectedIds.value = rows.map((r) => r.id)
}

onMounted(() => {
  if (getAdminPwd()) {
    loadAll()
      .then(() => (unlocked.value = true))
      .catch(() => clearAdminPwd())
  }
})
</script>

<template>
  <div class="system-view">
    <!-- ============ 未解锁：锁屏 ============ -->
    <div v-if="!unlocked" class="lock-screen">
      <el-icon :size="52" class="lock-icon"><Lock /></el-icon>
      <h2>系统管理</h2>
      <p>进入系统管理界面需要管理员权限</p>
      <el-button type="primary" size="large" @click="unlock">输入密码进入</el-button>
    </div>

    <!-- ============ 已解锁：管理面板 ============ -->
    <div v-else v-loading="loading" class="admin-panel">
      <header class="sys-header">
        <div class="sys-title">
          <h2>系统管理</h2>
          <span class="vllm-pill" :class="{ online: vllm?.online }">
            <el-icon :size="12"><CircleCheckFilled /></el-icon>
            模型服务 {{ vllm?.online ? `在线 · ${vllm.latencyMs}ms` : '离线' }}
          </span>
        </div>
        <div class="sys-actions">
          <el-button :icon="Download" :loading="backingUp" @click="handleBackup">备份数据库</el-button>
          <el-button :icon="Refresh" @click="refresh">刷新</el-button>
          <el-button @click="logout">退出登录</el-button>
        </div>
      </header>

      <!-- 统计概览 -->
      <div class="stat-grid">
        <div class="stat-card">
          <el-icon class="stat-icon" :size="26"><User /></el-icon>
          <div class="stat-num">{{ stats?.users ?? 0 }}</div>
          <div class="stat-label">用户数</div>
        </div>
        <div class="stat-card">
          <el-icon class="stat-icon" :size="26"><ChatDotRound /></el-icon>
          <div class="stat-num">{{ stats?.conversations ?? 0 }}</div>
          <div class="stat-label">会话总数</div>
        </div>
        <div class="stat-card">
          <el-icon class="stat-icon" :size="26"><Message /></el-icon>
          <div class="stat-num">{{ stats?.messages ?? 0 }}</div>
          <div class="stat-label">消息总数</div>
        </div>
        <div class="stat-card">
          <el-icon class="stat-icon" :size="26"><Document /></el-icon>
          <div class="stat-num">{{ stats?.kbDocuments ?? 0 }}</div>
          <div class="stat-label">知识库文档</div>
        </div>
        <div class="stat-card">
          <el-icon class="stat-icon" :size="26"><Files /></el-icon>
          <div class="stat-num">{{ stats?.kbChunks ?? 0 }}</div>
          <div class="stat-label">文档分块</div>
        </div>
        <div class="stat-card">
          <el-icon class="stat-icon" :size="26"><TrendCharts /></el-icon>
          <div class="stat-num">{{ stats?.weekConversations ?? 0 }}</div>
          <div class="stat-label">近7天会话</div>
        </div>
        <div class="stat-card">
          <el-icon class="stat-icon" :size="26"><Coin /></el-icon>
          <div class="stat-num">{{ fmtTokens(stats?.totalTokens ?? 0) }}</div>
          <div class="stat-label">Token 用量(估)</div>
        </div>
        <div class="stat-card">
          <el-icon class="stat-icon good" :size="26"><Star /></el-icon>
          <div class="stat-num">{{ stats?.feedbackGood ?? 0 }}</div>
          <div class="stat-label">好评</div>
        </div>
        <div class="stat-card">
          <el-icon class="stat-icon bad" :size="26"><CircleClose /></el-icon>
          <div class="stat-num">{{ stats?.feedbackBad ?? 0 }}</div>
          <div class="stat-label">差评</div>
        </div>
      </div>

      <!-- 近7天活跃 -->
      <div class="panel-card">
        <div class="panel-title">近 7 天活跃会话</div>
        <div class="daily-chart">
          <div v-for="(bar, i) in dailyBars" :key="i" class="daily-col">
            <div class="daily-bar-wrap">
              <div class="daily-bar" :style="{ height: bar.height + '%' }"></div>
            </div>
            <div class="daily-val">{{ bar.value }}</div>
            <div class="daily-label">{{ dayLabels[i] }}</div>
          </div>
        </div>
      </div>

      <!-- 知识库索引状态 -->
      <div class="panel-card">
        <div class="panel-title">
          知识库向量索引状态
          <span class="panel-sub">已索引 {{ indexStatus?.indexedChunks ?? 0 }} / {{ indexStatus?.totalChunks ?? 0 }} 块（{{ indexPercent }}%）</span>
        </div>
        <el-progress
          :percentage="indexPercent"
          :stroke-width="10"
          :status="indexPercent === 100 ? 'success' : undefined"
        />
        <el-table
          v-if="indexStatus && indexStatus.documents.length"
          :data="indexStatus.documents.slice(0, 20)"
          size="small"
          max-height="240"
          style="width: 100%; margin-top: 12px"
        >
          <el-table-column prop="filename" label="文档" min-width="200" show-overflow-tooltip />
          <el-table-column prop="lib_name" label="所属库" width="160" show-overflow-tooltip />
          <el-table-column prop="chunk_count" label="分块数" width="90" />
          <el-table-column prop="vec_count" label="已向量化" width="90" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.vec_count >= row.chunk_count" type="success" size="small">已索引</el-tag>
              <el-tag v-else-if="row.vec_count > 0" type="warning" size="small">部分</el-tag>
              <el-tag v-else type="info" size="small">未索引</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="panel-empty">暂无知识库文档</div>
      </div>

      <!-- 会话列表 -->
      <div class="panel-card">
        <div class="panel-title-row">
          <div class="panel-title">最近会话（{{ conversations.length }}）</div>
          <el-button type="danger" size="small" :disabled="!selectedIds.length" @click="handleBatchDelete">
            删除选中（{{ selectedIds.length }}）
          </el-button>
        </div>
        <el-table
          :data="conversations"
          size="small"
          max-height="360"
          style="width: 100%"
          @selection-change="onSelectionChange"
        >
          <el-table-column type="selection" width="42" />
          <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="userId" label="用户标识" min-width="130" show-overflow-tooltip />
          <el-table-column label="更新时间" width="150">
            <template #default="{ row }">{{ fmtTime(row.updateTime) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" :icon="View" @click="viewConversation(row)">查看</el-button>
              <el-button link type="primary" size="small" :icon="Download" @click="handleExport(row)">导出</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 模型配置 -->
      <div class="panel-card">
        <div class="panel-title">模型生成配置</div>
        <div class="config-form">
          <div class="config-item">
            <span class="config-label">温度（Temperature）</span>
            <el-input-number
              v-model="configForm.temperature"
              :min="0"
              :max="2"
              :step="0.1"
              :precision="1"
            />
            <span class="config-hint">越高越发散，越低越保守</span>
          </div>
          <div class="config-item">
            <span class="config-label">单次最大 Token</span>
            <el-input-number v-model="configForm.max_tokens" :min="256" :max="16384" :step="256" />
            <span class="config-hint">约 1 汉字 ≈ 1~1.5 token</span>
          </div>
          <div class="config-item">
            <span class="config-label">模型</span>
            <span class="config-value">{{ config?.VLLM_MODEL ?? '-' }}</span>
          </div>
          <div class="config-actions">
            <el-button type="primary" :loading="savingConfig" @click="saveConfig">保存配置</el-button>
            <span class="config-hint">保存后立即生效（重启服务后回落到 .env 值）</span>
          </div>
        </div>
      </div>

      <!-- 提示词模板 -->
      <div class="panel-card">
        <div class="panel-title">提示词模板</div>
        <div class="prompt-form">
          <div class="prompt-item">
            <span class="config-label">默认系统提示词</span>
            <el-input v-model="promptsForm.system_prompt_default" type="textarea" :rows="3" />
          </div>
          <div class="prompt-item">
            <span class="config-label">身份说明</span>
            <el-input v-model="promptsForm.identity_notice" type="textarea" :rows="3" />
          </div>
          <div class="prompt-item">
            <span class="config-label">输出格式约束</span>
            <el-input v-model="promptsForm.output_format_notice" type="textarea" :rows="2" />
          </div>
          <div class="config-actions">
            <el-button type="primary" :loading="savingPrompts" @click="savePrompts">保存提示词</el-button>
            <span class="config-hint">保存后立即生效；清空并保存可恢复默认值</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 会话详情弹窗 -->
    <el-dialog
      v-model="convDialogVisible"
      :title="convDetail?.title ?? '会话详情'"
      width="720px"
      top="6vh"
    >
      <div v-loading="convLoading" class="conv-dialog">
        <div v-for="m in convDetail?.messages ?? []" :key="m.id" class="conv-msg" :class="m.role">
          <div class="conv-role">{{ m.role === 'user' ? '用户' : '助手' }}</div>
          <div class="conv-content">{{ m.content }}</div>
        </div>
        <div v-if="!convLoading && !convDetail?.messages?.length" class="panel-empty">无消息</div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.system-view {
  height: 100%;
  overflow-y: auto;
  padding: 24px 32px;
}

/* 锁屏 */
.lock-screen {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--cj-text-secondary, #666);
}
.lock-icon {
  color: var(--cj-primary, #2f6bd4);
}
.lock-screen h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--cj-text-primary, #222);
}
.lock-screen p {
  margin: 0 0 8px;
  font-size: 14px;
}

/* 管理面板 */
.admin-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.sys-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sys-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.sys-title h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
.vllm-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 12px;
  background: #fde2e2;
  color: #d03050;
}
.vllm-pill.online {
  background: #e3f5e8;
  color: #18a058;
}
.sys-actions {
  display: flex;
  gap: 8px;
}

/* 统计卡片 */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}
.stat-card {
  background: #fff;
  border: 1px solid var(--cj-border, #e5e7eb);
  border-radius: 12px;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.stat-icon {
  color: var(--cj-primary, #2f6bd4);
}
.stat-icon.good {
  color: #18a058;
}
.stat-icon.bad {
  color: #d03050;
}
.stat-num {
  font-size: 24px;
  font-weight: 600;
  color: var(--cj-text-primary, #222);
  line-height: 1;
}
.stat-label {
  font-size: 12px;
  color: var(--cj-text-secondary, #666);
}

/* 面板卡片 */
.panel-card {
  background: #fff;
  border: 1px solid var(--cj-border, #e5e7eb);
  border-radius: 12px;
  padding: 16px 18px;
}
.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cj-text-primary, #222);
  margin-bottom: 14px;
}
.panel-sub {
  font-size: 12px;
  font-weight: 400;
  color: var(--cj-text-secondary, #999);
  margin-left: 8px;
}
.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.panel-title-row .panel-title {
  margin-bottom: 0;
}
.panel-empty {
  padding: 20px;
  text-align: center;
  font-size: 13px;
  color: var(--cj-text-secondary, #999);
}

/* 近7天柱状图 */
.daily-chart {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  height: 150px;
  padding: 0 8px;
}
.daily-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  height: 100%;
}
.daily-bar-wrap {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
.daily-bar {
  width: 60%;
  max-width: 42px;
  min-height: 4px;
  background: var(--cj-primary, #2f6bd4);
  border-radius: 6px 6px 0 0;
  transition: height 0.3s;
}
.daily-val {
  font-size: 13px;
  font-weight: 600;
  color: var(--cj-text-primary, #222);
}
.daily-label {
  font-size: 11px;
  color: var(--cj-text-secondary, #999);
}

/* 表单 */
.config-form,
.prompt-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.config-item {
  display: flex;
  align-items: center;
  gap: 14px;
}
.prompt-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.prompt-item .el-textarea {
  flex: 1;
}
.config-label {
  width: 150px;
  flex-shrink: 0;
  font-size: 14px;
  color: var(--cj-text-primary, #333);
  padding-top: 6px;
}
.config-hint {
  font-size: 12px;
  color: var(--cj-text-secondary, #999);
}
.config-value {
  font-size: 14px;
  color: var(--cj-primary, #2f6bd4);
  font-weight: 500;
}
.config-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 会话详情弹窗 */
.conv-dialog {
  max-height: 60vh;
  overflow-y: auto;
}
.conv-msg {
  margin-bottom: 14px;
  padding: 10px 14px;
  border-radius: 10px;
}
.conv-msg.user {
  background: #f0f5ff;
}
.conv-msg.assistant {
  background: #f7f8fa;
}
.conv-role {
  font-size: 12px;
  font-weight: 600;
  color: var(--cj-primary, #2f6bd4);
  margin-bottom: 4px;
}
.conv-content {
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
