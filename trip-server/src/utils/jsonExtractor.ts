/**
 * 从 LLM 输出中提取 JSON 对象。
 * 策略（按优先级）：
 * 1. 匹配 markdown ```json 代码块（多块取第一个能 parse 的）
 * 2. 整段 JSON.parse（处理 LLM 干净输出的常见情形）
 * 3. 括号配对扫描找所有候选顶层 {...}，挑最长的（避免截断+多对象边界）
 * 4. 失败时抛带诊断信息的错误
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

  const candidates = findAllBalancedObjects(text)
  if (candidates.length === 0) {
    const snippet = text.slice(0, 120).replace(/\n/g, ' ')
    throw new Error(`无法从 LLM 输出中提取 JSON（首 120 字符：${snippet}）`)
  }

  // 挑最长的候选对象（避免被空对象 {} 抢在前面）
  let longest = candidates[0]
  for (const c of candidates) {
    if (c.length > longest.length) longest = c
  }

  try {
    return JSON.parse(longest)
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    const snippet = longest.slice(0, 120).replace(/\n/g, ' ')
    throw new Error(`JSON 解析失败：${msg}（首 120 字符：${snippet}）`)
  }
}

/**
 * 从 LLM 输出中提取最长 balanced {...} 原始字符串（不 parse）。
 * 供 repairJson 等修复流程使用，避免 extractJson 解析失败时丢失原始 JSON 文本。
 */
export function extractJsonString(text: string): string {
  // 优先取 markdown code block 内的 JSON 文本（贪婪匹配，避免嵌套 JSON 被截断）
  const codeBlockRe = /```(?:json)?\s*(\{[\s\S]*\})\s*```/g
  let m: RegExpExecArray | null
  let best = ''
  while ((m = codeBlockRe.exec(text)) !== null) {
    if (m[1].length > best.length) best = m[1]
  }
  if (best) return best

  // 括号配对扫描，取最长的 balanced 候选
  const candidates = findAllBalancedObjects(text)
  for (const c of candidates) {
    if (c.length > best.length) best = c
  }
  if (best) return best

  // 兜底：返回 { 到 } 之间的文本
  const firstBrace = text.indexOf('{')
  const lastBrace = text.lastIndexOf('}')
  if (firstBrace !== -1 && lastBrace > firstBrace) {
    return text.slice(firstBrace, lastBrace + 1)
  }

  throw new Error(`无法从 LLM 输出中提取 JSON 字符串`)
}

/**
 * 扫描 text 中所有顶层 {...} 候选（按出现顺序）。
 * 字符串内 '}' 会被忽略，'\\' 转义正确处理。
 * 如果有未闭合的 '{'（截断），抛"输出被截断"错误。
 */
function findAllBalancedObjects(text: string): string[] {
  const results: string[] = []
  let i = 0
  while (i < text.length) {
    const idx = text.indexOf('{', i)
    if (idx === -1) break
    const candidate = extractBalancedObjectAt(text, idx)
    if (candidate === null) {
      // 截断或不平衡：诊断 + 终止
      const tail = text.slice(idx, idx + 120).replace(/\n/g, ' ')
      throw new Error(`LLM 输出被截断或括号不平衡：从位置 ${idx} 起 ${tail}`)
    }
    results.push(candidate)
    i = idx + candidate.length
  }
  return results
}

function extractBalancedObjectAt(text: string, startIdx: number): string | null {
  let depth = 0
  let inString = false
  let escape = false
  for (let i = startIdx; i < text.length; i++) {
    const ch = text[i]
    if (escape) {
      escape = false
      continue
    }
    if (inString && ch === '\\') {
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
