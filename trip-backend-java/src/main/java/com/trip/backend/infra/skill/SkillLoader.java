package com.trip.backend.infra.skill;

import com.trip.backend.domain.skill.SkillCatalog;
import com.trip.backend.domain.skill.SkillSpec;

import java.util.Collections;
import java.util.List;

/**
 * SkillLoader：解析 SKILL.md 文件为 SkillCatalog + SkillSpec
 *
 * 对应 Python: loader.py (parse_skill_file / parse_skill_catalog / discover_skill_paths)
 *
 * 功能：
 * - L1 目录：parseSkillCatalog() 仅解析 frontmatter
 * - L2 规格：parseSkillFile() 完整解析（frontmatter + sections + resources）
 * - 目录扫描：discoverSkillPaths() 递归查找 SKILL.md
 */
public class SkillLoader {

    /**
     * 解析单个 SKILL.md 文件（完整版）
     *
     * @param path SKILL.md 文件路径
     * @return SkillSpec（失败返回空 spec）
     */
    public static SkillSpec parseSkillFile(String path) {
        try {
            String content = readFileContent(path);
            return SkillParser.parse(content).spec();
        } catch (Exception e) {
            return SkillParser.createEmptySpec();
        }
    }

    /**
     * 仅解析 SKILL.md frontmatter（L1 目录懒加载）
     *
     * @param path SKILL.md 文件路径
     * @return SkillCatalog（失败返回空 catalog）
     */
    public static SkillCatalog parseSkillCatalog(String path) {
        try {
            String content = readFileContent(path);
            return SkillParser.parseCatalogOnly(content);
        } catch (Exception e) {
            return SkillParser.createEmptyCatalog();
        }
    }

    /**
     * 扫描目录下所有 SKILL.md 文件
     *
     * @param skillsDirs 技能目录列表（支持多目录）
     * @return SKILL.md 文件路径列表（排序）
     */
    public static List<String> discoverSkillPaths(List<String> skillsDirs) {
        List<String> paths = new java.util.ArrayList<>();

        for (String dir : skillsDirs) {
            if (dir == null || dir.trim().isEmpty()) {
                continue;
            }

            java.io.File rootDir = new java.io.File(dir);
            if (!rootDir.exists() || !rootDir.isDirectory()) {
                continue;
            }

            // 递归查找 SKILL.md（大小写不敏感）
            collectSkillFiles(rootDir, paths);
        }

        paths.sort(String::compareTo);
        return paths;
    }

    /**
     * 递归收集 SKILL.md 文件
     */
    private static void collectSkillFiles(java.io.File dir, List<String> paths) {
        java.io.File[] files = dir.listFiles();
        if (files == null) {
            return;
        }

        for (java.io.File file : files) {
            if (file.isDirectory()) {
                collectSkillFiles(file, paths);
            } else if (file.isFile() && "SKILL.MD".equalsIgnoreCase(file.getName())) {
                paths.add(file.getAbsolutePath());
            }
        }
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
}
