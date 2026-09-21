package com.trip.backend.service.agent.tools;

import com.trip.backend.service.llm.LlmClient;

import java.util.Map;

/**
 * Agent 业务工具统一接口（对应 Python services/agent/tools/*.py）。
 *
 * 每个工具：name/description/spec 用于 bind_tools；execute 做真实工作（抛异常由
 * ResilienceWrapper 兜底）；fallback 返回降级文案；韧性参数对齐 Python with_resilience。
 */
public interface AgentTool {

    /** 工具名（与 Python @tool 同名）。 */
    String name();

    /** 工具描述（LLM 何时调用）。 */
    String description();

    /** LLM 绑定用的参数 schema。 */
    LlmClient.ToolSpec spec();

    /** 真实执行；失败抛异常，由 ResilienceWrapper 捕获后返回 fallback。 */
    String execute(Map<String, Object> args) throws Exception;

    /** 降级文案（超时/重试失败/熔断时返回）。 */
    String fallback();

    /** 超时秒数。 */
    default long timeoutSec() {
        return 10;
    }

    /** 重试次数（不含首次）。 */
    default int retries() {
        return 1;
    }

    /** 熔断失败阈值。 */
    default int circuitThreshold() {
        return 5;
    }

    /** 熔断恢复秒数。 */
    default long circuitRecoverySec() {
        return 30;
    }
}
