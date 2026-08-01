package com.trip.backend.service;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.domain.entity.SpotDoc;
import com.trip.backend.domain.repository.SpotDocRepository;
import com.trip.backend.domain.repository.SpotRepository;
import com.trip.backend.utils.AppException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * 知识库服务（对应 Python services/knowledge_service.py）
 */
@Service
public class KnowledgeService {

    private final SpotRepository spotRepository;
    private final SpotDocRepository spotDocRepository;

    public KnowledgeService(SpotRepository spotRepository, SpotDocRepository spotDocRepository) {
        this.spotRepository = spotRepository;
        this.spotDocRepository = spotDocRepository;
    }

    /**
     * 获取景点列表（分页/城市/分类筛选）
     */
    public Page<Spot> getSpots(String city, String category, int page, int pageSize) {
        if (category != null && !category.isBlank()) {
            return spotRepository.findByCityAndCategory(city, category, PageRequest.of(page - 1, pageSize));
        }
        return spotRepository.findByCity(city, PageRequest.of(page - 1, pageSize));
    }

    /**
     * 获取景点详情
     */
    public Spot getSpot(Long id) {
        return spotRepository.findById(id)
            .orElseThrow(() -> AppException.notFound("景点不存在"));
    }

    /**
     * 创建景点
     */
    public Spot createSpot(Map<String, Object> data) {
        Spot spot = new Spot();
        spot.setName((String) data.get("name"));
        spot.setCity((String) data.get("city"));
        spot.setCategory((String) data.get("category"));
        spot.setDescription((String) data.get("description"));
        spot.setTags((Map<String, Object>) data.get("tags"));
        spot.setAvgCost(data.get("avg_cost") != null ? ((Number) data.get("avg_cost")).intValue() : null);
        spot.setDuration(data.get("duration") != null ? ((Number) data.get("duration")).intValue() : null);
        spot.setOpenTime((String) data.get("open_time"));
        spot.setRating(data.get("rating") != null ? ((Number) data.get("rating")).doubleValue() : null);
        return spotRepository.save(spot);
    }

    /**
     * 批量创建景点（bulk import）
     */
    public BulkResult bulkCreateSpots(List<Map<String, Object>> spotsData) {
        int success = 0;
        int failed = 0;

        for (Map<String, Object> data : spotsData) {
            try {
                createSpot(data);
                success++;
            } catch (Exception e) {
                failed++;
            }
        }

        return new BulkResult(success, failed);
    }

    /**
     * 更新景点
     */
    public Spot updateSpot(Long id, Map<String, Object> data) {
        Spot spot = spotRepository.findById(id)
            .orElseThrow(() -> AppException.notFound("景点不存在"));

        if (data.containsKey("name")) spot.setName((String) data.get("name"));
        if (data.containsKey("city")) spot.setCity((String) data.get("city"));
        if (data.containsKey("category")) spot.setCategory((String) data.get("category"));
        if (data.containsKey("description")) spot.setDescription((String) data.get("description"));
        if (data.containsKey("tags")) spot.setTags((Map<String, Object>) data.get("tags"));
        if (data.containsKey("avg_cost")) spot.setAvgCost(((Number) data.get("avg_cost")).intValue());
        if (data.containsKey("duration")) spot.setDuration(((Number) data.get("duration")).intValue());
        if (data.containsKey("open_time")) spot.setOpenTime((String) data.get("open_time"));
        if (data.containsKey("rating")) spot.setRating(((Number) data.get("rating")).doubleValue());

        return spotRepository.save(spot);
    }

    /**
     * 删除景点
     */
    public void deleteSpot(Long id) {
        if (!spotRepository.existsById(id)) {
            throw AppException.notFound("景点不存在");
        }
        spotRepository.deleteById(id);
    }

    /**
     * 获取 spot-docs（分页/城市/来源类型筛选 + chroma 状态）
     */
    public Page<SpotDoc> getSpotDocs(String city, String sourceType, int page, int pageSize) {
        if (sourceType != null && !sourceType.isBlank()) {
            return spotDocRepository.findByCityAndSourceType(city, sourceType, PageRequest.of(page - 1, pageSize));
        }
        // TODO: 实现 city 过滤的 custom query
        return spotDocRepository.findAll(PageRequest.of(page - 1, pageSize));
    }

    public record BulkResult(int success, int failed) {}
}
