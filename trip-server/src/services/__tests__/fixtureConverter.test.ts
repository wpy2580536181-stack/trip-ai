import { describe, it, expect } from 'vitest'
import { toYAML, slugify, type ConvertInput, MAX_CONTENT_LENGTH } from '../fixtureConverter'
import * as yaml from 'js-yaml'

const baseInput: ConvertInput = {
  feedbackId: 113,
  feedbackComment: '推荐不准',
  feedbackTags: ['recommend'],
  feedbackCreatedAt: new Date('2026-06-24T10:00:00Z'),
  messageId: 848,
  messageContent: 'agent 的回复...',
  userId: 5,
  username: 'eval-test',
  userPreferences: { travelStyle: 'relaxed', interests: ['美食'] },
  conversationMessages: [
    { id: 845, role: 'user', content: '上海 2 天推荐几个好吃的', createdAt: new Date() },
    { id: 846, role: 'assistant', content: '好的，为您推荐...', createdAt: new Date() },
    { id: 847, role: 'user', content: '加点辣的', createdAt: new Date() },
    { id: 848, role: 'assistant', content: 'agent 这次回复', createdAt: new Date() },
  ],
}

describe('slugify', () => {
  it('处理中文 + 英文 + 数字', () => {
    expect(slugify('上海 2 天 推荐!')).toBe('上海-2-天-推荐')
  })

  it('空字符串返回 untitled', () => {
    expect(slugify('')).toBe('untitled')
    expect(slugify('!!!')).toBe('untitled')
  })

  it('截断到 30 字符', () => {
    const long = 'a'.repeat(50)
    expect(slugify(long).length).toBeLessThanOrEqual(30)
  })
})

describe('toYAML - input.message 选择', () => {
  it('选 < messageId 的最后 user turn', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.input.message).toBe('加点辣的')
  })

  it('没有 user turn 时 message 为空', () => {
    const input = {
      ...baseInput,
      conversationMessages: [
        { id: 845, role: 'assistant' as const, content: '...', createdAt: new Date() },
        { id: 848, role: 'assistant' as const, content: 'agent 这次回复', createdAt: new Date() },
      ],
    }
    const parsed = yaml.load(toYAML(input)) as any
    expect(parsed.input.message).toBe('')
  })
})

describe('toYAML - history 过滤', () => {
  it('只包含 < messageId 的轮次', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.input.history).toHaveLength(3)
  })

  it('history 排除 target message (assistant response, id=848)', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.input.history.find((h: any) => h.content === 'agent 这次回复')).toBeUndefined()
  })
})

describe('toYAML - 元数据', () => {
  it('source 含 feedback_id + message_id + user + created_at', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.source.feedback_id).toBe(113)
    expect(parsed.source.message_id).toBe(848)
    expect(parsed.source.user).toBe('eval-test')
    expect(parsed.source.original_comment).toBe('推荐不准')
  })

  it('tags 含 feedback-imported + user-reported + 原 tags', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.tags).toEqual(['feedback-imported', 'user-reported', 'recommend'])
  })

  it('description 含 feedbackId + comment', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.description).toContain('#113')
    expect(parsed.description).toContain('推荐不准')
  })

  it('source 含 bad_response 字段（admin 看到的坏回复）', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.source.bad_response).toBe('agent 的回复...')
  })

  it('bad_response 超 500 字符截断', () => {
    const input = {
      ...baseInput,
      messageContent: 'a'.repeat(800),
    }
    const parsed = yaml.load(toYAML(input)) as any
    expect(parsed.source.bad_response).toContain('[已截断]')
  })
})

describe('toYAML - 截断', () => {
  it('content 超 10KB 截断', () => {
    const huge = 'a'.repeat(15000)
    const input = {
      ...baseInput,
      conversationMessages: [
        { id: 847, role: 'user' as const, content: huge, createdAt: new Date() },
        { id: 848, role: 'assistant' as const, content: 'agent 这次回复', createdAt: new Date() },
      ],
    }
    const parsed = yaml.load(toYAML(input)) as any
    expect(parsed.input.message).toContain('[已截断]')
    expect(parsed.input.message.length).toBe(MAX_CONTENT_LENGTH + '...[已截断]'.length)
  })
})

describe('toYAML - id slug', () => {
  it('id 格式: feedback-{id}-{user}-{msg}', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.id).toMatch(/^feedback-113-eval-test-/)
  })
})

describe('toYAML - evaluators 默认', () => {
  it('默认 evaluators: schema_check + keyword_coverage', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.evaluators).toEqual(['schema_check', 'keyword_coverage'])
  })
})
