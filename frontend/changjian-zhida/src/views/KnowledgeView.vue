<script setup lang="ts">
/**
 * 知识库模块：按部门分库管理文档
 * 一级：知识库卡片网格（12 个部门库 + 新建/删除）
 * 二级：库详情（文档上传/列表/删除 + 关键词检索，无问答）
 */
import { onMounted, ref } from 'vue'
import {
  Plus,
  Upload,
  Search,
  Document,
  Delete,
  Folder,
  ArrowLeft,
  Collection,
  CopyDocument,
  Refresh,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  fetchKbLibraries,
  createKbLibrary,
  removeKbLibrary,
  uploadKbDocument,
  fetchKbDocuments,
  fetchKbDocument,
  removeKbDocument,
  searchKb,
  reindexKb,
} from '@/api/chat'
import { copyText } from '@/utils/clipboard'
import type { KbLibrary, KbDocument, KbDocumentDetail, KbSearchResult } from '@/types'

const libraries = ref<KbLibrary[]>([])
const libsLoading = ref(false)
const reindexing = ref(false)

/** 当前视图：list=库列表，detail=库详情 */
const view = ref<'list' | 'detail'>('list')
const currentLibrary = ref<KbLibrary | null>(null)

// 库详情：文档 + 检索
const docs = ref<KbDocument[]>([])
const docsLoading = ref(false)
const query = ref('')
const results = ref<KbSearchResult[]>([])
const searching = ref(false)
const hasSearched = ref(false)

const fileInputRef = ref<HTMLInputElement | null>(null)

// 文档查看（点击弹窗展示原文）
const docDetail = ref<KbDocumentDetail | null>(null)
const docDialogVisible = ref(false)
const docLoading = ref(false)

/** 加载库列表 */
async function loadLibraries() {
  libsLoading.value = true
  try {
    libraries.value = await fetchKbLibraries()
  } catch (e) {
    ElMessage.error('加载知识库失败：' + (e as Error).message)
  } finally {
    libsLoading.value = false
  }
}

/** 重建向量索引（给旧文档补向量，需管理员密码） */
async function handleReindex() {
  try {
    await ElMessageBox.confirm(
      '将为所有缺少向量的文档分块重新生成向量索引，以便旧文档也能参与语义检索。此操作可能需要一些时间，是否继续？',
      '重建向量索引',
      { confirmButtonText: '下一步', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  // 输入管理员密码
  let password = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入管理员密码', '身份验证', {
      confirmButtonText: '开始重建',
      cancelButtonText: '取消',
      inputType: 'password',
      inputValidator: (v: string) => (v && v.trim() ? true : '密码不能为空'),
    })
    password = value
  } catch {
    return
  }
  reindexing.value = true
  try {
    const r = await reindexKb(password)
    if (r.total === 0) {
      ElMessage.success('所有文档已是最新索引，无需重建')
    } else if (r.failed === 0) {
      ElMessage.success(`重建完成：成功 ${r.indexed} 块`)
    } else {
      ElMessage.warning(`重建完成：成功 ${r.indexed} 块，失败 ${r.failed} 块`)
    }
  } catch (e) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '重建索引失败')
  } finally {
    reindexing.value = false
  }
}

/** 新建知识库 */
async function handleCreate() {
  try {
    const { value } = await ElMessageBox.prompt('请输入知识库名称', '新建知识库', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputValidator: (v: string) => (v && v.trim() ? true : '名称不能为空'),
    })
    const lib = await createKbLibrary(value.trim())
    libraries.value.push(lib)
    ElMessage.success('已创建「' + lib.name + '」')
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '创建失败')
  }
}

/** 删除知识库（需管理员密码确认） */
async function handleDeleteLibrary(lib: KbLibrary) {
  try {
    await ElMessageBox.confirm(
      `确定删除知识库「${lib.name}」吗？库内 ${lib.docCount} 篇文档将被一并删除，且不可恢复。`,
      '删除知识库',
      { confirmButtonText: '下一步', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  // 输入管理员密码
  let password = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入管理员密码', '身份验证', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      inputType: 'password',
      inputValidator: (v: string) => (v && v.trim() ? true : '密码不能为空'),
    })
    password = value
  } catch {
    return
  }
  try {
    await removeKbLibrary(lib.id, password)
    libraries.value = libraries.value.filter((l) => l.id !== lib.id)
    ElMessage.success('已删除')
  } catch (e) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '删除失败')
  }
}

