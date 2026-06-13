/**
 * 查询改写服务：将用户的自然语言 query 改写为适合检索的关键词组合。
 *
 * 示例：
 *   "我想吃点辣的" → "川菜 湘菜 辣味 火锅 餐厅"
 *   "带小孩去玩的" → "亲子 儿童 乐园 博物馆 互动 景点"
 *   "成都有什么好玩的" → "成都 景点 公园 博物馆 文化 地标"
 *
 * 失败时直接返回原始 query，不阻塞检索链路。
 */

function loadEnv(): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined) result[key] = value
  }
  return result
}

/**
 * 调用 DeepSeek LLM 改写查询
 * @returns 改写后的关键词字符串（多个词用空格分隔）；失败返回原始 query
 */
export async function rewriteQuery(query: string): Promise<string> {
  let cfg: { apiKey: string; baseURL: string; model: string }
  try {
    const provider = (process.env.MODEL_PROVIDER as 'KIMI' | 'DEEPSEEK') || 'DEEPSEEK'
    if (provider === 'KIMI') {
      cfg = {
        apiKey: process.env.KIMI_API_KEY!,
        baseURL: process.env.KIMI_BASE_URL!,
        model: process.env.KIMI_MODEL!,
      }
    } else {
      cfg = {
        apiKey: process.env.DEEPSEEK_API_KEY!,
        baseURL: process.env.DEEPSEEK_BASE_URL!,
        model: process.env.DEEPSEEK_MODEL!,
      }
    }
    if (!cfg.apiKey || !cfg.baseURL || !cfg.model) {
      console.warn('[QueryRewrite] LLM 配置缺失，跳过改写')
      return query
    }
  } catch (e) {
    console.warn('[QueryRewrite] LLM 配置错误:', e)
    return query
  }

  const systemPrompt = `你是一个旅行查询改写专家。用户会输入一段自然语言搜索词，你需要将其改写为适合向量检索的关键词组合。

规则：
1. 保留核心实体（城市名、景点类型如"火锅""博物馆""公园"）
2. 提取隐含意图（"想吃的"→"美食 餐厅"，"带孩子玩"→"亲子 儿童 乐园"）
3. 用空格分隔多个关键词，最多 8 个词
4. 不要加解释，只输出关键词本身
5. 如果用户已包含城市名，保留城市名；否则不添加城市

示例：
输入: "我想吃点辣的"
输出: 川菜 湘菜 辣味 火锅 餐厅

输入: "带小孩去玩的"
输出: 亲子 儿童 乐园 博物馆 互动 景点

输入: "有什么好玩的"
输出: 景点 公园 博物馆 文化 地标

输入: "便宜的地方"
输出: 免费 低价 平价 景点`

  const userPrompt = `将以下查询改写为检索关键词：\n"${query}"`

  try {
    const url = `${cfg.baseURL}/chat/completions`
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${cfg.apiKey}`,
      },
      body: JSON.stringify({
        model: cfg.model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt },
        ],
        temperature: 0,
        max_tokens: 100,
      }),
    })

    if (!res.ok) {
      console.warn(`[QueryRewrite] LLM 请求失败 (${res.status})，使用原始 query`)
      return query
    }

    const data: any = await res.json()
    const content = data.choices?.[0]?.message?.content?.trim() || ''

    // 清理可能的 markdown 代码块
    const cleaned = content.replace(/```[\w]*\n?/g, '').replace(/```/g, '').trim()
    return cleaned || query
  } catch (e) {
    console.warn('[QueryRewrite] LLM 调用异常，使用原始 query:', e instanceof Error ? e.message : e)
    return query
  }
}
