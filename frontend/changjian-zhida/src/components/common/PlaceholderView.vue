<script setup lang="ts">
/**
 * 通用模块占位页
 * 其他模块（智能体/知识库/微课堂/OCR/系统管理）暂未开发，
 * 统一使用该组件做页面占位与基础结构
 */
import { computed, markRaw, type Component } from 'vue'
import { useRoute } from 'vue-router'
import {
  MagicStick,
  Collection,
  VideoPlay,
  DocumentCopy,
  Setting,
} from '@element-plus/icons-vue'

const props = defineProps<{
  /** 模块标题 */
  title: string
  /** 功能描述 */
  description?: string
}>()

const route = useRoute()

const iconMap: Record<string, Component> = {
  MagicStick: markRaw(MagicStick),
  Collection: markRaw(Collection),
  VideoPlay: markRaw(VideoPlay),
  DocumentCopy: markRaw(DocumentCopy),
  Setting: markRaw(Setting),
}

const iconName = computed(() => {
  const map: Record<string, string> = {
    Agents: 'MagicStick',
    Knowledge: 'Collection',
    MicroClass: 'VideoPlay',
    Ocr: 'DocumentCopy',
    System: 'Setting',
  }
  return map[String(route.name)] ?? 'MagicStick'
})
</script>

<template>
  <div class="placeholder cj-fade-in">
    <div class="placeholder-card">
      <div class="placeholder-icon">
        <el-icon :size="34" color="#fff"><component :is="iconMap[iconName]" /></el-icon>
      </div>
      <h2 class="placeholder-title">{{ props.title }}</h2>
      <p class="placeholder-desc">
        {{ props.description ?? '该模块正在建设中，敬请期待' }}
      </p>
      <el-tag size="small" effect="plain" round>开发中</el-tag>
    </div>
  </div>
</template>

<style scoped>
.placeholder {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.placeholder-card {
  text-align: center;
  padding: 48px 64px;
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 16px;
  box-shadow: 0 6px 24px rgba(31, 45, 61, 0.06);
}

.placeholder-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 18px;
  border-radius: 16px;
  background: var(--cj-primary-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 20px rgba(30, 79, 163, 0.3);
}

.placeholder-title {
  margin: 0 0 10px;
  font-size: 20px;
  font-weight: 600;
}

.placeholder-desc {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--cj-text-sub);
  max-width: 320px;
  line-height: 1.8;
}
</style>
