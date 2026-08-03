package com.trip.backend.eval.evaluators;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.eval.EvalUtils;
import com.trip.backend.eval.Evaluator;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.EvalResult;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.FixtureExpected;
import com.trip.backend.eval.types.PoiMatch;
import com.trip.backend.eval.types.ToolCall;
import com.trip.backend.eval.types.ToolCallRule;
import com.trip.backend.eval.registry.EvaluatorRegistry;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 通用 Evaluator 实现
 */
public class GeneralEvaluators {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final Pattern DAY_PATTERN = Pattern.compile("Day\\s*\\d+|第\\s*\\d+\\s*天", Pattern.CASE_INSENSITIVE);
    private static final Pattern BOLD_PATTERN = Pattern.compile("\\*\\*([^*]{2,30})\\*\\*");
    private static final Pattern SLOT_PATTERN = Pattern.compile("(?:上午|中午|下午|晚上|清晨|傍晚)\\s*[:：]?\\s*\\*?\\*?([^*\\n]{2,30})");
    private static final Set<String> SCHEMA_REQUIRED_FIELDS = Set.of("city", "days", "dailyItinerary", "budgetBreakdown", "totalBudget");
    private static final Set<String> NEGATION_WORDS = Set.of("不", "无", "没", "非", "禁", "勿", "未", "别", "远离", "避免", "避开", "排除", "剔除");

    static {
        EvaluatorRegistry.register("schema_check", GeneralEvaluators::schemaCheck);
        EvaluatorRegistry.register("poi_city_match", GeneralEvaluators::poiCityMatch);
        EvaluatorRegistry.register("keyword_coverage", GeneralEvaluators::keywordCoverage);
        EvaluatorRegistry.register("tool_call_audit", GeneralEvaluators::toolCallAudit);
        EvaluatorRegistry.register("pace_consistency", GeneralEvaluators::paceConsistency);
    }

    /**
     * 1. schema_check: 验证 JSON 结构合规
     */
    public static EvalResult schemaCheck(AgentOutput output, Fixture fixture) {
        boolean expected = fixture.getExpected().isJsonValid();

        // json_valid=false 且无 JSON → 跳过
        if (!expected && output.getJson() == null) {
            return EvalResult.pass();
        }

        if (!expected) {
            if (output.getJson() != null) {
                return EvalResult.fail("expected no JSON but got valid JSON");
            }
            return EvalResult.pass();
        }

        // expected=true
        if (output.getJson() != null) {
            try {
                Map<String, Object> jsonData = (Map<String, Object>) output.getJson();
                Set<String> keys = jsonData.keySet();
                Set<String> missing = new HashSet<>(SCHEMA_REQUIRED_FIELDS);
                missing.removeAll(keys);

                if (missing.isEmpty()) {
                    return EvalResult.pass();
                }
                return EvalResult.fail("JSON 缺少必要字段: " + String.join(", ", missing));
            } catch (Exception e) {
                return EvalResult.fail("JSON 解析失败: " + e.getMessage());
            }
        }

        // 没有 JSON → 放宽：text 含 "Day N" 或 "第N天" 标记也算 pass
        if (output.getText() != null && DAY_PATTERN.matcher(output.getText()).find()) {
            return EvalResult.pass();
        }
        return EvalResult.fail("expected valid JSON or markdown Day markers but got neither");
    }

    /**
     * 2. poi_city_match: 验证 POI 在期望城市
     */
    public static EvalResult poiCityMatch(AgentOutput output, Fixture fixture) {
        List<PoiMatch> required = fixture.getExpected().getMustContainPois();
        if (required == null || required.isEmpty()) {
            return EvalResult.pass();
        }

        // 提取所有 POI 名
        List<String> poiNames = extractPoiNames(output);
        Map<String, String> poiCityMap = extractPoiCityMap(output);

        List<String> missing = new ArrayList<>();
        List<String> cityMismatch = new ArrayList<>();

        for (PoiMatch req : required) {
            String reqName = req.getName();
            String reqNameContains = req.getNameContains();
            String reqCity = req.getCity();

            String needle = reqName != null ? reqName : reqNameContains;
            if (needle == null) continue;

            String found = null;
            for (String n : poiNames) {
                if (reqName != null && n.equals(reqName)) {
                    found = n;
                    break;
                }
                if (reqNameContains != null && n.contains(reqNameContains)) {
                    found = n;
                    break;
                }
            }

            if (found == null) {
                missing.add(needle);
                continue;
            }

            // 城市校验
            if (reqCity != null) {
                String foundCity = poiCityMap.get(found);
                if (foundCity != null && !isCityOrNearby(foundCity, reqCity)) {
                    cityMismatch.add(needle + " 期望 " + reqCity + " 实际 " + foundCity);
                }
            }
        }

        if (missing.isEmpty() && cityMismatch.isEmpty()) {
            return EvalResult.pass();
        }

        List<String> reasons = new ArrayList<>();
        if (!missing.isEmpty()) {
            reasons.add("未找到 POI: " + String.join(", ", missing));
        }
        if (!cityMismatch.isEmpty()) {
            reasons.add("城市不符: " + String.join("; ", cityMismatch));
        }
        return EvalResult.fail(String.join("; ", reasons));
    }

