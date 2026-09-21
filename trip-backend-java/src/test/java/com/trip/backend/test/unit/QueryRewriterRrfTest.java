package com.trip.backend.test.unit;

import com.trip.backend.service.rag.QueryRewriter;
import com.trip.backend.service.rag.Rrf;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-C2 QueryRewriter + Rrf 单元测试（纯内存，无 DB）。
 */
class QueryRewriterRrfTest {

    // ------------------------------------------------------------------
    // QueryRewriter（对齐 Python query_rewriter.py 实际实现）
    // ------------------------------------------------------------------

    @Test
    void extractKeywordsSplitsByWhitespace() {
        QueryRewriter rewriter = new QueryRewriter();
        // 空格分隔的中文词逐词提取（Python 实际行为）
        List<String> keywords = rewriter.extractKeywords("北京 故宫 玩");
        // "玩" len<2 被过滤
        assertEquals(List.of("北京", "故宫"), keywords);
    }

    @Test
    void extractKeywordsKeepsUnsplittedChineseAsWhole() {
        QueryRewriter rewriter = new QueryRewriter();
        // 无空格中文整串作为一个 \w+ 匹配（与 Python re.findall 实际行为一致）
        List<String> keywords = rewriter.extractKeywords("我想去北京故宫玩");
        assertEquals(List.of("我想去北京故宫玩"), keywords);
    }

    @Test
    void extractKeywordsFiltersStopWordsAndShortWords() {
        QueryRewriter rewriter = new QueryRewriter();
        // 单字与停用词全部被过滤 → 空（Python 实际行为一致）
        List<String> keywords = rewriter.extractKeywords("的 了 在 是 我 有 a an the 玩 吃");
        assertEquals(List.of(), keywords);
        // 双字以上且非停用词保留
        assertEquals(List.of("美食", "餐厅"), rewriter.extractKeywords("美食 餐厅 的 我"));
    }

    @Test
    void extractKeywordsDedupKeepsOrderAndLimits() {
        QueryRewriter rewriter = new QueryRewriter();
        List<String> keywords = rewriter.extractKeywords("故宫 长城 故宫 天安门 颐和园 故宫 鸟巢 水立方 798 南锣鼓巷 什刹海 雍和宫", 5);
        assertEquals(List.of("故宫", "长城", "天安门", "颐和园", "鸟巢"), keywords);
    }

    @Test
    void extractKeywordsHandlesEnglish() {
        QueryRewriter rewriter = new QueryRewriter();
        List<String> keywords = rewriter.extractKeywords("I want to visit the Great Wall");
        // 停用词过滤 i/want/to/the；visit/great/wall 保留
        assertEquals(List.of("want", "visit", "great", "wall"), keywords);
    }

    @Test
    void rewriteWithCityPrefix() {
        QueryRewriter rewriter = new QueryRewriter();
        // 与 Python 实际行为一致：rewrite_query("我想去故宫玩", city="北京") -> "北京 我想去故宫玩"
        assertEquals("北京 我想去故宫玩", rewriter.rewrite("我想去故宫玩", "北京", null));
    }

    @Test
    void rewriteWithoutCityReturnsKeywords() {
        QueryRewriter rewriter = new QueryRewriter();
        assertEquals("我想去故宫玩", rewriter.rewrite("我想去故宫玩", null, null));
        assertEquals("故宫 长城", rewriter.rewrite("故宫 长城", null, null));
    }

    @Test
    void rewriteCleansPunctuationAndWhitespace() {
        QueryRewriter rewriter = new QueryRewriter();
        assertEquals("北京 故宫", rewriter.rewrite(" 北京，故宫！ ", null, null));
        // 清洗后为两词且 city=北京 已在关键词中 → 不重复前置
        assertEquals("北京 故宫", rewriter.rewrite(" 北京，故宫！ ", "北京", null));
    }

