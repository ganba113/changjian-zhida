<script setup lang="ts">
/**
 * OCR 应用模块：卷宗文书、证据材料扫描件的文字识别
 * 流程：选择图片 → 预览 → 识别 → 展示文本（可复制）
 */
import { onMounted, ref, onBeforeUnmount } from 'vue'
import { Upload, Picture, CopyDocument, Refresh, CircleCheck, Warning, Document } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { fetchOcrStatus, recognizeOcr } from '@/api/chat'
import { copyText } from '@/utils/clipboard'
import type { OcrStatus, OcrResult } from '@/types'

const engineStatus = ref<OcrStatus | null>(null)
const statusLoading = ref(false)

const selectedFile = ref<File | null>(null)
const previewUrl = ref('')
const isPdf = ref(false)
const dragging = ref(false)
const recognizing = ref(false)
const result = ref<OcrResult | null>(null)

const fileInputRef = ref<HTMLInputElement | null>(null)

/** 图片格式校验（与后端 IMAGE_EXTS 对齐，另支持 PDF） */
const IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tif', 'tiff']

function extOf(name: string): string {
  return name.toLowerCase().split('.').pop() ?? ''
}

async function loadStatus() {
  statusLoading.value = true
  try {
    engineStatus.value = await fetchOcrStatus()
  } catch {
    engineStatus.value = { available: false, engine: null }
  } finally {
    statusLoading.value = false
  }
}

function clearPreview() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

function handleSelectFile(file: File) {
  const ext = extOf(file.name)
  const isPdfFile = ext === 'pdf'
  if (!IMAGE_EXTS.includes(ext) && !isPdfFile) {
    ElMessage.warning('请上传图片（png/jpg/jpeg/bmp/webp/tif 等）或 PDF 文件')
    return
  }
  clearPreview()
  selectedFile.value = file
  isPdf.value = isPdfFile
  // 图片生成预览 URL；PDF 无法用 img 预览，改用图标占位
  previewUrl.value = isPdfFile ? '' : URL.createObjectURL(file)
  result.value = null
}

function triggerUpload() {
  fileInputRef.value?.click()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) handleSelectFile(file)
  input.value = ''
}

function onDrop(e: DragEvent) {
  dragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) handleSelectFile(file)
}

async function handleRecognize() {
  if (!selectedFile.value || recognizing.value) return
  recognizing.value = true
  try {
    result.value = await recognizeOcr(selectedFile.value)
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    recognizing.value = false
  }
}

async function handleCopy() {
  if (!result.value?.text) return
  const ok = await copyText(result.value.text)
  if (ok) ElMessage.success('已复制识别文本')
  else ElMessage.error('复制失败，请手动选择复制')
}

function reset() {
  clearPreview()
  selectedFile.value = null
  isPdf.value = false
  result.value = null
}

function fmtChars(n: number): string {
  return n + ' 字'
}

function engineLabel(): string {
  if (!engineStatus.value?.available) return '引擎未部署'
  const m: Record<string, string> = {
    rapidocr: 'RapidOCR',
    paddleocr: 'PaddleOCR',
    tesseract: 'Tesseract',
  }
  return m[engineStatus.value.engine ?? ''] ?? engineStatus.value.engine ?? '未知引擎'
}

onMounted(loadStatus)
onBeforeUnmount(clearPreview)
</script>

