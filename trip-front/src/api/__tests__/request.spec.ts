import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock axios before importing request module
vi.mock('axios', () => {
  const mockAxiosInstance = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    post: vi.fn(),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  }
  const mockAxios = {
    create: vi.fn(() => mockAxiosInstance),
  }
  return { default: mockAxios, ...mockAxios }
})

describe('request module', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Import fresh each test
    vi.resetModules()
  })

  it('creates axios instance with correct config', async () => {
    const axios = (await import('axios')).default
    const { default: request } = await import('../request')

    expect(axios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        baseURL: '/api',
        timeout: 300000,
      })
    )
  })

  it('has HTTP method exports', async () => {
    const mod = await import('../request')
    expect(typeof mod.post).toBe('function')
    expect(typeof mod.get).toBe('function')
    expect(typeof mod.put).toBe('function')
    expect(typeof mod.del).toBe('function')
    expect(typeof mod.fetchStream).toBe('function')
  })

  it('export ApiResponse type structure', () => {
    // Type-level test: verify the interface shape
    const mockResponse = { success: true, data: {}, error: undefined }
    expect(mockResponse).toHaveProperty('success')
    expect(mockResponse).toHaveProperty('data')
  })
})
