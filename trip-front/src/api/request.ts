import axios from 'axios'

const request = axios.create({
  baseURL: '/api',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

request.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export interface ApiResponse<T = any> {
  success: boolean
  data?: T
  error?: string
}

export function post<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return request.post(url, params)
}

export function get<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return request.get(url, { params })
}

export function put<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return request.put(url, params)
}

export function del<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return request.delete(url, { params })
}

export async function fetchStream(
  url: string,
  data?: any,
  onChunk?: (chunk: string) => void,
  onComplete?: (data?: any) => void,
  onError?: (error: any) => void,
  onToolEvent?: (type: string, name: string) => void,
  onHeartbeat?: () => void,
): Promise<AbortController> {
    const controller = new AbortController()
    const token = localStorage.getItem('token')
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    try{
        const response = await fetch(`/api/${url}`, {
        method: 'POST',
        body: JSON.stringify(data),
        headers,
        signal: controller.signal,
      })
      if (!response.body) {
        throw new Error('Response body is null')
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while(true){
        const {done,value} = await reader.read()
        if(done){
          break
        }
        buffer += decoder.decode(value, { stream: true })
        let sepIdx
        while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
          const rawEvent = buffer.slice(0, sepIdx)
          buffer = buffer.slice(sepIdx + 2)
          for (const line of rawEvent.split('\n')) {
            if (!line.startsWith('data:')) continue
            const jsonStr = line.substring(5).trimStart()
            if (!jsonStr) continue
            let jsonData: any
            try {
              jsonData = JSON.parse(jsonStr)
            } catch {
              continue
            }
            if (jsonData.type === 'chunk') {
              onChunk?.(jsonData.content)
            } else if (jsonData.type === 'complete') {
              onComplete?.(jsonData.data)
            } else if (jsonData.type === 'error') {
              onError?.(jsonData.error || '流式数据解析异常')
            } else if (jsonData.type === 'tool_start' || jsonData.type === 'tool_end') {
              onToolEvent?.(jsonData.type, jsonData.name || '')
            } else if (jsonData.type === 'heartbeat') {
              onHeartbeat?.()
            }
          }
        }
      }

      controller.abort()

    }catch(error: any){
      if (error.name === 'AbortError') return controller
      onError?.(error.message || '请求失败')
    }
    return controller
}
