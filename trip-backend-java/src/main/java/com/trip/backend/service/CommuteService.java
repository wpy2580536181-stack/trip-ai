package com.trip.backend.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.service.http.AmapClient;
import com.trip.backend.utils.AppException;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * 通勤服务（对应 Python services/commute_service.py）
 */
@Service
public class CommuteService {

    private final AmapClient amapClient;
    private final ObjectMapper objectMapper;

    public CommuteService(AmapClient amapClient, ObjectMapper objectMapper) {
        this.amapClient = amapClient;
        this.objectMapper = objectMapper;
    }

    /**
     * 地理编码
     */
    public List<Map<String, Object>> geocode(String address) {
        JsonNode result = amapClient.geocode(address);
        List<Map<String, Object>> geocodes = new ArrayList<>();

        if (result != null && result.has("geocodes") && result.get("geocodes").isArray()) {
            for (JsonNode geo : result.get("geocodes")) {
                geocodes.add(Map.of(
                    "address", geo.path("formatted_address").asText(),
                    "location", geo.path("location").asText(),
                    "lng", geo.path("location").path("lng").asDouble(),
                    "lat", geo.path("location").path("lat").asDouble()
                ));
            }
        }

        return geocodes;
    }

    /**
     * 输入联想
     */
    public List<Map<String, Object>> inputTips(String keywords, String city) {
        JsonNode result = amapClient.inputTips(keywords, city);
        List<Map<String, Object>> tips = new ArrayList<>();

        if (result != null && result.has("tips") && result.get("tips").isArray()) {
            for (JsonNode tip : result.get("tips")) {
                tips.add(Map.of(
                    "name", tip.path("name").asText(),
                    "address", tip.path("address").asText(),
                    "district", tip.path("district").asText(),
                    "location", tip.path("location").asText()
                ));
            }
        }

        return tips;
    }

    /**
     * 周边 POI 搜索
     */
    public List<Map<String, Object>> nearbySearch(double lng, double lat, String keywords,
                                                  String types, int radius, int limit) {
        JsonNode result = amapClient.nearbySearch(lng, lat, keywords, types, radius, limit);
        List<Map<String, Object>> pois = new ArrayList<>();

        if (result != null && result.has("pois") && result.get("pois").isArray()) {
            for (JsonNode poi : result.get("pois")) {
                pois.add(Map.of(
                    "id", poi.path("id").asText(),
                    "name", poi.path("name").asText(),
                    "type", poi.path("type").asText(),
                    "address", poi.path("address").asText(),
                    "location", poi.path("location").asText(),
                    "distance", poi.path("distance").asInt()
                ));
            }
        }

        return pois;
    }

    /**
     * 最优通勤路径计算（简化版 TODO）
     */
    public Map<String, Object> computeOptimalCommute(CommuteRequest request) {
        // TODO: 调用高德路径规划 API
        return Map.of(
            "origin", request.origin(),
            "destination", request.destinations(),
            "mode", request.mode(),
            "options", List.of()
        );
    }

    public record CommuteRequest(String origin, List<String> destinations, String mode, String city,
                                 boolean compareModes) {}
}
