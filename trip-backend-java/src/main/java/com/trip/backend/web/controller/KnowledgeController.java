package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.domain.entity.SpotDoc;
import com.trip.backend.service.KnowledgeService;
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
 * Knowledge controller（对应 Python controllers/knowledge_controller.py）
 *
 * 端点：
 * - GET /api/knowledge/spots（获取景点列表，公开）
 * - GET /api/knowledge/spots/{spotId}（获取景点详情，公开）
 * - POST /api/knowledge/spots（创建景点，admin）
 * - PUT /api/knowledge/spots/{spotId}（更新景点，admin）
 * - DELETE /api/knowledge/spots/{spotId}（删除景点，admin）
 * - POST /api/knowledge/spots/bulk（批量导入景点，admin）
 * - GET /api/knowledge/spot-docs（获取文本层文档块列表，公开）
 */
@RestController
@RequestMapping("/api/knowledge")
@Validated
public class KnowledgeController {

    private final KnowledgeService knowledgeService;

    public KnowledgeController(KnowledgeService knowledgeService) {
        this.knowledgeService = knowledgeService;
    }

    /**
     * GET /api/knowledge/spots
     *
     * 获取景点列表（公开）
     */
    @GetMapping("/spots")
    public ResponseEntity<Map<String, Object>> getSpots(
            @RequestParam(name = "city", required = false) String city,
            @RequestParam(name = "category", required = false) String category,
            @RequestParam(name = "page", defaultValue = "1") @Min(1) int page,
            @RequestParam(name = "pageSize", defaultValue = "20") @Min(1) @Max(100) int pageSize,
            HttpServletRequest request) {

        Page<Spot> spotPage = knowledgeService.getSpots(city, category, page, pageSize);

        // 转换为响应格式
        List<Map<String, Object>> items = spotPage.getContent().stream()
            .map(spot -> {
                Map<String, Object> item = new HashMap<>();
                item.put("id", spot.getId());
                item.put("name", spot.getName());
                item.put("city", spot.getCity());
                item.put("category", spot.getCategory());
                item.put("description", spot.getDescription());
                item.put("tags", spot.getTags());
                item.put("avgCost", spot.getAvgCost());
                item.put("duration", spot.getDuration());
                item.put("openTime", spot.getOpenTime());
                item.put("rating", spot.getRating());
                item.put("createdAt", spot.getCreatedAt());
                return item;
            })
            .toList();

        Map<String, Object> data = new HashMap<>();
        data.put("items", items);
        data.put("total", spotPage.getTotalElements());
        data.put("page", page);
        data.put("pageSize", pageSize);

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.ok(Map.of("success", true, "data", data));
        } else {
            return ResponseEntity.ok(Map.of(
                "code", 200,
                "data", data,
                "message", "获取景点列表成功",
                "error", null
            ));
        }
    }

    /**
     * GET /api/knowledge/spots/{spotId}
     *
     * 获取景点详情（公开）
     */
    @GetMapping("/spots/{spotId}")
    public ResponseEntity<Map<String, Object>> getSpot(
            @PathVariable Long spotId,
            HttpServletRequest request) {

        Spot spot = knowledgeService.getSpot(spotId);

        Map<String, Object> spotData = new HashMap<>();
        spotData.put("id", spot.getId());
        spotData.put("name", spot.getName());
        spotData.put("city", spot.getCity());
        spotData.put("category", spot.getCategory());
        spotData.put("description", spot.getDescription());
        spotData.put("tags", spot.getTags());
        spotData.put("avgCost", spot.getAvgCost());
        spotData.put("duration", spot.getDuration());
        spotData.put("openTime", spot.getOpenTime());
        spotData.put("rating", spot.getRating());
        spotData.put("hasEmbedding", false);
        spotData.put("createdAt", spot.getCreatedAt());
        spotData.put("updatedAt", null);

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.ok(Map.of("success", true, "data", spotData));
        } else {
            return ResponseEntity.ok(Map.of(
                "code", 200,
                "data", spotData,
                "message", "获取景点详情成功",
                "error", null
            ));
        }
    }

    /**
     * POST /api/knowledge/spots
     *
     * 创建景点（admin）
     */
    @PostMapping("/spots")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> createSpot(
            @RequestBody Map<String, Object> spotData,
            HttpServletRequest request) {

        Spot spot = Spot.create(null, null, null);
        spot.setName((String) spotData.get("name"));
        spot.setCity((String) spotData.get("city"));
        spot.setCategory((String) spotData.get("category"));
        spot.setDescription((String) spotData.get("description"));
        spot.setTags((Map<String, Object>) spotData.get("tags"));
        spot.setAvgCost((Integer) spotData.get("avgCost"));
        spot.setDuration((Integer) spotData.get("duration"));
        spot.setOpenTime((String) spotData.get("openTime"));
        spot.setRating((Double) spotData.get("rating"));

        Spot created = knowledgeService.createSpot(spot);

        Map<String, Object> data = toSpotMap(created);

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("success", true, "data", data));
        } else {
            return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
                "code", 201,
                "data", data,
                "message", "创建景点成功",
                "error", null
            ));
        }
    }

    /**
     * PUT /api/knowledge/spots/{spotId}
     *
     * 更新景点（admin）
     */
    @PutMapping("/spots/{spotId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> updateSpot(
            @PathVariable Long spotId,
            @RequestBody Map<String, Object> spotData,
            HttpServletRequest request) {

        Spot updated = knowledgeService.updateSpot(spotId, spotData);

        Map<String, Object> data = toSpotMap(updated);

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.ok(Map.of("success", true, "data", data));
        } else {
            return ResponseEntity.ok(Map.of(
                "code", 200,
                "data", data,
                "message", "更新景点成功",
                "error", null
            ));
        }
    }

    /**
     * DELETE /api/knowledge/spots/{spotId}
     *
     * 删除景点（admin）
     */
    @DeleteMapping("/spots/{spotId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> deleteSpot(
            @PathVariable Long spotId,
            HttpServletRequest request) {

        knowledgeService.deleteSpot(spotId);

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.ok(Map.of("success", true, "data", null));
        } else {
            return ResponseEntity.ok(Map.of(
                "code", 200,
                "data", null,
                "message", "删除景点成功",
                "error", null
            ));
        }
    }

    /**
     * POST /api/knowledge/spots/bulk
     *
     * 批量导入景点（admin）
     */
    @PostMapping("/spots/bulk")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> bulkImportSpots(
            @RequestBody List<Map<String, Object>> spotsData,
            HttpServletRequest request) {

        Map<String, Object> result = knowledgeService.bulkImportSpots(spotsData);

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.ok(Map.of("success", true, "data", result));
        } else {
            return ResponseEntity.ok(Map.of(
                "code", 200,
                "data", result,
                "message", String.format("批量导入完成：成功 %d 条，失败 %d 条",
                    (int) result.get("success"), (int) result.get("failed")),
                "error", null
            ));
        }
    }

    /**
     * GET /api/knowledge/spot-docs
     *
     * 获取文本层文档块列表（公开）
     */
    @GetMapping("/spot-docs")
    public ResponseEntity<Map<String, Object>> getSpotDocs(
            @RequestParam(name = "city", required = false) String city,
            @RequestParam(name = "sourceType", required = false) String sourceType,
            @RequestParam(name = "page", defaultValue = "1") @Min(1) int page,
            @RequestParam(name = "pageSize", defaultValue = "20") @Min(1) @Max(100) int pageSize,
            HttpServletRequest request) {

        Page<Object[]> docPage = knowledgeService.listSpotDocs(city, sourceType, page, pageSize);

        // 转换为响应格式
        List<Map<String, Object>> items = docPage.getContent().stream()
            .map(row -> {
                SpotDoc doc = (SpotDoc) row[0];
                String spotName = (String) row[1];
                String spotCity = (String) row[2];

                Map<String, Object> item = new HashMap<>();
                item.put("id", doc.getId());
                item.put("spotId", doc.getSpotId());
                item.put("spotName", spotName);
                item.put("city", spotCity);
                item.put("sourceType", doc.getSourceType());
                item.put("sourceName", doc.getSourceName());
                item.put("sourceUrl", doc.getSourceUrl());
                item.put("title", doc.getTitle());
                item.put("content", doc.getContent());
                item.put("chunkIndex", doc.getChunkIndex());
                item.put("credibilityScore", doc.getCredibilityScore());
                item.put("vectorId", null);
                item.put("retrievedAt", doc.getRetrievedAt());
                return item;
            })
            .toList();

        Map<String, Object> data = new HashMap<>();
        data.put("items", items);
        data.put("total", docPage.getTotalElements());
        data.put("page", page);
        data.put("pageSize", pageSize);
        data.put("chroma", Map.of("available", true, "spotDocsCount", null));

        if (FormatResolver.isFormatA(request)) {
            return ResponseEntity.ok(Map.of("success", true, "data", data));
        } else {
            return ResponseEntity.ok(Map.of(
                "code", 200,
                "data", data,
                "message", "获取文本层文档成功",
                "error", null
            ));
        }
    }

    /**
     * 转换为响应 Map
     */
    private Map<String, Object> toSpotMap(Spot spot) {
        Map<String, Object> map = new HashMap<>();
        map.put("id", spot.getId());
        map.put("name", spot.getName());
        map.put("city", spot.getCity());
        map.put("category", spot.getCategory());
        map.put("description", spot.getDescription());
        map.put("tags", spot.getTags());
        map.put("avgCost", spot.getAvgCost());
        map.put("duration", spot.getDuration());
        map.put("openTime", spot.getOpenTime());
        map.put("rating", spot.getRating());
        map.put("hasEmbedding", false);
        map.put("createdAt", spot.getCreatedAt());
        map.put("updatedAt", null);
        return map;
    }
}
