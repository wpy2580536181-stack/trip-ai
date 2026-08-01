package com.trip.backend.service.http;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * 高德 HTTP 客户端（对应 Python services/http/amap_client.py）
 * 4 个端点：
 * - GET /v3/geocode/geo（地理编码）
 * - GET /v3/assistant/inputtips（输入联想）
 * - GET /v3/place/text（POI 搜索）
 * - POST /v3/direction/transit/integrated/drive（路径规划 - TODO）
 */
@Service
public class AmapClient {

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;
    private final String apiKey;
    private final String baseUrl;

    public AmapClient(RestTemplate restTemplate, ObjectMapper objectMapper,
                     @Value("${amap.maps-api-key:}") String apiKey) {
        this.restTemplate = restTemplate;
        this.objectMapper = objectMapper;
        this.apiKey = apiKey;
        this.baseUrl = "https://restapi.amap.com/v3";
    }

    /**
     * 地理编码（地址 → 坐标）
     */
    public JsonNode geocode(String address) {
        String url = UriComponentsBuilder.fromHttpUrl(baseUrl + "/geocode/geo")
            .queryParam("key", apiKey)
            .queryParam("address", address)
            .encode()
            .toUriString();

        HttpHeaders headers = new HttpHeaders();
        headers.set("Accept", "application/json");
        HttpEntity<Void> entity = new HttpEntity<>(headers);

        ResponseEntity<JsonNode> response = restTemplate.exchange(
            url,
            HttpMethod.GET,
            entity,
            JsonNode.class
        );

        return response.getBody();
    }

    /**
     * 输入联想
     */
    public JsonNode inputTips(String keywords, String city) {
        UriComponentsBuilder builder = UriComponentsBuilder.fromHttpUrl(baseUrl + "/assistant/inputtips")
            .queryParam("key", apiKey)
            .queryParam("keywords", keywords);

        if (city != null && !city.isBlank()) {
            builder.queryParam("city", city);
        }

        String url = builder.encode().toUriString();

        HttpHeaders headers = new HttpHeaders();
        headers.set("Accept", "application/json");
        HttpEntity<Void> entity = new HttpEntity<>(headers);

        ResponseEntity<JsonNode> response = restTemplate.exchange(
            url,
            HttpMethod.GET,
            entity,
            JsonNode.class
        );

        return response.getBody();
    }

    /**
     * 周边 POI 搜索
     */
    public JsonNode nearbySearch(double lng, double lat, String keywords, String types, int radius, int limit) {
        UriComponentsBuilder builder = UriComponentsBuilder.fromHttpUrl(baseUrl + "/place/text")
            .queryParam("key", apiKey)
            .queryParam("keywords", keywords)
            .queryParam("location", lng + "," + lat)
            .queryParam("radius", radius)
            .queryParam("offset", limit)
            .queryParam("extensions", "all");

        if (types != null && !types.isBlank()) {
            builder.queryParam("types", types);
        }

        String url = builder.encode().toUriString();

        HttpHeaders headers = new HttpHeaders();
        headers.set("Accept", "application/json");
        HttpEntity<Void> entity = new HttpEntity<>(headers);

        ResponseEntity<JsonNode> response = restTemplate.exchange(
            url,
            HttpMethod.GET,
            entity,
            JsonNode.class
        );

        return response.getBody();
    }

    /**
     * 路径规划（驾车/步行/公交/骑行）
     */
    public JsonNode direction(String origin, String destination, String mode) {
        // TODO: 实现完整参数
        return null;
    }
}