/** 进入库详情 */
async function enterLibrary(lib: KbLibrary) {
  currentLibrary.value = lib
  view.value = 'detail'
  query.value = ''
  results.value = []
  hasSearched.value = false
  await loadDocs(lib.id)
}

/** 返回列表 */
function backToList() {
  view.value = 'list'
  currentLibrary.value = null
}

/** 加载库内文档 */
async function loadDocs(libraryId: string) {
  docsLoading.value = true
  try {
    docs.value = await fetchKbDocuments(libraryId)
  } catch (e) {
    ElMessage.error('加载文档失败：' + (e as Error).message)
  } finally {
    docsLoading.value = false
  }
}

/** 上传文档到当前库 */
function triggerUpload() {
  fileInputRef.value?.click()
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || !files.length || !currentLibrary.value) return
  try {
    for (const f of Array.from(files)) {
      await uploadKbDocument(currentLibrary.value.id, f)
    }
    ElMessage.success(`已导入 ${files.length} 个文档`)
    await loadDocs(currentLibrary.value.id)
    // 同步库列表文档数
    await loadLibraries()
  } catch (err) {
    ElMessage.error('导入失败：' + (err as Error).message)
  } finally {
    input.value = ''
  }
}

/** 删除文档 */
async function handleDeleteDocument(doc: KbDocument) {
  try {
    await removeKbDocument(doc.id)
    docs.value = docs.value.filter((d) => d.id !== doc.id)
    ElMessage.success('已删除')
    await loadLibraries()
  } catch (e) {
    ElMessage.error('删除失败：' + (e as Error).message)
  }
}

/** 点击文档查看原文 */
async function viewDocument(doc: KbDocument) {
  docDialogVisible.value = true
  docLoading.value = true
  docDetail.value = null
  try {
    docDetail.value = await fetchKbDocument(doc.id)
  } catch (e) {
    ElMessage.error('加载文档内容失败：' + (e as Error).message)
    docDialogVisible.value = false
  } finally {
    docLoading.value = false
  }
}

/** 复制文档原文 */
async function copyContent() {
  if (!docDetail.value) return
  const ok = await copyText(docDetail.value.content)
  if (ok) ElMessage.success('已复制全文')
  else ElMessage.error('复制失败，请手动选择复制')
}

/** 检索当前库 */
async function handleSearch() {
  const q = query.value.trim()
  if (!q || !currentLibrary.value) return
  searching.value = true
  hasSearched.value = true
  try {
    results.value = await searchKb(q, currentLibrary.value.id)
    if (!results.value.length) {
      ElMessage.info('该知识库中未检索到相关内容')
    }
  } catch (e) {
    ElMessage.error('检索失败：' + (e as Error).message)
  } finally {
    searching.value = false
  }
}

function handleSearchKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    handleSearch()
  }
}

function fmtChars(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + ' 万字'
  return n + ' 字'
}

onMounted(loadLibraries)
</script>

