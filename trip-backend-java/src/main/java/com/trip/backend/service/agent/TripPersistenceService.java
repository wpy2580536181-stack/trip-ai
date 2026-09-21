package com.trip.backend.service.agent;

import com.trip.backend.domain.entity.Trip;
import com.trip.backend.domain.repository.TripRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * 行程落库服务（对应 Python TripPersistenceService）。
 *
 *  - plan 成功 → trips 表真落库（status=completed/candidate）
 *  - 发 trip_planned / trip_diff 事件
 *  - 修复"返回假 id、variants=List.of()"：落库后返回真实 trip.id
 */
@Service
public class TripPersistenceService {

    private static final Logger log = LoggerFactory.getLogger(TripPersistenceService.class);

    /** 事件接收器（SSE 推送 / 测试断言用）。 */
    public interface EventSink {
        void emit(String eventType, Map<String, Object> payload);
    }

    private final List<EventSink> sinks = new ArrayList<>();
    private final Function<Trip, Trip> saver;

    /** 生产构造：用 TripRepository.save。 */
    public TripPersistenceService(TripRepository tripRepository) {
        this(tripRepository::save);
    }

    /** 测试构造：注入 saver lambda。 */
    public TripPersistenceService(Function<Trip, Trip> saver) {
        this.saver = saver;
    }

    public void registerSink(EventSink sink) {
        sinks.add(sink);
    }

    /**
     * 落库一份规划行程，返回真实 trip.id。
     *
     * @param status "completed" 或 "candidate"
     */
    public Long savePlan(Long userId, String city, Integer days, Integer budget,
                         Map<String, Object> plan, String status, Long parentTripId) {
        Trip trip = Trip.create(userId, city, days, budget);
        trip.setContent(plan);
        trip.setStatus(status);
        if (parentTripId != null) {
            trip.setParentTripId(parentTripId);
        }
        Trip saved = saver.apply(trip);
        log.info("[TripPersistence] saved trip id={} userId={} city={} status={}",
            saved.getId(), userId, city, status);

        emit("trip_planned", Map.of(
            "trip_id", saved.getId(),
            "user_id", userId,
            "city", city,
            "days", days,
            "budget", budget,
            "status", status
        ));
        return saved.getId();
    }

    /** 修改后落库新版本并发 trip_diff。 */
    public Long saveModification(Long userId, String city, Integer days, Integer budget,
                                 Map<String, Object> newPlan, Long parentTripId,
                                 Map<String, Object> diff) {
        Long newId = savePlan(userId, city, days, budget, newPlan, "candidate", parentTripId);
        emit("trip_diff", Map.of(
            "trip_id", newId,
            "parent_trip_id", parentTripId,
            "user_id", userId,
            "diff", diff == null ? Map.of() : diff
        ));
        return newId;
    }

    private void emit(String type, Map<String, Object> payload) {
        for (EventSink sink : sinks) {
            try {
                sink.emit(type, payload);
            } catch (Exception e) {
                log.warn("[TripPersistence] sink 投递失败 type={}: {}", type, e.getMessage());
            }
        }
    }
}
