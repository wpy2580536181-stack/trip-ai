export function extractJson(text: string): unknown {
  const codeBlocks: string[] = []
  const codeBlockRe = /```(?:json)?\s*(\{[\s\S]*?\})\s*```/g
  let m: RegExpExecArray | null
  while ((m = codeBlockRe.exec(text)) !== null) {
    codeBlocks.push(m[1])
  }
  if (codeBlocks.length > 0) {
    return JSON.parse(codeBlocks[0])
  }

  const braceMatch = text.match(/\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/)
  if (braceMatch) {
    return JSON.parse(braceMatch[0])
  }

  throw new Error('无法从 LLM 输出中提取 JSON')
}
