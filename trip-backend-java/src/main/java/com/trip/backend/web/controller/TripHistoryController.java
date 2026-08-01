package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.Trip;
import com.trip.backend.service.TripService;
import com.trip.backend.utils.AppException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 行程历史控制器（对应 Python routers/trip.py）
 * 4 个端点：
 * - GET /api/history/trips（分页）
 * - GET /api/history/trips/{id}
 * - GET /api/history/trips/{id}/versions
 * - DELETE /api/history/trips/{id}
 */
@RestController
@RequestMapping("/api/history/trips")
public class TripHistoryController {

    private final TripService tripService;

    public TripHistoryController(TripService tripService) {
        this.tripService = tripService;
    }

    /**
     * GET /api/history/trips
     */
    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getTrips(
            @RequestAttribute("userId") Long userId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        Page<Trip> trips = tripService.getTrips(userId, page, pageSize);

        Map<String, Object> data = Map.of(
            "items", trips.getContent(),
            "total", trips.getTotalElements(),
            "page", page,
            "pageSize", pageSize
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * GET /api/history/trips/{id}
     */
    @GetMapping("/{id}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getTrip(
            @RequestAttribute("userId") Long userId,
            @PathVariable Long id) {
        Trip trip = tripService.getTrip(userId, id);

        Map<String, Object> data = Map.of(
            "id", trip.getId(),
            "from_city", trip.getFromCity(),
            "city", trip.getCity(),
            "days", trip.getDays(),
            "budget", trip.getBudget(),
            "content", trip.getContent(),
            "status", trip.getStatus(),
            "created_at", trip.getCreatedAt().toString()
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * GET /api/history/trips/{id}/versions
     */
    @GetMapping("/{id}/versions")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getTripVersions(
            @RequestAttribute("userId") Long userId,
            @PathVariable Long id) {
        List<Trip> versions = tripService.getTripVersions(userId, id);

        // 转换为 V1/V2... 格式
        Map<String, Object> data = Map.of(
            "versions", versions.stream()
                .map(v -> Map.of(
                    "version", "V" + v.getId(),
                    "trip_id", v.getId(),
                    "status", v.getStatus(),
                    "created_at", v.getCreatedAt().toString()
                ))
                .toList()
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * DELETE /api/history/trips/{id}
     */
    @DeleteMapping("/{id}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Void> deleteTrip(
            @RequestAttribute("userId") Long userId,
            @PathVariable Long id) {
        tripService.deleteTrip(userId, id);
        return ResponseEntity.noContent().build();
    }
}
