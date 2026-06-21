import { z } from 'zod'
import { DynamicStructuredTool } from '@langchain/community/tools/dynamic'
import { withResilience } from '../resilience'
import { agentLog as log } from '../../../utils/logger'

const GetWeatherInputSchema = z.object({
  city: z.string().describe('城市名，中文或拼音'),
})

interface WttrCondition {
  temp_C: string
  weatherDesc: { value: string }[]
  humidity: string
  windspeedKmph: string
  FeelsLikeC: string
}

interface WttrDay {
  date: string
  astronomy: { sunrise: string; sunset: string }[]
  maxtempC: string
  mintempC: string
  hourly: WttrCondition[]
}

interface WttrResponse {
  current_condition: WttrCondition[]
  weather: WttrDay[]
}

// 修复 P2-6：SSRF 防护 — 域名白名单 + 内网地址拒绝
const ALLOWED_HOST = 'wttr.in'
const PRIVATE_IP_RE = /^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|0\.0\.0\.0|169\.254\.)/

function isPrivateHost(host: string): boolean {
  return PRIVATE_IP_RE.test(host) || host === 'localhost'
}

export const getWeatherTool = withResilience(
  new DynamicStructuredTool({
    name: 'get_weather',
    description: `查询目标城市当前天气和未来天气预报。
当用户询问天气、温度、要不要带伞、什么季节去合适时使用。
输入：city（城市名，中英文均可）。`,
    schema: GetWeatherInputSchema,
    func: async (input: z.infer<typeof GetWeatherInputSchema>) => {
      const url = `https://wttr.in/${encodeURIComponent(input.city)}?format=j1`

      // SSRF 防护：先解析 URL 检查 host
      let parsed: URL
      try {
        parsed = new URL(url)
      } catch {
        return `${input.city} 的城市名格式无效。`
      }
      if (parsed.protocol !== 'https:') {
        return '仅支持 HTTPS 协议访问天气服务。'
      }
      if (parsed.hostname !== ALLOWED_HOST) {
        log.warn({ hostname: parsed.hostname }, 'SSRF 防护：拒绝非白名单域名')
        return '天气服务域名未授权。'
      }
      if (isPrivateHost(parsed.hostname)) {
        log.warn({ hostname: parsed.hostname }, 'SSRF 防护：拒绝内网地址')
        return '天气服务地址无效。'
      }

      const res = await fetch(url)
      if (!res.ok) {
        return `暂时无法获取 ${input.city} 的天气信息。`
      }
      const data = (await res.json()) as WttrResponse
      const parts: string[] = []

      const now = data.current_condition?.[0]
      if (now) {
        const desc = now.weatherDesc.map(d => d.value).join(', ')
        parts.push(`当前天气：${desc}`)
        parts.push(`温度：${now.temp_C}°C（体感 ${now.FeelsLikeC}°C）`)
        parts.push(`湿度：${now.humidity}% · 风速：${now.windspeedKmph}km/h`)
        parts.push('')
      }

      const forecast = data.weather?.slice(0, 3) ?? []
      if (forecast.length > 0) {
        parts.push('未来天气预报：')
        for (const day of forecast) {
          const sunrise = day.astronomy?.[0]?.sunrise ?? ''
          const sunset = day.astronomy?.[0]?.sunset ?? ''
          parts.push(`  ${day.date}：${day.mintempC}~${day.maxtempC}°C${sunrise ? ` · 日出${sunrise} 日落${sunset}` : ''}`)
        }
      }

      return parts.join('\n') || `${input.city} 天气数据暂不可用。`
    },
  }),
  {
    timeout: 10000,
    retries: 1,
    fallback: '天气服务暂时不可用，请根据季节常识判断。',
  },
)
