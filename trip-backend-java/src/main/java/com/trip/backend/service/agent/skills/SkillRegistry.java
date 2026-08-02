package com.trip.backend.service.agent.skills;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * SkillRegistry 技能注册表
 *
 * 对应 Python services/agent/skills/skill_registry.py
 *
 * L1：目录 name/description/tags 常驻上下文
 * L2：选中才读整篇 SKILL.md
 * L3：执行
 */
@Service
public class SkillRegistry {

    private static final Logger log = LoggerFactory.getLogger(SkillRegistry.class);

    public record SkillDef(
        String name,
        String description,
        List<String> tags
    ) {}

    private final Map<String, SkillDef> skills = new LinkedHashMap<>();

    public SkillRegistry() {
        // TODO: D9 实现后补充从 .claude/skills 加载
    }

    public void register(SkillDef skill) {
        skills.put(skill.name(), skill);
        log.debug("[SkillRegistry] Registered skill: {}", skill.name());
    }

    /**
     * 获取 L1 目录（常驻上下文）
     */
    public List<SkillDef> getL1Directory() {
        return new ArrayList<>(skills.values());
    }

    /**
     * 查找技能
     *
     * @param name 技能名
     * @return 技能定义（未找到返回 null）
     */
    public SkillDef findByName(String name) {
        return skills.get(name);
    }
}
