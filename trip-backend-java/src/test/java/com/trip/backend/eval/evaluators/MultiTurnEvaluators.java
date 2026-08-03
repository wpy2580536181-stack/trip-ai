package com.trip.backend.eval.evaluators;

import com.trip.backend.eval.types.EvalResult;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.FixtureExpected;
import com.trip.backend.eval.types.PoiMatch;
import com.trip.backend.eval.registry.EvaluatorRegistry;

import java.util.*;
import java.util.regex.Pattern;

/**
 * 多轮对话 + 反例 Evaluator 实现（3 个）
 */
public class MultiTurnEvaluators {

    // 硬塞行程检测
    private static final List<Pattern> ITINERARY_HARDCODE_PATTERNS = List.of(
            Pattern.compile("第\\s*\\d+\\s*天"),
            Pattern.compile("Day\\s*\\d+", Pattern.CASE_INSENSITIVE),
            Pattern.compile("D\\d+", Pattern.CASE_INSENSITIVE),
            Pattern.compile("行程安排[:：]")
    );

    static {
        EvaluatorRegistry.register("destination_override", MultiTurnEvaluators::destinationOverride);
        EvaluatorRegistry.register("context_memory", MultiTurnEvaluators::contextMemory);
        EvaluatorRegistry.register("no_forced_itinerary", MultiTurnEvaluators::noForcedItinerary);
    }

    /**
     * 1. destination_override: 跟随最新目的地指令
     */
    public static EvalResult destinationOverride(AgentOutput output, Fixture fixture) {
        // 非多轮对话 → 跳过
        if (fixture.getInput().getHistory() == null || fixture.getInput().getHistory().isEmpty()) {
            return EvalResult.pass("无 history，非多轮对话，跳过");
        }

        List<PoiMatch> required = fixture.getExpected().getMustContainPois();
        Set<String> targetCities = new HashSet<>();
        for (PoiMatch req : required) {
            String city = req.getCity();
            if (city != null) targetCities.add(city);
        }

        if (targetCities.isEmpty()) {
            return EvalResult.pass("no target city specified in must_contain_pois, skipping");
        }

        List<String> bannedKeywords = fixture.getExpected().getMustNotContainKeywords();
        List<String> violations = new ArrayList<>();

        // JSON 行程检查
        if (output.getJson() instanceof Map) {
            Map<?, ?> jsonData = (Map<?, ?>) output.getJson();
            Object dailyItinerary = jsonData.get("dailyItinerary");
            if (dailyItinerary instanceof List) {
                for (int dayIdx = 0; dayIdx < ((List<?>) dailyItinerary).size(); dayIdx++) {
                    Object dayObj = ((List<?>) dailyItinerary).get(dayIdx);
                    if (dayObj instanceof Map) {
                        Map<?, ?> day = (Map<?, ?>) dayObj;
                        for (String slotKey : List.of("morning", "afternoon", "evening")) {
                            Object slot = day.get(slotKey);
                            if (slot instanceof Map) {
                                String spot = (String) ((Map<?, ?>) slot).get("spot");
                                if (spot != null && bannedKeywords != null) {
                                    for (String kw : bannedKeywords) {
                                        if (spot.contains(kw)) {
                                            violations.add("Day " + (dayIdx + 1) + " 推荐了原目的地 POI：\"" + spot + "\"，未跟随新指令");
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // 文本检查
        if (bannedKeywords != null && output.getText() != null) {
            for (String kw : bannedKeywords) {
                if (output.getText().contains(kw)) {
                    violations.add("文本中提到原目的地关键词：\"" + kw + "\"");
                }
            }
        }

        if (violations.isEmpty()) {
            Map<String, Object> details = new HashMap<>();
            details.put("targetCities", targetCities);
            return EvalResult.pass(details);
        }
        return EvalResult.fail(String.join("; ", violations));
    }

    /**
     * 2. context_memory: 是否记得上文关键信息
     */
    public static EvalResult contextMemory(AgentOutput output, Fixture fixture) {
        // 非多轮对话 → 跳过
        if (fixture.getInput().getHistory() == null || fixture.getInput().getHistory().isEmpty()) {
            return EvalResult.pass("无 history，非多轮对话，跳过");
        }

        List<String> must = fixture.getExpected().getMustContainKeywords();
        if (must == null || must.isEmpty()) {
            return EvalResult.pass("no must_contain_keywords, skipping");
        }

        // 查找最后一条 assistant 消息
        List<Map<String, Object>> history = fixture.getInput().getHistory();
        Map<String, Object> lastAssistant = null;
        for (int i = history.size() - 1; i >= 0; i--) {
            Map<String, Object> msg = history.get(i);
            if ("assistant".equals(msg.get("role"))) {
                lastAssistant = msg;
                break;
            }
        }

        if (lastAssistant == null) {
            return EvalResult.pass("no last assistant message, skipping");
        }

        // 验证 output.text 至少包含 must 中的关键词
        String text = output.getText() != null ? output.getText() : "";
        List<String> missing = must.stream().filter(kw -> !text.contains(kw)).toList();

        if (missing.isEmpty()) {
            Map<String, Object> details = new HashMap<>();
            details.put("mustHit", must.size());
            return EvalResult.pass(details);
        }
        return EvalResult.fail("缺失上文关键信息：" + String.join(", ", missing));
    }

    /**
     * 3. no_forced_itinerary: 不该硬塞完整行程（反例场景）
     */
    public static EvalResult noForcedItinerary(AgentOutput output, Fixture fixture) {
        FixtureExpected exp = fixture.getExpected();

        // 判断是否是反例场景
        boolean isRejectionFixture = (exp.getDays() == 0 && !exp.isRecommendation())
                || !exp.isJsonValid()
                || exp.isRecommendation();

        if (!isRejectionFixture) {
            return EvalResult.pass("非反例 fixture，跳过");
        }

        List<String> violations = new ArrayList<>();
        String text = output.getText() != null ? output.getText() : "";

        // 1. JSON 行程不该被硬塞
        if (output.getJson() instanceof Map) {
            Map<?, ?> jsonData = (Map<?, ?>) output.getJson();
            Object dailyItinerary = jsonData.get("dailyItinerary");
            if (dailyItinerary instanceof List && !((List<?>) dailyItinerary).isEmpty()) {
                violations.add("反例场景却输出了 " + ((List<?>) dailyItinerary).size() + " 天行程");
            }
        }

        // 2. 文本里不该有结构化行程词
        for (Pattern pat : ITINERARY_HARDCODE_PATTERNS) {
            List<String> matches = new ArrayList<>();
            var matcher = pat.matcher(text);
            while (matcher.find()) {
                matches.add(matcher.group());
            }
            if (!matches.isEmpty()) {
                violations.add("反例场景包含硬塞关键词：" + pat.pattern() + "（匹配 " + matches.size() + " 次）");
            }
        }

        // 3. 必不含关键词
        List<String> banned = exp.getMustNotContainKeywords();
        if (banned != null) {
            List<String> bannedHit = banned.stream().filter(text::contains).toList();
            if (!bannedHit.isEmpty()) {
                violations.add("出现硬塞关键词：" + String.join(", ", bannedHit));
            }
        }

        if (violations.isEmpty()) {
            return EvalResult.pass();
        }
        return EvalResult.fail(String.join("; ", violations));
    }
}
