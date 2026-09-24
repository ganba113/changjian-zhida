<script setup lang="ts">
/**
 * 检护营商智能体 —— 食品安全领域行政处罚监督线索筛查
 * 输入：字段表(xlsx) / 处罚文书(doc/txt/pdf) / 粘贴文本
 * 输出：两档线索清单（明显异常 / 疑点线索），可筛选、导出
 */
import { onMounted, ref, computed } from 'vue'
import {
  Upload,
  Search,
  Download,
  DataAnalysis,
  CircleCheck,
  Warning,
  Refresh,
  Back,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { fetchYsStatus, importYsCollision, screenYs } from '@/api/chat'
import type { YsScreenResult, YsHint } from '@/types'

const router = useRouter()

const collisionCount = ref(0)
const statusLoading = ref(false)

// 输入
const selectedFile = ref<File | null>(null)
const inputText = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const screening = ref(false)

// 结果
const result = ref<YsScreenResult | null>(null)
const levelFilter = ref('')
const filteredHints = computed<YsHint[]>(() => {
  const hints = result.value?.hints ?? []
  if (!levelFilter.value) return hints
  return hints.filter((h) => h.level === levelFilter.value)
})

async function loadStatus() {
  statusLoading.value = true
  try {
    const s = await fetchYsStatus()
    collisionCount.value = s.collisionCount
  } catch {
    collisionCount.value = 0
  } finally {
    statusLoading.value = false
  }
}

function triggerUpload() {
  fileInputRef.value?.click()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) selectedFile.value = file
  input.value = ''
}

/** 导入市监局许可/备案表（主体碰撞数据） */
async function handleImportCollision() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择要导入的许可/备案表 xlsx 文件')
    return
  }
  const ext = (selectedFile.value.name.split('.').pop() ?? '').toLowerCase()
  if (!['xlsx', 'xls'].includes(ext)) {
    ElMessage.warning('主体碰撞数据需上传 xlsx 格式的许可/备案表')
    return
  }
  statusLoading.value = true
  try {
    const r = await importYsCollision(selectedFile.value)
    collisionCount.value = (await fetchYsStatus()).collisionCount
    ElMessage.success(`已导入 ${r.imported} 条主体数据`)
    selectedFile.value = null
  } catch (err) {
    ElMessage.error('导入失败：' + (err as Error).message)
  } finally {
    statusLoading.value = false
  }
}

/** 筛查 */
async function handleScreen() {
  if (!selectedFile.value && !inputText.value.trim()) {
    ElMessage.warning('请上传字段表/文书，或粘贴文书文本')
    return
  }
  screening.value = true
  try {
    result.value = await screenYs({
      file: selectedFile.value ?? undefined,
      text: inputText.value.trim() || undefined,
    })
    if (!result.value.hintCount) {
      ElMessage.success('筛查完成，未发现明显线索')
    } else {
      ElMessage.success(`筛查完成，命中 ${result.value.hintCount} 条线索`)
    }
  } catch (err) {
    ElMessage.error('筛查失败：' + (err as Error).message)
  } finally {
    screening.value = false
  }
}

function resetInput() {
  selectedFile.value = null
  inputText.value = ''
  result.value = null
}

function fmtLevel(level: string) {
  return level === '明显异常' ? 'danger' : 'warning'
}

