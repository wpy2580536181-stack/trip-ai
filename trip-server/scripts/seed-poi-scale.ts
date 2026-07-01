/**
 * 大规模 POI 导入 — 测试 Chroma 在 5w+ 数据量下的表现
 *
 * 用法: npx tsx scripts/seed-poi-scale.ts
 *
 * 覆盖 ~300 个地级市，每城市多组关键词，目标新增 ~50,000 条
 */
import 'dotenv/config'
import * as amapMcpProcess from '../src/services/mcp/amapMcpProcess'
import * as amapMcpClient from '../src/services/mcp/amapMcpClient'
import { bulkImportSpots } from '../src/services/knowledgeService'
import type { SpotInput } from '../src/types/agent'
import prisma from '../src/config/database'

// 300+ 地级市（含县级市、自治州）
const CITIES: string[] = [
  // 直辖市 + 省会
  '北京', '上海', '天津', '重庆', '石家庄', '太原', '呼和浩特', '沈阳', '长春', '哈尔滨',
  '南京', '杭州', '合肥', '福州', '南昌', '济南', '郑州', '武汉', '长沙', '广州',
  '南宁', '海口', '成都', '贵阳', '昆明', '拉萨', '西安', '兰州', '西宁', '银川', '乌鲁木齐',
  // 河北
  '唐山', '秦皇岛', '邯郸', '邢台', '保定', '张家口', '承德', '沧州', '廊坊', '衡水',
  // 山西
  '大同', '阳泉', '长治', '晋城', '朔州', '晋中', '运城', '忻州', '临汾', '吕梁',
  // 内蒙古
  '包头', '乌海', '赤峰', '通辽', '鄂尔多斯', '呼伦贝尔', '巴彦淖尔', '乌兰察布', '兴安盟', '锡林郭勒',
  // 辽宁
  '大连', '鞍山', '抚顺', '本溪', '丹东', '锦州', '营口', '阜新', '辽阳', '盘锦', '铁岭', '朝阳', '葫芦岛',
  // 吉林
  '吉林', '四平', '辽源', '通化', '白山', '松原', '白城', '延边',
  // 黑龙江
  '齐齐哈尔', '鸡西', '鹤岗', '双鸭山', '大庆', '伊春', '佳木斯', '七台河', '牡丹江', '黑河', '绥化', '大兴安岭',
  // 江苏
  '无锡', '徐州', '常州', '苏州', '南通', '连云港', '淮安', '盐城', '扬州', '镇江', '泰州', '宿迁',
  // 浙江
  '宁波', '温州', '嘉兴', '湖州', '绍兴', '金华', '衢州', '舟山', '台州', '丽水',
  // 安徽
  '芜湖', '蚌埠', '淮南', '马鞍山', '淮北', '铜陵', '安庆', '黄山', '滁州', '阜阳', '宿州', '六安', '亳州', '池州', '宣城',
  // 福建
  '厦门', '莆田', '三明', '泉州', '漳州', '南平', '龙岩', '宁德',
  // 江西
  '景德镇', '萍乡', '九江', '新余', '鹰潭', '赣州', '吉安', '宜春', '抚州', '上饶',
  // 山东
  '青岛', '淄博', '枣庄', '东营', '烟台', '潍坊', '济宁', '泰安', '威海', '日照', '临沂', '德州', '聊城', '滨州', '菏泽',
  // 河南
  '开封', '洛阳', '平顶山', '安阳', '鹤壁', '新乡', '焦作', '濮阳', '许昌', '漯河', '三门峡', '南阳', '商丘', '信阳', '周口', '驻马店', '济源',
  // 湖北
  '黄石', '十堰', '宜昌', '襄阳', '鄂州', '荆门', '孝感', '荆州', '黄冈', '咸宁', '随州', '恩施', '仙桃', '潜江', '天门', '神农架',
  // 湖南
  '株洲', '湘潭', '衡阳', '邵阳', '岳阳', '常德', '张家界', '益阳', '郴州', '永州', '怀化', '娄底', '湘西',
  // 广东
  '韶关', '深圳', '珠海', '汕头', '佛山', '江门', '湛江', '茂名', '肇庆', '惠州', '梅州', '汕尾', '河源', '阳江', '清远', '东莞', '中山', '潮州', '揭阳', '云浮',
  // 广西
  '柳州', '桂林', '梧州', '北海', '防城港', '钦州', '贵港', '玉林', '百色', '贺州', '河池', '来宾', '崇左',
  // 海南
  '三亚', '三沙', '儋州',
  // 四川
  '自贡', '攀枝花', '泸州', '德阳', '绵阳', '广元', '遂宁', '内江', '乐山', '南充', '眉山', '宜宾', '广安', '达州', '雅安', '巴中', '资阳', '阿坝', '甘孜', '凉山',
  // 贵州
  '六盘水', '遵义', '安顺', '毕节', '铜仁', '黔西南', '黔东南', '黔南',
  // 云南
  '曲靖', '玉溪', '保山', '昭通', '丽江', '普洱', '临沧', '楚雄', '红河', '文山', '西双版纳', '大理', '德宏', '怒江', '迪庆',
  // 西藏
  '日喀则', '昌都', '林芝', '山南', '那曲', '阿里',
  // 陕西
  '铜川', '宝鸡', '咸阳', '渭南', '延安', '汉中', '榆林', '安康', '商洛',
  // 甘肃
  '嘉峪关', '金昌', '白银', '天水', '武威', '张掖', '平凉', '酒泉', '庆阳', '定西', '陇南', '临夏', '甘南',
  // 青海
  '海东', '海北', '黄南', '海南', '果洛', '玉树', '海西',
  // 宁夏
  '石嘴山', '吴忠', '固原', '中卫',
  // 新疆
  '克拉玛依', '吐鲁番', '哈密', '昌吉', '博尔塔拉', '巴音郭楞', '阿克苏', '克孜勒苏', '喀什', '和田', '伊犁', '塔城', '阿勒泰',
]

