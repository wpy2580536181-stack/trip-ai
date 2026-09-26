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
    public Map<String, Object> recommend(Long userId, String city, int budget, int days, String message) {
        log.info("[TripService] 行程推荐: userId={}, city={}, days={}, budget={}",
            userId, city, days, budget);

        try {
            // 构造 PlanRequest
            PlanRequest request = new PlanRequest(city, days, budget, message);

            // 调用 Orchestrator
            PlanResult result = orchestrator.plan(request);

            // 检查是否有错误
            if (result.plan().containsKey("error")) {
                String error = (String) result.plan().get("error");
                log.error("[TripService] Orchestrator 返回错误: {}", error);
                throw AppException.badRequest("行程推荐失败：" + error);
            }

            // 落库完整行程，返回真实 trip.id
            Long tripId = persistence.savePlan(userId, city, days, budget, result.plan(), "completed", null);

            // 转换为 Format A 响应（对齐 Python 版本）
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("id", tripId);
            data.put("city", result.plan().get("city"));
            data.put("days", result.plan().get("days"));
            data.put("totalBudget", result.plan().get("totalBudget"));
            data.put("dailyItinerary", result.plan().get("dailyItinerary"));
            data.put("budgetBreakdown", result.plan().get("budgetBreakdown"));
            data.put("tips", result.plan().get("tips"));
            data.put("warnings", result.plan().get("warnings"));
            data.put("variants", List.of());  // plan_variants 待阶段 4
            data.put("toolCalls", result.plan().get("toolCalls"));

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

    /**
     * Chat 改行程：取用户最近一条 completed 行程，按自然语言要求局部重出指定天，
     * merge 回原行程后落库为 candidate 新版本（parentTripId 指向原行程）。
     *
     * @param userId       用户
     * @param modifyRequest 用户的修改要求（自然语言）
     * @param targetDays   需要重出的天（1-based）；空则全部重出
     * @return {success, data:{...plan..., id, parentTripId}} 或 {success:false,error}
     */
    @Transactional
    public Map<String, Object> modifyLatestTrip(Long userId, String modifyRequest, List<Integer> targetDays) {
        Trip latest = tripRepository.findTopByUserIdAndStatusOrderByCreatedAtDesc(userId, "completed")
            .orElse(null);
        if (latest == null) {
            return Map.of("success", false, "error", "没有可修改的行程，请先生成一份行程");
        }

        Map<String, Object> existing = latest.getContent();
        if (existing == null) {
            return Map.of("success", false, "error", "原行程内容为空，无法修改");
        }

        PlanRequest req = new PlanRequest(latest.getCity(), latest.getDays(), latest.getBudget(), modifyRequest);
        List<Integer> days = (targetDays != null && !targetDays.isEmpty()) ? targetDays
            : java.util.stream.IntStream.rangeClosed(1, latest.getDays()).boxed().toList();

        PlanResult result = orchestrator.modify(existing, modifyRequest, req, days);
        if (result.plan().containsKey("error")) {
            return Map.of("success", false, "error", String.valueOf(result.plan().get("error")));
        }

        Long newId = persistence.saveModification(
            userId, latest.getCity(), latest.getDays(), latest.getBudget(),
            result.plan(), latest.getId(), Map.of("modifiedDays", days));

        Map<String, Object> data = new LinkedHashMap<>(result.plan());
        data.put("id", newId);
        data.put("parentTripId", latest.getId());
        log.info("[TripService] 改行程完成: parentId={} newId={} city={} days={}",
            latest.getId(), newId, latest.getCity(), days);
        return Map.of("success", true, "data", data);
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
