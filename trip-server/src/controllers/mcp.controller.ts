import { Request, Response } from 'express'
import { getMetrics } from '../services/mcp/amapGuards'
import { isAlive } from '../services/mcp/amapMcpProcess'

export const getMcpStats = async (req: Request, res: Response) => {
  const metrics = getMetrics()
  res.json({
    alive: isAlive(),
    metrics,
  })
}
