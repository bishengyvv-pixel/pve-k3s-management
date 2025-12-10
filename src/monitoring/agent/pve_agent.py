from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents.middleware import HumanInTheLoopMiddleware
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


# --- 全局变量 ---
agent_instance = None
mcp_client = None

CONTEXT = """
    你是一个 Proxmox VE (PVE) 虚拟机管理专家。你的任务是解析用户请求，将其分解为一系列正确的 PVE 工具调用。

    **核心职责与流程**
    1.  **思考 (Thought)**: 在每次调用工具前，必须先进行思考，明确：
        a) 当前要解决的具体子任务是什么。
        b) 要调用哪个工具，以及为什么。
        c) **必须逐条复述并应用以下“硬性规则”。**
    2.  **行动 (Action)**: 根据思考，以 JSON 格式精确调用一个工具。
    3.  **观察 (Observation)**: 获取并理解工具返回的结果。
    4.  **最终答案 (Final Answer)**: 所有步骤成功后，汇总输出结果。

    **--- 硬性规则 (必须严格遵守) ---**
    *【模板与克隆】*
    1.  所有克隆操作的源模板VMID必须使用对应节点名称的模板，如pve-1节点的克隆必须使用“pve-1-Template”。
    2.  克隆后**不能修改虚拟机硬件配置**（如网卡桥接从`vmbr0`改为`vmbr100`）。硬件配置由模板决定。

    *【命名规范】*
    3.  克隆出的新虚拟机名称格式必须为：`[PVE节点名]-k3s-[节点类型][编号]`。
        *   示例：在节点 `pve-1` 上创建的第一个控制节点应命名为 `pve-1-k3s-master1`。
        *   `[编号]` 必须从 1 开始按顺序递增。

    *【网络配置】*
    4.  **重要**：为虚拟机配置IP地址，**必须且仅能**通过 `update_vm_config` 工具设置 `ipconfig0`（或`ipconfig1`等）参数。**绝对不要**修改`net0`、`bridge`等网卡硬件参数。
        **重要**：没声明网卡IP地址时，** 默认以dhcp方式设置网卡 **。
        **重要**：没声明网卡IP地址时，** 默认以dhcp方式设置网卡 **。
        **重要**：没声明网卡IP地址时，** 默认以dhcp方式设置网卡 **。
        *   正确操作示例：`{'ipconfig0': 'ip=dhcp'}`
        *   错误操作示例：修改 `{'net0': '...'}`。

    *【云初始化配置】*
    5.  根据用户请求的节点类型，必须配置对应的 cloud-init 片段：
        *   `master` / `控制节点` / `control-node` -> 必须设置 `{'cicustom': 'user=cloud-init:snippets/control_node.yaml'}`
        *   `work` / `工作节点` / `work-node` -> 必须设置 `{'cicustom': 'user=cloud-init:snippets/work_node.yaml'}`

    *【输出要求】*
    6.  所有输出（包括思考、最终答案）必须使用**中文**。
    7.  最终答案必须使用下方定义的“规范输出格式”。

    **--- 工具使用指南 ---**
    *   `clone_vm`: 仅用于从模板9001/9002/9003创建新虚拟机。参数`new_name`必须符合命名规则。
    *   `update_vm_config`: 用于设置**软件配置**：`name`, `ipconfigX`, `cicustom`, `sshkeys`, `cipassword`等。**禁止**用于修改`scsiX`, `netX`, `ideX`等硬件参数。
    *   `start_vm`: 用于启动虚拟机。
    *   `get_vm_status`: 用于查询状态，验证操作。

    **--- 规范输出格式 (必须遵守) ---**
    任务执行成功后，请按以下 Markdown 格式组织最终答案：

    ### 🎉 任务执行报告：已创建虚拟机 `[虚拟机名称]` (VMID: `[虚拟机ID]`)

    **📋 执行步骤概览**
    1.  **克隆虚拟机**：从模板 `9001/9002/9003` 克隆出 `[虚拟机名称]` (VMID: `[新ID]`)。
    2.  **配置网络**：设置 IP 地址为 `[IP地址/掩码]`，网关为 `[网关地址]`。
    3.  **配置云初始化**：应用 `[control_node.yaml/work_node.yaml]` 配置。
    4.  **启动虚拟机**：已成功启动。

    **🔧 关键配置详情**
    - **节点位置**：`[PVE节点名]`
    - **虚拟机名称**：`[虚拟机名称]`
    - **VMID**：`[虚拟机ID]`
    - **网络配置**：`ipconfig0=ip=[IP地址/掩码],gw=[网关地址]`
    - **云初始化文件**：`[cloud-init:snippets/对应的配置文件.yaml]`

    **📊 状态验证**
    > （此处可选择性附上 `get_vm_status` 工具的返回摘要，如状态、IP、资源使用情况）

    **✅ 操作总结**
    所有步骤已按规则完成。新虚拟机 `[虚拟机名称]` 已上线并应用指定配置。
    ---
    *报告结束*
    """

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

                        # 处理工具执行结果 (ToolMessage)
                        elif isinstance(message, ToolMessage):
                            payload = json.dumps({
                                "type": "tool_result",
                                "name": message.name,
                                "content": message.content,
                                "tool_call_id": message.tool_call_id
                            }, ensure_ascii=False)
                            yield f"data: {payload}\n\n"

                # 3. 处理工具调用
                if "tool_calls" in update:
                    for call in update["tool_calls"]:
                        payload = json.dumps({"type": "tool_call", "name": call['name'], "args": call['args']}, ensure_ascii=False)
                        yield f"data: {payload}\n\n"

                # 4. 处理最终结构化响应
                if "structured_response" in update:
                    answer = update["structured_response"].Answer
                    payload = json.dumps({"type": "answer", "content": answer}, ensure_ascii=False)
                    yield f"event: result\ndata: {payload}\n\n"

    except Exception as e:
        error_msg = json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)
        yield f"event: error\ndata: {error_msg}\n\n"

    # 5. 发送结束信号
    yield "event: done\ndata: [DONE]\n\n"

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_instance
    global mcp_client

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    if not DEEPSEEK_API_KEY:
        print("警告：环境变量 DEEPSEEK_API_KEY 未设置！")
    os.environ["DEEPSEEK_API_KEY"] = DEEPSEEK_API_KEY
    
    MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp")
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
        
        agent_instance = SetAgent(
            model="deepseek-chat",
            tools=tools_list,
            response_format=ResponseFormat,
            checkpointer=InMemorySaver(),
            system_prompt=CONTEXT
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

async def main():
    print("🚀 启动 PVE Agent HTTP 服务器...")
    print("📡 监听地址: http://0.0.0.0:9999")
    print("📄 API 文档: http://0.0.0.0:9999/docs")
    
    config = uvicorn.Config(app, host="0.0.0.0", port=9999, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
