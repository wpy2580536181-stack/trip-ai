// JWT 工具：解析 token payload（不验证签名）+ 过期检测
// 浏览器侧 base64 解码无法验签，仅用于 UI 提示，不作为安全判断依据

export interface JwtPayload {
  userId: number
  username: string
  roleId: number
  iat: number
  exp: number
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = parts[1]
    // base64url → base64
    const padded = payload.replace(/-/g, '+').replace(/_/g, '/')
    const decoded = atob(padded)
    return JSON.parse(decoded) as JwtPayload
  } catch {
    return null
  }
}

export function isTokenExpired(token: string, skewSeconds = 60): boolean {
  const payload = decodeJwtPayload(token)
  if (!payload || !payload.exp) return true
  // 提前 skew 秒视为过期，避免边界请求失败
  return Date.now() / 1000 > payload.exp - skewSeconds
}

export function clearAuth() {
  localStorage.removeItem('token')
  localStorage.removeItem('userInfo')
}

export function checkAndCleanExpiredToken() {
  const token = localStorage.getItem('token')
  if (!token) return
  if (isTokenExpired(token)) {
    console.warn('[Auth] Token 已过期，自动清除')
    clearAuth()
  }
}