/** 导出 CSV（UTF-8 BOM，Excel 可打开） */
function exportCsv() {
  const hints = filteredHints.value
  if (!hints.length) return
  const head = ['等级', '文号', '当事人', '统一社会信用代码', '检索来源池', '主处罚条款', '罚款(万元)', '货值(元)', '命中规则']
  const esc = (v: string) => '"' + String(v ?? '').replace(/"/g, '""') + '"'
  const lines = [head.join(',')]
  for (const h of hints) {
    const rules = h.rules.map((r) => `${r.code}${r.name}`).join('；')
    lines.push([
      h.level, h.doc_no, h.party, h.credit_code, h.source_pool,
      h.main_article, h.fine, h.goods_value, rules,
    ].map(esc).join(','))
  }
  const csv = '\uFEFF' + lines.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `检护营商筛查线索-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(link.href)
}

onMounted(loadStatus)
</script>

<template>
  <div class="ys-view">
    <!-- 顶部 -->
    <header class="ys-header">
      <el-button text :icon="Back" @click="router.push('/agents')">返回广场</el-button>
      <div class="ys-title">
        <h2>检护营商智能体</h2>
        <p class="ys-sub">食品安全领域行政处罚监督线索筛查：批量识别同案不同罚、罚重罚轻、用错法律等疑点</p>
      </div>
      <div class="ys-status" :class="{ ok: collisionCount > 0 }">
        <el-icon :size="14">
          <CircleCheck v-if="collisionCount > 0" />
          <Warning v-else />
        </el-icon>
        <span v-if="statusLoading">检测中…</span>
        <span v-else>{{ collisionCount > 0 ? `主体碰撞数据 ${collisionCount} 条` : '尚未导入主体碰撞数据' }}</span>
      </div>
      <el-button :loading="statusLoading" :icon="Upload" @click="handleImportCollision">导入主体数据</el-button>
    </header>

    <!-- 主体 -->
    <div class="ys-body">
      <!-- 输入区 -->
      <section class="ys-input">
        <input
          ref="fileInputRef"
          type="file"
          accept=".xlsx,.xls,.doc,.docx,.txt,.md,.pdf"
          style="display: none"
          @change="onFileChange"
        />

        <div
          class="drop-zone"
          @click="triggerUpload"
        >
          <div class="drop-icon"><el-icon :size="30"><Upload /></el-icon></div>
          <div class="drop-title">上传字段表或处罚文书</div>
          <div class="drop-tip">
            字段提取表（xlsx）直接筛查；处罚文书（doc/txt/pdf）自动提取字段后筛查
          </div>
          <div v-if="selectedFile" class="selected-file">
            <el-icon :size="14"><DataAnalysis /></el-icon>
            <span class="selected-name">{{ selectedFile.name }}</span>
            <el-icon class="selected-clear" :size="14" @click.stop="selectedFile = null"><Warning /></el-icon>
          </div>
        </div>

        <div class="text-input">
          <textarea
            v-model="inputText"
            class="text-area"
            rows="5"
            placeholder="或在此粘贴行政处罚文书 / 公示信息文本（可含多份文书）"
          ></textarea>
        </div>

        <div class="input-actions">
          <el-button :icon="Refresh" @click="resetInput">重置</el-button>
          <el-button
            type="primary"
            :icon="Search"
            :loading="screening"
            @click="handleScreen"
          >
            {{ screening ? '筛查中…' : '开始筛查' }}
          </el-button>
        </div>
      </section>

      <!-- 结果区 -->
      <section class="ys-result">
        <div class="result-head">
          <span class="result-title">
            <el-icon><DataAnalysis /></el-icon>
            筛查结果
          </span>
          <template v-if="result">
            <span class="result-meta">共 {{ result.total }} 件 · 命中 {{ result.hintCount }} 条线索</span>
            <el-select v-model="levelFilter" clearable placeholder="全部等级" size="small" class="level-filter">
              <el-option label="明显异常" value="明显异常" />
              <el-option label="疑点线索" value="疑点线索" />
            </el-select>
            <el-button size="small" :icon="Download" @click="exportCsv">导出 CSV</el-button>
          </template>
        </div>

        <div v-if="!result" class="result-empty">
          <el-icon :size="44"><Search /></el-icon>
          <p>上传或粘贴文书后点击「开始筛查」，线索清单将显示在这里</p>
        </div>

        <el-table v-else :data="filteredHints" class="hint-table" border stripe max-height="100%">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="rule-detail">
                <div v-for="(r, i) in row.rules" :key="i" class="rule-item">
                  <span class="rule-code">{{ r.code }}</span>
                  <span class="rule-name">{{ r.name }}</span>
                  <span class="rule-detail-text">{{ r.detail }}</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="等级" width="100" fixed>
            <template #default="{ row }">
              <el-tag :type="fmtLevel(row.level)" size="small" effect="dark">{{ row.level }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="doc_no" label="文号" width="190" show-overflow-tooltip />
          <el-table-column prop="party" label="当事人" min-width="200" show-overflow-tooltip />
          <el-table-column prop="main_article" label="主处罚条款" width="130" show-overflow-tooltip />
          <el-table-column prop="fine" label="罚款(万)" width="90" />
          <el-table-column prop="goods_value" label="货值(元)" width="100" show-overflow-tooltip />
          <el-table-column label="命中规则" width="110">
            <template #default="{ row }">
              <span class="rule-codes">{{ row.rules.map((r: any) => r.code).join('、') }}</span>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>
  </div>
</template>

<style scoped>
.ys-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 顶部 */
.ys-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 28px 13px;
  background: #fff;
  border-bottom: 1px solid var(--cj-border);
}
.ys-title {
  flex: 1;
}
.ys-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
.ys-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--cj-text-sub);
}
.ys-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  color: #c4762a;
  background: #fdf3e7;
}
.ys-status.ok {
  color: #0f6e56;
  background: #e1f5ee;
}

/* 主体 */
.ys-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 28px;
  overflow: hidden;
}

/* 输入区 */
.ys-input {
  flex-shrink: 0;
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 12px;
  padding: 14px 16px;
}
.drop-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 18px;
  border: 2px dashed var(--cj-border);
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.drop-zone:hover {
  border-color: var(--cj-primary);
  background: var(--cj-hover-bg);
}
.drop-icon {
  width: 52px;
  height: 52px;
  border-radius: 13px;
  background: var(--cj-primary-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.drop-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--cj-text-main);
}
.drop-tip {
  font-size: 12px;
  color: var(--cj-text-sub);
}
.selected-file {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  padding: 4px 10px;
  background: var(--cj-hover-bg);
  border: 1px solid var(--cj-border);
  border-radius: 6px;
  font-size: 12px;
  color: var(--cj-text-main);
  max-width: 90%;
}
.selected-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.selected-clear {
  color: var(--cj-text-sub);
  cursor: pointer;
}
.selected-clear:hover {
  color: #e5484d;
}

.text-input {
  margin-top: 10px;
}
.text-area {
  width: 100%;
  border: 1px solid var(--cj-border);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.7;
  font-family: inherit;
  color: var(--cj-text-main);
  resize: vertical;
  outline: none;
  box-sizing: border-box;
}
.text-area:focus {
  border-color: var(--cj-primary-light);
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 12px;
}

/* 结果区 */
.ys-result {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 12px;
  overflow: hidden;
}
.result-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--cj-border);
}
.result-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
}
.result-meta {
  margin-left: auto;
  font-size: 12px;
  color: var(--cj-text-sub);
}
.level-filter {
  width: 120px;
}
.result-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--cj-text-sub);
}
.result-empty p {
  margin: 0;
  font-size: 13px;
}

.hint-table {
  flex: 1;
  min-height: 0;
}
.rule-codes {
  font-size: 12px;
  color: var(--cj-primary);
}
.rule-detail {
  padding: 6px 12px;
}
.rule-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}
.rule-code {
  flex-shrink: 0;
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--cj-primary);
  color: #fff;
  font-weight: 600;
}
.rule-name {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--cj-text-main);
}
.rule-detail-text {
  color: var(--cj-text-sub);
  line-height: 1.6;
}
</style>
