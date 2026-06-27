import { describe, it, expect } from 'vitest'
import { isPlanningRequest } from '../router'

describe('isPlanningRequest', () => {
  it('含规划关键词 + 天数 → true', () => {
    expect(isPlanningRequest('帮我规划北京三日游')).toBe(true)
    expect(isPlanningRequest('帮我安排成都5日行程')).toBe(true)
    expect(isPlanningRequest('做个西安几日游攻略')).toBe(true)
  })

  it('只有关键词无天数 → false', () => {
    expect(isPlanningRequest('帮我规划北京')).toBe(false)
    expect(isPlanningRequest('成都有什么好玩的行程')).toBe(false)
  })

  it('只有天数无关键词 → false', () => {
    expect(isPlanningRequest('北京3日')).toBe(false)
    expect(isPlanningRequest('5天去哪玩')).toBe(false)
  })

  it('闲聊/单点查询 → false', () => {
    expect(isPlanningRequest('北京今天天气怎么样')).toBe(false)
    expect(isPlanningRequest('成都有什么好吃的')).toBe(false)
    expect(isPlanningRequest('上海到杭州多远')).toBe(false)
  })

  it('空字符串 → false', () => {
    expect(isPlanningRequest('')).toBe(false)
  })

  it('"几天" 也算天数表达', () => {
    expect(isPlanningRequest('帮我规划北京几天游行程')).toBe(true)
  })
})
