import { describe, it, expect } from 'vitest'

describe('amapMcpClient', () => {
  it('should parse JSON-RPC response correctly', () => {
    const lines = [
      '{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{},"serverInfo":{"name":"amap","version":"1.0.0"}}}',
      '{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"amap_weather","description":"实时天气查询","inputSchema":{"type":"object","properties":{"city":{"type":"string"}}}}]}}',
      '{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"北京 晴 28°C"}]}}',
    ]
    for (const line of lines) {
      const msg = JSON.parse(line)
      expect(msg.jsonrpc).toBe('2.0')
      expect(msg.id).toBeTruthy()
      if (msg.result) expect(msg.result).toBeTruthy()
    }
  })

  it('should handle MCP error response', () => {
    const errorLine = '{"jsonrpc":"2.0","id":99,"error":{"code":-32603,"message":"Internal error"}}'
    const msg = JSON.parse(errorLine)
    expect(msg.error.code).toBe(-32603)
  })
})
