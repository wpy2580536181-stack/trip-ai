import { Request, Response } from 'express'
import * as conversationService from '../services/conversationService'
import { parseIntParam, isInvalidParamError } from '../utils/params'

export const list = async (req: Request, res: Response) => {
  if (!req.user) return res.status(401).json({ code: 401, error: '未登录' })
  const page = Number(req.query.page) || 1
  const pageSize = Number(req.query.pageSize) || 20
  try {
    const result = await conversationService.listConversations(req.user.userId, page, pageSize)
    return res.json({ code: 200, data: result })
  } catch (e) {
    return res.status(500).json({ code: 500, error: '获取对话列表失败' })
  }
}

export const detail = async (req: Request, res: Response) => {
  if (!req.user) return res.status(401).json({ code: 401, error: '未登录' })
  try {
    const id = parseIntParam(req.params.id, 'id')!
    const conv = await conversationService.getConversationDetail(id, req.user.userId)
    if (!conv) return res.status(404).json({ code: 404, error: '对话不存在' })
    return res.json({ code: 200, data: conv })
  } catch (e) {
    if (isInvalidParamError(e)) return res.status(400).json({ code: 400, error: e.message })
    return res.status(500).json({ code: 500, error: '获取对话详情失败' })
  }
}

export const remove = async (req: Request, res: Response) => {
  if (!req.user) return res.status(401).json({ code: 401, error: '未登录' })
  try {
    const id = parseIntParam(req.params.id, 'id')!
    await conversationService.deleteConversation(id, req.user.userId)
    return res.json({ code: 200, message: '删除成功' })
  } catch (e) {
    if (isInvalidParamError(e)) return res.status(400).json({ code: 400, error: e.message })
    const msg = e instanceof Error ? e.message : '删除失败'
    return res.status(400).json({ code: 400, error: msg })
  }
}
