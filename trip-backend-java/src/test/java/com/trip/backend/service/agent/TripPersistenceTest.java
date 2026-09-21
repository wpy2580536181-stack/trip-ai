package com.trip.backend.service.agent;

import com.trip.backend.domain.entity.Trip;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-D8 判定 3/4：trip_planned/trip_diff 事件字段 + 落库真新增。
 * 用 in-memory saver（模拟 TripRepository.save），真实 PG 验证标 [需真实环境]。
 */
class TripPersistenceTest {

    /** 记录落库行 + 事件。 */
    static class Harness {
        final List<Trip> saved = new ArrayList<>();
        final List<Map<String, Object>> events = new ArrayList<>();
        TripPersistenceService svc;
        Harness() {
            svc = new TripPersistenceService(t -> {
                t.setId((long) (saved.size() + 1));
                saved.add(t);
                return t;
            });
            svc.registerSink((type, payload) -> events.add(Map.of("type", type, "payload", payload)));
        }
    }

    @Test
    void tripPlannedEventFieldsCorrect() {
        Harness h = new Harness();
        Long id = h.svc.savePlan(42L, "成都", 3, 2000,
            Map.of("city", "成都"), "completed", null);

        assertNotNull(id);
        assertEquals(1, h.saved.size(), "应新增 1 行");
        assertEquals("completed", h.saved.get(0).getStatus());
        assertEquals(42L, h.saved.get(0).getUserId());

        assertEquals(1, h.events.size());
        Map<String, Object> ev = h.events.get(0);
        assertEquals("trip_planned", ev.get("type"));
        @SuppressWarnings("unchecked")
        Map<String, Object> p = (Map<String, Object>) ev.get("payload");
        assertEquals(id, p.get("trip_id"));
        assertEquals(42L, p.get("user_id"));
        assertEquals("成都", p.get("city"));
        assertEquals(3, p.get("days"));
        assertEquals("completed", p.get("status"));
    }

    @Test
    void tripDiffEventOnModification() {
        Harness h = new Harness();
        Long baseId = h.svc.savePlan(1L, "北京", 2, 1000, Map.of(), "completed", null);
        Long newId = h.svc.saveModification(1L, "北京", 2, 1000,
            Map.of("changed", true), baseId, Map.of("day2", "replaced"));

        // 先 trip_planned ×2（savePlan 内部），再 trip_diff ×1
        assertEquals(3, h.events.size());
        Map<String, Object> last = h.events.get(2);
        assertEquals("trip_diff", last.get("type"));
        @SuppressWarnings("unchecked")
        Map<String, Object> p = (Map<String, Object>) last.get("payload");
        assertEquals(newId, p.get("trip_id"));
        assertEquals(baseId, p.get("parent_trip_id"));
        assertTrue(p.containsKey("diff"));
        // 新版本 status=candidate，parent 指向旧版
        assertEquals("candidate", h.saved.get(1).getStatus());
        assertEquals(baseId, h.saved.get(1).getParentTripId());
    }
}
