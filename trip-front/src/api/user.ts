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

export interface UserPreferences {
  travelStyle?: 'cultural' | 'nature' | 'food' | 'shopping' | 'leisure'
  budgetLevel?: 'economy' | 'standard' | 'comfort' | 'luxury'
  pace?: 'compact' | 'moderate' | 'relaxed'
  avoidCrowds?: boolean
  interests?: string[]
}

export interface UpdateProfileData {
  nickname?: string
  avatar?: string
  phone?: string
  bio?: string
  preferences?: UserPreferences | null
}

export function login(data: LoginData) {
  return post('/auth/login', data)
}

export function register(data: RegisterData) {
  return post('/auth/register', data)
}

export function getUserInfo() {
  return get('/auth/me')
}

export function updateUserInfo(data: UpdateProfileData) {
  return put('/auth/info', data)
}

export function changePassword(data: { oldPassword: string; newPassword: string }) {
  return put('/auth/password', data)
}

export function forgotPassword(email: string) {
  return post('/auth/reset-password', { email })
}

export function resetPassword(data: { email: string; token: string; newPassword: string }) {
  return post('/auth/reset-password/confirm', data)
}
