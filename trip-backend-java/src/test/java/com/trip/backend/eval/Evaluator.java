package com.trip.backend.eval;

import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.EvalResult;
import com.trip.backend.eval.types.Fixture;

/**
 * Evaluator 接口
 */
@FunctionalInterface
public interface Evaluator {

    /**
     * 评估 Agent 输出
     *
     * @param output  Agent 输出
     * @param fixture 测试用例
     * @return 评估结果
     */
    EvalResult evaluate(AgentOutput output, Fixture fixture);
}
