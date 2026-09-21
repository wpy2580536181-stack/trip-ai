package com.trip.backend.infra.ai;

import org.springframework.stereotype.Component;

/**
 * Embedding 模型可用性状态（fail-closed，对应 Python mark_embedder_unavailable / load_embedder_force）。
 *
 * - 启动即标记不可用（fail-closed）：所有 embedding 调用直接降级，
 *   避免首个请求卡在模型加载
 * - 后台 warmup() 成功才恢复 AVAILABLE
 * - 预热失败保持降级、不阻塞启动
 */
@Component
public class EmbedderHealth {

    public enum State {
        AVAILABLE,
        UNAVAILABLE
    }

    private volatile State state = State.UNAVAILABLE;
    private volatile String reason = "not warmed up";

    /** 标记模型不可用（fail-closed）。 */
    public void markUnavailable(String reason) {
        this.state = State.UNAVAILABLE;
        this.reason = reason == null ? "unknown" : reason;
    }

    /** 标记模型可用（warmup 成功）。 */
    public void markAvailable() {
        this.state = State.AVAILABLE;
        this.reason = "ok";
    }

    public boolean isAvailable() {
        return state == State.AVAILABLE;
    }

    public State getState() {
        return state;
    }

    public String getReason() {
        return reason;
    }
}
