<script setup lang="ts">
/**
 * 主布局：三栏结构
 * 左侧导航（固定宽度） + 对话列表栏（可折叠，仅 AI 对话页显示） + 主内容区
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import LeftNav from '@/components/layout/LeftNav.vue'
import ConversationList from '@/components/layout/ConversationList.vue'

const appStore = useAppStore()
const route = useRoute()

/** 仅在 AI 对话页显示中间的对话列表栏 */
const showConvList = computed(() => route.name === 'Chat')
</script>

<template>
  <div class="main-layout">
    <!-- 第一栏：左侧导航 -->
    <LeftNav />

    <!-- 第二栏：对话列表（可折叠，仅对话页显示） -->
    <ConversationList v-if="showConvList" />

    <!-- 第三栏：主内容区（路由出口） -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.main-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

.main-content {
  flex: 1;
  min-width: 0; /* 允许内容区收缩 */
  display: flex;
  flex-direction: column;
  background: var(--cj-bg);
  overflow: hidden;
}
</style>
