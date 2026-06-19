import { AsyncLocalStorage } from 'async_hooks'
import { BaseCallbackHandler } from '@langchain/core/callbacks/base'
import type { LLMResult } from '@langchain/core/outputs'
import { tokenBudget } from './tokenBudget'

export const llmContext = new AsyncLocalStorage<{ userId: string | number }>()

export class TokenTrackingCallback extends BaseCallbackHandler {
  name = 'token_tracking'

  async onLLMEnd(output: LLMResult): Promise<void> {
    const tokenUsage = output.llmOutput?.tokenUsage
    if (!tokenUsage) return
    const total = (tokenUsage.totalTokens ?? 0) as number
    if (total <= 0) return

    const ctx = llmContext.getStore()
    if (ctx) {
      await tokenBudget.recordUserUsage(ctx.userId, total)
    }
    await tokenBudget.recordGlobalUsage(total)
  }
}

export const tokenTracker = new TokenTrackingCallback()

export function recordFetchTokenUsage(data: { usage?: { total_tokens?: number } }): void {
  const total = data?.usage?.total_tokens
  if (!total || total <= 0) return
  const ctx = llmContext.getStore()
  if (ctx) {
    tokenBudget.recordUserUsage(ctx.userId, total)
  }
  tokenBudget.recordGlobalUsage(total)
}
