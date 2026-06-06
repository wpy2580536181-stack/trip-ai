import { Request, Response, NextFunction } from 'express'
import { verifyToken, JwtPayload } from '../config/jwt'

// 扩展 Express Request 类型
declare global {
  namespace Express {
    interface Request {
      user?: JwtPayload
    }
  }
}

// JWT认证中间件
export function authMiddleware(req: Request, res: Response, next: NextFunction) {
   // 1. 从请求头获取 Authorization 字段
  const authHeader = req.headers.authorization
   // 2. 检查格式：必须是 "Bearer <token>" 格式
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ code: 401, error: '未登录，请先登录' })
  }

   // 3. 提取纯 Token：截取掉前7个字符（"Bearer "）
  const token = authHeader.substring(7)
  // 4. 验证 Token：调用你上一段代码写的验证函数
  const decoded = verifyToken(token)
  if (!decoded) {
    return res.status(401).json({ code: 401, error: 'token无效或已过期' })
  }

  // 5. 挂载用户信息并放行请求
  req.user = decoded
  next()
}

// 角色权限中间件
export function roleMiddleware(...allowedRoles: number[]) {
  return (req: Request, res: Response, next: NextFunction) => {
    // 1. 确保用户已经登录（必须先经过 authMiddleware）
    if (!req.user) {
      return res.status(401).json({ code: 401, error: '未登录' })
    }
    // 2. 检查用户的 roleId 是否在允许的名单中
    if (!allowedRoles.includes(req.user.roleId)) {
      return res.status(403).json({ code: 403, error: '权限不足' })
    }
    // 3. 如果权限足够，放行请求
    next()
  }
}