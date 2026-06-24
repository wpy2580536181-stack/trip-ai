#!/usr/bin/env ts-node
/**
 * feedback-to-fixture CLI
 *
 * 用法：
 *   pnpm feedback:to-fixture --feedback-id=113
 *   pnpm feedback:to-fixture --days=7
 *   pnpm feedback:to-fixture --days=7 --dry-run
 *
 * 把生产环境的负反馈（rating=-1）转成 eval fixture 骨架 YAML，
 * 输出到 trip-server/eval/fixtures/generated/。
 *
 * 注意：CLI 不鉴权（admin 手动执行，等价 dev 工具）。
 */

import { feedbackService } from '../src/services/feedbackService'
import prisma from '../src/config/database'

interface Args {
  feedbackId?: number
  days?: number
  dryRun: boolean
}

function parseArgs(): Args {
  const argv = process.argv.slice(2)
  const args: Args = { dryRun: false }
  for (const a of argv) {
    if (a.startsWith('--feedback-id=')) args.feedbackId = parseInt(a.split('=')[1], 10)
    else if (a.startsWith('--days=')) args.days = parseInt(a.split('=')[1], 10)
    else if (a === '--dry-run') args.dryRun = true
  }
  return args
}

async function main() {
  const args = parseArgs()
  let feedbackIds: number[] = []

  if (args.feedbackId !== undefined) {
    feedbackIds = [args.feedbackId]
  } else if (args.days !== undefined) {
    const since = new Date(Date.now() - args.days * 24 * 60 * 60 * 1000)
    const downs = await prisma.feedback.findMany({
      where: { createdAt: { gte: since }, rating: -1 },
      select: { id: true },
      orderBy: { createdAt: 'desc' },
      take: 50,
    })
    feedbackIds = downs.map((d) => d.id)
    console.log(`[info] 找到 ${feedbackIds.length} 条 ${args.days} 天内的负反馈`)
  } else {
    console.error('错误：必须传 --feedback-id=N 或 --days=N')
    process.exit(1)
  }

  if (feedbackIds.length === 0) {
    console.log('[info] 没有可处理的 feedback，退出。')
    await prisma.$disconnect()
    return
  }

  if (args.dryRun) {
    console.log(`[dry-run] 将处理 ${feedbackIds.length} 条 feedback：${feedbackIds.join(', ')}`)
    console.log(`[dry-run] 不写文件，仅打印。去掉 --dry-run 真正执行。`)
    await prisma.$disconnect()
    return
  }

  const success: string[] = []
  const skipped: Array<{ id: number; reason: string }> = []
  for (const id of feedbackIds) {
    try {
      const file = await feedbackService.convertToFixture(id)
      success.push(file)
      console.log(`[ok] feedback #${id} → ${file}`)
    } catch (e) {
      const reason = e instanceof Error ? e.message : String(e)
      skipped.push({ id, reason })
      console.warn(`[skip] feedback #${id}：${reason}`)
    }
  }

  console.log(`\n[summary]`)
  console.log(`  ✓ 成功: ${success.length}`)
  console.log(`  ✗ 跳过: ${skipped.length}`)
  if (skipped.length > 0) {
    for (const s of skipped) console.log(`    - feedback #${s.id}: ${s.reason}`)
  }
  if (success.length > 0) {
    console.log(`\n[next] 请到 IDE 编辑生成的文件，补 expected 段后 git commit。`)
  }
  await prisma.$disconnect()
}

main().catch((e) => {
  console.error('[fatal]', e)
  process.exit(1)
})