<template>
  <div class="ocr-view">
    <!-- 顶部 -->
    <header class="ocr-header">
      <div class="ocr-title">
        <h2>OCR 应用</h2>
        <p class="ocr-sub">上传卷宗、文书、证据材料扫描件，智能提取图片与 PDF 中的文字</p>
      </div>
      <div class="ocr-status" :class="{ ok: engineStatus?.available }">
        <el-icon :size="14">
          <CircleCheck v-if="engineStatus?.available" />
          <Warning v-else />
        </el-icon>
        <span v-if="statusLoading">检测中…</span>
        <span v-else>{{ engineLabel() }}</span>
      </div>
    </header>

    <!-- 主体：左上传 + 右结果 -->
    <div class="ocr-body">
      <!-- 左：上传与预览 -->
      <section class="upload-panel">
        <input
          ref="fileInputRef"
          type="file"
          accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.tif,.tiff,.pdf"
          style="display: none"
          @change="onFileChange"
        />

        <div
          v-if="!selectedFile"
          class="drop-zone"
          :class="{ dragging }"
          @click="triggerUpload"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <div class="drop-icon"><el-icon :size="34"><Upload /></el-icon></div>
          <div class="drop-title">点击或拖拽图片 / PDF 到此处</div>
          <div class="drop-tip">支持 png / jpg / jpeg / bmp / webp / tif / pdf，单文件不超过 20MB</div>
        </div>

        <div v-else class="preview-wrap">
          <div class="preview-head">
            <span class="preview-name" :title="selectedFile?.name">{{ selectedFile?.name }}</span>
            <el-button size="small" text :icon="Refresh" @click="reset">更换文件</el-button>
          </div>
          <div class="preview-box">
            <div v-if="isPdf" class="pdf-placeholder">
              <el-icon :size="56"><Document /></el-icon>
              <span class="pdf-name">{{ selectedFile?.name }}</span>
              <span class="pdf-hint">PDF 优先提取文字层，扫描件自动逐页 OCR</span>
            </div>
            <img v-else :src="previewUrl" alt="预览" />
          </div>
          <div class="preview-actions">
            <el-button
              type="primary"
              :loading="recognizing"
              :disabled="!engineStatus?.available"
              :icon="Picture"
              @click="handleRecognize"
            >
              {{ recognizing ? '识别中…' : '开始识别' }}
            </el-button>
            <span v-if="!engineStatus?.available" class="no-engine-tip">
              服务器未部署 OCR 引擎，请联系管理员
            </span>
          </div>
        </div>
      </section>

      <!-- 右：识别结果 -->
      <section class="result-panel">
        <div class="result-head">
          <span class="result-title">识别结果</span>
          <template v-if="result">
            <span class="result-meta">
              {{ fmtChars(result.chars) }} · {{ engineLabel() }}
            </span>
            <el-button size="small" :icon="CopyDocument" @click="handleCopy">复制</el-button>
          </template>
        </div>

        <div v-if="!result" class="result-empty">
          <el-icon :size="44"><Picture /></el-icon>
          <p>上传图片并开始识别后，提取的文字将显示在这里</p>
        </div>
        <pre v-else class="result-content">{{ result.text }}</pre>
      </section>
    </div>
  </div>
</template>

<style scoped>
.ocr-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 顶部 */
.ocr-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 28px 13px;
  background: #fff;
  border-bottom: 1px solid var(--cj-border);
}
.ocr-title {
  flex: 1;
}
.ocr-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
.ocr-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--cj-text-sub);
}
.ocr-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  color: #c4762a;
  background: #fdf3e7;
}
.ocr-status.ok {
  color: #0f6e56;
  background: #e1f5ee;
}

/* 主体 */
.ocr-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
  padding: 16px 28px;
}

.upload-panel {
  width: 380px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}

/* 拖拽上传区 */
.drop-zone {
  flex: 1;
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: #fff;
  border: 2px dashed var(--cj-border);
  border-radius: 14px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.drop-zone:hover,
.drop-zone.dragging {
  border-color: var(--cj-primary);
  background: var(--cj-hover-bg);
}
.drop-icon {
  width: 64px;
  height: 64px;
  border-radius: 16px;
  background: var(--cj-primary-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 6px 16px rgba(30, 79, 163, 0.28);
}
.drop-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cj-text-main);
}
.drop-tip {
  font-size: 12px;
  color: var(--cj-text-sub);
}

/* 预览区 */
.preview-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 14px;
  overflow: hidden;
}
.preview-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--cj-border);
}
.preview-name {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-box {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--cj-bg);
  padding: 12px;
}
.preview-box img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 6px;
}
.pdf-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: var(--cj-primary);
}
.pdf-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--cj-text-main);
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pdf-hint {
  font-size: 12px;
  color: var(--cj-text-sub);
}
.preview-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-top: 1px solid var(--cj-border);
}
.no-engine-tip {
  font-size: 12px;
  color: #c4762a;
}

/* 结果面板 */
.result-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 14px;
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
  font-size: 14px;
  font-weight: 600;
}
.result-meta {
  margin-left: auto;
  font-size: 12px;
  color: var(--cj-text-sub);
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
.result-content {
  flex: 1;
  min-height: 0;
  margin: 0;
  overflow-y: auto;
  padding: 16px 18px;
  font-size: 14px;
  line-height: 1.9;
  font-family: 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
  color: var(--cj-text-main);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
