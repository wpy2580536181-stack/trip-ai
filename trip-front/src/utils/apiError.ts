/**
 * 统一 API 错误处理工具（Phase 1 改进）。
 *
 * 目标：收敛分散在各视图里的 message.error(...) 文案，提供一致的：
 * - getApiErrorText(error)：从异常中提取用户可读的提示文案
 * - handleApiError(error, message?)：弹 toast（优先使用调用方传入的 message 实例，
 *   否则尝试 useMessage()，再不行降级为 console.error，避免在异步上下文调用
 *   useMessage() 抛错导致页面崩溃）
 * - safeList(resp, fallback)：列表类请求的安全兜底，请求失败时返回默认空数组
 */

import { useMessage, type MessageApi } from 'naive-ui'
import type { ApiResponse } from '@/api/request'

/** 各状态码对应的默认提示文案（与服务端入站 429/503 守卫文案风格对齐） */
const STATUS_TEXT: Record<number, string> = {
  401: '登录已失效，请重新登录',
  403: '没有权限执行此操作',
  404: '请求的资源不存在',
  429: '请求过于频繁，请稍后重试',
  500: '服务暂时不可用，请稍后重试',
  502: '网关错误，请稍后重试',
  503: '服务繁忙，请稍后重试',
  504: '请求超时，请稍后重试',
}

/**
 * 从异常中提取用户可读的提示文案。
 *
 * 优先级：服务端返回的业务 message / error 字段 > 状态码默认文案 > 兜底文案。
 * 注意：仅取业务错误信息用于展示，不向上层泄露原始异常对象。
 */
export function getApiErrorText(error: any): string {
  const status = error?.response?.status

  const data = error?.response?.data
  if (data) {
    const biz = data.message || data.error
    if (typeof biz === 'string' && biz.trim()) return biz
    if (typeof data === 'string' && data.trim()) return data
  }

  if (status && STATUS_TEXT[status]) return STATUS_TEXT[status]
  return '网络异常，请稍后重试'
}

/**
 * 弹出一个错误处理 toast。
 *
 * @param error      捕获到的异常（axios 错误 / 普通 Error）
 * @param message    可选。调用方在 setup 中通过 useMessage() 获取的实例；
 *                   传入可确保在异步回调中也能正常弹窗（推荐）。
 *                   若不传，则尝试 useMessage()，失败则降级为 console.error。
 */
export function handleApiError(error: any, message?: MessageApi): void {
  const text = getApiErrorText(error)

  if (message) {
    message.error(text)
    return
  }

  try {
    // 仅在能拿到组件实例的同步上下文中有效；异步回调里可能抛错
    useMessage().error(text)
  } catch {
    // 异步上下文拿不到 message provider 时，至少把错误打到控制台
    // eslint-disable-next-line no-console
    console.error('[apiError]', text, error)
  }
}

/**
 * 列表类请求的安全兜底。
 *
 * 请求层不会返回兜底数据，因此视图在解构时统一用本函数避免 undefined 崩页。
 *
 * @example
 *   const items = safeList(await get<X[]>('/api/list'))
 */
export function safeList<T>(resp?: ApiResponse<T[]>, fallback: T[] = []): T[] {
  return resp?.data ?? fallback
}
