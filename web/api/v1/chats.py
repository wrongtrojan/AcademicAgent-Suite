import json
import asyncio
from fastapi import APIRouter, Request, Query
from sse_starlette.sse import EventSourceResponse
from core.chats_manager import ChatsManager

router = APIRouter()
chats_manager = ChatsManager()

@router.post("/create")
async def create_chat():
    """
    1. 前端点击“新对话”按钮
    2. 返回 chat_id
    """
    chat_id = await chats_manager.create_empty_chat()
    return {"chat_id": chat_id}

@router.get("/stream")
async def chat_stream(
    request: Request, 
    chat_id: str = Query(...), 
    message: str = Query(...)
):
    async def event_generator():
        # 1. 状态锁检查
        if chat_id in chats_manager.running_tasks:
             yield {"event": "error", "data": "Task already running"}
             return

        try:
            # 标记任务开始（虽然不再使用 create_task，但可以用个占位符防止并发）
            chats_manager.running_tasks[chat_id] = True 
            
            last_status = None
            
            # 2. 直接迭代异步生成器
            # 注意：这里直接 await 异步生成器对象
            async for chunk in chats_manager.execute_reasoning_flow(chat_id, message):
                
                # 在迭代过程中，顺便检查并推送状态变更（state_change）
                details = chats_manager.get_chat_details(chat_id)
                if details and details['status'] != last_status:
                    last_status = details['status']
                    yield {
                        "event": "state_change",
                        "data": json.dumps({"status": last_status}, ensure_ascii=False)
                    }

                # 推送当前获取到的流式 Token 或最终结果
                # chunk 可能是 token，也可能是最后的完整消息
                yield {
                    "event": "message",
                    "data": json.dumps({"content": chunk, "status": "processing"}, ensure_ascii=False)
                }

                if await request.is_disconnected():
                    break
            
            # 迭代结束，发送完成信号
            yield {
                "event": "message",
                "data": json.dumps({"status": "completed"}, ensure_ascii=False)
            }

        except Exception as e:
            import traceback
            print(traceback.format_exc()) # 打印具体的错误堆栈到控制台
            yield {"event": "error", "data": str(e)}
        finally:
            chats_manager.running_tasks.pop(chat_id, None)

    return EventSourceResponse(event_generator())