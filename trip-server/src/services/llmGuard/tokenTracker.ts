import { AsyncLocalStorage } from 'async_hooks'
import { BaseCallbackHandler } from '@langchain/core/callbacks/base'
import type { LLMResult } from '@langchain/core/outputs'
import { tokenBudget } from './tokenBudget'
import { tokenUsageLog } from './tokenUsageLog'

export const llmContext = new AsyncLocalStorage<{ userId: string | number; endpoint?: string }>()

function recordUsage(tokens: number): void {
  const ctx = llmContext.getStore()
  const userId = ctx?.userId ?? 0
  const endpoint = ctx?.endpoint ?? 'background'
  tokenUsageLog.recordLog({ userId, endpoint, tokens, timestamp: Date.now() })
  if (ctx) {
    void tokenBudget.recordUserUsage(ctx.userId, tokens)
  }
  void tokenBudget.recordGlobalUsage(tokens)
}

export class TokenTrackingCallback extends BaseCallbackHandler {
  name = 'token_tracking'

  async onLLMEnd(output: LLMResult): Promise<void> {
    const tokenUsage = output.llmOutput?.tokenUsage
    if (!tokenUsage) return
    const total = (tokenUsage.totalTokens ?? 0) as number
    if (total <= 0) return
    recordUsage(total)
  }
}

export const tokenTracker = new TokenTrackingCallback()

export function recordFetchTokenUsage(data: { usage?: { total_tokens?: number } }): void {
  const total = data?.usage?.total_tokens
  if (!total || total <= 0) return
  recordUsage(total)
}
