import { Request, Response } from 'express'
import prisma from '../config/database'

export const listTrips = async (req: Request, res: Response) => {
  if (!req.user) return res.status(401).json({ code: 401, error: '未登录' })
  const page = Number(req.query.page) || 1
  const pageSize = Number(req.query.pageSize) || 20
  try {
    const [items, total] = await Promise.all([
      prisma.trip.findMany({
        where: { userId: req.user.userId },
        orderBy: { createdAt: 'desc' },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      prisma.trip.count({ where: { userId: req.user.userId } }),
    ])
    return res.json({ code: 200, data: { items, total, page, pageSize } })
  } catch (e) {
    return res.status(500).json({ code: 500, error: '获取行程历史失败' })
  }
}

export const getTrip = async (req: Request, res: Response) => {
  if (!req.user) return res.status(401).json({ code: 401, error: '未登录' })
  const id = Number(req.params.id)
  try {
    const trip = await prisma.trip.findFirst({
      where: { id, userId: req.user.userId },
    })
    if (!trip) return res.status(404).json({ code: 404, error: '行程不存在' })
    return res.json({ code: 200, data: trip })
  } catch (e) {
    return res.status(500).json({ code: 500, error: '获取行程详情失败' })
  }
}
