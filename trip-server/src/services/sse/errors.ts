/**
 * SSE 流错误类型
 *
 * 用于 controller 层通过 instanceof 区分 HTTP 响应状态码：
 * - StreamNotFoundError  → 404
 * - StreamForbiddenError → 403 (IDOR 防护)
 * - StreamBadRequestError → 400
 */

/**
 * Stream 不存在或已过期 (404)
 */
export class StreamNotFoundError extends Error {
  constructor(streamId: string) {
    super(`Stream not found or expired: ${streamId}`)
    this.name = 'StreamNotFoundError'
  }
}

/**
 * 无权访问此 stream (403)
 * IDOR 防护：防止用户访问其他用户的 stream
 */
export class StreamForbiddenError extends Error {
  constructor() {
    super('Forbidden: stream belongs to another user')
    this.name = 'StreamForbiddenError'
  }
}

/**
 * 请求参数错误 (400)
 * 例如：Last-Event-ID 格式错误、超过 totalSeq 等
 */
export class StreamBadRequestError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'StreamBadRequestError'
  }
}
