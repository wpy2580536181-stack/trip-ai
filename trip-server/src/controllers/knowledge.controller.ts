import { Request, Response } from 'express'
import * as knowledgeService from '../services/knowledgeService'
import prisma from '../config/database'

export const list = async (req: Request, res: Response) => {
  const city = req.query.city as string | undefined
  const category = req.query.category as any
  const page = Number(req.query.page) || 1
  const pageSize = Number(req.query.pageSize) || 20
  try {
    const result = await knowledgeService.listSpots({ city, category, page, pageSize })
    return res.json({ code: 200, data: result })
  } catch (e) {
    return res.status(500).json({ code: 500, error: '获取列表失败' })
  }
}

export const detail = async (req: Request, res: Response) => {
  const id = Number(req.params.id)
  try {
    const spot = await prisma.spot.findUnique({ where: { id } })
    if (!spot) return res.status(404).json({ code: 404, error: '景点不存在' })
    return res.json({ code: 200, data: spot })
  } catch (e) {
    return res.status(500).json({ code: 500, error: '获取详情失败' })
  }
}

export const create = async (req: Request, res: Response) => {
  try {
    const spot = await knowledgeService.createSpot(req.body)
    return res.json({ code: 200, data: spot })
  } catch (e) {
    const msg = e instanceof Error ? e.message : '创建失败'
    return res.status(400).json({ code: 400, error: msg })
  }
}

export const update = async (req: Request, res: Response) => {
  const id = Number(req.params.id)
  try {
    const spot = await knowledgeService.updateSpot(id, req.body)
    return res.json({ code: 200, data: spot })
  } catch (e) {
    const msg = e instanceof Error ? e.message : '更新失败'
    return res.status(400).json({ code: 400, error: msg })
  }
}

export const remove = async (req: Request, res: Response) => {
  const id = Number(req.params.id)
  try {
    await knowledgeService.deleteSpot(id)
    return res.json({ code: 200, message: '删除成功' })
  } catch (e) {
    const msg = e instanceof Error ? e.message : '删除失败'
    return res.status(400).json({ code: 400, error: msg })
  }
}
