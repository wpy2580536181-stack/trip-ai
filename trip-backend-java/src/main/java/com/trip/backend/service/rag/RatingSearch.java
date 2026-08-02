package com.trip.backend.service.rag;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.domain.repository.SpotRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 评分检索
 *
 * 对应 Python services/rag/rating_search.py
 *
 * 功能：
 * - ORDER BY rating DESC NULLS LAST
 * - 按城市/分类过滤
 */
@Service
public class RatingSearch {

    private final SpotRepository spotRepository;

    public RatingSearch(SpotRepository spotRepository) {
        this.spotRepository = spotRepository;
    }

    /**
     * 评分检索
     *
     * @param city 城市（可选）
     * @param category 分类（可选）
     * @param limit 返回数量
     * @return 景点列表（按评分降序）
     */
    public List<Spot> search(String city, String category, int limit) {
        // 调用 Repository 查询
        List<Spot> results = spotRepository.findByCityAndCategoryOrderByRatingDesc(
            city,
            category != null ? category : "attraction",
            PageRequest.of(0, limit)
        );

        return results;
    }
}