<template>
  <div class="kb-view">
    <!-- ============ 一级：知识库列表 ============ -->
    <template v-if="view === 'list'">
      <header class="kb-header">
        <div class="kb-title">
          <h2>知识库</h2>
          <p class="kb-sub">按部门分类管理知识库，导入法律法规、司法解释、典型案例与内部规范</p>
        </div>
        <el-button :icon="Refresh" :loading="reindexing" @click="handleReindex">重建索引</el-button>
        <el-button type="primary" :icon="Plus" @click="handleCreate">新建知识库</el-button>
      </header>

      <div v-loading="libsLoading" class="lib-grid">
        <div v-for="lib in libraries" :key="lib.id" class="lib-card" @click="enterLibrary(lib)">
          <div class="lib-card-head">
            <span class="lib-icon"><el-icon :size="22"><Folder /></el-icon></span>
            <el-icon
              class="lib-del"
              :size="16"
              @click.stop="handleDeleteLibrary(lib)"
            >
              <Delete />
            </el-icon>
          </div>
          <div class="lib-name">{{ lib.name }}</div>
          <div class="lib-count">{{ lib.docCount }} 篇文档</div>
        </div>

        <div v-if="!libsLoading && !libraries.length" class="lib-empty">
          <el-empty description="暂无知识库，点击右上角新建" :image-size="100" />
        </div>
      </div>
    </template>

    <!-- ============ 二级：库详情 ============ -->
    <template v-else>
      <header class="kb-header">
        <el-button text :icon="ArrowLeft" @click="backToList">返回</el-button>
        <div class="kb-title">
          <h2>{{ currentLibrary?.name }}</h2>
          <p class="kb-sub">管理该知识库内的文档，支持关键词检索</p>
        </div>
        <el-button type="primary" :icon="Upload" @click="triggerUpload">上传文档</el-button>
        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept=".txt,.md,.csv,.json,.pdf,.docx,.doc,.wps,.xlsx,.xls,.html,.log"
          style="display: none"
          @change="onFileChange"
        />
      </header>

      <div class="kb-detail-body">
        <!-- 左：文档列表 -->
        <aside class="docs-panel">
          <div class="panel-head">
            <span class="panel-title">
              <el-icon><Collection /></el-icon>
              文档列表
            </span>
            <span class="panel-count">{{ docs.length }} 篇</span>
          </div>
          <div v-loading="docsLoading" class="docs-list">
            <el-empty
              v-if="!docsLoading && !docs.length"
              description="暂无文档，点击右上角上传"
              :image-size="72"
            />
            <div
              v-for="doc in docs"
              :key="doc.id"
              class="doc-item"
              title="点击查看内容"
              @click="viewDocument(doc)"
            >
              <el-icon class="doc-icon"><Document /></el-icon>
              <div class="doc-meta">
                <div class="doc-name" :title="doc.filename">{{ doc.filename }}</div>
                <div class="doc-sub">{{ fmtChars(doc.charCount) }} · {{ doc.chunkCount }} 块</div>
              </div>
              <el-tooltip content="删除" placement="top">
                <el-icon class="doc-del" :size="15" @click.stop="handleDeleteDocument(doc)">
                  <Delete />
                </el-icon>
              </el-tooltip>
            </div>
          </div>
        </aside>

        <!-- 右：检索 -->
        <section class="search-panel">
          <div class="search-box">
            <textarea
              v-model="query"
              rows="2"
              class="search-textarea"
              placeholder="输入关键词检索该知识库，Enter 检索"
              @keydown="handleSearchKeydown"
            ></textarea>
            <div class="search-actions">
              <el-button
                type="primary"
                :loading="searching"
                :disabled="!query.trim()"
                :icon="Search"
                @click="handleSearch"
              >
                检索
              </el-button>
            </div>
          </div>

          <div v-if="!hasSearched" class="search-empty">
            <el-empty description="输入关键词，检索知识库内容" :image-size="110" />
          </div>
          <div v-else class="search-results">
            <div v-if="results.length" class="refs-head">命中片段（{{ results.length }}）</div>
            <div v-for="(r, i) in results" :key="i" class="ref-item">
              <div class="ref-meta">
                <span class="ref-idx">#{{ i + 1 }}</span>
                <span class="ref-src">{{ r.filename }}</span>
                <span class="ref-score">相关度 {{ r.score }}</span>
              </div>
              <p class="ref-content">{{ r.content }}</p>
            </div>
            <div v-if="!results.length" class="ref-none">
              <el-icon><Search /></el-icon>
              该知识库中未检索到相关内容，可更换关键词
            </div>
          </div>
        </section>
      </div>

      <!-- 查看文档原文弹窗 -->
      <el-dialog
        v-model="docDialogVisible"
        :title="docDetail?.filename || '文档内容'"
        width="720px"
        top="6vh"
        destroy-on-close
      >
        <div v-loading="docLoading" class="doc-detail-wrap">
          <div v-if="docDetail" class="doc-detail-meta">
            共 {{ fmtChars(docDetail.charCount) }} · {{ docDetail.chunkCount }} 个分块
          </div>
          <pre class="doc-detail-content">{{ docDetail?.content || '' }}</pre>
        </div>
        <template #footer>
          <el-button :disabled="!docDetail" :icon="CopyDocument" @click="copyContent">
            复制全文
          </el-button>
          <el-button type="primary" @click="docDialogVisible = false">关闭</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<style scoped>
