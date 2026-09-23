import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 应用级状态：对话列表栏折叠状态（带 localStorage 记忆）
 */
export const useAppStore = defineStore('app', () => {
  const STORAGE_KEY = 'cj-conv-collapsed'

  const convCollapsed = ref<boolean>(
    localStorage.getItem(STORAGE_KEY) === '1',
  )

  /** 切换对话列表栏折叠状态并持久化 */
  function toggleConvList() {
    convCollapsed.value = !convCollapsed.value
    localStorage.setItem(STORAGE_KEY, convCollapsed.value ? '1' : '0')
  }

  return { convCollapsed, toggleConvList }
})
