// trip-server/src/services/agent/chatGraph.ts
import { StateGraph, END } from '@langchain/langgraph'
import type { RunnableConfig } from '@langchain/core/runnables'
import { HumanMessage } from '@langchain/core/messages'
import type { BaseMessage } from '@langchain/core/messages'
import type { StreamEvent } from '@langchain/core/tracers/log_stream'
import { PlannerState } from './state'
import { isPlanningRequest } from './nodes/router'
import { researchNode } from './nodes/research'
import { chatPlannerNode } from './nodes/chatPlanner'
import type { PlannerConfig } from './types'
import type { TokenUsage } from '../../types/agent'

/** 从消息文本中提取城市关键词；未命中则返回空串（由 router 决定回退到 general） */
function extractCityFromMessage(message: string): string {
  const cities = ['北京', '上海', '广州', '深圳', '成都', '杭州', '武汉', '西安', '重庆', '南京',
    '天津', '长沙', '苏州', '厦门', '青岛', '大连', '昆明', '三亚', '哈尔滨', '桂林',
    '拉萨', '乌鲁木齐', '贵阳', '南宁', '南昌', '福州', '合肥', '郑州', '济南', '太原', '兰州',
    // 常见旅游目的地
    '丽江', '大理', '西双版纳', '张家界', '九寨沟', '黄山', '鼓浪屿', '凤凰', '平遥', '敦煌',
    '婺源', '稻城', '林芝', '纳木错', '喀纳斯', '伊犁', '阿尔山', '雪乡', '漠河', '北海',
    '涠洲岛', '舟山', '普陀山', '嵊泗', '千岛湖', '乌镇', '西塘', '周庄', '香格里拉']
  return cities.find(c => message.includes(c)) ?? ''
}

/** 从对话历史中提取城市关键词（多轮修改场景 message 可能不包含城市名） */
function extractCityFromHistory(history: import('@langchain/core/messages').BaseMessage[]): string {
  const cities = ['北京', '上海', '广州', '深圳', '成都', '杭州', '武汉', '西安', '重庆', '南京',
    '天津', '长沙', '苏州', '厦门', '青岛', '大连', '昆明', '三亚', '哈尔滨', '桂林',
    '拉萨', '乌鲁木齐', '贵阳', '南宁', '南昌', '福州', '合肥', '郑州', '济南', '太原', '兰州',
    '丽江', '大理', '西双版纳', '张家界', '九寨沟', '黄山', '鼓浪屿', '凤凰', '平遥', '敦煌',
    '婺源', '稻城', '林芝', '纳木错', '喀纳斯', '伊犁', '阿尔山', '雪乡', '漠河', '北海',
    '涠洲岛', '舟山', '普陀山', '嵊泗', '千岛湖', '乌镇', '西塘', '周庄', '香格里拉']
  for (const m of history) {
    const content = typeof m.content === 'string' ? m.content : ''
    const found = cities.find(c => content.includes(c))
    if (found) return found
  }
  return ''
}

/** legacy agent 节点：用现有 AgentExecutor 跑 streamEvents */
async function legacyAgentNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { onEvent, signal, buildAgent, conversationHistory, traceRecorder, stepCounter } = config.configurable as PlannerConfig & {
    buildAgent: () => Promise<{ streamEvents: (input: any, opts: any) => AsyncIterable<any> }>
    conversationHistory: BaseMessage[]
  }
  const executor = await buildAgent()
  const input = { chat_history: [...(conversationHistory ?? []), new HumanMessage(state.message)] }
  const usage: TokenUsage = { prompt: 0, completion: 0, total: 0, cached: 0 }
  let fullResponse = ''
  let streamEnabled = true

  const eventStream = executor.streamEvents(input, { version: 'v2', signal })
  for await (const event of eventStream as AsyncIterable<StreamEvent & { data?: any }>) {
    if (signal?.aborted) break
    if (event.event === 'on_tool_start') {
      streamEnabled = false
      const name = event.name || 'unknown'
      traceRecorder.add({ step: stepCounter.value++, type: 'tool_start', name })
      await onEvent({ type: 'tool_start', name })
    } else if (event.event === 'on_tool_end') {
      fullResponse = ''
      streamEnabled = true
      const name = event.name || 'unknown'
      traceRecorder.add({ step: stepCounter.value++, type: 'tool_end', name, durationMs: undefined })
      await onEvent({ type: 'tool_end', name })
    } else if (event.event === 'on_chat_model_stream') {
      const data = event.data
      const chunk = data?.chunk
      const text = chunk?.content
      let piece: string | null = null
      if (typeof text === 'string') piece = text
      else if (Array.isArray(text)) {
        piece = text.map((p: any) => typeof p === 'string' ? p : p?.text ?? '').join('')
      }
      if (piece && streamEnabled) {
        fullResponse += piece
        await onEvent({ type: 'chunk', content: piece })
      }
    } else if (event.event === 'on_chat_model_end') {
      const msg = event.data?.output as { toJSON?: () => { kwargs?: any } } | undefined
      const kwargs = msg?.toJSON?.()?.kwargs as any
      const um = kwargs?.usage_metadata
      const ru = kwargs?.response_metadata?.usage
      if (um) {
        usage.prompt += um.input_tokens ?? 0
        usage.completion += um.output_tokens ?? 0
        usage.total += um.total_tokens ?? (usage.prompt + usage.completion)
        usage.cached += um.input_token_details?.cache_read ?? 0
      } else if (ru) {
        usage.prompt += ru.prompt_tokens ?? 0
        usage.completion += ru.completion_tokens ?? 0
        usage.total += ru.total_tokens ?? (usage.prompt + usage.completion)
        usage.cached += ru.prompt_tokens_details?.cached_tokens ?? ru.prompt_cache_hit_tokens ?? 0
      }
    }
  }

  return { rawOutput: fullResponse, usage }
}

export function buildChatGraph() {
  const graph = new StateGraph(PlannerState)
    .addNode('router', async (state: typeof PlannerState.State) => {
      let route = isPlanningRequest(state.message) ? 'planning' : 'general'
      let city = route === 'planning' ? extractCityFromMessage(state.message) : state.city
      if (route === 'planning' && !city) {
        // 多轮修改场景 message 可能不包含城市名（"第二天能加个火锅吗"）
        // 从对话历史里找（turn 1 user 消息含"成都"）
        city = extractCityFromHistory(state.conversationHistory ?? [])
        // 还找不到：回退到 general 由 legacy agent 处理
        if (!city) route = 'general'
      }
      return { route, city }
    })
    .addNode('research', researchNode)
    .addNode('chat_planner', chatPlannerNode)
    .addNode('legacy_agent', legacyAgentNode)

  graph.addEdge('__start__', 'router')
  graph.addConditionalEdges('router', (state: typeof PlannerState.State) =>
    state.route === 'planning' ? 'research' : 'legacy_agent',
  )
  graph.addEdge('research', 'chat_planner')
  graph.addEdge('chat_planner', END)
  graph.addEdge('legacy_agent', END)

  return graph.compile()
}