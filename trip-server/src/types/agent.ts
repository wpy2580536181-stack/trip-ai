import { z } from 'zod'

export const SpotCategorySchema = z.enum(['attraction', 'food', 'hotel', 'transport'])
export type SpotCategory = z.infer<typeof SpotCategorySchema>

export const SpotInputSchema = z.object({
  name: z.string().min(1).max(100),
  city: z.string().min(1).max(50),
  category: SpotCategorySchema,
  description: z.string().min(1),
  tags: z.array(z.string()).default([]),
  avgCost: z.number().optional(),
  duration: z.string().optional(),
  openTime: z.string().optional(),
  rating: z.number().min(0).max(5).optional(),
})
export type SpotInput = z.infer<typeof SpotInputSchema>

export interface SpotVectorDoc {
  id: string
  embedding: number[]
  document: string
  metadata: {
    city: string
    name: string
    category: string
    tags: string
    rating?: number
  }
}

export const TripContentSchema = z.object({
  city: z.string(),
  days: z.number(),
  totalBudget: z.number(),
  dailyItinerary: z.array(z.any()),
  budgetBreakdown: z.object({
    accommodation: z.number(),
    food: z.number(),
    transportation: z.number(),
    tickets: z.number(),
    other: z.number(),
  }),
  tips: z.array(z.string()),
  warnings: z.array(z.string()).optional(),
})
export type TripContent = z.infer<typeof TripContentSchema>

export type AgentStreamEvent =
  | { type: 'tool_start'; name: string }
  | { type: 'tool_end'; name: string; output?: string }
  | { type: 'chunk'; content: string }
  | { type: 'complete'; content: string }
  | { type: 'error'; error: string }
