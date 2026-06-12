/**
 * 从 LLM 输出中提取 JSON 对象。
 * 策略：
 * 1. 优先匹配 markdown ```json 代码块（多块取第一个）
 * 2. 尝试用 JSON.parse 解析整段文本
 * 3. 用括号配对算法从首字符起扫描，匹配最深完整 {...} 顶层对象
 */
export function extractJson(text: string): unknown {
  const codeBlockRe = /```(?:json)?\s*(\{[\s\S]*?\})\s*```/g
  let m: RegExpExecArray | null
  while ((m = codeBlockRe.exec(text)) !== null) {
    try {
      return JSON.parse(m[1])
    } catch {
      continue
    }
  }

  try {
    return JSON.parse(text)
  } catch {
    // fall through to brace scan
  }

  const firstBrace = text.indexOf('{')
  if (firstBrace === -1) {
    throw new Error('无法从 LLM 输出中提取 JSON')
  }
  const candidate = extractBalancedBraces(text, firstBrace)
  if (!candidate) {
    throw new Error('无法从 LLM 输出中提取 JSON')
  }
  return JSON.parse(candidate)
}

/**
 * 从 startIdx 位置的 '{' 起扫描，用括号配对找出匹配的 '}'，
 * 字符串内 '}' 会被忽略。返回匹配的子串，找不到返回 null。
 */
function extractBalancedBraces(text: string, startIdx: number): string | null {
  let depth = 0
  let inString = false
  let escape = false
  for (let i = startIdx; i < text.length; i++) {
    const ch = text[i]
    if (escape) {
      escape = false
      continue
    }
    if (ch === '\\' && inString) {
      escape = true
      continue
    }
    if (ch === '"') {
      inString = !inString
      continue
    }
    if (inString) continue
    if (ch === '{') {
      depth++
    } else if (ch === '}') {
      depth--
      if (depth === 0) {
        return text.slice(startIdx, i + 1)
      }
    }
  }
  return null
}
