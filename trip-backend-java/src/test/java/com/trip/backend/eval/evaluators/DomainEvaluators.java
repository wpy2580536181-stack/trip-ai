package com.trip.backend.eval.evaluators;

import com.trip.backend.eval.types.EvalResult;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.FixtureExpected;
import com.trip.backend.eval.registry.EvaluatorRegistry;

import java.util.*;
import java.util.regex.Pattern;

/**
 * 领域 Evaluator 实现（5 个）
 */
public class DomainEvaluators {

    // 宠物禁入场所
    private static final List<String> PET_BANNED_KEYWORDS = List.of(
            "动物园", "野生动物园", "水族馆", "海洋馆", "美术馆", "科技馆", "展览馆"
    );

    private static final List<String> PET_REQUIRED_KEYWORDS = List.of(
            "宠物", "牵引绳", "防疫", "便便", "狗证", "宠物友好", "遛狗"
    );

    private static final Pattern PET_MENTION_RE = Pattern.compile(
            "宠物|狗|猫|金毛|柯基|泰迪|边牧|拉布拉多|萨摩|哈士奇|比熊|贵宾"
    );

    // 饮食规则
    private static final Map<String, DietaryRule> DIETARY_RULES = Map.of(
            "halal", new DietaryRule("清真", List.of("清真"), List.of(
                    "猪肉", "培根", "火腿", "香肠", "烤肠", "猪骨", "猪蹄", "烤鸭", "羊肉", "牛肉"
            )),
            "vegetarian", new DietaryRule("素食", List.of("素食", "素菜", "斋饭"), List.of(
                    "牛肉", "羊肉", "鸡肉", "猪肉", "鱼", "虾", "蟹"
            )),
            "glutenfree", new DietaryRule("无麸质", List.of("无麸质", "面筋"), List.of(
                    "面条", "面包", "馒头", "包子", "饺子皮"
            ))
    );

    private static final List<DietaryPattern> DIETARY_DETECT_PATTERNS = List.of(
            new DietaryPattern("halal", Pattern.compile("穆斯林|清真|halal", Pattern.CASE_INSENSITIVE)),
            new DietaryPattern("vegetarian", Pattern.compile("素食|不吃肉|吃素")),
            new DietaryPattern("glutenfree", Pattern.compile("无麸质|麸质过敏|gluten", Pattern.CASE_INSENSITIVE))
    );

    // 天气
    private static final Pattern WEATHER_MENTION_RE = Pattern.compile("雨|雪|台风|高温|寒冷|雾霾|沙尘|暴晒");
    private static final Pattern WEATHER_ADAPTATION_RE = Pattern.compile("雨|雪|室内|备选|避雨|防寒|防晒|防雾霾");
    private static final List<String> WEATHER_BAD_KEYWORDS = List.of("露天", "草坪", "野餐", "露营", "骑行环湖", "冲浪", "日光浴");
    private static final Pattern WEATHER_SAFE_CONTEXT_RE = Pattern.compile("室内|改|避|不推荐|避免|建议改");

    // 亲子
    private static final Pattern KID_MENTION_RE = Pattern.compile("孩子|小孩|宝宝|儿子|女儿|亲子|带.+岁|家庭");
    private static final Pattern KID_TIP_RE = Pattern.compile("儿童|孩子|亲子|家长|安全|休息|午休|体力");
    private static final List<String> KID_BAD_KEYWORDS = List.of(
            "徒步", "登山", "攀岩", "蹦极", "夜店", "通宵", "潜水", "跳伞", "飙车", "鬼屋"
    );

    private static final Set<String> NEGATION_WORDS = Set.of(
            "无", "不", "没", "避免", "避开", "拒绝", "排除", "慎", "禁",
            "已帮你排除", "已排除", "未标注", "未推荐", "不含", "不提供", "不涉及", "不会有", "全程无"
    );

    static {
        EvaluatorRegistry.register("pet_constraint_check", DomainEvaluators::petConstraintCheck);
        EvaluatorRegistry.register("dietary_constraint_check", DomainEvaluators::dietaryConstraintCheck);
        EvaluatorRegistry.register("weather_adaptation_check", DomainEvaluators::weatherAdaptationCheck);
        EvaluatorRegistry.register("budget_field_present", DomainEvaluators::budgetFieldPresent);
        EvaluatorRegistry.register("kid_friendly_check", DomainEvaluators::kidFriendlyCheck);
    }

