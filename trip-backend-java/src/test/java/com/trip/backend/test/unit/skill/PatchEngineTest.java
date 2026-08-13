package com.trip.backend.test.unit.skill;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.infra.skill.patch.PatchEngine;
import com.trip.backend.infra.skill.patch.PatchError;
import com.trip.backend.infra.skill.patch.PatchEngine.PatchParams;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/**
 * PatchEngine 单元测试
 *
 * 对标 Python: test_patch_engine.py
 */
public class PatchEngineTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private JsonNode createSampleTrip() {
        String tripJson = """
            {
                "dailyItinerary": [
                    {"day": 1, "morning": {"spot": "故宫", "duration": "3h", "ticket": "60元", "transportation": "地铁", "description": "明清皇宫"}, "afternoon": {"spot": "景山公园", "duration": "1h", "ticket": "2元", "transportation": "步行", "description": "俯瞰故宫"}, "evening": {"spot": "王府井", "duration": "2h", "ticket": "", "transportation": "地铁", "description": "购物美食"}},
                    {"day": 2, "morning": {"spot": "天安门广场", "duration": "1h", "ticket": "", "transportation": "地铁", "description": "升旗仪式"}, "afternoon": {"spot": "国家博物馆", "duration": "3h", "ticket": "", "transportation": "步行", "description": "历史文化"}, "evening": {"spot": "前门大街", "duration": "2h", "ticket": "", "transportation": "步行", "description": "老北京风情"}}
                ]
            }
            """;
        try {
            return MAPPER.readTree(tripJson);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    @Test
    void testReplaceSlotSuccess() {
        PatchEngine engine = new PatchEngine(MAPPER);
        JsonNode trip = createSampleTrip();

        JsonNode result = engine.applyPatch(trip, "replace_slot", 1,
            PatchParams.forReplace("afternoon", "北海公园", "皇家园林"));

        assertEquals("北海公园", result.get("dailyItinerary").get(0).get("afternoon").get("spot").asText());
        assertEquals("皇家园林", result.get("dailyItinerary").get(0).get("afternoon").get("description").asText());
        // 其他时段不变
        assertEquals("故宫", result.get("dailyItinerary").get(0).get("morning").get("spot").asText());
    }

    @Test
    void testRemoveSlotSuccess() {
        PatchEngine engine = new PatchEngine(MAPPER);
        JsonNode trip = createSampleTrip();

        JsonNode result = engine.applyPatch(trip, "remove_slot", 1,
            PatchParams.forRemove("evening"));

        assertEquals("", result.get("dailyItinerary").get(0).get("evening").get("spot").asText());
        assertEquals("", result.get("dailyItinerary").get(0).get("evening").get("description").asText());
    }

    @Test
    void testSwapSlotSuccess() {
        PatchEngine engine = new PatchEngine(MAPPER);
        JsonNode trip = createSampleTrip();

        JsonNode result = engine.applyPatch(trip, "swap_slot", 1,
            PatchParams.forSwap("morning", "afternoon"));

        // morning 和 afternoon 应该交换
        assertEquals("景山公园", result.get("dailyItinerary").get(0).get("morning").get("spot").asText());
        assertEquals("故宫", result.get("dailyItinerary").get(0).get("afternoon").get("spot").asText());
    }

    @Test
    void testReplaceSlotDuplicateError() {
        PatchEngine engine = new PatchEngine(MAPPER);
        JsonNode trip = createSampleTrip();

        // 第 1 天 morning 已有"故宫"，再 replace afternoon 为"故宫"应该报错
        assertThrows(PatchError.class, () ->
            engine.applyPatch(trip, "replace_slot", 1,
                PatchParams.forReplace("afternoon", "故宫", "desc"))
        );
    }

    @Test
    void testInvalidPeriodError() {
        PatchEngine engine = new PatchEngine(MAPPER);
        JsonNode trip = createSampleTrip();

        assertThrows(PatchError.class, () ->
            engine.applyPatch(trip, "replace_slot", 1,
                PatchParams.forReplace("invalid_period", "test", ""))
        );
    }

    @Test
    void testSwapSamePeriodError() {
        PatchEngine engine = new PatchEngine(MAPPER);
        JsonNode trip = createSampleTrip();

        assertThrows(PatchError.class, () ->
            engine.applyPatch(trip, "swap_slot", 1,
                PatchParams.forSwap("morning", "morning"))
        );
    }

    @Test
    void testUnsupportedOpError() {
        PatchEngine engine = new PatchEngine(MAPPER);
        JsonNode trip = createSampleTrip();

        assertThrows(PatchError.class, () ->
            engine.applyPatch(trip, "invalid_op", 1, PatchParams.forReplace("morning", "test", ""))
        );
    }

    @Test
    void testDayNotFoundError() {
        PatchEngine engine = new PatchEngine(MAPPER);
        JsonNode trip = createSampleTrip();

        assertThrows(PatchError.class, () ->
            engine.applyPatch(trip, "replace_slot", 99,
                PatchParams.forReplace("morning", "test", ""))
        );
    }

    @Test
    void testDeepCopyNoSideEffect() {
        PatchEngine engine = new PatchEngine(MAPPER);
        JsonNode trip = createSampleTrip();
        JsonNode original = trip.deepCopy();

        engine.applyPatch(trip, "replace_slot", 1,
            PatchParams.forReplace("afternoon", "新景点", ""));

        // 原 trip 不应被修改
        assertEquals(original, trip);
    }
}
