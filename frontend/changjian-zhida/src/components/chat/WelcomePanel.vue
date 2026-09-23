<script setup lang="ts">
/**
 * 欢迎页：问候语 + 描述（无热门智能体卡片）
 * 在 ChatView 中与输入框一起居中展示
 */
import { Promotion } from '@element-plus/icons-vue'
</script>

<template>
  <div class="welcome-panel cj-fade-in">
    <!-- 标题区 -->
    <header class="welcome-header">
      <div class="welcome-badge">
        <el-icon :size="26" color="#fff"><Promotion /></el-icon>
      </div>
      <h1 class="welcome-title">你好</h1>
      <h2 class="welcome-subtitle">
        我是<span class="brand-name">「昌检智答」</span>AI助手
      </h2>
      <p class="welcome-desc">
        依托人工智能技术，面向检察办案全流程提供智能辅助。无论是法条检索、案件分析、文书起草，还是类案参考、证据梳理、程序指引，都可以在这里获得精准、高效的智能支持。请输入您的问题，我将为您提供精准解答。
      </p>
    </header>
  </div>
</template>

<style scoped>
.welcome-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.welcome-header {
  text-align: center;
}

.welcome-badge {
  width: 52px;
  height: 52px;
  margin: 0 auto 18px;
  border-radius: 14px;
  background: var(--cj-primary-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 20px rgba(30, 79, 163, 0.35);
}

.welcome-title {
  margin: 0;
  font-size: 30px;
  font-weight: 600;
  letter-spacing: 1px;
}

.welcome-subtitle {
  margin: 10px 0 0;
  font-size: 24px;
  font-weight: 500;
  color: var(--cj-primary);
  letter-spacing: 1px;
}

/* 「昌检智答」品牌字：加粗 + 流光渐变 */
.brand-name {
  margin: 0 2px;
  font-weight: 800;
  font-size: 28px;
  letter-spacing: 2px;
  /* 渐变文字：政务蓝 → 天青亮色 → 政务蓝，背景拉宽以承载流光 */
  background: linear-gradient(
    100deg,
    #1e4fa3 0%,
    #1e4fa3 35%,
    #4facf7 50%,
    #1e4fa3 65%,
    #1e4fa3 100%
  );
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
  animation: brand-shine 3.2s linear infinite;
}

/* 流光动画：渐变背景水平循环滚动 */
@keyframes brand-shine {
  0% {
    background-position: 0% 50%;
  }
  100% {
    background-position: 300% 50%;
  }
}

.welcome-desc {
  margin: 16px auto 0;
  max-width: 560px;
  font-size: 13px;
  line-height: 1.9;
  color: var(--cj-text-sub);
}
</style>
