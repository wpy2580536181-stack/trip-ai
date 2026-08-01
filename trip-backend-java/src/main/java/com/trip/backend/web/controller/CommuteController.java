package com.trip.backend.web.controller;

import com.trip.backend.service.CommuteService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 通勤控制器（对应 Python routers/commute.py）
 * 4 个端点（公开）：
 * - GET /api/commute/geocode
 * - GET /api/commute/inputtips
 * - GET /api/commute/nearby
 * - POST /api/commute/optimal
 */
@RestController
@RequestMapping("/api/commute")
public class CommuteController {

    private final CommuteService commuteService;

    public CommuteController(CommuteService commuteService) {
        this.commuteService = commuteService;
    }

    /**
     * GET /api/commute/geocode（裸对象返回）
     */
    @GetMapping("/geocode")
    public ResponseEntity<List<Map<String, Object>>> geocode(
            @RequestParam String address) {
        List<Map<String, Object>> result = commuteService.geocode(address);
        return ResponseEntity.ok(result);
    }

    /**
     * GET /api/commute/inputtips（裸对象返回）
     */
    @GetMapping("/inputtips")
    public ResponseEntity<List<Map<String, Object>>> inputTips(
            @RequestParam String keywords,
            @RequestParam(required = false) String city) {
        List<Map<String, Object>> result = commuteService.inputTips(keywords, city);
        return ResponseEntity.ok(result);
    }

    /**
     * GET /api/commute/nearby（裸对象返回）
     */
    @GetMapping("/nearby")
    public ResponseEntity<List<Map<String, Object>>> nearby(
            @RequestParam double lng,
            @RequestParam double lat,
            @RequestParam String keywords,
            @RequestParam(required = false) String types,
            @RequestParam(defaultValue = "1000") int radius,
            @RequestParam(defaultValue = "10") int limit) {
        List<Map<String, Object>> result = commuteService.nearbySearch(lng, lat, keywords, types, radius, limit);
        return ResponseEntity.ok(result);
    }

    /**
     * POST /api/commute/optimal（{code:0, data, message:"ok"}）
     */
    @PostMapping("/optimal")
    public ResponseEntity<Map<String, Object>> optimal(
            @Valid @RequestBody CommuteRequest request,
            HttpServletRequest httpRequest) {
        Map<String, Object> result = commuteService.computeOptimalCommute(request);

        Map<String, Object> response = Map.of(
            "code", 0,
            "data", result,
            "message", "ok"
        );

        return ResponseEntity.ok(response);
    }

    public record CommuteRequest(
        String origin,
        List<String> destinations,
        String mode, // driving/walking/transit/cycling
        String city,
        boolean compare_modes
    ) {}
}