const KEYWORDS: Record<string, string[]> = {
  attraction: ['景点', '公园', '广场', '风景区'],
  food: ['美食', '小吃', '火锅', '餐厅'],
  hotel: ['酒店', '宾馆', '住宿', '民宿'],
}

function parsePois(raw: string, city: string, category: SpotInput['category']): SpotInput[] {
  try {
    const data = JSON.parse(raw)
    return (data?.pois || []).map((poi: any) => ({
      name: (poi.name || '').slice(0, 100),
      city,
      category,
      description: (poi.address ? `位于${poi.address}` : poi.name || '').slice(0, 500),
      tags: poi.typecode ? [poi.typecode.slice(0, 6)] : [],
    }))
  } catch {
    return []
  }
}

async function main() {
  console.log(`\n=== 大规模 POI 导入（Chroma 压测）===`)
  console.log(`城市: ${CITIES.length} | 每城市 ${Object.values(KEYWORDS).flat().length} 次搜索`)

  // 加载已有去重 key
  console.log('\n[1/5] 加载已有数据...')
  const existing = await prisma.spot.findMany({ select: { city: true, name: true, category: true } })
  const existingSet = new Set(existing.map(s => `${s.city}:${s.name}:${s.category}`))
  console.log(`  DB 已有 ${existing.length} 条`)

  // 启动 MCP
  console.log('\n[2/5] 启动高德 MCP...')
  await amapMcpProcess.start()
  if (!amapMcpProcess.isAlive()) { console.error('MCP 启动失败'); process.exit(1) }
  await amapMcpClient.connect()
  console.log('  就绪')

  // 搜索
  console.log('\n[3/5] 搜索 POI...')
  const startTime = Date.now()
  let totalNew = 0
  let totalCalls = 0

  for (let ci = 0; ci < CITIES.length; ci++) {
    const city = CITIES[ci]
    const seen = new Set<string>()
    const citySpots: SpotInput[] = []

    for (const [cat, keywords] of Object.entries(KEYWORDS)) {
      for (const kw of keywords) {
        totalCalls++
        try {
          const raw = await amapMcpClient.callTool('maps_text_search', { keywords: kw, city })
          const parsed = parsePois(raw, city, cat as SpotInput['category'])
          for (const spot of parsed) {
            const key = `${spot.city}:${spot.name}:${spot.category}`
            if (seen.has(key) || existingSet.has(key)) continue
            seen.add(key)
            citySpots.push(spot)
          }
        } catch {
          // 跳过单个搜索失败
        }
        // 50ms 延迟，防止打满高德限流
        await new Promise(r => setTimeout(r, 50))
      }
    }

    if (citySpots.length === 0) continue
    const result = await bulkImportSpots(citySpots)
    totalNew += result.success
    const elapsed = Math.round((Date.now() - startTime) / 1000)
    console.log(`  [${ci + 1}/${CITIES.length}] ${city}: ${citySpots.length} 条 (累计 ${totalNew}，已用 ${elapsed}s)`)
  }

  // 关闭
  console.log('\n[4/5] 关闭 MCP...')
  amapMcpClient.close()
  amapMcpProcess.stop()

  // 统计
  console.log('\n[5/5] 结果')
  const finalCount = await prisma.spot.count()
  console.log(`  MCP 调用次数: ${totalCalls}`)
  console.log(`  新增记录: ${totalNew}`)
  console.log(`  DB 总数: ${finalCount}`)
  console.log(`  用时: ${Math.round((Date.now() - startTime) / 1000)}s`)
  await prisma.$disconnect()
  process.exit(0)
}

main().catch(err => {
  console.error('脚本失败:', err)
  amapMcpClient.close()
  amapMcpProcess.stop()
  process.exit(1)
})
