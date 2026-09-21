package com.trip.backend.service.agent;

/**
 * Research Agent（对应 Python agents/research_agent.py）。
 *
 * 并行调 5 工具（attractions/food/hotels/weather/distance）收集候选池。
 * 默认实现返回空 bundle；真实工具收集在阶段 4 挂接。
 */
public interface ResearchAgent {

    /** 输入。 */
    record Input(String city, int days, int budget) {}

    /** 输出。 */
    record Output(ResearchBundle bundle, String error) {
        public static Output ok(ResearchBundle b) {
            return new Output(b, null);
        }
        public static Output fail(String err) {
            return new Output(ResearchBundle.empty(), err);
        }
    }

    Output run(Input input);
}
