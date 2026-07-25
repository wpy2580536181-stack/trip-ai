"""arq 任务定义包。

约定：每个任务函数签名 `async def task(ctx, *args, **kwargs)`。
ctx 由 arq worker 自动注入，含 redis 连接 / job_id / 尝试次数等。

调用方通过 src.services.task_queue.get_task_queue().enqueue(func, *args, **kwargs) 入队。
"""
