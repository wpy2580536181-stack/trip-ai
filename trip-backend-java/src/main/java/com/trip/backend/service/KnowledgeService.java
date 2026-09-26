package com.trip.backend.service;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.domain.entity.SpotDoc;
import com.trip.backend.domain.repository.SpotDocRepository;
import com.trip.backend.domain.repository.SpotRepository;
import com.trip.backend.task.EmbeddingSyncTask;
import com.trip.backend.utils.AppException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Knowledge service（简化版）
 * - 景点 CRUD
 * - 文档查询
 */
@Service
public class KnowledgeService {

    private final SpotRepository spotRepository;
    private final SpotDocRepository spotDocRepository;
    private final EmbeddingSyncTask embeddingSync;

    public KnowledgeService(SpotRepository spotRepository, SpotDocRepository spotDocRepository,
                            EmbeddingSyncTask embeddingSync) {
        this.spotRepository = spotRepository;
        this.spotDocRepository = spotDocRepository;
        this.embeddingSync = embeddingSync;
    }

    /** best-effort 入队 embedding 同步（失败不阻塞 CRUD）。 */
    private void triggerEmbeddingSync(Spot spot) {
        if (embeddingSync == null || spot.getId() == null) return;
        try {
            embeddingSync.enqueue(spot.getId(), spot.getCity(), spot.getName(),
                spot.getDescription(), null, spot.getCategory());
        } catch (Exception e) {
            org.slf4j.LoggerFactory.getLogger(KnowledgeService.class)
                .warn("embedding_sync 入队失败 spot={}: {}", spot.getId(), e.getMessage());
        }
    }

    /**
     * 获取景点列表
     */
    @Transactional(readOnly = true)
    public Page<Spot> getSpots(String city, String category, int page, int pageSize) {
        PageRequest pageable = PageRequest.of(page - 1, pageSize);

        if (city != null && !city.isEmpty() && category != null && !category.isEmpty()) {
            return spotRepository.findByCityAndCategory(city, category, pageable);
        } else if (city != null && !city.isEmpty()) {
            return spotRepository.findByCity(city, pageable);
        } else if (category != null && !category.isEmpty()) {
            return spotRepository.findByCategory(category, pageable);
        } else {
            return spotRepository.findAll(pageable);
        }
    }

    /**
     * 获取景点详情
     */
    @Transactional(readOnly = true)
    public Spot getSpot(Long spotId) {
        return spotRepository.findById(spotId)
            .orElseThrow(() -> new AppException("景点不存在", 404));
    }

    /**
     * 获取文档列表
     */
    @Transactional(readOnly = true)
    public Page<SpotDoc> listSpotDocs(String city, String sourceType, int page, int pageSize) {
        PageRequest pageable = PageRequest.of(page - 1, pageSize);

        if (city != null && !city.isEmpty() && sourceType != null && !sourceType.isEmpty()) {
            return spotDocRepository.findByCityAndSourceTypeUsingJoin(city, sourceType, pageable);
        } else if (city != null && !city.isEmpty()) {
            return spotDocRepository.findByCityUsingJoin(city, pageable);
        } else if (sourceType != null && !sourceType.isEmpty()) {
            return spotDocRepository.findBySourceType(sourceType, pageable);
        } else {
            return spotDocRepository.findAll(pageable);
        }
    }

    /**
     * 创建景点
     */
    @Transactional
    public Map<String, Object> createSpot(Map<String, Object> data) {
        Spot spot = Spot.create(
            (String) data.get("name"),
            (String) data.get("city"),
            (String) data.get("category")
        );
        spot.setDescription((String) data.get("description"));
        spot.setTags((java.util.List<String>) data.get("tags"));
        spot.setAvgCost((Integer) data.get("avgCost"));
        spot.setDuration((Integer) data.get("duration"));
        spot.setOpenTime((String) data.get("openTime"));
        spot.setRating((Double) data.get("rating"));

        spotRepository.save(spot);
        triggerEmbeddingSync(spot);

        // 返回 Map
        Map<String, Object> result = new HashMap<>();
        result.put("id", spot.getId());
        result.put("name", spot.getName());
        result.put("city", spot.getCity());
        result.put("category", spot.getCategory());
        result.put("description", spot.getDescription());
        result.put("tags", spot.getTags());
        result.put("avgCost", spot.getAvgCost());
        result.put("duration", spot.getDuration());
        result.put("openTime", spot.getOpenTime());
        result.put("rating", spot.getRating());
        result.put("createdAt", spot.getCreatedAt());
        result.put("updatedAt", null);
        return result;
    }

    /**
     * 更新景点
     */
    @Transactional
    public Spot updateSpot(Long spotId, Map<String, Object> updates) {
        Spot spot = getSpot(spotId);

        updates.forEach((key, value) -> {
            switch (key) {
                case "name" -> spot.setName((String) value);
                case "city" -> spot.setCity((String) value);
                case "category" -> spot.setCategory((String) value);
                case "description" -> spot.setDescription((String) value);
                case "tags" -> spot.setTags((java.util.List<String>) value);
                case "avgCost" -> spot.setAvgCost((Integer) value);
                case "duration" -> spot.setDuration((Integer) value);
                case "openTime" -> spot.setOpenTime((String) value);
                case "rating" -> spot.setRating((Double) value);
            }
        });

        spotRepository.save(spot);
        triggerEmbeddingSync(spot);
        return spot;
    }

    /**
     * 删除景点
     */
    @Transactional
    public void deleteSpot(Long spotId) {
        Spot spot = getSpot(spotId);
        spotRepository.delete(spot);
    }

    /**
     * 批量导入景点
     */
    @Transactional
    public Map<String, Object> bulkImportSpots(List<Map<String, Object>> spotsData) {
        int total = spotsData.size();
        int success = 0;
        int failed = 0;
        StringBuilder errors = new StringBuilder();

        for (int i = 0; i < spotsData.size(); i++) {
            Map<String, Object> data = spotsData.get(i);
            String name = (String) data.getOrDefault("name", "unknown-" + i);

            try {
                Spot spot = Spot.create(
                    (String) data.get("name"),
                    (String) data.get("city"),
                    (String) data.get("category")
                );
                spot.setDescription((String) data.get("description"));
                spot.setTags((java.util.List<String>) data.get("tags"));
                spot.setAvgCost((Integer) data.get("avgCost"));
                spot.setDuration((Integer) data.get("duration"));
                spot.setOpenTime((String) data.get("openTime"));
                spot.setRating((Double) data.get("rating"));

                spotRepository.save(spot);
                triggerEmbeddingSync(spot);
                success++;
            } catch (Exception e) {
                failed++;
                errors.append(name).append(": ").append(e.getMessage()).append("; ");
            }
        }

        Map<String, Object> result = new HashMap<>();
        result.put("success", success);
        result.put("failed", failed);
        result.put("total", total);
        result.put("errors", errors.toString());

        return result;
    }
}
