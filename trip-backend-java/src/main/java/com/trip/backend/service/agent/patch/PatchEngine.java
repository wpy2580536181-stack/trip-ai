package com.trip.backend.service.agent.patch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.Map;

/**
 * PatchEngine 补丁引擎
 *
 * 对应 Python services/agent/patch_engine.py
 *
 * 支持操作：
 * - replace_slot：替换槽位
 * - remove_slot：移除槽位
 * - swap_slot：交换槽位
 */
@Service
public class PatchEngine {

    private static final Logger log = LoggerFactory.getLogger(PatchEngine.class);

    // 支持的操作
    public static final String OP_REPLACE = "replace_slot";
    public static final String OP_REMOVE = "remove_slot";
    public static final String OP_SWAP = "swap_slot";

    /**
     * 应用补丁
     *
     * @param plan 原计划
     * @param patches 补丁列表
     * @return 修改后的计划
     */
    public Map<String, Object> applyPatch(Map<String, Object> plan, java.util.List<Map<String, Object>> patches) {
        if (plan == null || patches == null || patches.isEmpty()) {
            return plan;
        }

        Map<String, Object> result = new java.util.LinkedHashMap<>(plan);

        for (Map<String, Object> patch : patches) {
            try {
                String op = (String) patch.get("op");
                if (op == null) {
                    throw new PatchError("Missing 'op' field");
                }

                switch (op) {
                    case OP_REPLACE -> applyReplace(result, patch);
                    case OP_REMOVE -> applyRemove(result, patch);
                    case OP_SWAP -> applySwap(result, patch);
                    default -> throw new PatchError("Unsupported operation: " + op);
                }

            } catch (PatchError e) {
                log.error("[PatchEngine] Patch failed: {}", patch, e);
                throw e; // 抛出 PatchError 触发降级 modify
            }
        }

        return result;
    }

    /**
     * replace_slot：替换槽位
     */
    private void applyReplace(Map<String, Object> plan, Map<String, Object> patch) {
        // TODO: D9 实现后补充
        Object day = patch.get("day");
        Object period = patch.get("period");
        Object newSpot = patch.get("new_spot");

        log.debug("[PatchEngine] replace_slot: day={}, period={}, new_spot={}", day, period, newSpot);

        // 占位：实际需修改 plan 的对应 day/period 槽位
    }

    /**
     * remove_slot：移除槽位
     */
    private void applyRemove(Map<String, Object> plan, Map<String, Object> patch) {
        // TODO: D9 实现后补充
        Object day = patch.get("day");
        Object period = patch.get("period");

        log.debug("[PatchEngine] remove_slot: day={}, period={}", day, period);
    }

    /**
     * swap_slot：交换槽位
     */
    private void applySwap(Map<String, Object> plan, Map<String, Object> patch) {
        // TODO: D9 实现后补充
        Object day = patch.get("day");
        Object period1 = patch.get("period_1");
        Object period2 = patch.get("period_2");

        log.debug("[PatchEngine] swap_slot: day={}, period_1={}, period_2={}", day, period1, period2);
    }

    /**
     * PatchError
     */
    public static class PatchError extends RuntimeException {
        public PatchError(String message) {
            super(message);
        }
    }
}
