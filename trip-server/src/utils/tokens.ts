/**
 * Token 估算工具
 *
 * 中文 token 化没有精确的 BPE 映射，使用启发式估算：
 * - CJK 字符（中文/日文/韩文）：~1.5 字符/token
 * - 英文/数字/其他：~4 字符/token
 * - 混合文本取加权平均
 *
 * 精确度约 ±15%，对滑动窗口控制足够
 */
export function estimateTokens(text: string): number {
  if (!text) return 0
  let cjkCount = 0
  let otherCount = 0
  for (const ch of text) {
    const code = ch.charCodeAt(0)
    if (
      (code >= 0x4E00 && code <= 0x9FFF) ||  // CJK Unified
      (code >= 0x3400 && code <= 0x4DBF) ||  // CJK Extension A
      (code >= 0x20000 && code <= 0x2A6DF) || // CJK Extension B
      (code >= 0x3040 && code <= 0x309F) ||  // Hiragana
      (code >= 0x30A0 && code <= 0x30FF)     // Katakana
    ) {
      cjkCount++
    } else {
      otherCount++
    }
  }
  return Math.max(1, Math.ceil(cjkCount / 1.5 + otherCount / 4))
}

export const DEFAULT_HISTORY_MAX_TOKENS = 16000

/**
 * 压缩后目标 token 数。压缩时把 TAIL 从 maxTokens 压到该值，
 * 留出 ~25% buffer 避免下一两轮立刻又触发压缩。
 */
export const DEFAULT_COMPACTION_TARGET_TOKENS = 12000

export function getHistoryMaxTokens(): number {
  const env = process.env.HISTORY_MAX_TOKENS
  if (env && !isNaN(Number(env))) return Number(env)
  return DEFAULT_HISTORY_MAX_TOKENS
}