    /**
     * 1. pet_constraint_check: 宠物友好场所校验
     */
    public static EvalResult petConstraintCheck(AgentOutput output, Fixture fixture) {
        String message = fixture.getInput().getMessage();
        if (!PET_MENTION_RE.matcher(message).find()) {
            return EvalResult.pass("用户没提宠物，跳过");
        }

        String text = output.getText() != null ? output.getText() : "";
        List<String> violations = new ArrayList<>();

        // 必含宠物提示
        boolean hasPetTip = PET_REQUIRED_KEYWORDS.stream().anyMatch(text::contains);
        if (!hasPetTip) {
            violations.add("未提示宠物注意事项（缺少关键词：" + String.join("/", PET_REQUIRED_KEYWORDS.subList(0, 3)) + " 等）");
        }

        // 禁入场所（文本）
        List<String> bannedHit = PET_BANNED_KEYWORDS.stream().filter(text::contains).toList();
        if (!bannedHit.isEmpty()) {
            violations.add("推荐了宠物禁入场所：" + String.join(", ", bannedHit));
        }

        // 禁入场所（JSON）
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
                                if (spot != null) {
                                    for (String kw : PET_BANNED_KEYWORDS) {
                                        if (spot.contains(kw)) {
                                            violations.add("Day " + (dayIdx + 1) + " 推荐了宠物禁入 POI：\"" + spot + "\"");
                                        }
                                    }
                                }
                            }
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

    /**
     * 2. dietary_constraint_check: 饮食禁忌校验
     */
    public static EvalResult dietaryConstraintCheck(AgentOutput output, Fixture fixture) {
        String message = fixture.getInput().getMessage();
        List<String> detected = new ArrayList<>();

        for (DietaryPattern dp : DIETARY_DETECT_PATTERNS) {
            // vegetarian 优先级低于 vegan（避免重复）
            if ("vegetarian".equals(dp.key()) && detected.contains("vegan")) {
                continue;
            }
            if (dp.pattern().matcher(message).find()) {
                detected.add(dp.key());
            }
        }

        if (detected.isEmpty()) {
            return EvalResult.pass("用户没提饮食禁忌，跳过");
        }

        String text = output.getText() != null ? output.getText() : "";
        List<String> violations = new ArrayList<>();

        for (String key : detected) {
            DietaryRule rule = DIETARY_RULES.get(key);
            if (rule == null) continue;

            boolean hasRequired = rule.required().stream().anyMatch(text::contains);
            if (!hasRequired) {
                violations.add("未明确提到\"" + rule.label() + "\"相关（缺少：" + String.join("/", rule.required()) + "）");
            }

            // 检查禁忌食材（排除"避免"语境）
            List<String> bannedHit = rule.banned().stream()
                    .filter(kw -> text.contains(kw) && !isInAvoidanceContext(text, kw))
                    .toList();
            if (!bannedHit.isEmpty()) {
                violations.add("行程含 " + rule.label() + " 禁忌食材：" + String.join(", ", bannedHit));
            }
        }

        if (violations.isEmpty()) {
            return EvalResult.pass();
        }
        return EvalResult.fail(String.join("; ", violations));
    }

    /**
     * 3. weather_adaptation_check: 天气应对校验
     */
    public static EvalResult weatherAdaptationCheck(AgentOutput output, Fixture fixture) {
        String message = fixture.getInput().getMessage();
        if (!WEATHER_MENTION_RE.matcher(message).find()) {
            return EvalResult.pass("用户没提天气状况，跳过");
        }

        String text = output.getText() != null ? output.getText() : "";
        List<String> violations = new ArrayList<>();

        // 1. 必含应对关键词
        if (!WEATHER_ADAPTATION_RE.matcher(text).find()) {
            violations.add("未提供天气应对方案");
        }

        // 2. 必不含露天推荐（排除安全上下文）
        List<String> badHit = new ArrayList<>();
        for (String kw : WEATHER_BAD_KEYWORDS) {
            int idx = text.indexOf(kw);
            if (idx == -1) continue;
            String ctx = text.substring(Math.max(0, idx - 20), idx + kw.length() + 20);
            if (!WEATHER_SAFE_CONTEXT_RE.matcher(ctx).find()) {
                badHit.add(kw);
            }
        }
        if (!badHit.isEmpty()) {
            violations.add("推荐了露天活动（与天气不符）：" + String.join(", ", badHit));
        }

        if (violations.isEmpty()) {
            return EvalResult.pass();
        }
        return EvalResult.fail(String.join("; ", violations));
    }