    /**
     * 3. keyword_coverage: 验证必含/必不含关键词
     */
    public static EvalResult keywordCoverage(AgentOutput output, Fixture fixture) {
        List<String> must = fixture.getExpected().getMustContainKeywords();
        List<String> mustNot = fixture.getExpected().getMustNotContainKeywords();
        String mode = fixture.getExpected().getKeywordMatchMode();
        if (mode == null) mode = "all";

        String text = output.getText() != null ? output.getText() : "";
        String jsonStr = output.getJson() != null ? EvalUtils.parseJson(text).toString() : "";
        String combinedText = text + jsonStr;

        List<String> missing = new ArrayList<>();
        if ("any".equals(mode)) {
            boolean anyHit = must.stream().anyMatch(combinedText::contains);
            if (!anyHit) missing.addAll(must);
        } else {
            missing.addAll(must.stream().filter(kw -> !combinedText.contains(kw)).toList());
        }

        // 上下文感知：过滤否定句中的 must_not 关键词
        List<String> forbidden = new ArrayList<>();
        for (String kw : mustNot) {
            if (combinedText.contains(kw) && !isNegationContext(combinedText, kw)) {
                forbidden.add(kw);
            }
        }

        if (missing.isEmpty() && forbidden.isEmpty()) {
            return EvalResult.pass();
        }

        List<String> reasons = new ArrayList<>();
        if (!missing.isEmpty()) {
            reasons.add("缺少必含关键词: " + String.join(", ", missing));
        }
        if (!forbidden.isEmpty()) {
            reasons.add("出现禁用关键词: " + String.join(", ", forbidden));
        }
        return EvalResult.fail(String.join("; ", reasons));
    }

    /**
     * 4. tool_call_audit: 验证工具调用次数
     */
    public static EvalResult toolCallAudit(AgentOutput output, Fixture fixture) {
        List<ToolCallRule> rules = fixture.getExpected().getToolCalls();
        if (rules == null || rules.isEmpty()) {
            return EvalResult.pass();
        }

        List<ToolCall> calls = output.getToolCalls();
        if (calls == null) calls = List.of();

        List<String> violations = new ArrayList<>();

        for (ToolCallRule rule : rules) {
            String ruleName = normalizeToolName(rule.getName());
            long count = calls.stream()
                    .filter(tc -> normalizeToolName(tc.getName()).equals(ruleName))
                    .count();

            if (rule.getMinCalls() > 0 && count < rule.getMinCalls()) {
                violations.add(rule.getName() + " 调用 " + count + " 次 < 至少 " + rule.getMinCalls() + " 次");
            }
            if (rule.getMaxCalls() > 0 && count > rule.getMaxCalls()) {
                violations.add(rule.getName() + " 调用 " + count + " 次 > 至多 " + rule.getMaxCalls() + " 次");
            }
        }

        if (violations.isEmpty()) {
            return EvalResult.pass();
        }
        return EvalResult.fail(String.join("; ", violations));
    }

    /**
     * 5. pace_consistency: 验证天数 + 每天活动数
     */
    public static EvalResult paceConsistency(AgentOutput output, Fixture fixture) {
        int expectedDays = fixture.getExpected().getDays();
        int maxPerDay = fixture.getExpected().getMaxActivitiesPerDay();
        List<String> violations = new ArrayList<>();

        // 检查天数
        if (expectedDays > 0) {
            Integer actualDays = null;
            if (output.getJson() instanceof Map) {
                Object days = ((Map<?, ?>) output.getJson()).get("days");
                if (days instanceof Number) {
                    actualDays = ((Number) days).intValue();
                }
            }

            if (actualDays == null && output.getText() != null) {
                Matcher matcher = DAY_PATTERN.matcher(output.getText());
                Set<String> matches = new HashSet<>();
                while (matcher.find()) {
                    matches.add(matcher.group().toLowerCase().replace(" ", ""));
                }
                actualDays = matches.size();
            }

            if (actualDays == null) {
                return EvalResult.fail("output 找不到天数信息");
            }
            if (actualDays != expectedDays) {
                violations.add("行程天数 " + actualDays + " ≠ 期望 " + expectedDays);
            }
        }

        // 检查每天活动数
        if (maxPerDay > 0 && output.getJson() instanceof Map) {
            Map<?, ?> jsonData = (Map<?, ?>) output.getJson();
            Object dailyItinerary = jsonData.get("dailyItinerary");
            if (dailyItinerary instanceof List) {
                List<?> days = (List<?>) dailyItinerary;
                for (int i = 0; i < days.size(); i++) {
                    Object dayObj = days.get(i);
                    if (dayObj instanceof Map) {
                        Map<?, ?> day = (Map<?, ?>) dayObj;
                        int filledSlots = 0;
                        for (String slotKey : List.of("morning", "afternoon", "evening")) {
                            Object slot = day.get(slotKey);
                            if (slot instanceof Map && ((Map<?, ?>) slot).get("spot") != null) {
                                filledSlots++;
                            }
                        }
                        if (filledSlots > maxPerDay) {
                            violations.add("Day " + (i + 1) + " 有 " + filledSlots + " 个活动 > 上限 " + maxPerDay);
                        }
                    }
                }
            }
        }

        if (violations.isEmpty()) {
            return EvalResult.pass();
        }
        return EvalResult.fail(String.join("; ", violations));
    }

