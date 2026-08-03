package com.trip.backend.service;

import com.trip.backend.domain.entity.Trip;
import com.trip.backend.domain.entity.User;
import com.trip.backend.domain.repository.TripRepository;
import com.trip.backend.utils.AppException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Flux;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 行程服务（对应 Python services/trip_service.py）
 */
@Service
public class TripService {

    private static final Logger log = LoggerFactory.getLogger(TripService.class);

    private final TripRepository tripRepository;

    public TripService(TripRepository tripRepository) {
        this.tripRepository = tripRepository;
    }

    /**
     * 获取行程历史
     */
    public Page<Trip> getTrips(Long userId, int page, int pageSize) {
        return tripRepository.findByUserIdOrderByCreatedAtDesc(
            userId, PageRequest.of(page - 1, pageSize)
        );
    }

    /**
     * 获取行程详情
     */
    public Trip getTrip(Long userId, Long tripId) {
        Trip trip = tripRepository.findByIdAndUserId(tripId, userId)
            .orElseThrow(() -> AppException.notFound("行程不存在"));
        return trip;
    }

    /**
     * 获取行程版本链
     */
    public List<Trip> getTripVersions(Long userId, Long tripId) {
        Trip trip = tripRepository.findByIdAndUserId(tripId, userId)
            .orElseThrow(() -> AppException.notFound("行程不存在"));

        List<Trip> versions = new java.util.ArrayList<>();
        versions.add(trip);

        // 查找同 parent_trip_id 的后续版本
        if (trip.getParentTripId() != null) {
            versions.addAll(tripRepository.findByIdAndUserId(trip.getParentTripId(), userId)
                .map(List::of)
                .orElse(List.of()));
        }

        return versions;
    }

    /**
     * 创建新行程
     */
    @Transactional
    public Trip createTrip(Long userId, String fromCity, String city, int days, int budget,
                          java.util.Map<String, Object> content) {
        Trip trip = Trip.create(userId, city, days, budget);
        trip.setFromCity(fromCity);
        trip.setContent(content);
        trip.setStatus("completed");
        return tripRepository.save(trip);
    }

    /**
     * 创建候选行程（修改/升级时使用）
     */
    @Transactional
    public Trip createCandidateTrip(Long userId, Long parentTripId, java.util.Map<String, Object> content) {
        Trip parent = tripRepository.findById(parentTripId)
            .orElseThrow(() -> AppException.notFound("父行程不存在"));

        Trip candidate = new Trip();
        candidate.setUserId(userId);
        candidate.setFromCity(parent.getFromCity());
        candidate.setCity(parent.getCity());
        candidate.setDays(parent.getDays());
        candidate.setBudget(parent.getBudget());
        candidate.setContent(content);
        candidate.setStatus("candidate");
        candidate.setParentTripId(parentTripId);
        return tripRepository.save(candidate);
    }

    /**
     * 确认行程（candidate → completed）
     */
    @Transactional
    public Trip confirmTrip(Long userId, Long tripId) {
        Trip trip = tripRepository.findById(tripId)
            .orElseThrow(() -> AppException.notFound("行程不存在"));

        if (!"candidate".equals(trip.getStatus())) {
            throw AppException.badRequest("仅 candidate 状态行程可确认");
        }

        trip.setStatus("completed");
        return tripRepository.save(trip);
    }

    /**
     * 丢弃行程（candidate → discarded）
     */
    @Transactional
    public Trip discardTrip(Long userId, Long tripId) {
        Trip trip = tripRepository.findById(tripId)
            .orElseThrow(() -> AppException.notFound("行程不存在"));

        if (!"candidate".equals(trip.getStatus())) {
            throw AppException.badRequest("仅 candidate 状态行程可丢弃");
        }

        trip.setStatus("discarded");
        return tripRepository.save(trip);
    }

    /**
     * 删除行程
     */
    @Transactional
    public void deleteTrip(Long userId, Long tripId) {
        Trip trip = tripRepository.findByIdAndUserId(tripId, userId)
            .orElseThrow(() -> AppException.notFound("行程不存在"));
        tripRepository.delete(trip);
    }

    // ==================== Recommend（G4 简化实现）====================

    /**
     * 行程推荐（G4 简化实现）
     *
     * @param userId 用户 ID
     * @param city 目的地城市
     * @param budget 预算
     * @param days 天数
     * @return 推荐结果（Format A）
     */
    public Map<String, Object> recommend(Long userId, String city, int budget, int days) {
        log.info("[TripService] 行程推荐: userId={}, city={}, days={}, budget={}",
            userId, city, days, budget);

        try {
            Map<String, Object> plan = Map.of(
                "title", city + days + "日游",
                "city", city,
                "days", days,
                "budget", budget,
                "dailyItinerary", List.of(),
                "budgetBreakdown", Map.of(
                    "accommodation", budget * 25 / 100,
                    "food", budget * 20 / 100,
                    "transportation", budget * 15 / 100,
                    "tickets", budget * 30 / 100,
                    "other", budget * 10 / 100
                ),
                "totalBudget", budget,
                "tips", List.of("提前订票", "注意天气"),
                "warnings", List.of()
            );

            Map<String, Object> response = new LinkedHashMap<>();
            response.put("success", true);
            response.put("data", plan);

            return response;

        } catch (Exception e) {
            log.error("[TripService] 推荐失败", e);
            throw AppException.badRequest("行程推荐失败：" + e.getMessage());
        }
    }
}
