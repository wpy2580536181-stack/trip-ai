import { queryRewriteLog as log } from '../utils/logger'

/**
 * 本地查询改写：从自然语言 query 中提取检索关键词
 *
 * 替代原来的 LLM 改写（每次 ~800ms），节省 ~750ms/次
 *
 * 策略：
 * 1. 去掉常见停用词
 * 2. 提取 2-5 字中文片段
 * 3. 意图映射 → 分类关键词（"吃"→"美食 餐厅"）
 * 4. 去重后返回最多 6 个关键词
 */

const STOP_WORDS = new Set([
  '什么', '怎么', '哪里', '哪个', '哪些', '谁', '何时',
  '推荐', '请问', '我想', '需要', '可以', '有没有', '是不是',
  '帮我', '介绍', '告诉', '知道', '觉得', '想去', '打算',
  '一下', '一下', '吧', '啊', '呢', '吗', '了', '的', '啦',
  '在', '有', '和', '与', '或', '是', '的', '这', '那',
  '去', '来', '到', '从', '给', '为', '对',
  '好玩', '好吃', '好看', '好喝', '有趣', '漂亮', '不错',
  '大概', '多少', '便宜', '方便', '适合',
])

const INTENT_MAP: Array<[RegExp, string]> = [
  [/吃|美食|餐厅|饭馆|菜|辣|甜|口味/i, '美食 餐厅'],
  [/住|住宿|酒店|宾馆|民宿|客栈|房间/i, '住宿 酒店'],
  [/玩|逛|游|景点|景区|公园/i, '景点 游览'],
  [/买|购物|商业街|商场|街/i, '购物 商业街'],
  [/票|门票|收费|价格|价钱|多少钱/i, '门票 价格'],
  [/交通|公交|地铁|打车|开车|停车/i, '交通'],
  [/拍照|摄影|照片|打卡/i, '拍照 打卡'],
  [/历史|文化|博物馆|古迹|文物/i, '文化 历史'],
  [/自然|山|水|湖|海|森林|风景|风/i, '自然 风景'],
  [/夜|晚上|夜景|夜市|酒吧/i, '夜景 夜市'],
  [/亲|子|小孩|儿童|亲子|带孩/i, '亲子 儿童'],
  [/情侣|约会|浪漫/i, '情侣 浪漫'],
  [/便宜|实惠|平价|经济|省钱|免费/i, '平价 实惠'],
  [/高。端|豪华|奢侈|五星|品质/i, '高端 品质'],
  [/室。内|下雨|天气|夏天|避暑|冬天|暖/i, '室内 避暑'],
]

function extractKeywords(query: string, city: string): string[] {
  const result = new Set<string>()

  // 1. 保留城市名
  if (city) result.add(city)

  // 2. 意图映射
  for (const [pattern, kw] of INTENT_MAP) {
    if (pattern.test(query)) {
      for (const word of kw.split(' ')) result.add(word)
    }
  }

  // 3. 保留原始 query 中的景点实体（去掉停用词后的原文）
  const cleanQuery = query.split(new RegExp(`[${' '.concat('的了吧吗呢啊啦在和有与或是这那来到从给为对').split('').join('')}]`, 'g')).filter(Boolean)
  for (const w of cleanQuery) {
    if (w.length >= 2 && /[一-龥]/.test(w) && !STOP_WORDS.has(w)) result.add(w)
  }

  // 4. 通配类别词
  const specialKeys = ['景点', '美食', '酒店', '住宿', '餐厅', '公园', '博物馆', '夜景', '亲子', '平价', '门票', '交通', '购物']
  for (const k of specialKeys) {
    if (query.includes(k)) result.add(k)
  }

  return [...result].slice(0, 6)
}

/**
 * 本地查询改写（替代原来的 LLM 调用）
 *
 * 速度 ~50ms，不再调 DeepSeek API
 */
export async function rewriteQuery(query: string, city?: string): Promise<string> {
  const keywords = extractKeywords(query, city || '')
  if (keywords.length === 0) return query
  const rewritten = keywords.join(' ')
  if (rewritten !== query) {
    log.debug({ original: query, rewritten }, 'query rewritten')
  }
  return rewritten
}
