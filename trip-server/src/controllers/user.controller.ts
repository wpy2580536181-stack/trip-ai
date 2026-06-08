import { Request, Response } from 'express'
import * as userService from '../services/userService'

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export const register = async (req: Request, res: Response) => {
  const { username, email, password } = req.body
  if (!username || !email || !password) {
    return res.status(400).json({ code: 400, error: '用户名、邮箱和密码不能为空' })
  }
  if (!EMAIL_REGEX.test(email)) {
    return res.status(400).json({ code: 400, error: '邮箱格式不正确' })
  }
  if (password.length < 6) {
    return res.status(400).json({ code: 400, error: '密码长度不能少于6位' })
  }
  try {
    const user = await userService.register(username, email, password)
    return res.json({ code: 200, message: '注册成功', data: user })
  } catch (error: any) {
    return res.status(400).json({ code: 400, error: error.message })
  }
}

export const login = async (req: Request, res: Response) => {
  const { username, password } = req.body
  if (!username || !password) {
    return res.status(400).json({ code: 400, error: '用户名和密码不能为空' })
  }
  try {
    const user = await userService.login(username, password)
    return res.json({ code: 200, message: '登录成功', data: user })
  } catch (error: any) {
    return res.status(400).json({ code: 400, error: error.message })
  }
}

export const getInfo = async (req: Request, res: Response) => {
  try {
    const user = await userService.getUserInfo(req.user!.userId)
    return res.json({ code: 200, data: user })
  } catch (error: any) {
    return res.status(400).json({ code: 400, error: error.message })
  }
}

export const updateInfo = async (req: Request, res: Response) => {
  const { nickname, avatar, phone, bio } = req.body
  try {
    const user = await userService.updateUserInfo(req.user!.userId, { nickname, avatar, phone, bio })
    return res.json({ code: 200, message: '更新成功', data: user })
  } catch (error: any) {
    return res.status(400).json({ code: 400, error: error.message })
  }
}

export const changePassword = async (req: Request, res: Response) => {
  const { oldPassword, newPassword } = req.body
  if (!oldPassword || !newPassword) {
    return res.status(400).json({ code: 400, error: '原密码和新密码不能为空' })
  }
  if (newPassword.length < 6) {
    return res.status(400).json({ code: 400, error: '新密码长度不能少于6位' })
  }
  try {
    const result = await userService.changePassword(req.user!.userId, oldPassword, newPassword)
    return res.json({ code: 200, message: '密码修改成功', data: result })
  } catch (error: any) {
    return res.status(400).json({ code: 400, error: error.message })
  }
}

export const forgotPassword = async (req: Request, res: Response) => {
  const { email } = req.body
  if (!email) {
    return res.status(400).json({ code: 400, error: '邮箱不能为空' })
  }
  if (!EMAIL_REGEX.test(email)) {
    return res.status(400).json({ code: 400, error: '邮箱格式不正确' })
  }
  try {
    const result = await userService.createPasswordResetToken(email)
    return res.json({ code: 200, message: '重置验证码已发送', data: result })
  } catch (error: any) {
    return res.status(400).json({ code: 400, error: error.message })
  }
}

export const resetPassword = async (req: Request, res: Response) => {
  const { email, token, newPassword } = req.body
  if (!email || !token || !newPassword) {
    return res.status(400).json({ code: 400, error: '邮箱、验证码和新密码不能为空' })
  }
  if (!EMAIL_REGEX.test(email)) {
    return res.status(400).json({ code: 400, error: '邮箱格式不正确' })
  }
  if (newPassword.length < 6) {
    return res.status(400).json({ code: 400, error: '新密码长度不能少于6位' })
  }
  try {
    const result = await userService.resetPassword(email, token, newPassword)
    return res.json({ code: 200, message: '密码重置成功', data: result })
  } catch (error: any) {
    return res.status(400).json({ code: 400, error: error.message })
  }
}
