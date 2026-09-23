<script setup lang="ts">
/**
 * 对话列表栏：新建对话按钮 + 历史对话列表（可折叠）
 */
import { computed, onMounted } from 'vue'
import { Delete, Fold, Expand, Plus } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import { useChatStore } from '@/stores/chat'

const appStore = useAppStore()
const chatStore = useChatStore()

// 首次挂载时加载历史会话列表
onMounted(() => {
  chatStore.loadConversations()
})

/** 时间展示：今天显示时间，否则显示日期 */
function formatTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  const pad = (n: number) => String(n).padStart(2, '0')
  if (sameDay) return `${pad(d.getHours())}:${pad(d.getMinutes())}`
  return `${d.getMonth() + 1}-${pad(d.getDate())}`
}

const list = computed(() => chatStore.conversations)
</script>

<template>
  <aside class="conv-list" :class="{ collapsed: appStore.convCollapsed }">
    <!-- 折叠态：仅显示一列按钮 -->
    <template v-if="appStore.convCollapsed">
      <div class="collapsed-bar">
        <el-tooltip content="展开对话列表" placement="right">
          <div class="collapse-btn" @click="appStore.toggleConvList()">
            <el-icon :size="16"><Expand /></el-icon>
          </div>
        </el-tooltip>
        <el-tooltip content="新建对话" placement="right">
          <div class="collapse-btn" @click="chatStore.newConversation()">
            <el-icon :size="16"><Plus /></el-icon>
          </div>
        </el-tooltip>
      </div>
    </template>

    <!-- 展开态 -->
    <template v-else>
      <div class="conv-header">
        <el-button class="new-chat-btn" @click="chatStore.newConversation()">
          <el-icon style="margin-right: 4px"><Plus /></el-icon>
          新建对话
        </el-button>
        <div class="collapse-btn" title="折叠对话列表" @click="appStore.toggleConvList()">
          <el-icon :size="15"><Fold /></el-icon>
        </div>
      </div>

      <div class="conv-scroll">
        <div v-if="list.length === 0" class="empty-tip">暂无历史对话</div>

        <div
          v-for="conv in list"
          :key="conv.id"
          class="conv-item"
          :class="{ active: conv.id === chatStore.activeConversationId }"
          @click="chatStore.selectConversation(conv.id)"
        >
          <div class="conv-title">{{ conv.title }}</div>
          <div class="conv-meta">
            <span class="conv-time">{{ formatTime(conv.updateTime) }}</span>
            <!-- hover 显示删除按钮 -->
            <span
              class="conv-delete"
              title="删除对话"
              @click.stop="chatStore.removeConversation(conv.id)"
            >
              <el-icon :size="13"><Delete /></el-icon>
            </span>
          </div>
        </div>
      </div>
    </template>
  </aside>
</template>

<style scoped>
.conv-list {
  width: var(--cj-conv-width);
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid var(--cj-border);
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease;
  overflow: hidden;
}

/* 折叠态 */
.conv-list.collapsed {
  width: 44px;
  align-items: center;
  padding-top: 10px;
}
.collapsed-bar {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.collapse-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--cj-text-sub);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.collapse-btn:hover {
  background: var(--cj-hover-bg);
  color: var(--cj-primary);
}

/* 展开态头部 */
.conv-header {
  padding: 12px 10px 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.new-chat-btn {
  flex: 1;
  --el-button-border-color: var(--cj-primary);
  --el-button-text-color: var(--cj-primary);
  --el-button-hover-border-color: var(--cj-primary-light);
  --el-button-hover-bg-color: var(--cj-hover-bg);
  border-radius: 8px;
}

/* 历史对话列表 */
.conv-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px 12px;
}
.empty-tip {
  text-align: center;
  color: var(--cj-text-sub);
  font-size: 12px;
  padding: 24px 0;
}

.conv-item {
  position: relative;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.conv-item:hover {
  background: #f3f6fc;
}

/* 当前对话高亮：左侧蓝色竖条 + 浅蓝背景 */
.conv-item.active {
  background: var(--cj-hover-bg);
}
.conv-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 2px;
  background: var(--cj-primary);
}

.conv-title {
  font-size: 13px;
  color: var(--cj-text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis; /* 标题超出一行省略 */
}

.conv-meta {
  margin-top: 4px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.conv-time {
  font-size: 12px;
  color: var(--cj-text-sub);
}

/* 删除按钮：默认隐藏，hover 时显示 */
.conv-delete {
  color: var(--cj-text-sub);
  opacity: 0;
  border-radius: 4px;
  padding: 2px;
  transition: opacity 0.15s, color 0.15s;
}
.conv-item:hover .conv-delete {
  opacity: 1;
}
.conv-delete:hover {
  color: #e5484d;
}
</style>