    /**
     * 4. budget_field_present: 预算字段完整性
     */
    public static EvalResult budgetFieldPresent(AgentOutput output, Fixture fixture) {
        if (!fixture.getExpected().isActivitiesHavePriceField()) {
            return EvalResult.pass("fixture 未要求 price 字段，跳过");
        }

        if (!(output.getJson() instanceof Map)) {
            return EvalResult.fail("output.json.dailyItinerary 不存在");
        }

        Map<?, ?> jsonData = (Map<?, ?>) output.getJson();
        Object dailyItinerary = jsonData.get("dailyItinerary");
        if (!(dailyItinerary instanceof List)) {
            return EvalResult.fail("output.json.dailyItinerary 不存在");
        }

        Pattern priceRe = Pattern.compile("￥|¥|元|\\d+\\s*元");
        List<String> missing = new ArrayList<>();

        for (int dayIdx = 0; dayIdx < ((List<?>) dailyItinerary).size(); dayIdx++) {
            Object dayObj = ((List<?>) dailyItinerary).get(dayIdx);
            if (dayObj instanceof Map) {
                Map<?, ?> day = (Map<?, ?>) dayObj;
                for (String slotKey : List.of("morning", "afternoon", "evening")) {
                    Object slot = day.get(slotKey);
                    if (slot instanceof Map) {
                        String spot = (String) ((Map<?, ?>) slot).get("spot");
                        String ticket = (String) ((Map<?, ?>) slot).get("ticket");
                        if (ticket == null || !priceRe.matcher(ticket).find()) {
                            missing.add("Day " + (dayIdx + 1) + " " + slotKey + "（" + spot + "）");
                        }
                    }
                }
            }
        }

        if (missing.isEmpty()) {
            return EvalResult.pass();
        }

        List<String> shown = missing.subList(0, Math.min(missing.size(), 5));
        String suffix = missing.size() > 5 ? " 等 " + missing.size() + " 项" : "";
        return EvalResult.fail("以下时段缺价格：" + String.join("; ", shown) + suffix);
    }

    /**
     * 5. kid_friendly_check: 亲子友好校验
     */
    public static EvalResult kidFriendlyCheck(AgentOutput output, Fixture fixture) {
        String message = fixture.getInput().getMessage();
        if (!KID_MENTION_RE.matcher(message).find()) {
            return EvalResult.pass("用户没提孩子，跳过");
        }

        String text = output.getText() != null ? output.getText() : "";
        List<String> violations = new ArrayList<>();

        // 1. 必含儿童相关提示
        if (!KID_TIP_RE.matcher(text).find()) {
            violations.add("未提示儿童注意事项");
        }

        // 2. 必不含儿童不宜（文本）
        List<String> badHit = KID_BAD_KEYWORDS.stream().filter(text::contains).toList();
        if (!badHit.isEmpty()) {
            violations.add("推荐了儿童不宜活动：" + String.join(", ", badHit));
        }

        // 3. JSON 行程检查
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
                                if (spot != null) {
                                    for (String kw : KID_BAD_KEYWORDS) {
                                        if (spot.contains(kw)) {
                                            violations.add("Day " + (dayIdx + 1) + " 推荐了儿童不宜 POI：\"" + spot + "\"");
                                        }
                                    }
                                }
                            }
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
     * 检查关键词是否在"避免/无/不"语境中
     */
    private static boolean isInAvoidanceContext(String text, String keyword) {
        int idx = 0;
        while (true) {
            idx = text.indexOf(keyword, idx);
            if (idx == -1) return false;
            int start = Math.max(0, idx - 12);
            int end = Math.min(text.length(), idx + keyword.length() + 30);
            String context = text.substring(start, end);
            boolean inContext = NEGATION_WORDS.stream().anyMatch(context::contains);
            if (inContext) return true;
            idx += keyword.length();
        }
    }

    // ========== 数据类 ==========

    private record DietaryRule(String label, List<String> required, List<String> banned) {
    }

    private record DietaryPattern(String key, Pattern pattern) {
    }
}
