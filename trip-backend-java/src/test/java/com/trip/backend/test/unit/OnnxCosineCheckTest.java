package com.trip.backend.test.unit;

import com.trip.backend.infra.ai.BgeEmbedder;
import com.trip.backend.infra.ai.EmbedderHealth;
import com.trip.backend.infra.ai.OnnxModelLoader;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

/**
 * J-C1 真实余弦对拍：Java 真 ONNX 复算 50 条 spot 文本向量，与 PG 库内向量余弦 ≥ 0.999。
 * 需要真实 PG（localhost:5432/trip_db）且 spots 表已有 embedding。
 */
class OnnxCosineCheckTest {

    @Test
    void cosineVsStoredVectors() throws Exception {
        BgeEmbedder embedder = new BgeEmbedder(new EmbedderHealth(), new OnnxModelLoader(),
                "models/bge-small-zh-v1.5", 512);
        assertTrue(embedder.warmup(), "embedder warmup 应成功（真 onnx 模型就位）");

        String url = "jdbc:postgresql://localhost:5432/trip_db";
        List<double[]> javaVecs = new ArrayList<>();
        List<double[]> dbVecs = new ArrayList<>();
        List<String[]> rows = new ArrayList<>();

        try (Connection c = DriverManager.getConnection(url, "trip", "trip123");
             Statement st = c.createStatement();
             ResultSet rs = st.executeQuery(
                     "SELECT city, name, coalesce(description,''), coalesce(tags::text,''), coalesce(category,''), embedding::text " +
                     "FROM spots WHERE embedding IS NOT NULL ORDER BY id LIMIT 50")) {
            while (rs.next()) {
                rows.add(new String[]{
                        rs.getString(1), rs.getString(2), rs.getString(3),
                        rs.getString(4), rs.getString(5), rs.getString(6)});
            }
        }
        assertFalse(rows.isEmpty(), "PG 应能取到带 embedding 的 spot 行");

        double minCos = 2.0, sumCos = 0; int n = 0; double bad = 0;
        for (String[] r : rows) {
            // 与 Python embedding_sync 同口径：city name description tags category
            String doc = (r[0] + " " + r[1] + " " + r[2] + " " + r[3] + " " + r[4]).trim();
            Optional<float[]> jv = embedder.embed(doc);
            assertTrue(jv.isPresent(), "Java embed 应出向量: " + r[1]);
            float[] ja = jv.get();
            double[] db = parseVector(r[5]);
            assertEquals(db.length, ja.length, "维度应一致 512");
            double cos = cosine(ja, db);
            minCos = Math.min(minCos, cos); sumCos += cos; n++;
            if (cos < 0.999) { bad++; System.out.printf("LOW cos=%.5f id?=%s%n", cos, r[1]); }
        }
        System.out.printf("J-C1 对拍: n=%d minCos=%.5f avgCos=%.5f low(<0.999)=%d%n",
                n, minCos, sumCos / n, bad);
        assertTrue(minCos >= 0.999, "最小余弦应 ≥ 0.999，实际 min=" + minCos);
    }

    private static double[] parseVector(String pg) {
        String t = pg.trim();
        if (t.startsWith("[")) t = t.substring(1);
        if (t.endsWith("]")) t = t.substring(0, t.length() - 1);
        String[] parts = t.split(",");
        double[] v = new double[parts.length];
        for (int i = 0; i < parts.length; i++) v[i] = Double.parseDouble(parts[i].trim());
        return v;
    }

    private static double cosine(float[] a, double[] b) {
        double dot = 0, na = 0, nb = 0;
        for (int i = 0; i < a.length; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
        return dot / (Math.sqrt(na) * Math.sqrt(nb));
    }
}
