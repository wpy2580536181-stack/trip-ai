import { AsyncLocalStorage } from 'async_hooks'
import { BaseCallbackHandler } from '@langchain/core/callbacks/base'
import type { LLMResult } from '@langchain/core/outputs'
import { tokenBudget } from './tokenBudget'
import { tokenUsageLog } from './tokenUsageLog'

export const llmContext = new AsyncLocalStorage<{ userId: string | number; endpoint?: string }>()

function recordUsage(usage: { prompt: number; completion: number; cached?: number }): void {
  const ctx = llmContext.getStore()
  const userId = ctx?.userId ?? 0
  const endpoint = ctx?.endpoint ?? 'background'
  const total = usage.prompt + usage.completion
  tokenUsageLog.recordLog({
    userId,
    endpoint,
    tokens: total,
    cached: usage.cached ?? 0,
    timestamp: Date.now(),
  })
  if (ctx) {
    void tokenBudget.recordUserUsage(ctx.userId, total)
  }
  void tokenBudget.recordGlobalUsage(total)
}

export class TokenTrackingCallback extends BaseCallbackHandler {
  name = 'token_tracking'

  async onLLMEnd(output: LLMResult): Promise<void> {
    const tokenUsage = output.llmOutput?.tokenUsage as
      | { promptTokens?: number; completionTokens?: number; totalTokens?: number }
      | undefined
    if (!tokenUsage) return
    const prompt = (tokenUsage.promptTokens ?? 0) as number
    const completion = (tokenUsage.completionTokens ?? 0) as number
    if (prompt + completion <= 0) return
    recordUsage({ prompt, completion })
  }
}

export const tokenTracker = new TokenTrackingCallback()

export function recordFetchTokenUsage(data: {
  usage?: {
    prompt_tokens?: number
    completion_tokens?: number
    total_tokens?: number
    prompt_cache_hit_tokens?: number
  }
}): void {
  const u = data?.usage
  if (!u) return
  const prompt = (u.prompt_tokens ?? 0) as number
  const completion = (u.completion_tokens ?? 0) as number
  const cached = (u.prompt_cache_hit_tokens ?? 0) as number
  if (prompt + completion <= 0) return
  recordUsage({ prompt, completion, cached })
}
