package com.trip.backend.service.agent;

import com.trip.backend.domain.entity.Trip;
import com.trip.backend.domain.entity.User;
import com.trip.backend.service.TripService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * 行程持久化服务
 *
 * 对应 Python services/agent/trip_persistence.py
 *
 * 职责：
 * - _persist_trip 语义
 * - trip_planned 事件
 * - trip_diff 构建
 */
@Service
public class TripPersistenceService {

    private static final Logger log = LoggerFactory.getLogger(TripPersistenceService.class);

    private final TripService tripService;

    public TripPersistenceService(TripService tripService) {
        this.tripService = tripService;
    }

    /**
     * 持久化行程（plan 成功）
     *
     * @param userId 用户 ID
     * @param fromCity 出发城市
     * @param parsed 解析后的行程内容
     * @param budget 预算
     * @return 持久化的行程
     */
    public Trip persistTrip(Long userId, String fromCity, Map<String, Object> parsed, int budget) {
        log.info("[TripPersistenceService] Persisting trip: userId={}, city={}, budget={}",
            userId, fromCity, budget);

        // TODO: D8 实现后补充具体字段提取
        String city = (String) parsed.get("city");
        Integer days = (Integer) parsed.get("days");

        Trip trip = tripService.createTrip(userId, fromCity, city, days != null ? days : 1, budget, parsed);

        // 发送 trip_planned 事件
        // TODO: D8 集成 EventSink

        return trip;
    }

    /**
     * 持久化候选行程（modify/patch）
     *
     * @param userId 用户 ID
     * @param parentTripId 父行程 ID
     * @param parsed 解析后的行程内容
     * @param budget 预算
     * @return 候选行程
     */
    public Trip persistCandidateTrip(Long userId, Long parentTripId, Map<String, Object> parsed, int budget) {
        log.info("[TripPersistenceService] Persisting candidate trip: userId={}, parentTripId={}",
            userId, parentTripId);

        Trip candidate = tripService.createCandidateTrip(userId, parentTripId, parsed);

        // 构建 trip_diff
        // TODO: D8 实现后补充

        return candidate;
    }

    /**
     * 构建 trip_diff
     *
     * @param oldSpot 原景点
     * @param newSpot 新景点
     * @param day 天数
     * @param period 时段
     * @return trip_diff 映射
     */
    public Map<String, Object> buildTripDiff(String oldSpot, String newSpot, int day, String period) {
        return Map.of(
            "day", day,
            "period", period != null ? period : "(无)",
            "oldSpot", oldSpot != null ? oldSpot : "(无)",
            "newSpot", newSpot != null ? newSpot : "(无)"
        );
    }
}
