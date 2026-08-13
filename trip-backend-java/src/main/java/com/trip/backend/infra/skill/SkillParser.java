package com.trip.backend.infra.skill;

import com.trip.backend.domain.skill.SkillCatalog;
import com.trip.backend.domain.skill.SkillSpec;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * SKILL.md 解析器：轻量自写解析（不引入 YAML 库）
 *
 * 对应 Python: parse_skill_file / parse_skill_catalog (loader.py)
 *
 * 功能：
 * - 解析 frontmatter（name/description/tags/kind）
 * - 解析正文 sections（## 标题分割）
 * - 检测 resources 引用（references/scripts/assets/*.md）
 */
public class SkillParser {

    /**
     * Frontmatter 正则：---\n(.*?)\n---\n(.*)$
     */
    private static final Pattern FRONTMATTER_PATTERN = Pattern.compile(
        "^---\\s*\n(.*?)\n---\\s*\n?(.*)$",
        Pattern.DOTALL
    );

    /**
     * Section 标题正则：## 标题
     */
    private static final Pattern SECTION_HEADING_PATTERN = Pattern.compile(
        "^##\\s+(.+)$",
        Pattern.MULTILINE
    );

    /**
     * Resources 引用正则：references/scripts/assets/*.md
     */
    private static final Pattern RESOURCE_PATTERN = Pattern.compile(
        "(?:references|scripts|assets)/[^\\s)\\]]+" +
        "\\.(?:md|py|txt|json|ya?ml|csv|png|jpe?g|svg|html)"
    );

    /**
     * 解析 SKILL.md 全文
     *
     * @param text SKILL.md 文件内容
     * @return (SkillCatalog, SkillSpec) 元组
     */
    public static ParsedSkill parse(String text) {
        if (text == null || text.trim().isEmpty()) {
            return new ParsedSkill(createEmptyCatalog(), createEmptySpec());
        }

        // 1. 解析 frontmatter
        Frontmatter fm = parseFrontmatter(text);

        // 2. 提取 body
        String body = fm.remainingBody;

        // 3. 解析 sections
        Map<String, String> sections = parseSections(body);

        // 4. 创建 catalog（L1 目录）
        String name = fm.get("name", "");
        SkillCatalog catalog;
        if (name.isEmpty()) {
            catalog = createEmptyCatalog();
        } else {
            catalog = new SkillCatalog(
                name,
                fm.get("description", ""),
                parseTags(fm.get("tags", "")),
                fm.get("kind", "agent")
            );
        }

        // 5. 创建 spec（L2 规格）
        SkillSpec spec = new SkillSpec(
            sections.getOrDefault("Trigger", ""),
            sections.getOrDefault("Instructions", ""),
            sections.getOrDefault("Input Schema", ""),
            sections.getOrDefault("Examples", ""),
            body,
            detectResources(body)
        );

        return new ParsedSkill(catalog, spec);
    }

    /**
     * 仅解析 frontmatter（用于 L1 目录懒加载）
     *
     * @param text SKILL.md 文件内容
     * @return SkillCatalog（失败返回空 catalog）
     */
    public static SkillCatalog parseCatalogOnly(String text) {
        if (text == null || text.trim().isEmpty()) {
            return createEmptyCatalog();
        }

        Frontmatter fm = parseFrontmatter(text);
        String name = fm.get("name", "");

        if (name.isEmpty()) {
            return createEmptyCatalog();
        }

        return new SkillCatalog(
            name,
            fm.get("description", ""),
            parseTags(fm.get("tags", "")),
            fm.get("kind", "agent")
        );
    }

