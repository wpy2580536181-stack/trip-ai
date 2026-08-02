package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * 触发工具（四升级工具）
 *
 * 对应 Python services/agent/trigger_tools.py
 *
 * 功能：
 * - trigger_plan: 生成行程
 * - trigger_modify: 修改行程
 * - trigger_patch: 局部修改
 * - select_skill: 选择技能
 */
@Service
public class TriggerTools {

    private static final Logger log = LoggerFactory.getLogger(TriggerTools.class);

    private final Orchestrator orchestrator;

    public TriggerTools(Orchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    /**
     * 触发行程生成
     *
     * @param city 城市
     * @param days 天数
     * @param budget 预算
     * @return 生成结果
     */
    public CompletableFuture<PlanResult> triggerPlan(String city, int days, int budget, Long userId) {
        log.info("[TriggerTools] trigger_plan: city={}, days={}, budget={}", city, days, budget);

        PlanRequest request = new PlanRequest(city, days, budget, null, List.of(), userId);
        return orchestrator.plan(request);
    }

    /**
     * 触发行程修改（全量）
     *
     * @param tripId 行程 ID
     * @param feedback 修改反馈
     * @return 修改结果
     */
    public CompletableFuture<PlanResult> triggerModify(Long tripId, String feedback, Long userId) {
        log.info("[TriggerTools] trigger_modify: tripId={}, feedback={}", tripId, feedback);

        // TODO: D8 实现后补充
        return CompletableFuture.failedFuture(new UnsupportedOperationException("trigger_modify not implemented"));
    }

    /**
     * 触发局部修改（patch）
     *
     * @param tripId 行程 ID
     * @param day 天数
     * @param period 时段
     * @param oldSpot 原景点
     * @param newSpot 新景点
     * @return 修改结果
     */
    public CompletableFuture<PlanResult> triggerPatch(Long tripId, int day, String period,
                                                       String oldSpot, String newSpot, Long userId) {
        log.info("[TriggerTools] trigger_patch: tripId={}, day={}, period={}, {} -> {}",
            tripId, day, period, oldSpot, newSpot);

        // TODO: D8 实现后补充
        return CompletableFuture.failedFuture(new UnsupportedOperationException("trigger_patch not implemented"));
    }

    /**
     * 触发技能选择
     *
     * @param skillName 技能名
     * @param input 输入
     * @return 技能执行结果
     */
    public CompletableFuture<Map<String, Object>> selectSkill(String skillName, Map<String, Object> input) {
        log.info("[TriggerTools] select_skill: skill={}", skillName);

        // TODO: D8 实现后补充
        return CompletableFuture.failedFuture(new UnsupportedOperationException("select_skill not implemented"));
    }
}
