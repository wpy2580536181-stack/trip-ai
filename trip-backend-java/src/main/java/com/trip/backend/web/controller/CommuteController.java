package com.trip.backend.web.controller;

import com.trip.backend.service.CommuteService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Commute controller（通勤最短路径）
 *
 * 端点：
 * - GET /api/commute/geocode（地理编码）
 * - GET /api/commute/inputtips（输入联想）
 * - GET /api/commute/nearby（周边 POI 搜索）
 * - POST /api/commute/optimal（最优通勤路径）
 */
@RestController
@RequestMapping("/api/commute")
@Validated
public class CommuteController {

    private final CommuteService commuteService;

    public CommuteController(CommuteService commuteService) {
        this.commuteService = commuteService;
    }

    /**
     * GET /api/commute/geocode
     *
     * 地址地理编码
     */
    @GetMapping("/geocode")
    public ResponseEntity<Map<String, Object>> geocode(
            @RequestParam String address,
            @RequestParam(required = false) String city,
            HttpServletRequest request) {

        try {
            List<Map<String, Object>> geocodes = commuteService.geocode(address);

            if (geocodes.isEmpty()) {
                return ResponseEntity.ok(Map.of("found", false));
            }

            Map<String, Object> first = geocodes.get(0);
            return ResponseEntity.ok(Map.of(
                "lat", first.get("lat"),
                "lng", first.get("lng"),
                "found", true
            ));
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "地理编码异常：" + e.getMessage()));
        }
    }

    /**
     * GET /api/commute/inputtips
     *
     * 地址输入联想
     */
    @GetMapping("/inputtips")
    public ResponseEntity<Map<String, Object>> inputTips(
            @RequestParam String keywords,
            @RequestParam(required = false) String city,
            HttpServletRequest request) {

        if (keywords.trim().isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "keywords 不能为空"));
        }

        try {
            List<Map<String, Object>> tips = commuteService.inputTips(keywords, city);
            return ResponseEntity.ok(Map.of("tips", tips));
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "联想服务异常：" + e.getMessage()));
        }
    }

    /**
     * GET /api/commute/nearby
     *
     * 周边 POI 搜索
     */
    @GetMapping("/nearby")
    public ResponseEntity<Map<String, Object>> nearby(
            @RequestParam Double lat,
            @RequestParam Double lng,
            @RequestParam(defaultValue = "1000") @Min(100) @Max(5000) int radius,
            @RequestParam(required = false) String keywords,
            @RequestParam(required = false) String types,
            HttpServletRequest request) {

        try {
            List<Map<String, Object>> pois = commuteService.nearbySearch(
                lng, lat, keywords, types, radius, 20
            );
            return ResponseEntity.ok(Map.of("pois", pois));
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "周边搜索异常：" + e.getMessage()));
        }
    }

    /**
     * POST /api/commute/optimal
     *
     * 最优通勤路径计算
     */
    @PostMapping("/optimal")
    public ResponseEntity<Map<String, Object>> optimal(
            @RequestBody Map<String, Object> req,
            HttpServletRequest request) {

        try {
            Map<String, Object> result = commuteService.computeOptimalCommute(
                new CommuteService.CommuteRequest(
                    (String) req.get("origin"),
                    (List<String>) req.get("destinations"),
                    (String) req.getOrDefault("mode", "driving"),
                    (String) req.get("city"),
                    (Boolean) req.getOrDefault("compare_modes", false)
                )
            );

            return ResponseEntity.ok(Map.of(
                "code", 0,
                "data", result,
                "message", "ok"
            ));
        } catch (Exception e) {
            return ResponseEntity.badRequest()
                .body(Map.of("code", 400, "error", e.getMessage()));
        }
    }
}
