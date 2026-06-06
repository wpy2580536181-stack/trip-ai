import { post, get, put } from './request'

export interface LoginData {
  username: string
  password: string
}

export interface RegisterData {
  username: string
  email: string
  password: string
}

export interface UpdateProfileData {
  nickname?: string
  avatar?: string
  phone?: string
  bio?: string
}

export function login(data: LoginData) {
  return post('/user/login', data)
}

export function register(data: RegisterData) {
  return post('/user/register', data)
}

export function getUserInfo() {
  return get('/user/info')
}

export function updateUserInfo(data: UpdateProfileData) {
  return put('/user/info', data)
}

export function changePassword(data: { oldPassword: string; newPassword: string }) {
  return put('/user/password', data)
}

export function forgotPassword(email: string) {
  return post('/user/forgot-password', { email })
}

export function resetPassword(data: { email: string; token: string; newPassword: string }) {
  return post('/user/reset-password', data)
}
