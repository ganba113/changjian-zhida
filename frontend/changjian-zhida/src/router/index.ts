import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

/**
 * 路由表
 * 主布局 MainLayout 挂载在根层级，内部子路由对应左侧导航的各模块
 */
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/views/layout/MainLayout.vue'),
    redirect: '/chat',
    children: [
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/ChatView.vue'),
        meta: { title: 'AI对话' },
      },
      {
        path: 'agents',
        name: 'Agents',
        component: () => import('@/views/AgentsView.vue'),
        meta: { title: '智能体' },
      },
      {
        path: 'agents/yingshang',
        name: 'AgentYingshang',
        component: () => import('@/views/agents/YingshangView.vue'),
        meta: { title: '检护营商智能体' },
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/KnowledgeView.vue'),
        meta: { title: '知识库' },
      },
      {
        path: 'micro-class',
        name: 'MicroClass',
        component: () => import('@/views/MicroClassView.vue'),
        meta: { title: '微课堂' },
      },
      {
        path: 'ocr',
        name: 'Ocr',
        component: () => import('@/views/OcrView.vue'),
        meta: { title: 'OCR应用' },
      },
      {
        path: 'system',
        name: 'System',
        component: () => import('@/views/SystemView.vue'),
        meta: { title: '系统管理' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
