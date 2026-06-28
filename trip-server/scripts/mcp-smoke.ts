import 'dotenv/config'
import * as amapMcpProcess from '../src/services/mcp/amapMcpProcess'
import * as amapMcpClient from '../src/services/mcp/amapMcpClient'

async function main() {
  console.log('[Smoke] Starting Amap MCP process...')
  await amapMcpProcess.start()
  if (!amapMcpProcess.isAlive()) {
    console.error('[Smoke] Failed to start MCP process')
    process.exit(1)
  }
  console.log('[Smoke] Process started')

  console.log('[Smoke] Connecting...')
  await amapMcpClient.connect()
  console.log('[Smoke] Connected')

  console.log('[Smoke] Listing tools...')
  const tools = await amapMcpClient.listTools()
  console.log(`[Smoke] Found ${tools.length} tools:`)
  for (const t of tools) {
    console.log(`  - ${t.name}: ${t.description}`)
  }

  const weatherTool = tools.find(t => t.name.includes('weather'))
  if (weatherTool) {
    console.log(`\n[Smoke] Calling ${weatherTool.name}...`)
    const result = await amapMcpClient.callTool(weatherTool.name, { city: '北京' })
    console.log(`[Smoke] Result:\n${result.slice(0, 500)}`)
  }

  amapMcpClient.close()
  amapMcpProcess.stop()
  console.log('[Smoke] Done')
}

main().catch(err => {
  console.error('[Smoke] Failed:', err)
  process.exit(1)
})
