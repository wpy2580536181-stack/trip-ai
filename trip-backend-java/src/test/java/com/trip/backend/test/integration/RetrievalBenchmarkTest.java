package com.trip.backend.test.integration;

import com.trip.backend.infra.ai.BgeEmbedder;
import com.trip.backend.infra.ai.EmbedderHealth;
import com.trip.backend.infra.ai.OnnxModelLoader;
import com.trip.backend.service.rag.CredibilityService;
import com.trip.backend.service.rag.FulltextSearch;
import com.trip.backend.service.rag.QueryRewriter;
import com.trip.backend.service.rag.RatingSearch;
import com.trip.backend.service.rag.RetrievalPipeline;
import com.trip.backend.service.rag.VectorSearchSpots;
import com.trip.backend.service.rag.VectorSearchSpotDocs;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 总验收 #1：RAG 四路召回 vs 双路基线的 Hit@K/MRR 对拍。
 *
 * 真实环境：PostgreSQL (localhost:5432/trip_db) + ONNX bge-small embedder。
 * reranker 因 sentencepiece tokenizer 不在 Java 侧支持，四路模式传 null 自动降级 RRF。
 *
 * 相关性标注：每个查询指定一组相关 spot name 关键词，检索结果 name 包含任一关键词即相关。
 *
 * 输出：每查询 Hit@5/Hit@10/MRR 对比表 + 平均值 + 结论。
 * 弱断言：四路 avg Hit@10 不低于双路的 90%（召回质量不降）。
 */
class RetrievalBenchmarkTest {

    private static final String EMBEDDER_DIR = "/tmp/onnx-out/bge-small";

    private record QueryCase(String query, String city, List<String> relevant) {}

    private static final List<QueryCase> CASES = List.of(
        new QueryCase("北京故宫附近的景点", "北京", List.of("故宫","天安门","景山","北海","中山公园","太庙")),
        new QueryCase("北京烤鸭推荐", "北京", List.of("烤鸭","四季民福","全聚德","大董","便宜坊","鸭")),
        new QueryCase("西安历史文化景点", "西安", List.of("大明宫","大雁塔","陕西历史博物馆","城墙","钟楼","碑林","汉城湖")),
        new QueryCase("西安美食小吃推荐", "西安", List.of("泡馍","肉夹馍","凉皮","水盆","西安饭庄","biang","胡辣汤","饺子")),
        new QueryCase("成都大熊猫基地", "成都", List.of("熊猫","大熊猫")),
        new QueryCase("成都火锅推荐", "成都", List.of("火锅","串串","麻辣烫")),
        new QueryCase("杭州西湖景点", "杭州", List.of("西湖","断桥","雷峰塔","灵隐","苏堤","白堤")),
        new QueryCase("上海外滩夜景", "上海", List.of("外滩","陆家嘴","东方明珠","南京路")),
        new QueryCase("重庆洪崖洞", "重庆", List.of("洪崖洞","解放碑","朝天门")),
        new QueryCase("广州早茶美食", "广州", List.of("早茶","茶楼","点心","虾饺","肠粉")),
        new QueryCase("昆明滇池周边", "昆明", List.of("滇池","翠湖","西山","民族村")),
        new QueryCase("武汉黄鹤楼", "武汉", List.of("黄鹤楼","东湖","户部巷","长江大桥"))
    );

    private static RetrievalPipeline dualPipeline;
    private static RetrievalPipeline fourPipeline;

    @BeforeAll
    static void setup() throws Exception {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.postgresql.Driver");
        ds.setUrl("jdbc:postgresql://localhost:5432/trip_db");
        ds.setUsername("trip");
        ds.setPassword("trip123");
        JdbcTemplate jdbc = new JdbcTemplate(ds);

        // ONNX embedder 同步预热
        OnnxModelLoader loader = new OnnxModelLoader();
        EmbedderHealth health = new EmbedderHealth();
        BgeEmbedder embedder = new BgeEmbedder(health, loader, EMBEDDER_DIR, 512);
        boolean warmed = embedder.warmup();
        System.out.println("[benchmark] embedder warmup=" + warmed + " available=" + health.isAvailable());
        assertTrue(warmed, "ONNX embedder 预热失败，无法跑四路对拍");

        QueryRewriter rewriter = new QueryRewriter();
        FulltextSearch fulltext = new FulltextSearch(jdbc);
        RatingSearch rating = new RatingSearch(jdbc);
        VectorSearchSpots vecSpots = new VectorSearchSpots(jdbc);
        VectorSearchSpotDocs vecDocs = new VectorSearchSpotDocs(jdbc);
        CredibilityService cred = new CredibilityService();

        // 双路（C2 基线）
        dualPipeline = new RetrievalPipeline(rewriter, rating, fulltext, 10);
        // 四路（rerank=null 自动降级 RRF，仍含两路向量召回 + credibility）
        fourPipeline = new RetrievalPipeline(rewriter, rating, fulltext,
            embedder, vecSpots, vecDocs, cred, null, true, 10);
    }

