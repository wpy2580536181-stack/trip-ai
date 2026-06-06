export const createStreamResponse = (res: any) => {
    res.setHeader('Content-Type', 'text/event-stream')
    res.setHeader('Cache-Control', 'no-cache')
    res.setHeader('Connection', 'keep-alive')
    return {
        send:(data:any)=>{
            try{
                res.write(`data: ${JSON.stringify(data)}\n\n`)
            }catch(error){
                console.log('流式发送错误',error)
            }
        },
        end:()=>{
            try{
                res.write('event: end\ndata: {"done":true}\n\n')
                res.end()
            }catch(error){
                console.log('流式结束错误',error)
            }
        },
        error:(message:string)=>{
            try{
                res.write(`event: error\ndata: ${JSON.stringify(message)}\n\n`)
                res.end()
            }catch(error){
                console.log('流式错误错误',error)
            }
        }
    }
}
