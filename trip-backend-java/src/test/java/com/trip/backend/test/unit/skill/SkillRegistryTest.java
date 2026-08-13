package com.trip.backend.test.unit.skill;

import com.trip.backend.domain.skill.SkillCatalog;
import com.trip.backend.domain.skill.SkillSpec;
import com.trip.backend.infra.skill.SkillLoader;
import com.trip.backend.infra.skill.SkillRegistry;
import com.trip.backend.infra.skill.Skill;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

/**
 * SkillRegistry 单元测试
 *
 * 对标 Python: test_skills_foundation.py
 */
public class SkillRegistryTest {

    @Test
    void testEmptyRegistry() {
        SkillRegistry registry = new SkillRegistry();
        assertTrue(registry.listCatalog().isEmpty());
        assertTrue(registry.catalogPrompt().isEmpty());
        assertNull(registry.select("test"));
    }

    @Test
    void testRegisterAndGet() {
        SkillRegistry registry = new SkillRegistry();
        SkillCatalog catalog = new SkillCatalog("test-skill", "Test description", List.of("test", "demo"));
        Skill skill = new Skill(catalog, "/fake/path/SKILL.md");

        registry.register(skill);

        assertEquals(1, registry.listCatalog().size());
        assertTrue(registry.get("test-skill").isPresent());
        assertFalse(registry.get("non-existent").isPresent());
    }

    @Test
    void testCatalogPrompt() {
        SkillRegistry registry = new SkillRegistry();
        SkillCatalog catalog = new SkillCatalog("trip-planner", "Plan your trip", List.of("travel", "itinerary"));
        registry.register(new Skill(catalog, "/fake/SKILL.md"));

        String prompt = registry.catalogPrompt();
        assertTrue(prompt.contains("trip-planner"));
        assertTrue(prompt.contains("Plan your trip"));
        assertTrue(prompt.contains("travel"));
        assertTrue(prompt.contains("itinerary"));
    }

    @Test
    void testSelectByKeyword() {
        SkillRegistry registry = new SkillRegistry();
        SkillCatalog catalog = new SkillCatalog("local-life", "Discover nearby places", List.of("food", "attraction"));
        registry.register(new Skill(catalog, "/fake/SKILL.md"));

        // 匹配 name (3分)
        assertEquals("local-life", registry.select("local"));

        // 匹配 tags (2分)
        assertEquals("local-life", registry.select("food"));

        // 无匹配
        assertNull(registry.select("xyz123"));
    }

    @Test
    void testLoadSpecLazy() {
        SkillRegistry registry = new SkillRegistry();
        SkillCatalog catalog = new SkillCatalog("test", "Test", List.of());
        Skill skill = new Skill(catalog, "/non-existent/SKILL.md");
        registry.register(skill);

        // spec 未加载
        assertFalse(skill.isSpecLoaded());

        // 加载 spec（文件不存在，返回空 spec）
        SkillSpec spec = registry.loadSpec("test");
        assertNotNull(spec);
        assertTrue(spec.isEmpty());

        // 现在已加载
        assertTrue(skill.isSpecLoaded());
    }

    @Test
    void testLoadFromDirectory() {
        // 使用真实的 skill 目录（如果存在）
        SkillRegistry registry = new SkillRegistry();
        // TODO: 需要一个真实的 SKILL.md 文件用于测试
        // registry.loadFromDirectory("/path/to/skills");
        // assertFalse(registry.listCatalog().isEmpty());
    }
}
