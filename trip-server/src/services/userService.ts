import crypto from 'crypto'
import prisma from '../config/database'
import bcrypt from 'bcryptjs'
import { generateToken, JwtPayload } from '../config/jwt'

const SALT_ROUNDS = 10

// 用户注册
export async function register(username: string, email: string, password: string) {
  // 检查用户名是否已存在
  const existingUser = await prisma.user.findFirst({
    where: {
      OR: [{ username }, { email }],
    },
  })
  if (existingUser) {
    throw new Error(existingUser.username === username ? '用户名已存在' : '邮箱已注册')
  }

  // 加密密码
  const hashedPassword = await bcrypt.hash(password, SALT_ROUNDS)

  // 创建用户（默认角色为普通用户 roleId=2）
  const user = await prisma.user.create({
    data: {
      username,
      email,
      password: hashedPassword,
      nickname: username,
    },
  })

  const token = generateToken({
    userId: user.id,
    username: user.username,
    roleId: user.roleId,
  })

  return {
    id: user.id,
    username: user.username,
    email: user.email,
    nickname: user.nickname,
    avatar: user.avatar,
    roleId: user.roleId,
    token,
  }
}

// 用户登录
export async function login(username: string, password: string) {
  const user = await prisma.user.findFirst({
    where: {
      OR: [{ username }, { email: username }],
    },
  })

  if (!user) {
    throw new Error('用户不存在')
  }

  if (user.status === 0) {
    throw new Error('账号已被禁用')
  }

  const isPasswordValid = await bcrypt.compare(password, user.password)
  if (!isPasswordValid) {
    throw new Error('密码错误')
  }

  const token = generateToken({
    userId: user.id,
    username: user.username,
    roleId: user.roleId,
  })

  return {
    id: user.id,
    username: user.username,
    email: user.email,
    nickname: user.nickname,
    avatar: user.avatar,
    phone: user.phone,
    bio: user.bio,
    roleId: user.roleId,
    token,
  }
}

// 获取用户信息
export async function getUserInfo(userId: number) {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: {
      id: true,
      username: true,
      email: true,
      nickname: true,
      avatar: true,
      phone: true,
      bio: true,
      roleId: true,
      status: true,
      createdAt: true,
      preferences: true,
    },
  })
  if (!user) {
    throw new Error('用户不存在')
  }
  return user
}

// 更新用户信息
export async function updateUserInfo(
  userId: number,
  data: { nickname?: string; avatar?: string; phone?: string; bio?: string; preferences?: Record<string, any> | null }
) {
  const user = await prisma.user.update({
    where: { id: userId },
    data: {
      ...data,
      preferences: data.preferences ?? undefined,
    },
    select: {
      id: true,
      username: true,
      email: true,
      nickname: true,
      avatar: true,
      phone: true,
      bio: true,
      roleId: true,
      preferences: true,
    },
  })
  return user
}

// 修改密码
export async function changePassword(userId: number, oldPassword: string, newPassword: string) {
  const user = await prisma.user.findUnique({ where: { id: userId } })
  if (!user) {
    throw new Error('用户不存在')
  }

  const isPasswordValid = await bcrypt.compare(oldPassword, user.password)
  if (!isPasswordValid) {
    throw new Error('原密码错误')
  }

  const hashedPassword = await bcrypt.hash(newPassword, SALT_ROUNDS)
  await prisma.user.update({
    where: { id: userId },
    data: { password: hashedPassword },
  })

  return { success: true }
}

// 重置密码（通过邮箱）
export async function createPasswordResetToken(email: string) {
  const user = await prisma.user.findUnique({ where: { email } })
  if (!user) {
    throw new Error('该邮箱未注册')
  }

  const token = crypto.randomUUID()
  const expiresAt = new Date(Date.now() + 30 * 60 * 1000) // 30分钟有效

  await prisma.passwordReset.create({
    data: {
      email,
      token,
      expiresAt,
    },
  })

  return { success: true, token }
}

export async function resetPassword(email: string, token: string, newPassword: string) {
  const resetRecord = await prisma.passwordReset.findFirst({
    where: {
      email,
      token,
      used: false,
      expiresAt: { gt: new Date() },
    },
  })
  if (!resetRecord) {
    throw new Error('重置链接无效或已过期')
  }

  const hashedPassword = await bcrypt.hash(newPassword, SALT_ROUNDS)
  await prisma.user.update({
    where: { email },
    data: { password: hashedPassword },
  })

  await prisma.passwordReset.update({
    where: { id: resetRecord.id },
    data: { used: true },
  })

  return { success: true }
}