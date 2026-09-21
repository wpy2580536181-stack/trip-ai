package com.trip.backend.service.agent;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * ResearchAgent 默认实现（占位）。
 *
 * 真实 5 工具并行收集（attractions/food/hotels/weather/distance）在阶段 4 挂接；
 * 当前返回空 bundle，ReviewService 据此跳过封闭世界校验。
 */
@Component
public class DefaultResearchAgent implements ResearchAgent {

    private static final Logger log = LoggerFactory.getLogger(DefaultResearchAgent.class);

    @Override
    public Output run(Input input) {
        log.info("[DefaultResearchAgent] research city={} days={}（占位实现）", input.city(), input.days());
        return Output.ok(ResearchBundle.empty());
    }
}
