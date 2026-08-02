package com.trip.backend.service.agent.skills;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.*;
import java.util.List;

/**
 * SkillLoader 技能加载器
 *
 * 对应 Python services/agent/skills/skill_loader.py
 *
 * 职责：
 * - 读取 .claude/skills 目录
 */
@Service
public class SkillLoader {

    private static final Logger log = LoggerFactory.getLogger(SkillLoader.class);

    private final Path skillsDir;

    public SkillLoader() {
        this.skillsDir = Paths.get(System.getProperty("user.dir"), ".claude", "skills");
    }

    /**
     * 加载所有技能
     */
    public List<SkillRegistry.SkillDef> loadSkills() {
        if (!Files.exists(skillsDir) || !Files.isDirectory(skillsDir)) {
            log.warn("[SkillLoader] Skills directory not found: {}", skillsDir);
            return List.of();
        }

        try {
            return Files.list(skillsDir)
                .filter(Files::isDirectory)
                .map(this::loadSkillFromDir)
                .filter(java.util.Objects::nonNull)
                .toList();
        } catch (IOException e) {
            log.error("[SkillLoader] Failed to list skills directory", e);
            return List.of();
        }
    }

    /**
     * 从目录加载技能
     */
    private SkillRegistry.SkillDef loadSkillFromDir(Path skillDir) {
        try {
            String name = skillDir.getFileName().toString();

            // 读取 SKILL.md
            Path skillMd = skillDir.resolve("SKILL.md");
            if (!Files.exists(skillMd)) {
                return null;
            }

            // TODO: D9 实现后补充解析 SKILL.md（提取 description + tags）
            log.debug("[SkillLoader] Loaded skill: {}", name);
            return new SkillRegistry.SkillDef(
                name,
                "Skill: " + name, // 占位
                List.of() // 占位
            );

        } catch (Exception e) {
            log.warn("[SkillLoader] Failed to load skill from: {}", skillDir, e);
            return null;
        }
    }
}
