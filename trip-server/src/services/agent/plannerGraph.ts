// trip-server/src/services/agent/plannerGraph.ts
import { StateGraph, END } from '@langchain/langgraph'
import { PlannerState } from './state'
import { researchNode } from './nodes/research'
import { plannerNode, retryPlannerNode } from './nodes/planner'
import { validateOutput } from './nodes/validate'

export function buildPlannerGraph() {
  const graph = new StateGraph(PlannerState)
    .addNode('research', researchNode)
    .addNode('planner', plannerNode)
    .addNode('validate', async (state: typeof PlannerState.State) => {
      try {
        const { parsed } = validateOutput(state.rawOutput!)
        return { parsed }
      } catch (e) {
        const errMsg = e instanceof Error ? e.message : String(e)
        return { parsed: undefined, errors: [...state.errors, errMsg] }
      }
    })
    .addNode('retry_planner', retryPlannerNode)

  graph.addEdge('__start__', 'research')
  graph.addEdge('research', 'planner')
  graph.addEdge('planner', 'validate')
  graph.addConditionalEdges('validate', (state: typeof PlannerState.State) => {
    if (state.parsed) return END
    return 'retry_planner'
  })
  // retry 后直接结束（避免无限循环，外层 recommend() 再做二次校验）
  graph.addEdge('retry_planner', END)

  return graph.compile()
}