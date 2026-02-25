import logging
import json
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

# Import our orchestrator gateway
from web.orchestrator import get_orchestrator, AgentLogicOrchestrator

# Standardized logging for Chat API
logger = logging.getLogger("ChatAPI")

router = APIRouter()

@router.get("/stream")
async def chat_stream(
    query: str = Query(..., description="The academic question to ask."),
    thread_id: str = Query("default_user", description="Redis thread ID for persistence."),
    core: AgentLogicOrchestrator = Depends(get_orchestrator)
):
    """
    SSE Endpoint for real-time Agent reasoning.
    Yields: 
    - node_start: Indicating which tool/logic node is active.
    - token: Real-time LLM characters.
    - final_result: Structured citations and final answer status.
    """
    
    async def event_generator():
        logger.info(f"SSE: Connection established for thread [{thread_id}]")
        
        # Get the generator from Orchestrator (which routes to ReasoningStream)
        #
        async_gen = core.stream_chat(query, thread_id)
        
        try:
            async for raw_json in async_gen:
                # Wrap each internal JSON message into the SSE 'data: ' format
                yield f"data: {raw_json}\n\n"
        except Exception as e:
            logger.error(f"SSE: Error during streaming: {str(e)}")
            yield f"data: {json.dumps({'event': 'error', 'content': str(e)})}\n\n"
        finally:
            logger.info(f"SSE: Stream for [{thread_id}] closed.")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Critical for Nginx/Proxy streaming
        }
    )