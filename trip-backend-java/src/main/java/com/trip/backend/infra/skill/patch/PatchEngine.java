package com.trip.backend.infra.skill.patch;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.util.Iterator;

/**
 * Patch 引擎：直接对行程 JSON 应用结构化修改
 *
 * 对应 Python: patch_engine.py (apply_patch)
 *
 * 用于 Slot 级局部修改，不走 LLM 重生成。
 *
 * 支持操作：
 * - replace_slot: 替换指定时段景点
 * - remove_slot: 清空指定时段
 * - swap_slot: 交换两个时段内容
 *
 * 校验规则：
 * - period 必须为 morning/afternoon/evening
 * - replace_slot 需要 spot_name
 * - swap_slot 不能同时段
 * - 去重校验（同天其他时段不能有相同景点）
 */
public class PatchEngine {

    private static final String[] VALID_PERIODS = {"morning", "afternoon", "evening"};

    private final ObjectMapper objectMapper;

    public PatchEngine(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /**
     * 应用一个 patch 操作
     *
     * @param trip 原行程 JSON（不会被修改）
     * @param op   操作类型（replace_slot / remove_slot / swap_slot）
     * @param day  目标天数（从 1 开始）
     * @param params 操作参数
     *               - period: "morning" / "afternoon" / "evening"（replace/remove 需要）
     *               - spot_name: 景点名称（replace 需要）
     *               - description: 描述（replace 可选）
     *               - period_b: 第二个时段（swap 需要）
     * @return 修改后的新行程 JSON
     * @throws PatchError 校验不通过或操作不合法
     */
    public JsonNode applyPatch(JsonNode trip, String op, int day, PatchParams params) throws PatchError {
        if (trip == null || trip.isNull()) {
            throw new PatchError("行程不能为空");
        }

        if (day < 1) {
            throw new PatchError("天数必须 >= 1");
        }

        return switch (op) {
            case "replace_slot" -> applyReplace(trip, day, params);
            case "remove_slot" -> applyRemove(trip, day, params);
            case "swap_slot" -> applySwap(trip, day, params);
            default -> throw new PatchError("不支持的 patch 操作: " + op);
        };
    }

    /**
     * replace_slot: 替换指定时段景点
     */
    private JsonNode applyReplace(JsonNode trip, int day, PatchParams params) throws PatchError {
        String period = params.period();
        String spotName = params.spotName();

        if (period == null || !isValidPeriod(period)) {
            throw new PatchError("replace_slot 需要有效的 period (morning/afternoon/evening)");
        }
        if (spotName == null || spotName.trim().isEmpty()) {
            throw new PatchError("replace_slot 需要 spot_name");
        }

        JsonNode merged = trip.deepCopy();
        JsonNode dayObj = getDay(merged, day);
        ObjectNode slot = (ObjectNode) dayObj.get(period);
        if (slot == null) {
            slot = objectMapper.createObjectNode();
        }

        // 去重校验（同天其他时段）
        validateNoDuplicate(merged, day, spotName, period);

        slot.put("spot", spotName);
        if (params.description() != null) {
            slot.put("description", params.description());
        }
        ((ObjectNode) dayObj).set(period, slot);

        logPatch("replace day=%d period=%s spot=%s", day, period, spotName);
        return merged;
    }

    /**
     * remove_slot: 清空指定时段
     */
    private JsonNode applyRemove(JsonNode trip, int day, PatchParams params) throws PatchError {
        String period = params.period();

        if (period == null || !isValidPeriod(period)) {
            throw new PatchError("remove_slot 需要有效的 period (morning/afternoon/evening)");
        }

        JsonNode merged = trip.deepCopy();
        JsonNode dayObj = getDay(merged, day);
        ObjectNode emptySlot = objectMapper.createObjectNode();
        emptySlot.put("spot", "");
        emptySlot.put("duration", "");
        emptySlot.put("ticket", "");
        emptySlot.put("transportation", "");
        emptySlot.put("description", "");
        ((ObjectNode) dayObj).set(period, emptySlot);

        logPatch("remove day=%d period=%s", day, period);
        return merged;
    }

    /**
     * swap_slot: 交换两个时段内容
     */
    private JsonNode applySwap(JsonNode trip, int day, PatchParams params) throws PatchError {
        String periodA = params.period();
        String periodB = params.periodB();

        if (periodA == null || !isValidPeriod(periodA)) {
            throw new PatchError("swap_slot 需要有效的 period_a (morning/afternoon/evening)");
        }
        if (periodB == null || !isValidPeriod(periodB)) {
            throw new PatchError("swap_slot 需要有效的 period_b (morning/afternoon/evening)");
        }
        if (periodA.equals(periodB)) {
            throw new PatchError("不能对调同一个时段");
        }

        JsonNode merged = trip.deepCopy();
        JsonNode dayObj = getDay(merged, day);
        ObjectNode slotA = (ObjectNode) dayObj.get(periodA);
        ObjectNode slotB = (ObjectNode) dayObj.get(periodB);

        // 交换
        ((ObjectNode) dayObj).set(periodA, slotB);
        ((ObjectNode) dayObj).set(periodB, slotA);

        logPatch("swap day=%d %s<->%s", day, periodA, periodB);
        return merged;
    }

    // ---- 辅助方法 ----

    /**
     * 获取指定天的行程对象
     */
    private JsonNode getDay(JsonNode trip, int day) throws PatchError {
        ArrayNode itinerary = (ArrayNode) trip.get("dailyItinerary");
        if (itinerary == null) {
            throw new PatchError("行程缺少 dailyItinerary 字段");
        }

        for (JsonNode d : itinerary) {
            if (d.get("day") != null && d.get("day").asInt() == day) {
                return d;
            }
        }

        throw new PatchError("第 " + day + " 天不存在");
    }

    /**
     * 校验 period 是否有效
     */
    private boolean isValidPeriod(String period) {
        for (String p : VALID_PERIODS) {
            if (p.equals(period)) {
                return true;
            }
        }
        return false;
    }

    /**
     * 检查同一天内是否有重复景点（跨时段去重）
     */
    private void validateNoDuplicate(JsonNode trip, int day, String newSpot, String excludePeriod) throws PatchError {
        ArrayNode itinerary = (ArrayNode) trip.get("dailyItinerary");
        if (itinerary == null) {
            return;
        }

        for (JsonNode d : itinerary) {
            if (d.get("day") != null && d.get("day").asInt() == day) {
                for (String period : VALID_PERIODS) {
                    if (period.equals(excludePeriod)) {
                        continue;
                    }
                    JsonNode slot = d.get(period);
                    if (slot != null && slot.has("spot")) {
                        String spot = slot.get("spot").asText();
                        if (newSpot.equals(spot)) {
                            throw new PatchError("第 " + day + " 天 " + period + " 已存在景点「" + newSpot + "」，请选择其他景点");
                        }
                    }
                }
            }
        }
    }

    /**
     * 日志记录
     */
    private void logPatch(String format, Object... args) {
        // TODO: 接入 SLF4J logger
        System.out.println("[patch] " + String.format(format, args));
    }

    /**
     * Patch 参数
     */
    public record PatchParams(
        String period,        // 时段（morning/afternoon/evening）
        String spotName,      // 景点名称（replace 需要）
        String description,   // 描述（replace 可选）
        String periodB        // 第二个时段（swap 需要）
    ) {
        /**
         * 创建 replace_slot 参数
         */
        public static PatchParams forReplace(String period, String spotName, String description) {
            return new PatchParams(period, spotName, description, null);
        }

        /**
         * 创建 remove_slot 参数
         */
        public static PatchParams forRemove(String period) {
            return new PatchParams(period, null, null, null);
        }

        /**
         * 创建 swap_slot 参数
         */
        public static PatchParams forSwap(String periodA, String periodB) {
            return new PatchParams(periodA, null, null, periodB);
        }
    }
}
