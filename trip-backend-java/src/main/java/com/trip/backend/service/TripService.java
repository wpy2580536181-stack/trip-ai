package com.trip.backend.service;

import com.trip.backend.domain.entity.Trip;
import com.trip.backend.domain.entity.User;
import com.trip.backend.domain.repository.TripRepository;
import com.trip.backend.utils.AppException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 行程服务（对应 Python services/trip_service.py）
 */
@Service
public class TripService {

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
    public Trip createTrip(Long userId, String fromCity, String city, int days, int budget,
                          java.util.Map<String, Object> content) {
        Trip trip = new Trip();
        trip.setUserId(userId);
        trip.setFromCity(fromCity);
        trip.setCity(city);
        trip.setDays(days);
        trip.setBudget(budget);
        trip.setContent(content);
        trip.setStatus("completed");
        return tripRepository.save(trip);
    }

    /**
     * 创建候选行程（修改/升级时使用）
     */
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
    public void deleteTrip(Long userId, Long tripId) {
        Trip trip = tripRepository.findByIdAndUserId(tripId, userId)
            .orElseThrow(() -> AppException.notFound("行程不存在"));
        tripRepository.delete(trip);
    }
}
