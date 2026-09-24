<script setup lang="ts">
/**
 * 智能体广场 —— 展示所有可用智能体，点击进入对应智能体
 * 当前已接入：检护营商智能体；后续新增智能体只需往 AGENT_LIST 里添加
 */
import { computed, markRaw, type Component } from 'vue'
import { useRouter } from 'vue-router'
import {
  OfficeBuilding,
  Right,
  MagicStick,
} from '@element-plus/icons-vue'

const router = useRouter()

/** 智能体广场配置（后续可改为后端下发） */
interface PlazaAgent {
  /** 唯一标识（路由 path 用） */
  id: string
  name: string
  /** 一句话定位 */
  tagline: string
  /** 详细描述 */
  description: string
  /** 能力标签 */
  tags: string[]
  icon: Component
  color: string
  /** 跳转路由 */
  route: string
  /** 是否可用（开发中则为 false，卡片置灰） */
  enabled: boolean
}

const AGENT_LIST: PlazaAgent[] = [
  {
    id: 'yingshang',
    name: '检护营商智能体',
    tagline: '食品安全领域行政处罚监督线索筛查',
    description:
      '面向昌平区检察院的检察监督场景，批量识别行政处罚案件中的同案不同罚、罚重罚轻、用错法律等疑点，输出「明显异常 / 疑点线索」两档清单，辅助发现监督线索。',
    tags: ['行政处罚监督', '食品安全', '线索筛查'],
    icon: markRaw(OfficeBuilding),
    color: '#1e4fa3',
    route: '/agents/yingshang',
    enabled: true,
  },
]

const enabledAgents = computed(() => AGENT_LIST.filter((a) => a.enabled))

function enter(agent: PlazaAgent) {
  if (!agent.enabled) return
  router.push(agent.route)
}
</script>

<template>
  <div class="plaza cj-fade-in">
    <!-- 顶部标题 -->
    <header class="plaza-header">
      <div class="plaza-title">
        <h2>智能体广场</h2>
        <p class="plaza-sub">选择智能体，进入对应的检察业务智能辅助工具</p>
      </div>
      <el-tag size="small" effect="plain" round>{{ enabledAgents.length }} 个智能体已上线</el-tag>
    </header>

    <!-- 卡片网格 -->
    <div class="plaza-grid">
      <div
        v-for="agent in AGENT_LIST"
        :key="agent.id"
        class="agent-card"
        :class="{ disabled: !agent.enabled }"
        @click="enter(agent)"
      >
        <div class="card-icon" :style="{ background: agent.color }">
          <el-icon :size="26" color="#fff"><component :is="agent.icon" /></el-icon>
        </div>

        <div class="card-body">
          <div class="card-name-row">
            <span class="card-name">{{ agent.name }}</span>
            <el-tag v-if="!agent.enabled" size="small" type="info" effect="plain">开发中</el-tag>
          </div>
          <div class="card-tagline">{{ agent.tagline }}</div>
          <p class="card-desc">{{ agent.description }}</p>

          <div class="card-tags">
            <span v-for="t in agent.tags" :key="t" class="tag">{{ t }}</span>
          </div>
        </div>

        <div class="card-enter">
          <span class="enter-text">{{ agent.enabled ? '进入' : '敬请期待' }}</span>
          <el-icon :size="14"><Right /></el-icon>
        </div>
      </div>
    </div>

    <!-- 空态（后续全下线时兜底） -->
    <div v-if="!AGENT_LIST.length" class="plaza-empty">
      <el-icon :size="48"><MagicStick /></el-icon>
      <p>智能体正在建设中，敬请期待</p>
    </div>
  </div>
</template>

<style scoped>
.plaza {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.plaza-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 28px 14px;
  background: #fff;
  border-bottom: 1px solid var(--cj-border);
}
.plaza-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
.plaza-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--cj-text-sub);
}

.plaza-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 18px;
  padding: 20px 28px;
  align-content: start;
}

.agent-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px;
  background: #fff;
  border: 1px solid var(--cj-border);
  border-radius: 14px;
  cursor: pointer;
  transition: transform 0.18s, box-shadow 0.18s, border-color 0.18s;
}
.agent-card:hover {
  transform: translateY(-3px);
  border-color: var(--cj-primary-light);
  box-shadow: 0 10px 28px rgba(30, 79, 163, 0.12);
}
.agent-card.disabled {
  cursor: not-allowed;
  opacity: 0.62;
}
.agent-card.disabled:hover {
  transform: none;
  border-color: var(--cj-border);
  box-shadow: none;
}

.card-icon {
  width: 54px;
  height: 54px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 6px 16px rgba(30, 79, 163, 0.24);
}

.card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.card-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--cj-text-main);
}
.card-tagline {
  font-size: 13px;
  font-weight: 500;
  color: var(--cj-primary);
}
.card-desc {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--cj-text-sub);
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
}
.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--cj-primary);
  background: var(--cj-hover-bg);
}

.card-enter {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  font-size: 13px;
  color: var(--cj-primary);
  border-top: 1px solid var(--cj-border);
  padding-top: 12px;
}
.agent-card.disabled .card-enter {
  color: var(--cj-text-sub);
}

.plaza-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--cj-text-sub);
}
.plaza-empty p {
  margin: 0;
  font-size: 13px;
}
</style>
