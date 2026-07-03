import { z } from 'zod'

/**
 * 行程推荐请求 Schema
 */
export const RecommendRequestSchema = z.object({
  city: z.string().min(1, '城市不能为空').max(50, '城市名称过长'),
  budget: z.number().min(50, '预算最低 50 元').max(1_000_000, '预算最高 1,000,000 元'),
  days: z.number().int().min(1, '最少 1 天').max(30, '最多 30 天'),
  departureCity: z.string().max(50, '出发城市名称过长').optional(),
})

export type RecommendRequest = z.infer<typeof RecommendRequestSchema>

/**
 * 行程优化请求 Schema
 */
export const OptimizeRequestSchema = z.object({
  tripId: z.number().int().positive('行程 ID 必须为正整数'),
  instruction: z.string().max(1000, '优化指令过长').optional(),
})

export type OptimizeRequest = z.infer<typeof OptimizeRequestSchema>

/**
 * 景点 Schema（行程响应中的单个景点）
 */
export const SpotSchema = z.object({
  spot: z.string(),
  duration: z.string().optional(),
  ticket: z.string().optional(),
  transportation: z.string().optional(),
  description: z.string().optional(),
  latitude: z.number().optional(),
  longitude: z.number().optional(),
  imageUrl: z.string().url().optional(),
})

export type Spot = z.infer<typeof SpotSchema>

/**
 * 每日行程 Schema
 */
export const DailyItinerarySchema = z.object({
  day: z.number().int().positive(),
  date: z.string().optional(),
  morning: SpotSchema,
  afternoon: SpotSchema,
  evening: SpotSchema,
  breakfast: SpotSchema.optional(),
  lunch: SpotSchema.optional(),
  dinner: SpotSchema.optional(),
  accommodation: SpotSchema.optional(),
})

export type DailyItinerary = z.infer<typeof DailyItinerarySchema>

/**
 * 预算分解 Schema
 */
export const BudgetBreakdownSchema = z.object({
  accommodation: z.number().nonnegative(),
  food: z.number().nonnegative(),
  transportation: z.number().nonnegative(),
  tickets: z.number().nonnegative(),
  other: z.number().nonnegative(),
})

export type BudgetBreakdown = z.infer<typeof BudgetBreakdownSchema>

/**
 * 行程推荐响应 Schema
 */
export const RecommendResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    id: z.number().int().positive().nullable(),
    city: z.string(),
    days: z.number().int().positive(),
    totalBudget: z.number().nonnegative(),
    dailyItinerary: z.array(DailyItinerarySchema),
    budgetBreakdown: BudgetBreakdownSchema,
    tips: z.array(z.string()),
    warnings: z.array(z.string()),
  }),
})

export type RecommendResponse = z.infer<typeof RecommendResponseSchema>

/**
 * 行程优化响应 Schema（与推荐响应相同）
 */
export const OptimizeResponseSchema = RecommendResponseSchema
export type OptimizeResponse = RecommendResponse