    /**
     * 解析 frontmatter
     */
    private static Frontmatter parseFrontmatter(String text) {
        Matcher m = FRONTMATTER_PATTERN.matcher(text);
        if (!m.matches()) {
            return new Frontmatter(Collections.emptyMap(), text);
        }

        Map<String, String> data = new LinkedHashMap<>();
        String fmBody = m.group(1);
        String remainingBody = m.group(2);

        // 逐行解析键值对
        for (String line : fmBody.split("\n")) {
            if (!line.contains(":")) {
                continue;
            }

            String[] parts = line.split(":", 2);
            String key = parts[0].trim();
            String value = parts[1].trim();

            // 处理 YAML 折叠标量（>-）和多行描述
            if (value.startsWith(">-")) {
                value = value.substring(2).trim();
            }

            // 处理数组 [a, b, c]
            if (value.startsWith("[") && value.endsWith("]")) {
                String inner = value.substring(1, value.length() - 1).trim();
                if (!inner.isEmpty()) {
                    // 数组格式：a, b, c（存储为逗号分隔字符串，由调用方解析）
                    // 为简化，这里保持原始字符串，由 parseTags() 处理
                    value = inner;
                } else {
                    value = "";
                }
            }

            // 去除引号
            value = value.replaceAll("^[\"']|[\"']$", "");

            data.put(key, value);
        }

        return new Frontmatter(data, remainingBody);
    }

    /**
     * 按 ## 标题分割正文
     */
    private static Map<String, String> parseSections(String body) {
        Map<String, String> sections = new LinkedHashMap<>();

        if (body == null || body.trim().isEmpty()) {
            return sections;
        }

        Matcher m = SECTION_HEADING_PATTERN.matcher(body);
        List<Integer> headingPositions = new ArrayList<>();

        // 收集所有标题位置
        while (m.find()) {
            headingPositions.add(m.start());
        }

        // 提取每个标题对应的内容
        for (int i = 0; i < headingPositions.size(); i++) {
            int start = headingPositions.get(i);
            int end = (i + 1 < headingPositions.size())
                ? headingPositions.get(i + 1)
                : body.length();

            // 提取标题名
            String headingLine = body.substring(start, end).split("\n")[0];
            String title = headingLine.replaceFirst("^##\\s+", "").trim();

            // 提取内容（跳过标题行）
            int contentStart = start + headingLine.length() + 1;
            String content = body.substring(contentStart, end).trim();

            sections.put(title, content);
        }

        return sections;
    }

    /**
     * 解析 tags 字段（支持 "tag1, tag2" 格式）
     */
    static List<String> parseTags(String tagsStr) {
        if (tagsStr == null || tagsStr.trim().isEmpty()) {
            return Collections.emptyList();
        }

        List<String> tags = new ArrayList<>();
        for (String tag : tagsStr.split(",")) {
            tag = tag.trim();
            if (!tag.isEmpty()) {
                tags.add(tag);
            }
        }
        return tags;
    }

    /**
     * 检测 resources 引用
     */
    static List<String> detectResources(String body) {
        if (body == null || body.trim().isEmpty()) {
            return Collections.emptyList();
        }

        Set<String> resources = new LinkedHashSet<>();
        Matcher m = RESOURCE_PATTERN.matcher(body);
        while (m.find()) {
            resources.add(m.group());
        }
        return new ArrayList<>(resources);
    }

    /**
     * 创建空 catalog
     */
    static SkillCatalog createEmptyCatalog() {
        return new SkillCatalog("", "", Collections.emptyList(), "agent");
    }

    /**
     * 创建空 spec
     */
    static SkillSpec createEmptySpec() {
        return new SkillSpec("", "", "", "", "", Collections.emptyList());
    }

    /**
     * Frontmatter 解析结果
     */
    private static record Frontmatter(Map<String, String> data, String remainingBody) {
        String get(String key, String defaultValue) {
            return data.getOrDefault(key, defaultValue);
        }
    }

    /**
     * 解析结果
     */
    public record ParsedSkill(SkillCatalog catalog, SkillSpec spec) {
        // record 组件在 Java 21 中访问器可能是私有，显式提供 getter
        public SkillCatalog getCatalog() {
            return catalog;
        }

        public SkillSpec getSpec() {
            return spec;
        }
    }
}
