from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel
import asyncio
import os
import time
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Body
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Generator, List, Dict, Any, Optional
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


# --- 全局变量 ---
agent_instance = None
mcp_client = None
MONITOR_QUEUES: List[asyncio.Queue] = []

async def broadcast_event(event_data: Dict[str, Any]):
    """向所有监控客户端广播事件"""
    for q in MONITOR_QUEUES:
        await q.put(event_data)

class ResponseFormat(BaseModel):
    """ 
    Agent最终输出的结构。
    """
    Answer: str 

class ChatRequest(BaseModel):
    message: str
    thread_id: int = 1

def SetAgent(model: str, tools: list, response_format: type, checkpointer: InMemorySaver, system_prompt: str):
    agent = create_agent(
        model=model,
        tools=tools,
        response_format=ToolStrategy(response_format),
        checkpointer=checkpointer,
        system_prompt=system_prompt,
    )
    return agent

async def sse_generator(agent, msg: str, thread_id: int):
    """
    将 LangGraph 的输出转换为 SSE (Server-Sent Events) 格式流。
    """
    print(f"--- 收到请求: {msg} (Thread: {thread_id}) ---")
    
    # 广播开始事件
    await broadcast_event({
        "timestamp": time.time(),
        "thread_id": thread_id,
        "type": "start",
        "content": f"New Request: {msg}"
    })

    # 1. 发送开始信号
    yield f"event: start\ndata: 开始处理...\n\n"

    try:
        async for step in agent.astream(
            {"messages": [{"role": "user", "content": msg}]},
            {"configurable": {"thread_id": thread_id}},
        ):
            for update in step.values():
                
                # 2. 处理消息 (思考过程)
                if "messages" in update:
                    for message in update["messages"]:
                        # 处理思考过程 (AIMessage)
                        if isinstance(message, AIMessage) and message.content:
                            # 过滤掉最终的结构化响应原始文本
                            if message.content.startswith("Returning structured response"):
                                continue

                            # 构造 JSON 数据
                            payload = json.dumps({"type": "thought", "content": message.content}, ensure_ascii=False)
                            yield f"data: {payload}\n\n"
                            
                            # 广播思考事件
                            await broadcast_event({
                                "timestamp": time.time(),
                                "thread_id": thread_id,
                                "type": "thought",
                                "content": message.content
                            })

                        # 处理工具执行结果 (ToolMessage)
                        elif isinstance(message, ToolMessage):
                            payload = json.dumps({
                                "type": "tool_result",
                                "name": message.name,
                                "content": message.content,
                                "tool_call_id": message.tool_call_id
                            }, ensure_ascii=False)
                            yield f"data: {payload}\n\n"

                            # 广播工具结果事件
                            await broadcast_event({
                                "timestamp": time.time(),
                                "thread_id": thread_id,
                                "type": "tool_result",
                                "name": message.name,
                                "content": message.content,
                                "tool_call_id": message.tool_call_id
                            })

                # 3. 处理工具调用
                if "tool_calls" in update:
                    for call in update["tool_calls"]:
                        payload = json.dumps({"type": "tool_call", "name": call['name'], "args": call['args']}, ensure_ascii=False)
                        yield f"data: {payload}\n\n"
                        
                        # 广播工具调用事件
                        await broadcast_event({
                            "timestamp": time.time(),
                            "thread_id": thread_id,
                            "type": "tool_call",
                            "name": call['name'],
                            "args": call['args']
                        })

                # 4. 处理最终结构化响应
                if "structured_response" in update:
                    answer = update["structured_response"].Answer
                    payload = json.dumps({"type": "answer", "content": answer}, ensure_ascii=False)
                    yield f"event: result\ndata: {payload}\n\n"
                    
                    # 广播最终答案事件
                    await broadcast_event({
                        "timestamp": time.time(),
                        "thread_id": thread_id,
                        "type": "answer",
                        "content": answer
                    })

    except Exception as e:
        error_msg = json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)
        yield f"event: error\ndata: {error_msg}\n\n"
        
        # 广播错误事件
        await broadcast_event({
            "timestamp": time.time(),
            "thread_id": thread_id,
            "type": "error",
            "content": str(e)
        })

    # 5. 发送结束信号
    yield "event: done\ndata: [DONE]\n\n"

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_instance
    global mcp_client

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    if not DEEPSEEK_API_KEY:
        print("警告：环境变量 DEEPSEEK_API_KEY 未设置！")
    else:
        os.environ["DEEPSEEK_API_KEY"] = DEEPSEEK_API_KEY
    
    MCP_URL = os.getenv("MCP_URL") 
    os.environ["MCP_URL"] = MCP_URL
    
    print(f"正在使用 MCP URL: {MCP_URL}")
    
    mcp_client = MultiServerMCPClient(
        {
            "pve_tool": {
                "transport": "streamable_http",
                "url": f"{MCP_URL}"
            }
        }
    )
    
    print("正在连接 MCP 工具...")
    try:
        tools_list = await mcp_client.get_tools()
        print(f"获取到工具: {[t.name for t in tools_list]}")
        
        # 从 prompt.txt 读取 System Prompt
        try:
            with open("prompt.txt", "r", encoding="utf-8") as f:
                system_prompt = f.read()
        except FileNotFoundError:
             print("警告：prompt.txt 未找到！将使用默认空 Prompt。")
             system_prompt = "You are a helpful assistant."

        agent_instance = SetAgent(
            model="deepseek-chat",
            tools=tools_list,
            response_format=ResponseFormat,
            checkpointer=InMemorySaver(),
            system_prompt=system_prompt
        )
        print("Agent 初始化成功！")
    except Exception as e:
        print(f"Agent 初始化失败，可能无法连接到 MCP 服务 ({MCP_URL})。错误信息: {e}")
    
    yield
    
    print("服务正在关闭...")

# --- 初始化 FastAPI ---
app = FastAPI(lifespan=lifespan, title="PVE Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 定义 API 端点 ---
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    SSE 流式对话接口
    """
    if not agent_instance:
        return JSONResponse({"error": "Agent not initialized. Check server logs for MCP connection failure."}, status_code=503)

    return StreamingResponse(
        sse_generator(agent_instance, request.message, request.thread_id),
        media_type="text/event-stream"
    )

async def monitor_generator(q: asyncio.Queue):
    try:
        while True:
            data = await q.get()
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    except asyncio.CancelledError:
        MONITOR_QUEUES.remove(q)

@app.get("/monitor")
async def monitor_endpoint():
    """
    实时监控 SSE 接口
    """
    q = asyncio.Queue()
    MONITOR_QUEUES.append(q)
    return StreamingResponse(monitor_generator(q), media_type="text/event-stream")

async def main():
    print("🚀 启动 PVE Agent HTTP 服务器...")
    print("📡 监听地址: http://0.0.0.0:9999")
    
    config = uvicorn.Config(app, host="0.0.0.0", port=9999, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
