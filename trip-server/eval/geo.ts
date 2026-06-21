/**
 * 城市坐标 + 周边城市判定（100km 直线距离）
 *
 * 用 Haversine 公式算两点间球面距离。
 * 100km 是一个比较保守的"周边"——城市群内 1.5h 高铁可达范围。
 */

interface CityCoord {
  name: string
  lat: number
  lng: number
}

const CITY_COORDS: CityCoord[] = [
  // 一线
  { name: '北京', lat: 39.9042, lng: 116.4074 },
  { name: '上海', lat: 31.2304, lng: 121.4737 },
  { name: '广州', lat: 23.1291, lng: 113.2644 },
  { name: '深圳', lat: 22.5431, lng: 114.0579 },
  // 强二线 / 旅游热门
  { name: '成都', lat: 30.5728, lng: 104.0668 },
  { name: '重庆', lat: 29.5630, lng: 106.5516 },
  { name: '杭州', lat: 30.2741, lng: 120.1551 },
  { name: '西安', lat: 34.3416, lng: 108.9398 },
  { name: '南京', lat: 32.0603, lng: 118.7969 },
  { name: '苏州', lat: 31.2989, lng: 120.5853 },
  { name: '天津', lat: 39.3434, lng: 117.3616 },
  { name: '武汉', lat: 30.5928, lng: 114.3055 },
  { name: '长沙', lat: 28.2282, lng: 112.9388 },
  { name: '青岛', lat: 36.0671, lng: 120.3826 },
  { name: '厦门', lat: 24.4798, lng: 118.0894 },
  { name: '大连', lat: 38.9140, lng: 121.6147 },
  { name: '昆明', lat: 25.0389, lng: 102.7183 },
  { name: '丽江', lat: 26.8721, lng: 100.2330 },
  { name: '大理', lat: 25.6065, lng: 100.2676 },
  { name: '三亚', lat: 18.2528, lng: 109.5119 },
  { name: '桂林', lat: 25.2736, lng: 110.2907 },
  { name: '张家界', lat: 29.1170, lng: 110.4791 },
  { name: '黄山', lat: 29.7147, lng: 118.3376 },
  { name: '拉萨', lat: 29.6500, lng: 91.1700 },
  { name: '敦煌', lat: 40.1421, lng: 94.6612 },
  // 城市群周边（100km 内常见旅游目的地）
  { name: '都江堰', lat: 30.9912, lng: 103.6190 },      // 成都西北 ~50km
  { name: '青城山', lat: 30.9000, lng: 103.5667 },      // 成都西 ~60km
  { name: '乐山', lat: 29.5521, lng: 103.7660 },        // 成都南 ~130km（出 100km，但旅游线常连）
  { name: '峨眉山', lat: 29.5167, lng: 103.4833 },      // 成都南 ~140km
  { name: '昆山', lat: 31.3819, lng: 120.9786 },        // 上海西 ~50km
  { name: '嘉兴', lat: 30.7522, lng: 120.7506 },        // 上海南 ~85km
  { name: '无锡', lat: 31.4912, lng: 120.3119 },        // 上海西 ~100km
  { name: '绍兴', lat: 30.0023, lng: 120.5810 },        // 杭州东 ~60km
  { name: '乌镇', lat: 30.7461, lng: 120.4943 },        // 杭州北 ~80km
  { name: '千岛湖', lat: 29.6058, lng: 119.0217 },      // 杭州西 ~120km
  { name: '西塘', lat: 30.9303, lng: 120.8916 },        // 上海西 ~85km
  { name: '秦皇岛', lat: 39.9354, lng: 119.6005 },      // 北京东 ~280km
  { name: '承德', lat: 40.9519, lng: 117.9634 },        // 北京东北 ~200km
  { name: '平遥', lat: 37.1894, lng: 112.1742 },        // 太原南
  { name: '华山', lat: 34.4833, lng: 110.0833 },        // 西安东 ~120km
  { name: '武当山', lat: 32.4000, lng: 111.0000 },      // 武汉西北 ~400km
  { name: '凤凰', lat: 27.9483, lng: 109.5992 },        // 长沙西
  { name: '北戴河', lat: 39.8300, lng: 119.4900 },      // 北京东
  { name: '婺源', lat: 29.2485, lng: 117.8612 },        // 景德镇
  { name: '宏村', lat: 29.9110, lng: 117.9833 },        // 黄山
  // 国际
  { name: '东京', lat: 35.6762, lng: 139.6503 },
  { name: '京都', lat: 35.0116, lng: 135.7681 },
  { name: '大阪', lat: 34.6937, lng: 135.5023 },
  { name: '首尔', lat: 37.5665, lng: 126.9780 },
  { name: '曼谷', lat: 13.7563, lng: 100.5018 },
  { name: '清迈', lat: 18.7883, lng: 98.9853 },
  { name: '巴黎', lat: 48.8566, lng: 2.3522 },
  { name: '伦敦', lat: 51.5074, lng: -0.1278 },
  { name: '纽约', lat: 40.7128, lng: -74.0060 },
  { name: '罗马', lat: 41.9028, lng: 12.4964 },
  { name: '巴塞罗那', lat: 41.3851, lng: 2.1734 },
  { name: '香港', lat: 22.3193, lng: 114.1694 },
  { name: '澳门', lat: 22.1987, lng: 113.5439 },
  { name: '台北', lat: 25.0330, lng: 121.5654 },
  { name: '镰仓', lat: 35.3197, lng: 139.5466 },        // 东京南 ~50km
  { name: '横滨', lat: 35.4437, lng: 139.6380 },        // 东京南 ~30km
  { name: '奈良', lat: 34.6851, lng: 135.8048 },        // 京都西 ~30km
  { name: '神户', lat: 34.6901, lng: 135.1955 },        // 大阪西 ~30km
  { name: '日惹', lat: -7.7956, lng: 110.3695 },
  { name: '巴厘岛', lat: -8.4095, lng: 115.1889 },
  { name: '普吉岛', lat: 7.8804, lng: 98.3923 },
]

const EARTH_RADIUS_KM = 6371

function haversineKm(a: CityCoord, b: CityCoord): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const lat1 = toRad(a.lat)
  const lat2 = toRad(b.lat)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h))
}

const COORD_MAP = new Map(CITY_COORDS.map((c) => [c.name, c]))

/** 计算两个城市之间的直线距离 km；任一城市未登记返回 null */
export function cityDistanceKm(a: string, b: string): number | null {
  const ca = COORD_MAP.get(a)
  const cb = COORD_MAP.get(b)
  if (!ca || !cb) return null
  return haversineKm(ca, cb)
}

/** 100km 内的城市视为周边 */
export const NEARBY_RADIUS_KM = 100

/**
 * 判断 poiCity 是否在 expectedCity 周边（100km 内）或同名
 * - 任一未登记 → 仅做严格相等
 */
export function isCityOrNearby(poiCity: string, expectedCity: string): boolean {
  if (poiCity === expectedCity) return true
  const dist = cityDistanceKm(poiCity, expectedCity)
  if (dist === null) return false
  return dist <= NEARBY_RADIUS_KM
}

/** 列出某城市 100km 内的所有已知城市（调试用） */
export function listNearby(city: string): string[] {
  const c = COORD_MAP.get(city)
  if (!c) return []
  return CITY_COORDS.filter((other) => other.name !== city && haversineKm(c, other) <= NEARBY_RADIUS_KM).map(
    (x) => x.name,
  )
}
