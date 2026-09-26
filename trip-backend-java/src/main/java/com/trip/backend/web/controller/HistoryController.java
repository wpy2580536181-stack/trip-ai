package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.Trip;
import com.trip.backend.service.HistoryService;
import com.trip.backend.web.handler.FormatResolver;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * History controller（对应 Python controllers/history_controller.py）
 *
 * 端点：
 * - GET /api/history/trips（获取行程历史列表，分页）
 * - GET /api/history/trips/{trip_id}（获取行程详情）
 * - GET /api/history/trips/{trip_id}/versions（获取行程版本链）
 * - DELETE /api/history/trips/{trip_id}（删除行程）
 */
@RestController
@RequestMapping({"/api/history/trips", "/api/trip/history"})
@Validated
public class HistoryController {

    private final HistoryService historyService;

    public HistoryController(HistoryService historyService) {
        this.historyService = historyService;
    }

    /**
     * GET /api/history/trips
     *
     * 获取行程历史列表（分页）
     */
    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getTrips(
            @RequestAttribute("userId") Long userId,
            @RequestParam(name = "page", defaultValue = "1") @Min(1) int page,
            @RequestParam(name = "pageSize", defaultValue = "20") @Min(1) @Max(100) int pageSize,
            HttpServletRequest request) {

        Page<Trip> tripPage = historyService.getTrips(userId, page, pageSize);

        // 转换为响应格式
        List<Map<String, Object>> items = tripPage.getContent().stream()
            .map(trip -> {
                Map<String, Object> item = new HashMap<>();
                item.put("id", trip.getId());
                item.put("userId", trip.getUserId());
                item.put("fromCity", trip.getFromCity());
                item.put("city", trip.getCity());
                item.put("days", trip.getDays());
                item.put("budget", trip.getBudget());
                item.put("content", trip.getContent());
                item.put("status", trip.getStatus());
                item.put("parentTripId", trip.getParentTripId());
                item.put("createdAt", trip.getCreatedAt());
                item.put("updatedAt", null);
                return item;
            })
            .toList();

        Map<String, Object> data = new HashMap<>();
        data.put("items", items);
        data.put("total", tripPage.getTotalElements());
        data.put("page", page);
        data.put("pageSize", pageSize);

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.ok(Map.of("success", true, "data", data));
        } else {
            Map<String, Object> response = new HashMap<>();
            response.put("code", 200);
            response.put("data", data);
            response.put("message", "获取行程历史成功");
            response.put("error", null);
            return ResponseEntity.ok(response);
        }
    }

    /**
     * GET /api/history/trips/{tripId}
     *
     * 获取行程详情
     */
    @GetMapping("/{tripId}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getTrip(
            @PathVariable Long tripId,
            @RequestAttribute("userId") Long userId,
            HttpServletRequest request) {

        Trip trip = historyService.getTrip(tripId, userId);

        Map<String, Object> tripData = new HashMap<>();
        tripData.put("id", trip.getId());
        tripData.put("userId", trip.getUserId());
        tripData.put("fromCity", trip.getFromCity());
        tripData.put("city", trip.getCity());
        tripData.put("days", trip.getDays());
        tripData.put("budget", trip.getBudget());
        tripData.put("content", trip.getContent());
        tripData.put("status", trip.getStatus());
        tripData.put("parentTripId", trip.getParentTripId());
        tripData.put("createdAt", trip.getCreatedAt());
        tripData.put("updatedAt", null);

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.ok(Map.of("success", true, "data", tripData));
        } else {
            Map<String, Object> response = new HashMap<>();
            response.put("code", 200);
            response.put("data", tripData);
            response.put("message", "获取行程详情成功");
            response.put("error", null);
            return ResponseEntity.ok(response);
        }
    }

    /**
     * GET /api/history/trips/{tripId}/versions
     *
     * 获取行程版本链（V1...Vn，根版本在前）
     */
    @GetMapping("/{tripId}/versions")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getTripVersions(
            @PathVariable Long tripId,
            @RequestAttribute("userId") Long userId,
            HttpServletRequest request) {

        List<Trip> versions = historyService.getTripVersions(tripId, userId);

        // 转换为响应格式
        List<Map<String, Object>> items = new java.util.ArrayList<>();
        for (int i = 0; i < versions.size(); i++) {
            Trip trip = versions.get(i);
            Map<String, Object> item = new HashMap<>();
            item.put("id", trip.getId());
            item.put("label", "V" + (i + 1));
            item.put("createdAt", trip.getCreatedAt());
            item.put("isCurrent", trip.getId().equals(tripId));
            items.add(item);
        }

        Map<String, Object> data = new HashMap<>();
        data.put("items", items);

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.ok(Map.of("success", true, "data", data));
        } else {
            Map<String, Object> response = new HashMap<>();
            response.put("code", 200);
            response.put("data", data);
            response.put("message", "获取行程版本链成功");
            response.put("error", null);
            return ResponseEntity.ok(response);
        }
    }

    /**
     * DELETE /api/history/trips/{tripId}
     *
     * 删除行程
     */
    @DeleteMapping("/{tripId}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> deleteTrip(
            @PathVariable Long tripId,
            @RequestAttribute("userId") Long userId,
            HttpServletRequest request) {

        historyService.deleteTrip(tripId, userId);

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.ok(Map.of("success", true, "data", null));
        } else {
            Map<String, Object> response = new HashMap<>();
            response.put("code", 200);
            response.put("data", null);
            response.put("message", "删除行程成功");
            response.put("error", null);
            return ResponseEntity.ok(response);
        }
    }
}