    // ========== 辅助方法 ==========

    /**
     * 提取所有 POI 名称
     */
    private static List<String> extractPoiNames(AgentOutput output) {
        List<String> names = new ArrayList<>();

        // 1. JSON dailyItinerary
        if (output.getJson() instanceof Map) {
            Map<?, ?> jsonData = (Map<?, ?>) output.getJson();
            Object dailyItinerary = jsonData.get("dailyItinerary");
            if (dailyItinerary instanceof List) {
                for (Object dayObj : (List<?>) dailyItinerary) {
                    if (dayObj instanceof Map) {
                        Map<?, ?> day = (Map<?, ?>) dayObj;
                        for (String slotKey : List.of("morning", "afternoon", "evening")) {
                            Object slot = day.get(slotKey);
                            if (slot instanceof Map) {
                                String spot = (String) ((Map<?, ?>) slot).get("spot");
                                if (spot != null) names.add(spot);
                            }
                        }
                    }
                }
            }
        }

        // 2. Markdown 加粗
        if (output.getText() != null) {
            Matcher matcher = BOLD_PATTERN.matcher(output.getText());
            while (matcher.find()) {
                String content = matcher.group(1).trim();
                if (!DAY_PATTERN.matcher(content).find() && !content.matches("^\\d+[.、]")) {
                    names.add(content);
                }
            }

            // 3. 时段前缀
            Matcher slotMatcher = SLOT_PATTERN.matcher(output.getText());
            while (slotMatcher.find()) {
                String content = slotMatcher.group(1).trim().replace("*", "").trim();
                String cleaned = content.split("[，。；,;\\n]")[0].trim();
                if (cleaned.length() >= 2) {
                    names.add(cleaned);
                }
            }
        }

        // 去重（保持顺序）
        return names.stream().distinct().toList();
    }

    /**
     * 提取 POI 到城市的映射
     */
    private static Map<String, String> extractPoiCityMap(AgentOutput output) {
        Map<String, String> map = new HashMap<>();
        if (output.getJson() instanceof Map) {
            Map<?, ?> jsonData = (Map<?, ?>) output.getJson();
            Object dailyItinerary = jsonData.get("dailyItinerary");
            if (dailyItinerary instanceof List) {
                for (Object dayObj : (List<?>) dailyItinerary) {
                    if (dayObj instanceof Map) {
                        Map<?, ?> day = (Map<?, ?>) dayObj;
                        for (String slotKey : List.of("morning", "afternoon", "evening")) {
                            Object slot = day.get(slotKey);
                            if (slot instanceof Map) {
                                String spot = (String) ((Map<?, ?>) slot).get("spot");
                                String city = (String) ((Map<?, ?>) slot).get("city");
                                if (spot != null && city != null) {
                                    map.put(spot, city);
                                }
                            }
                        }
                    }
                }
            }
        }
        return map;
    }

    /**
     * 判断是否在城市或周边 100km
     * TODO: 集成 CityGeo 模块
     */
    private static boolean isCityOrNearby(String foundCity, String expectedCity) {
        // 简化实现：只判断城市名是否相等
        // 后续可以集成 CityGeo 的 100km 周边计算
        return foundCity.equals(expectedCity);
    }

    /**
     * 检查关键词是否在否定句中
     */
    private static boolean isNegationContext(String text, String keyword) {
        int idx = text.indexOf(keyword);
        if (idx == -1) return false;
        String context = text.substring(Math.max(0, idx - 15), idx);
        return NEGATION_WORDS.stream().anyMatch(context::contains);
    }

    /**
     * 归一化工具名
     */
    private static String normalizeToolName(String name) {
        return name.toLowerCase().replaceAll("[_\\-]", "");
    }
}
