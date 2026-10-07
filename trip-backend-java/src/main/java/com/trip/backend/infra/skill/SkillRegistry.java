package com.trip.backend.infra.skill;

import com.trip.backend.domain.skill.SkillCatalog;
import com.trip.backend.domain.skill.SkillContext;
import com.trip.backend.domain.skill.SkillLayer;
import com.trip.backend.domain.skill.SkillResult;
import com.trip.backend.domain.skill.SkillSpec;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

/**
 * SkillRegistry：三层渐进式披露的技能中枢
 *
 * 对应 Python: registry.py (SkillRegistry)
 *
 * 功能：
 * - L1 目录层：listCatalog() / catalogPrompt()
 * - L2 规格层：loadSpec(name) 按需加载
 * - L3 实现层：execute(name, ctx, **kwargs)
 * - 粗选兜底：select(query) 关键词匹配（无 LLM 时）
 * - 批量加载：loadBuiltinSkills()
 */
@Component
public class SkillRegistry {

    /** 技能存储 */
    private final Map<String, Skill> skills = new HashMap<>();

    // ---- 注册管理 ----

    /**
     * 注册技能
     */
    public void register(Skill skill) {
        if (skill != null && skill.name() != null && !skill.name().isEmpty()) {
            skills.put(skill.name(), skill);
        }
    }

    /**
     * 获取技能
     */
    public Optional<Skill> get(String name) {
        return Optional.ofNullable(skills.get(name));
    }

    // ---- L1 目录层 ----

    /**
     * 列出所有技能目录（L1 轻量元信息）
     */
    public List<SkillCatalog> listCatalog() {
        return skills.values().stream()
            .map(Skill::catalog)
            .toList();
    }

    /**
     * 渲染 L1 目录为提示词片段
     *
     * @return 格式：
     *   # 可用技能
     *
     *   - **name** [kind]：description（tags: tag1, tag2）
     */
    public String catalogPrompt() {
        return catalogPrompt("# 可用技能");
    }

    /**
     * 渲染 L1 目录为提示词片段
     *
     * @param header 标题
     */
    public String catalogPrompt(String header) {
        if (skills.isEmpty()) {
            return "";
        }

        StringBuilder sb = new StringBuilder();
        sb.append(header).append("\n\n");

        for (SkillCatalog catalog : listCatalog()) {
            sb.append(catalog.toPromptFragment()).append("\n");
        }

        return sb.toString();
    }

    // ---- L2 规格层 ----

    /**
     * 加载技能规格（L2）
     *
     * @param name 技能名称
     * @return SkillSpec（未找到返回 null）
     */
    public SkillSpec loadSpec(String name) {
        Skill skill = skills.get(name);
        return skill != null ? skill.loadSpec() : null;
    }

    // ---- 粗选（兜底/无 LLM 时） ----

    /**
     * 按 name/tags/Trigger 关键词做轻量粗选，返回最匹配技能名
     *
     * 作为「无 LLM 时」或「LLM 路由失败」的确定性兜底。
     * 匹配策略：name(3分) + tags(2分) + trigger keywords(1分)
     *
     * @param query 用户查询
     * @return 最匹配技能名（无匹配返回 null）
     */
    public String select(String query) {
        if (query == null || query.trim().isEmpty()) {
            return null;
        }

        String q = query.toLowerCase();
        String best = null;
        int bestScore = 0;

        for (Skill skill : skills.values()) {
            int score = 0;

            // 匹配 name（3分）
            if (skill.name().toLowerCase().contains(q)) {
                score += 3;
            }

            // 匹配 tags（2分）
            for (String tag : skill.catalog().tags()) {
                if (tag.toLowerCase().contains(q)) {
                    score += 2;
                }
            }

            // 匹配 Trigger keywords（1分）
            SkillSpec spec = skill.loadSpec();
            if (spec != null && spec.trigger() != null) {
                for (String kw : extractTriggerKeywords(spec.trigger())) {
                    if (kw.toLowerCase().contains(q)) {
                        score += 1;
                    }
                }
            }

            if (score > bestScore) {
                bestScore = score;
                best = skill.name();
            }
        }

        return best;
    }

    /**
     * 从 Trigger 文本抽取关键词
     *
     * 支持「a / b / c」或 a / b 形式
     */
    private static List<String> extractTriggerKeywords(String trigger) {
        if (trigger == null || trigger.trim().isEmpty()) {
            return Collections.emptyList();
        }

        // 尝试匹配「包含「关键词」」
        Matcher m = Pattern.compile("包含[「\"](.+?)[」\"]").matcher(trigger);
        String raw;
        if (m.find()) {
            raw = m.group(1);
        } else {
            raw = trigger;
        }

        // 按 / 、 分割
        List<String> kws = new ArrayList<>();
        for (String kw : raw.split("[、/]")) {
            kw = kw.trim();
            if (!kw.isEmpty()) {
                kws.add(kw);
            }
        }

        return kws;
    }

    // ---- L1→L2 路由（已废弃，保留向后兼容） ----

    /**
     * [DEPRECATED] 用 LLM 从 L1 目录中选取最匹配的技能
     *
     * 已废弃：新架构通过 select_skill 工具绑定到主 LLM 调用，由主 LLM
     * 自行判断是否激活技能，无需独立路由调用。保留此方法仅为向后兼容。
     *
     * 无 LLM 或解析失败时回退到 select() 关键字匹配。
     */
    public Optional<String> routeSkill(String query, Object llm) {
        // 无 LLM → 降级关键字匹配
        if (llm == null) {
            return Optional.ofNullable(select(query));
        }

        // TODO: LLM 路由实现（暂时不需要，先返回关键字匹配）
        return Optional.ofNullable(select(query));
    }

    // ---- L3 实现层 ----

    /**
     * 执行技能（L3）
     *
     * @param name  技能名称
     * @param ctx   执行上下文
     * @param kwargs 附加参数
     * @return 执行结果
     */
    public SkillResult execute(String name, SkillContext ctx, Map<String, Object> kwargs) {
        Skill skill = skills.get(name);
        if (skill == null) {
            return SkillResult.failure(name, "未注册技能: " + name);
        }

        // L1：已被选中（目录命中）
        List<String> disclosure = new ArrayList<>(ctx.disclosure());
        disclosure.add(SkillLayer.L1.name() + ":catalog:" + name);

        // L2：加载规格（指令）
        skill.loadSpec();
        disclosure.add(SkillLayer.L2.name() + ":spec:" + name);

        // L3：执行（指令驱动 LLM 编排）
        return skill.execute(ctx, kwargs);
    }

    // ---- 批量加载 ----

    /**
     * 从目录批量加载 SKILL.md
     *
     * @param skillsDir 技能目录路径
     * @return this（支持链式调用）
     */
    public SkillRegistry loadFromDirectory(String skillsDir) {
        List<String> paths = SkillLoader.discoverSkillPaths(List.of(skillsDir));
        for (String path : paths) {
            SkillSpec spec = SkillLoader.parseSkillFile(path);
            SkillCatalog catalog = SkillLoader.parseSkillCatalog(path);
            if (catalog != null && !catalog.name().isEmpty()) {
                register(new Skill(catalog, path));
            }
        }
        return this;
    }

    /**
     * 从多个目录批量加载 SKILL.md
     */
    public SkillRegistry loadFromDirectories(List<String> skillsDirs) {
        for (String dir : skillsDirs) {
            loadFromDirectory(dir);
        }
        return this;
    }
}