.kb-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 顶部 */
.kb-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 28px 13px;
  background: #fff;
  border-bottom: 1px solid var(--cj-border);
}
.kb-title {
  flex: 1;
}
.kb-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
.kb-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--cj-text-sub);
}

/* 库卡片网格 */
.lib-grid {
  flex: 1;
  overflow-y: auto;
  padding: 22px 28px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  align-content: start;
}
.lib-card {
  position: relative;
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 12px;
  padding: 18px 16px 16px;
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s, transform 0.2s;
}
.lib-card:hover {
  border-color: var(--cj-primary-light);
  box-shadow: 0 8px 24px rgba(30, 79, 163, 0.12);
  transform: translateY(-2px);
}
.lib-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.lib-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--cj-primary-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 6px 14px rgba(30, 79, 163, 0.28);
}
.lib-del {
  color: #c0c8d6;
  padding: 2px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
}
.lib-card:hover .lib-del {
  opacity: 1;
}
.lib-del:hover {
  color: #e5484d;
}
.lib-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--cj-text-main);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lib-count {
  margin-top: 6px;
  font-size: 12px;
  color: var(--cj-text-sub);
}
.lib-empty {
  grid-column: 1 / -1;
}

/* 库详情 */
.kb-detail-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
  padding: 16px 28px;
}

.docs-panel {
  width: 340px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 12px;
  overflow: hidden;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--cj-border);
}
.panel-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
}
.panel-count {
  font-size: 12px;
  color: var(--cj-text-sub);
}
.docs-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.doc-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.doc-item:hover {
  background: var(--cj-hover-bg);
}
.doc-icon {
  font-size: 18px;
  color: var(--cj-primary);
  flex-shrink: 0;
}
.doc-meta {
  flex: 1;
  min-width: 0;
}
.doc-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--cj-text-sub);
}
.doc-del {
  color: var(--cj-text-sub);
  cursor: pointer;
  flex-shrink: 0;
}
.doc-del:hover {
  color: #e5484d;
}

/* 检索面板 */
.search-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.search-box {
  flex-shrink: 0;
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 2px 10px rgba(31, 45, 61, 0.04);
}
.search-textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  line-height: 1.7;
  font-family: inherit;
  color: var(--cj-text-main);
  background: transparent;
  min-height: 52px;
}
.search-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
.search-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.search-results {
  flex: 1;
  overflow-y: auto;
  margin-top: 14px;
}
.refs-head {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}
.ref-item {
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 8px;
}
.ref-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.ref-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 5px;
  background: var(--cj-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}
.ref-src {
  font-size: 12px;
  color: var(--cj-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
}
.ref-score {
  margin-left: auto;
  font-size: 11px;
  color: var(--cj-text-sub);
}
.ref-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: #37475a;
  white-space: pre-wrap;
  word-break: break-word;
}
.ref-none {
  padding: 24px;
  text-align: center;
  color: var(--cj-text-sub);
  font-size: 13px;
  background: #fff;
  border: 1px dashed var(--cj-border);
  border-radius: 10px;
}

/* 文档查看弹窗 */
.doc-detail-wrap {
  min-height: 200px;
}
.doc-detail-meta {
  font-size: 12px;
  color: var(--cj-text-sub);
  margin-bottom: 10px;
}
.doc-detail-content {
  margin: 0;
  max-height: 60vh;
  overflow-y: auto;
  background: var(--cj-bg);
  border: 1px solid var(--cj-border);
  border-radius: 8px;
  padding: 14px 16px;
  font-size: 13px;
  line-height: 1.9;
  font-family: 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
  color: var(--cj-text-main);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
