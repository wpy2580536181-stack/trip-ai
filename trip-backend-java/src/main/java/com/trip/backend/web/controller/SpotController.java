package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.service.KnowledgeService;
import com.trip.backend.utils.AppException;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

/**
 * 知识库控制器（对应 Python routers/knowledge.py）
 * 7 个端点：
 * - GET /api/knowledge/spots（分页/城市/分类筛选）
 * - GET /api/knowledge/spots/{id}
 * - POST /api/knowledge/spots（snake_case 响应）
 * - PUT /api/knowledge/spots/{id}（snake_case 响应）
 * - DELETE /api/knowledge/spots/{id}
 * - POST /api/knowledge/spots/bulk（裸 JSON 数组）
 * - GET /api/knowledge/spot-docs（带 chroma 状态）
 */
@RestController
@RequestMapping("/api/knowledge")
public class SpotController {

    private final KnowledgeService knowledgeService;

    public SpotController(KnowledgeService knowledgeService) {
        this.knowledgeService = knowledgeService;
    }

    /**
     * GET /api/knowledge/spots
     */
    @GetMapping("/spots")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getSpots(
            @RequestParam(defaultValue = "") String city,
            @RequestParam(defaultValue = "") String category,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        Page<Spot> spots = knowledgeService.getSpots(city, category, page, pageSize);

        // 转换为 snake_case
        List<Map<String, Object>> items = spots.getContent().stream()
            .map(spot -> Map.of(
                "id", spot.getId(),
                "name", spot.getName(),
                "city", spot.getCity(),
                "category", spot.getCategory(),
                "description", spot.getDescription(),
                "rating", spot.getRating(),
                "avg_cost", spot.getAvgCost(),
                "duration", spot.getDuration(),
                "open_time", spot.getOpenTime(),
                "tags", spot.getTags()
            ))
            .toList();

        Map<String, Object> data = Map.of(
            "items", items,
            "total", spots.getTotalElements(),
            "page", page,
            "pageSize", pageSize
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * GET /api/knowledge/spots/{id}
     */
    @GetMapping("/spots/{id}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getSpot(@PathVariable Long id) {
        Spot spot = knowledgeService.getSpot(id);

        Map<String, Object> data = Map.of(
            "id", spot.getId(),
            "name", spot.getName(),
            "city", spot.getCity(),
            "category", spot.getCategory(),
            "description", spot.getDescription(),
            "rating", spot.getRating(),
            "avg_cost", spot.getAvgCost(),
            "duration", spot.getDuration(),
            "open_time", spot.getOpenTime(),
            "tags", spot.getTags(),
            "created_at", spot.getCreatedAt().toString()
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * POST /api/knowledge/spots（snake_case 请求体）
     */
    @PostMapping("/spots")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> createSpot(
            @Valid @RequestBody Map<String, Object> request) {
        Spot spot = knowledgeService.createSpot(request);

        Map<String, Object> data = Map.of(
            "id", spot.getId(),
            "name", spot.getName(),
            "city", spot.getCity(),
            "category", spot.getCategory()
        );

        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
            "code", 201, "data", data, "message", null, "error", null
        ));
    }

    /**
     * PUT /api/knowledge/spots/{id}（snake_case 请求体）
     */
    @PutMapping("/spots/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> updateSpot(
            @PathVariable Long id,
            @Valid @RequestBody Map<String, Object> request) {
        Spot spot = knowledgeService.updateSpot(id, request);

        Map<String, Object> data = Map.of(
            "id", spot.getId(),
            "name", spot.getName(),
            "city", spot.getCity(),
            "category", spot.getCategory(),
            "description", spot.getDescription(),
            "tags", spot.getTags()
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * DELETE /api/knowledge/spots/{id}
     */
    @DeleteMapping("/spots/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Void> deleteSpot(@PathVariable Long id) {
        knowledgeService.deleteSpot(id);
        return ResponseEntity.noContent().build();
    }

    /**
     * POST /api/knowledge/spots/bulk（裸 JSON 数组请求体）
     */
    @PostMapping("/spots/bulk")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> bulkCreateSpots(
            @Valid @RequestBody List<Map<String, Object>> request) {
        KnowledgeService.BulkResult result = knowledgeService.bulkCreateSpots(request);

        Map<String, Object> data = Map.of(
            "success", result.success(),
            "failed", result.failed()
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * GET /api/knowledge/spot-docs（带 chroma 状态）
     */
    @GetMapping("/spot-docs")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getSpotDocs(
            @RequestParam(defaultValue = "") String city,
            @RequestParam(defaultValue = "") String sourceType,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        Page<com.trip.backend.domain.entity.SpotDoc> docs = knowledgeService.getSpotDocs(city, sourceType, page, pageSize);

        List<Map<String, Object>> items = docs.getContent().stream()
            .map(doc -> Map.of(
                "id", doc.getId(),
                "spot_id", doc.getSpotId(),
                "source_type", doc.getSourceType(),
                "source_name", doc.getSourceName(),
                "title", doc.getTitle(),
                "chunk_index", doc.getChunkIndex(),
                "credibility_score", doc.getCredibilityScore(),
                "chroma", Map.of(
                    "available", true, // TODO: 检查 Chroma 实际状态
                    "spotDocsCount", doc.getSpotId() != null ? 1 : 0
                )
            ))
            .toList();

        Map<String, Object> data = Map.of(
            "items", items,
            "total", docs.getTotalElements(),
            "page", page,
            "pageSize", pageSize
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }
}