    @Test
    void hitAtKAndMrrBenchmark() {
        System.out.println();
        System.out.println("============================================================");
        System.out.println(" RAG 召回对拍：双路(C2基线) vs 四路");
        System.out.println("============================================================");
        System.out.printf("%-4s %-22s %6s %6s %6s | %6s %6s %6s%n",
            "#", "query", "H@5", "H@10", "MRR", "H@5", "H@10", "MRR");
        System.out.println("                                    ------ dual ------  ------ four ------");

        double dualH5=0, dualH10=0, dualMRR=0;
        double fourH5=0, fourH10=0, fourMRR=0;
        int dualPathSum=0, fourPathSum=0;

        for (int i=0; i<CASES.size(); i++) {
            QueryCase c = CASES.get(i);
            List<Map<String,Object>> dualRes = dualPipeline.retrieve(c.query(), c.city(), null, 10);
            List<Map<String,Object>> fourRes = fourPipeline.retrieve(c.query(), c.city(), null, 10);

            double[] d = metrics(dualRes, c.relevant());
            double[] f = metrics(fourRes, c.relevant());
            dualH5+=d[0]; dualH10+=d[1]; dualMRR+=d[2];
            fourH5+=f[0]; fourH10+=f[1]; fourMRR+=f[2];
            dualPathSum += dualPipeline.getLastFusedPathCount();
            fourPathSum += fourPipeline.getLastFusedPathCount();

            String q = c.query().length()>20 ? c.query().substring(0,20) : c.query();
            System.out.printf("%-4d %-22s %6.2f %6.2f %6.3f | %6.2f %6.2f %6.3f%n",
                i+1, q, d[0], d[1], d[2], f[0], f[1], f[2]);
        }

        int n = CASES.size();
        System.out.println("------------------------------------------------------------");
        System.out.printf("%-4s %-22s %6.2f %6.2f %6.3f | %6.2f %6.2f %6.3f%n",
            "", "AVG", dualH5/n, dualH10/n, dualMRR/n, fourH5/n, fourH10/n, fourMRR/n);
        System.out.println("------------------------------------------------------------");
        System.out.printf("平均融合路径数：双路=%.1f  四路=%.1f%n",
            (double)dualPathSum/n, (double)fourPathSum/n);

        double deltaH10 = fourH10/n - dualH10/n;
        double deltaMRR = fourMRR/n - dualMRR/n;
        System.out.printf("四路 - 双路：ΔHit@10=%+.2f  ΔMRR=%+.3f%n", deltaH10, deltaMRR);

        String verdict;
        if (fourH10/n >= dualH10/n * 0.9 && fourMRR/n >= dualMRR/n * 0.9) {
            verdict = "PASS：四路召回质量不低于双路基线（≥90%）";
        } else {
            verdict = "WARN：四路低于双路 90% 阈值，需检查";
        }
        System.out.println("结论：" + verdict);
        System.out.println("============================================================");

        assertTrue(fourH10/n >= dualH10/n * 0.9,
            "四路 Hit@10 低于双路 90%：dual=" + dualH10/n + " four=" + fourH10/n);
    }

    /** 返回 [hit@5, hit@10, mrr] */
    private double[] metrics(List<Map<String,Object>> results, List<String> relevant) {
        double hit5=0, hit10=0, mrr=0;
        int firstRelRank = -1;
        int relCountAt10 = 0;
        for (int i=0; i<results.size(); i++) {
            String name = String.valueOf(results.get(i).get("name"));
            boolean isRel = relevant.stream().anyMatch(name::contains);
            if (isRel) {
                if (firstRelRank < 0) firstRelRank = i+1;
                if (i < 10) relCountAt10++;
            }
        }
        if (firstRelRank > 0) {
            mrr = 1.0 / firstRelRank;
            if (firstRelRank <= 5) hit5 = 1;
            if (firstRelRank <= 10) hit10 = 1;
        }
        return new double[]{hit5, hit10, mrr};
    }
}
