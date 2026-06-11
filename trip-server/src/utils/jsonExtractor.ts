export function extractJson(text: string): unknown {
  const codeBlockMatch = text.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/)
  if (codeBlockMatch) {
    return JSON.parse(codeBlockMatch[1])
  }

  const braceMatch = text.match(/\{[\s\S]*\}/)
  if (braceMatch) {
    return JSON.parse(braceMatch[0])
  }

  throw new Error('无法从 LLM 输出中提取 JSON')
}