    @Test
    void rewriteCityPrefixesWhenNotInKeywords() {
        QueryRewriter rewriter = new QueryRewriter();
        // city=北京 不在关键词整串中 → 前置拼装（Python 实际行为）
        assertEquals("北京 北京故宫", rewriter.rewrite("北京故宫", "北京", null));
    }

    // ------------------------------------------------------------------
    // Rrf（对齐 Python rrf.py docstring 示例 + 加权）
    // ------------------------------------------------------------------

    private Map<String, Object> doc(String id, String name) {
        Map<String, Object> d = new LinkedHashMap<>();
        d.put("id", id);
        d.put("name", name);
        return d;
    }

    @Test
    void rrfMergeMatchesPythonExample() {
        // Python docstring: path1=[{1,故宫},{2,长城}], path2=[{2,长城},{3,天安门}]
        // merged[0]['id'] == '2'，且含 _rrf_score
        List<Map<String, Object>> path1 = new ArrayList<>();
        path1.add(doc("1", "故宫"));
        path1.add(doc("2", "长城"));
        List<Map<String, Object>> path2 = new ArrayList<>();
        path2.add(doc("2", "长城"));
        path2.add(doc("3", "天安门"));

        List<Map<String, Object>> merged = Rrf.rrfMerge(List.of(path1, path2), Rrf.DEFAULT_K, "id");

        assertEquals("2", merged.get(0).get("id"));
        assertTrue(merged.get(0).containsKey("_rrf_score"));
        // 分数 = 1/60 + 1/61 ≈ 0.03306
        double expected = 1.0 / 60 + 1.0 / 61;
        assertEquals(expected, (Double) merged.get(0).get("_rrf_score"), 1e-9);
        assertEquals("1", merged.get(1).get("id"));
        assertEquals("3", merged.get(2).get("id"));
        // 原路径数据不被修改（深拷贝语义）
        assertTrue(!path1.get(0).containsKey("_rrf_score"));
    }

    @Test
    void weightedRrfUsesWeights() {
        List<Map<String, Object>> path1 = new ArrayList<>();
        path1.add(doc("1", "故宫"));
        List<Map<String, Object>> path2 = new ArrayList<>();
        path2.add(doc("1", "故宫"));
        path2.add(doc("2", "长城"));

        List<Map<String, Object>> merged = Rrf.rrfMergeWithWeights(
            List.of(path1, path2), List.of(0.7, 0.5), Rrf.DEFAULT_K, "id");

        // id1 = 0.7/60 + 0.5/60 = 0.02；id2 = 0.5/61 ≈ 0.00820
        assertEquals("1", merged.get(0).get("id"));
        assertEquals(0.7 / 60 + 0.5 / 60, (Double) merged.get(0).get("_rrf_score"), 1e-9);
        assertEquals("2", merged.get(1).get("id"));
        assertEquals(0.5 / 61, (Double) merged.get(1).get("_rrf_score"), 1e-9);
    }

    @Test
    void weightedRrfRejectsMismatchedWeights() {
        List<Map<String, Object>> path1 = new ArrayList<>();
        path1.add(doc("1", "故宫"));
        assertThrows(IllegalArgumentException.class,
            () -> Rrf.rrfMergeWithWeights(List.of(path1), List.of(0.7, 0.5), Rrf.DEFAULT_K, "id"));
    }

    @Test
    void rrfFiltersEmptyPathsAndSkipsMissingIds() {
        List<Map<String, Object>> path1 = new ArrayList<>();
        path1.add(doc("1", "故宫"));
        Map<String, Object> noId = new LinkedHashMap<>();
        noId.put("name", "无名");
        path1.add(noId);

        List<Map<String, Object>> merged = Rrf.rrfMerge(List.of(List.of(), path1), Rrf.DEFAULT_K, "id");
        assertEquals(1, merged.size());
        assertEquals("1", merged.get(0).get("id"));
    }
}
