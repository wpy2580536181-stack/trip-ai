package com.trip.backend.service;

import com.trip.backend.domain.entity.Trip;
import com.trip.backend.domain.entity.User;
import com.trip.backend.domain.repository.TripRepository;
import com.trip.backend.service.agent.Orchestrator;
import com.trip.backend.service.agent.TripPersistenceService;
import com.trip.backend.service.agent.dto.PlanRequest;
import com.trip.backend.service.agent.dto.PlanResult;
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
    private final Orchestrator orchestrator;
    private final TripPersistenceService persistence;

    public TripService(TripRepository tripRepository, Orchestrator orchestrator,
                       TripPersistenceService persistence) {
        this.tripRepository = tripRepository;
        this.orchestrator = orchestrator;
        this.persistence = persistence;
    }

    /**
     * 获取行程历史
     */
    @Transactional(readOnly = true)
    public Page<Trip> getTrips(Long userId, int page, int pageSize) {
        return tripRepository.findByUserIdOrderByCreatedAtDesc(
            userId, PageRequest.of(page - 1, pageSize)
        );
    }

    /**
     * 获取行程详情
     */
    @Transactional(readOnly = true)
    public Trip getTrip(Long userId, Long tripId) {
        Trip trip = tripRepository.findByIdAndUserId(tripId, userId)
            .orElseThrow(() -> AppException.notFound("行程不存在"));
        return trip;
    }

    /**
     * 获取行程版本链
     */
    @Transactional(readOnly = true)
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
        Trip trip = tripRepository.findByIdAndUserId(tripId, userId)
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
        Trip trip = tripRepository.findByIdAndUserId(tripId, userId)
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

    // ==================== Recommend（G4 Agent 编排）====================

    /**
     * 行程推荐（调用 Orchestrator）
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
            // 构造 PlanRequest
            PlanRequest request = new PlanRequest(city, days, budget);

            // 调用 Orchestrator
            PlanResult result = orchestrator.plan(request);

            // 检查是否有错误
            if (result.plan().containsKey("error")) {
                String error = (String) result.plan().get("error");
                log.error("[TripService] Orchestrator 返回错误: {}", error);
                throw AppException.badRequest("行程推荐失败：" + error);
            }

            // 转换为 Format A 响应（对齐 Python 版本）
            Map<String, Object> data = new LinkedHashMap<>();
            // TODO: 保存行程到数据库后，返回真实的 trip.id
            data.put("id", null);
            data.put("city", result.plan().get("city"));
            data.put("days", result.plan().get("days"));
            data.put("totalBudget", result.plan().get("totalBudget"));
            data.put("dailyItinerary", result.plan().get("dailyItinerary"));
            data.put("budgetBreakdown", result.plan().get("budgetBreakdown"));
            data.put("tips", result.plan().get("tips"));
            data.put("warnings", result.plan().get("warnings"));
            data.put("variants", List.of());  // plan_variants 待阶段 4

            Map<String, Object> response = Map.of(
                "success", true,
                "data", data
            );

            log.info("[TripService] 推荐完成: city={}, days={}, keys={}",
                data.get("city"), data.get("days"), data.keySet());
            return response;

        } catch (AppException e) {
            throw e;
        } catch (Exception e) {
            log.error("[TripService] 推荐失败", e);
            throw AppException.badRequest("行程推荐失败：" + e.getMessage());
        }
    }

    // ==================== Chat（D4 mock 实现）====================

    /**
     * Chat 流式响应（mock 实现）
     *
     * TODO: D8 阶段替换为真实 ChatAgent 双流输出
     *
     * @return Flux 事件流
     */
    public Flux<String> chatStream(Long userId, String message, Long conversationId, Long tripId) {
        // Mock 响应：模拟 LLM 流式输出
        return Flux.just(
                "{\"type\":\"chunk\",\"data\":{\"content\":\"正在\"}}",
                "{\"type\":\"chunk\",\"data\":{\"content\":\"为您\"}}",
                "{\"type\":\"chunk\",\"data\":{\"content\":\"规划\"}}",
                "{\"type\":\"chunk\",\"data\":{\"content\":\"旅行\"}}",
                "{\"type\":\"chunk\",\"data\":{\"content\":\"行程\"}}",
                "{\"type\":\"complete\",\"data\":{\"usage\":{\"prompt\":15,\"completion\":25,\"total\":40,\"cached\":5}}}"
            )
            .delayElements(java.time.Duration.ofMillis(300))
            .doOnNext(event -> System.out.println("[ChatMock] " + event));
    }
}
