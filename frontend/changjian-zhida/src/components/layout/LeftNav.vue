<script setup lang="ts">
/**
 * 左侧导航栏：蓝色渐变背景
 * 顶部为检察院徽章；中部为功能导航；底部为系统管理（底部对齐）
 */
import { computed, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChatDotRound,
  MagicStick,
  Collection,
  VideoPlay,
  DocumentCopy,
  Setting,
} from '@element-plus/icons-vue'
import type { NavItem } from '@/types'

const router = useRouter()
const route = useRoute()

/** 导航配置：图标 + 文字（12px，垂直排列） */
const navItems = computed<(NavItem & { iconComp: Component })[]>(() => [
  { path: '/chat', title: 'AI对话', icon: 'ChatDotRound', iconComp: ChatDotRound },
  { path: '/agents', title: '智能体', icon: 'MagicStick', iconComp: MagicStick },
  { path: '/knowledge', title: '知识库', icon: 'Collection', iconComp: Collection },
  { path: '/micro-class', title: '微课堂', icon: 'VideoPlay', iconComp: VideoPlay },
  { path: '/ocr', title: 'OCR应用', icon: 'DocumentCopy', iconComp: DocumentCopy },
])

/** 系统管理固定在底部 */
const bottomItem: NavItem & { iconComp: Component } = {
  path: '/system',
  title: '系统管理',
  icon: 'Setting',
  iconComp: Setting,
}

/** 高亮判断：精确匹配，或子路由（如 /agents/yingshang 归属 /agents） */
const isActive = (path: string) => route.path === path || route.path.startsWith(path + '/')

function navigate(item: NavItem) {
  if (!isActive(item.path)) router.push(item.path)
}
</script>

<template>
  <aside class="left-nav">
    <!-- 顶部：检察院徽章 -->
    <div class="nav-emblem" title="昌检智答">
      <svg viewBox="0 0 32 32" width="34" height="34">
        <circle cx="16" cy="16" r="15" fill="none" stroke="#ffffff" stroke-width="1.2" opacity="0.9" />
        <path
          d="M16 5l8.5 3.2v7.3c0 5.2-3.6 9.5-8.5 11.5-4.9-2-8.5-6.3-8.5-11.5V8.2L16 5z"
          fill="rgba(255,255,255,0.12)"
          stroke="#ffffff"
          stroke-width="1.3"
        />
        <path
          d="M12 16.5l2.8 2.8 5.2-5.8"
          fill="none"
          stroke="#ffffff"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <span class="emblem-name">昌检智答</span>
    </div>

    <!-- 中部：主导航 -->
    <nav class="nav-menu">
      <div
        v-for="item in navItems"
        :key="item.path"
        class="nav-item"
        :class="{ active: isActive(item.path) }"
        @click="navigate(item)"
      >
        <el-icon :size="20"><component :is="item.iconComp" /></el-icon>
        <span class="nav-label">{{ item.title }}</span>
      </div>
    </nav>

    <!-- 底部：系统管理 -->
    <div class="nav-bottom">
      <div
        class="nav-item"
        :class="{ active: isActive(bottomItem.path) }"
        @click="navigate(bottomItem)"
      >
        <el-icon :size="20"><component :is="bottomItem.iconComp" /></el-icon>
        <span class="nav-label">{{ bottomItem.title }}</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.left-nav {
  width: var(--cj-nav-width);
  flex-shrink: 0;
  /* 静态渐变：深蓝 → 政务蓝 → 天青（自上而下） */
  background: linear-gradient(
    180deg,
    #1a3f8f 0%,
    #1e4fa3 50%,
    #4facf7 100%
  );
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 14px 0 16px;
  user-select: none;
}

/* 徽章 */
.nav-emblem {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin-bottom: 22px;
}
.emblem-name {
  font-size: 12px;
  letter-spacing: 2px;
  color: rgba(255, 255, 255, 0.85);
}

/* 导航菜单 */
.nav-menu {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  align-items: center;
}

.nav-bottom {
  width: 100%;
  display: flex;
  justify-content: center;
}

/* 单个导航项：图标在上、文字在下 */
.nav-item {
  width: 64px;
  padding: 9px 0 7px;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  color: rgba(255, 255, 255, 0.72);
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.nav-item:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.12);
}

/* 选中态：白色背景圆角高亮 */
.nav-item.active {
  background: #ffffff;
  color: var(--cj-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
}

.nav-label {
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
}
</style>
