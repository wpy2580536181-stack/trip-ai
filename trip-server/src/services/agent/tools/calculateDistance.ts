import { z } from 'zod'
import { DynamicStructuredTool } from '@langchain/community/tools/dynamic'
import { withResilience } from '../resilience'

const CITY_COORDS: Record<string, [number, number]> = {
  '北京': [39.9042, 116.4074],
  '上海': [31.2304, 121.4737],
  '广州': [23.1291, 113.2644],
  '深圳': [22.5431, 114.0579],
  '成都': [30.5728, 104.0668],
  '杭州': [30.2741, 120.1551],
  '武汉': [30.5928, 114.3055],
  '西安': [34.3416, 108.9398],
  '重庆': [29.4316, 106.9123],
  '南京': [32.0603, 118.7969],
  '天津': [39.3434, 117.3616],
  '长沙': [28.2282, 112.9388],
  '苏州': [31.2990, 120.5853],
  '厦门': [24.4798, 118.0894],
  '青岛': [36.0671, 120.3826],
  '大连': [38.9140, 121.6147],
  '昆明': [25.0389, 102.7183],
  '三亚': [18.2528, 109.5120],
  '哈尔滨': [45.8038, 126.5350],
  '桂林': [25.2736, 110.2900],
  '拉萨': [29.6500, 91.1000],
  '乌鲁木齐': [43.8256, 87.6168],
  '贵阳': [26.6470, 106.6302],
  '南宁': [22.8170, 108.3665],
  '南昌': [28.6829, 115.8582],
  '福州': [26.0745, 119.2965],
  '合肥': [31.8206, 117.2272],
  '郑州': [34.7466, 113.6253],
  '济南': [36.6512, 116.9972],
  '太原': [37.8706, 112.5489],
  '兰州': [36.0611, 103.8343],
}

const CalculateDistanceInputSchema = z.object({
  from: z.string().describe('出发城市名'),
  to: z.string().describe('目的地城市名'),
  mode: z.enum(['train', 'car', 'flight']).optional().describe('交通方式，默认 flight'),
})

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLon = (lon2 - lon1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function estimateTravel(km: number, mode: string): { time: string; costMin: number; costMax: number } {
  switch (mode) {
    case 'train':
      return {
        time: `${Math.round(km / 300)} 小时`,
        costMin: Math.round(km * 0.3),
        costMax: Math.round(km * 0.8),
      }
    case 'car':
      return {
        time: `${Math.round(km / 80)} 小时`,
        costMin: Math.round(km * 0.6),
        costMax: Math.round(km * 1.2),
      }
    default:
      return {
        time: `${Math.round(km / 800) + 1} 小时（含值机候机）`,
        costMin: Math.round(km * 0.5),
        costMax: Math.round(km * 1.5),
      }
  }
}

export const calculateDistanceTool = withResilience(
  new DynamicStructuredTool({
    name: 'calculate_distance',
    description: `计算两个城市之间的交通距离、时间和大致费用。
当用户询问"A到B多远"、"怎么去"、"交通时间"时使用。
输入：from（出发城市）、to（目的地城市）、mode（交通方式：train/car/flight）。`,
    schema: CalculateDistanceInputSchema,
    func: async (input: z.infer<typeof CalculateDistanceInputSchema>) => {
      const { from, to, mode = 'flight' } = input
      const c1 = CITY_COORDS[from]
      const c2 = CITY_COORDS[to]
      if (!c1 || !c2) {
        const unknown = [c1 ? '' : from, c2 ? '' : to].filter(Boolean).join('、')
        return `暂不支持城市 ${unknown} 的距离查询。可用的城市：${Object.keys(CITY_COORDS).slice(0, 15).join('、')}等。`
      }
      const km = haversineKm(c1[0], c1[1], c2[0], c2[1])
      const est = estimateTravel(km, mode)
      return [
        `从 ${from} 到 ${to}`,
        `直线距离：${Math.round(km)} 公里`,
        `交通方式：${mode === 'train' ? '高铁' : mode === 'car' ? '自驾' : '飞机'}`,
        `预估时间：${est.time}`,
        `预估费用：${est.costMin}~${est.costMax} 元`,
      ].join('\n')
    },
  }),
  {
    timeout: 5000,
    retries: 1,
    fallback: '距离计算暂时不可用。',
  },
)
