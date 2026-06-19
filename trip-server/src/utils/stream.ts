import { Response } from 'express'

interface StreamPayload {
  type: 'chunk' | 'complete' | 'tool_start' | 'tool_end' | 'error' | 'heartbeat'
  name?: string
  content?: string
  data?: unknown
}

export const createStreamResponse = (res: Response, onWriteError?: () => void) => {
    res.setHeader('Content-Type', 'text/event-stream')
    res.setHeader('Cache-Control', 'no-cache')
    res.setHeader('Connection', 'keep-alive')
    return {
        send: (data: StreamPayload) => {
            try {
                res.write(`data: ${JSON.stringify(data)}\n\n`)
            } catch (error) {
                console.error('流式发送错误', error)
                onWriteError?.()
            }
        },
        end: () => {
            try {
                res.write('event: end\ndata: {"done":true}\n\n')
                res.end()
            } catch (error) {
                console.error('流式结束错误', error)
            }
        },
        error: (message: string) => {
            try {
                res.write(`event: error\ndata: ${JSON.stringify({ type: 'error', error: message })}\n\n`)
                res.end()
            } catch (error) {
                console.error('流式错误错误', error)
            }
        }
    }
}