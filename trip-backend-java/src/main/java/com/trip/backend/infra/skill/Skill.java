package com.trip.backend.infra.skill;

import com.trip.backend.domain.skill.SkillCatalog;
import com.trip.backend.domain.skill.SkillContext;
import com.trip.backend.domain.skill.SkillLayer;
import com.trip.backend.domain.skill.SkillResult;
import com.trip.backend.domain.skill.SkillSpec;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Skill 运行时对象：由 SKILL.md 解析而来
 *
 * 对应 Python: base.py (Skill)
 *
 * 功能：
 * - L1 catalog：构造即持有（轻量元信息）
 * - L2 spec：loadSpec() 时才从磁盘读取（lazy-load）
 * - L3 resources：loadResources() 按需读取
 * - execute()：多轮 tool calling 执行
 */
public class Skill {

    private final SkillCatalog catalog;
    private final String path;  // SKILL.md 路径，用于加载同目录资源
    private SkillSpec spec;  // lazy-load，null 表示未加载

    /**
     * 构造 Skill（仅持有 L1 catalog）
     *
     * @param catalog L1 目录元信息
     * @param path    SKILL.md 文件路径
     */
    public Skill(SkillCatalog catalog, String path) {
        this.catalog = catalog;
        this.path = path;
        this.spec = null;
    }

    /**
     * 获取技能名称
     */
    public String name() {
        return catalog.name();
    }

    /**
     * 获取目录
     */
    public SkillCatalog catalog() {
        return catalog;
    }

    // ---- L2：规格层（被选中才读取，lazy-load） ----

    /**
     * 加载 L2 规格（首次调用时才从磁盘解析 SKILL.md 正文）
     *
     * @return SkillSpec
     */
    public synchronized SkillSpec loadSpec() {
        if (spec == null && path != null && !path.isEmpty()) {
            this.spec = SkillLoader.parseSkillFile(path);
        }
        return spec != null ? spec : SkillParser.createEmptySpec();
    }

    /**
     * 是否已加载 L2 规格
     */
    public boolean isSpecLoaded() {
        return spec != null;
    }

    // ---- L3：资源层（执行时按需读取） ----

    /**
     * 读取 SKILL.md 引用的 references/scripts/assets 文件内容
     *
     * @return (拼接后的资源文本, 实际成功加载的相对路径列表)
     */
    public ResourceLoadResult loadResources() {
        SkillSpec spec = loadSpec();
        if (path == null || path.isEmpty() || spec.resources() == null || spec.resources().isEmpty()) {
            return new ResourceLoadResult("", Collections.emptyList());
        }

        String baseDir = extractDirectory(path);
        StringBuilder parts = new StringBuilder();
        List<String> loaded = new ArrayList<>();

        for (String rel : spec.resources()) {
            String fp = baseDir + "/" + rel;
            try {
                String content = readFileContent(fp);
                parts.append("### ").append(rel).append("\n").append(content).append("\n\n");
                loaded.add(rel);
            } catch (Exception e) {
                // 资源文件读取失败，跳过
                continue;
            }
        }

        return new ResourceLoadResult(parts.toString(), loaded);
    }

    /**
     * 从文件路径提取目录
     */
    private static String extractDirectory(String filePath) {
        int lastSep = filePath.lastIndexOf('/');
        return lastSep >= 0 ? filePath.substring(0, lastSep) : filePath;
    }

    /**
     * 读取文件内容
     */
    private static String readFileContent(String path) throws Exception {
        StringBuilder sb = new StringBuilder();
        try (java.io.BufferedReader reader = new java.io.BufferedReader(
                new java.io.FileReader(path, java.nio.charset.StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line).append("\n");
            }
        }
        return sb.toString();
    }

    // ---- 内部：拼装执行用系统提示词 ----

    /**
     * 拼装执行用系统提示词（L2 正文 + L3 资源）
     *
     * @return (system_prompt, l3_tag)
     */
    public SystemPrompt buildSystemPrompt() {
        SkillSpec spec = loadSpec();

        // L2 激活层：加载整篇 SKILL.md 正文
        String l2Body = spec.body();
        if (l2Body == null || l2Body.isEmpty()) {
            l2Body = String.format(
                "## 触发条件\n%s\n\n## 执行指令\n%s\n\n## 输入契约\n%s",
                spec.trigger(), spec.instructions(), spec.inputSchema()
            );
        }

        StringBuilder system = new StringBuilder();
        system.append("你正在执行技能「").append(name()).append("」（类型：").append(catalog.kind()).append("）。\n");
        system.append("请严格遵循下面的技能说明，并使用可用工具完成任务。\n\n");
        system.append(l2Body);

        // L3 执行层：按需加载 references/scripts/assets
        ResourceLoadResult resources = loadResources();
        StringBuilder l3Tag = new StringBuilder(SkillLayer.L3.name()).append(":execute:").append(name());

        if (!resources.text().isEmpty()) {
            system.append("\n\n## 参考资料（L3 按需加载）\n").append(resources.text());
            if (!resources.paths().isEmpty()) {
                l3Tag.append(":resources=").append(String.join(",", resources.paths()));
            }
        }

        return new SystemPrompt(system.toString(), l3Tag.toString());
    }

    // ---- 执行层（多轮 tool calling agent loop） ----

    /**
     * 执行技能（L3 实现层）
     *
     * 注意：这里用 Object 表示 LLM 和 Tool，避免循环依赖
     * TODO: D9-7 ChatAgent 改造时替换为实际类型
     */
    public SkillResult execute(SkillContext ctx, Map<String, Object> kwargs) {
        // 参数校验
        if (ctx.llm() == null) {
            return SkillResult.failure(name(), "SkillContext.llm 未注入，无法执行指令驱动技能");
        }

        // 1. L1: catalog hit → disclosure append
        List<String> disclosure = new ArrayList<>(ctx.disclosure());
        disclosure.add(SkillLayer.L1.name() + ":catalog:" + name());

        // 2. L2: load spec → disclosure append
        SkillSpec spec = loadSpec();
        disclosure.add(SkillLayer.L2.name() + ":spec:" + name());

        // 3. L3: execute（指令驱动 LLM 编排）
        SystemPrompt sysPrompt = buildSystemPrompt();
        disclosure.add(sysPrompt.l3Tag());

        // TODO: 这里应该调用 LLM 执行多轮 tool calling
        // 暂时返回占位符，D9-4 SkillRuntime 实现具体执行逻辑
        return SkillResult.success(name(),
            "[技能执行占位符] 技能「" + name() + "」已加载，" +
            "instructions 长度=" + spec.instructions().length() + " 字符，" +
            "resources=" + sysPrompt.l3Tag(),
            disclosure
        );
    }

    // ---- 辅助类型 ----

    /**
     * 系统提示词
     */
    public record SystemPrompt(String text, String l3Tag) {
    }

    /**
     * 资源加载结果
     */
    public record ResourceLoadResult(String text, List<String> paths) {
    }
}
