/**
 * 清理 eval-test 账号的所有数据
 *
 * 用法：npx ts-node eval/cleanup.ts
 * 或：npm run eval:cleanup
 *
 * 删除顺序（外键依赖）：
 * 1) Message（依赖 Conversation）
 * 2) Conversation（依赖 User）
 * 3) Trip（依赖 User，可空）
 * 4) TokenUsage / Feedback（如果有）
 * 5) User 本身（最后）
 *
 * 警告：会真的删除数据！建议仅在 dev 环境跑。
 */

import prisma from '../src/config/database'

const EVAL_USERNAME = process.env.EVAL_USERNAME || 'eval-test'

const log = {
  info: (msg: string) => console.log(`[cleanup] ${msg}`),
  warn: (msg: string) => console.warn(`[cleanup] ${msg}`),
}

async function main() {
  log.info(`开始清理账号 ${EVAL_USERNAME} 的所有数据...`)

  const user = await prisma.user.findUnique({ where: { username: EVAL_USERNAME } })
  if (!user) {
    log.warn(`账号 ${EVAL_USERNAME} 不存在，无需清理`)
    return
  }

  // 1) 找所有 conversation
  const conversations = await prisma.conversation.findMany({
    where: { userId: user.id },
    select: { id: true, title: true },
  })
  const convIds = conversations.map((c) => c.id)
  log.info(`找到 ${conversations.length} 个 conversation`)

  // 2) 删 Message
  if (convIds.length > 0) {
    const msgResult = await prisma.message.deleteMany({
      where: { conversationId: { in: convIds } },
    })
    log.info(`删除了 ${msgResult.count} 条 Message`)
  }

  // 3) 删 Conversation
  const convResult = await prisma.conversation.deleteMany({
    where: { userId: user.id },
  })
  log.info(`删除了 ${convResult.count} 个 Conversation`)

  // 4) 删 Trip
  const tripResult = await prisma.trip.deleteMany({
    where: { userId: user.id },
  })
  log.info(`删除了 ${tripResult.count} 个 Trip`)

  // 5) 删 User 本身
  await prisma.user.delete({ where: { id: user.id } })
  log.info(`删除了 User ${EVAL_USERNAME}`)

  log.info('清理完成')
}

main()
  .catch((e) => {
    console.error('[cleanup] 失败:', e)
    process.exit(1)
  })
  .finally(async () => {
    await prisma.$disconnect()
  })
