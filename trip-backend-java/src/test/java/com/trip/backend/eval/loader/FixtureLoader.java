package com.trip.backend.eval.loader;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.FixtureExpected;
import com.trip.backend.eval.types.FixtureInput;
import com.trip.backend.eval.types.PoiMatch;
import com.trip.backend.eval.types.ToolCallRule;
import org.yaml.snakeyaml.Yaml;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/**
 * Fixture 加载器：从 YAML 文件加载测试用例
 */
public class FixtureLoader {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /**
     * 从目录加载所有 fixture
     */
    public static List<Fixture> loadFromDirectory(Path fixturesDir) throws IOException {
        if (!Files.isDirectory(fixturesDir)) {
            throw new IllegalArgumentException("Not a directory: " + fixturesDir);
        }

        List<Fixture> fixtures = new ArrayList<>();
        List<Path> yamlFiles = Files.walk(fixturesDir)
                .filter(p -> p.toString().endsWith(".yaml") || p.toString().endsWith(".yml"))
                .filter(p -> !p.getFileName().toString().startsWith("."))
                .sorted()
                .toList();

        for (Path yamlFile : yamlFiles) {
            try (InputStream is = Files.newInputStream(yamlFile)) {
                Fixture fixture = loadFromStream(is, yamlFile.getFileName().toString());
                if (fixture != null) {
                    fixtures.add(fixture);
                }
            } catch (Exception e) {
                System.err.println("Failed to load fixture: " + yamlFile + " - " + e.getMessage());
            }
        }

        return fixtures;
    }

    /**
     * 从输入流加载单个 fixture
     */
    public static Fixture loadFromStream(InputStream is, String filename) {
        try {
            Yaml yaml = new Yaml();
            Map<String, Object> data = yaml.load(is);

            if (data == null || data.isEmpty()) {
                System.err.println("Empty fixture: " + filename);
                return null;
            }

            return parseFixture(data);

        } catch (Exception e) {
            System.err.println("Failed to parse fixture " + filename + ": " + e.getMessage());
            return null;
        }
    }

    /**
     * 解析 fixture 数据
     */
    private static Fixture parseFixture(Map<String, Object> data) {
        try {
            // 解析 input
            Map<String, Object> inputMap = (Map<String, Object>) data.getOrDefault("input", Map.of());
            FixtureInput input = new FixtureInput();
            input.setMessage((String) inputMap.getOrDefault("message", ""));
            input.setPreferences((Map<String, Object>) inputMap.getOrDefault("preferences", Map.of()));
            input.setHistory((List<Map<String, Object>>) inputMap.getOrDefault("history", List.of()));

            // 解析 expected
            Map<String, Object> expectedMap = (Map<String, Object>) data.getOrDefault("expected", Map.of());
            FixtureExpected expected = new FixtureExpected();
            expected.setCity((String) expectedMap.getOrDefault("city", ""));
            expected.setJsonValid(Boolean.TRUE.equals(expectedMap.get("json_valid")));
            expected.setDays(expectedMap.get("days") instanceof Number ? ((Number) expectedMap.get("days")).intValue() : 0);
            expected.setMaxActivitiesPerDay(expectedMap.get("max_activities_per_day") instanceof Number ? ((Number) expectedMap.get("max_activities_per_day")).intValue() : 0);
            expected.setActivitiesHavePriceField(Boolean.TRUE.equals(expectedMap.get("activities_have_price_field")));
            expected.setRecommendation(Boolean.TRUE.equals(expectedMap.get("is_recommendation")));
            expected.setDetailAnswer(Boolean.TRUE.equals(expectedMap.get("is_detail_answer")));
            expected.setGroundTruth((String) expectedMap.getOrDefault("ground_truth", ""));
            expected.setKeywordMatchMode((String) expectedMap.getOrDefault("keyword_match_mode", "all"));

            // Lists
            expected.setSpotNames((List<String>) expectedMap.getOrDefault("spot_names", List.of()));
            expected.setMustContainKeywords((List<String>) expectedMap.getOrDefault("must_contain_keywords", List.of()));
            expected.setMustNotContainKeywords((List<String>) expectedMap.getOrDefault("must_not_contain_keywords", List.of()));

            // must_contain_pois (list of maps)
            List<Map<String, Object>> mustContainPois = (List<Map<String, Object>>) expectedMap.getOrDefault("must_contain_pois", List.of());
            List<PoiMatch> poiMatches = new ArrayList<>();
            for (Map<String, Object> poiMap : mustContainPois) {
                PoiMatch poiMatch = new PoiMatch();
                poiMatch.setName((String) poiMap.get("name"));
                poiMatch.setNameContains((String) poiMap.get("name_contains"));
                poiMatch.setCity((String) poiMap.get("city"));
                poiMatch.setCityNearby((String) poiMap.get("city_nearby"));
                poiMatches.add(poiMatch);
            }
            expected.setMustContainPois(poiMatches);

            // tool_calls (list of maps)
            List<Map<String, Object>> toolCalls = (List<Map<String, Object>>) expectedMap.getOrDefault("tool_calls", List.of());
            List<ToolCallRule> toolCallRules = new ArrayList<>();
            for (Map<String, Object> tcMap : toolCalls) {
                ToolCallRule rule = new ToolCallRule();
                rule.setName((String) tcMap.get("name"));
                rule.setMinCalls(tcMap.get("min_calls") instanceof Number ? ((Number) tcMap.get("min_calls")).intValue() : 0);
                rule.setMaxCalls(tcMap.get("max_calls") instanceof Number ? ((Number) tcMap.get("max_calls")).intValue() : -1);
                toolCallRules.add(rule);
            }
            expected.setToolCalls(toolCallRules);

            // 解析顶层字段
            String id = (String) data.getOrDefault("id", "");
            String description = (String) data.getOrDefault("description", "");
            List<String> tags = (List<String>) data.getOrDefault("tags", List.of());
            List<String> evaluators = (List<String>) data.getOrDefault("evaluators", List.of());

            return new Fixture(id, description, tags, input, expected, evaluators);

        } catch (Exception e) {
            System.err.println("Failed to parse fixture: " + e.getMessage());
            return null;
        }
    }
}
