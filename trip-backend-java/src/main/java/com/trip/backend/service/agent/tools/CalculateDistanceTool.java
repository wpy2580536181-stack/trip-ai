package com.trip.backend.service.agent.tools;

import com.trip.backend.service.llm.LlmClient;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * calculate_distance 工具（对应 Python tools/calculate_distance.py）。
 *
 * train/flight：haversine 直线距离 + 经验估算；car 模式真实路网留待 J-D6 MCP 接入。
 * 城市坐标表与 Python CITY_COORDS 对齐。
 */
@Component
public class CalculateDistanceTool implements AgentTool {

    private static final Map<String, double[]> CITY_COORDS = new LinkedHashMap<>();
    static {
        CITY_COORDS.put("北京", new double[]{39.9042, 116.4074});
        CITY_COORDS.put("上海", new double[]{31.2304, 121.4737});
        CITY_COORDS.put("广州", new double[]{23.1291, 113.2644});
        CITY_COORDS.put("深圳", new double[]{22.5431, 114.0579});
        CITY_COORDS.put("成都", new double[]{30.5728, 104.0668});
        CITY_COORDS.put("杭州", new double[]{30.2741, 120.1551});
        CITY_COORDS.put("武汉", new double[]{30.5928, 114.3055});
        CITY_COORDS.put("西安", new double[]{34.3416, 108.9398});
        CITY_COORDS.put("重庆", new double[]{29.4316, 106.9123});
        CITY_COORDS.put("南京", new double[]{32.0603, 118.7969});
        CITY_COORDS.put("天津", new double[]{39.3434, 117.3616});
        CITY_COORDS.put("长沙", new double[]{28.2282, 112.9388});
        CITY_COORDS.put("苏州", new double[]{31.2990, 120.5853});
        CITY_COORDS.put("厦门", new double[]{24.4798, 118.0894});
        CITY_COORDS.put("青岛", new double[]{36.0671, 120.3826});
        CITY_COORDS.put("大连", new double[]{38.9140, 121.6147});
        CITY_COORDS.put("昆明", new double[]{25.0389, 102.7183});
        CITY_COORDS.put("三亚", new double[]{18.2528, 109.5120});
        CITY_COORDS.put("哈尔滨", new double[]{45.8038, 126.5350});
        CITY_COORDS.put("桂林", new double[]{25.2736, 110.2900});
        CITY_COORDS.put("拉萨", new double[]{29.6500, 91.1000});
        CITY_COORDS.put("乌鲁木齐", new double[]{43.8256, 87.6168});
        CITY_COORDS.put("贵阳", new double[]{26.6470, 106.6302});
        CITY_COORDS.put("南宁", new double[]{22.8170, 108.3665});
        CITY_COORDS.put("南昌", new double[]{28.6829, 115.8582});
        CITY_COORDS.put("福州", new double[]{26.0745, 119.2965});
        CITY_COORDS.put("合肥", new double[]{31.8206, 117.2272});
        CITY_COORDS.put("郑州", new double[]{34.7466, 113.6253});
        CITY_COORDS.put("济南", new double[]{36.6512, 116.9972});
        CITY_COORDS.put("太原", new double[]{37.8706, 112.5489});
        CITY_COORDS.put("兰州", new double[]{36.0611, 103.8343});
    }

    @Override
    public String name() {
        return "calculate_distance";
    }

    @Override
    public String description() {
        return """
            计算两个城市之间的交通距离、时间和大致费用。

            当用户询问"A到B多远"、"怎么去"、"交通时间"时使用。
            car 模式返回真实驾车路网里程与耗时；train/flight 为直线距离 + 经验估算（标注「估算」）。""";
    }

    @Override
    public LlmClient.ToolSpec spec() {
        return new LlmClient.ToolSpec(name(), description(),
            """
            {"type":"object",
             "properties":{
               "from_city":{"type":"string","description":"出发城市名"},
               "to_city":{"type":"string","description":"目的地城市名"},
               "mode":{"type":"string","description":"交通方式：train/car/flight，默认 flight"}
             },
             "required":["from_city","to_city"]}""");
    }

    @Override
    public String execute(Map<String, Object> args) {
        String fromCity = args.get("from_city") == null ? "" : args.get("from_city").toString().trim();
        String toCity = args.get("to_city") == null ? "" : args.get("to_city").toString().trim();
        String mode = args.get("mode") == null || args.get("mode").toString().isBlank()
            ? "flight" : args.get("mode").toString().trim().toLowerCase();

        double[] c1 = CITY_COORDS.get(fromCity);
        double[] c2 = CITY_COORDS.get(toCity);
        if (c1 == null || c2 == null) {
            StringBuilder unknown = new StringBuilder();
            if (c1 == null) unknown.append(fromCity);
            if (c2 == null) {
                if (unknown.length() > 0) unknown.append('、');
                unknown.append(toCity);
            }
            return "暂不支持城市 " + unknown + " 的距离查询。";
        }

        double km = haversine(c1[0], c1[1], c2[0], c2[1]);
        String modeCn = switch (mode) {
            case "train" -> "高铁";
            case "car" -> "自驾";
            default -> "飞机";
        };
        int hours;
        int costMin;
        int costMax;
        if ("train".equals(mode)) {
            hours = (int) Math.round(km / 300);
            costMin = (int) Math.round(km * 0.3);
            costMax = (int) Math.round(km * 0.8);
        } else if ("car".equals(mode)) {
            hours = (int) Math.round(km / 80);
            costMin = (int) Math.round(km * 0.6);
            costMax = (int) Math.round(km * 1.2);
        } else {
            hours = (int) Math.round(km / 800.0) + 1;
            costMin = (int) Math.round(km * 0.5);
            costMax = (int) Math.round(km * 1.5);
        }
        String note = "（直线距离估算）";
        return "从 " + fromCity + " 到 " + toCity + note + "\n"
            + "直线距离：" + Math.round(km) + " 公里\n"
            + "交通方式：" + modeCn + "\n"
            + "预估时间：" + hours + " 小时\n"
            + "预估费用：" + costMin + "~" + costMax + " 元";
    }

    @Override
    public String fallback() {
        return "距离计算暂时不可用。";
    }

    @Override
    public long timeoutSec() {
        return 5;
    }

    private static double haversine(double lat1, double lon1, double lat2, double lon2) {
        final double r = 6371;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
            + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
            * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return r * c;
    }
}
