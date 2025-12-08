from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
import json
import uvicorn
import os

PVE_AGENT_ALERT_URL = os.getenv("PVE_AGENT_ALERT_URL", "http://agent:9999/chat")

app = FastAPI(title="Prometheus Alert Pusher")

def format_alert_for_agent(alert_data: dict) -> str:
    # format_alert_for_agent 将 Prometheus Webhook 格式的告警数据转换为 Agent 可理解的中文描述
    # @param alert_data: 接收到的原始 Alertmanager Webhook JSON 数据，字典类型
    # @note 该函数提取告警状态、级别、名称、实例和摘要，并组合成一条完整的中文通知消息
    # @return 格式化后的告警字符串，包含所有激活和已解决的告警信息
    
    alerts = alert_data.get('alerts', [])
    
    if not alerts:
        return "收到空告警通知。"

    formatted_messages = []
    
    for alert in alerts:
        status = "【激活中】" if alert['status'] == 'firing' else "【已解决】"
        severity = alert['labels'].get('severity', '未知')
        alertname = alert['labels'].get('alertname', '未知告警')
        instance = alert['labels'].get('instance', '未知节点')
        summary = alert['annotations'].get('summary', '无摘要')
        
        message = (
            f"{status} 级别: {severity} 告警名称: {alertname}。"
            f" 目标节点: {instance}。"
            f" 详细描述: {summary}。"
            f" 触发时间: {alert['startsAt']}。"
        )
        formatted_messages.append(message)
        
    return "\n".join(formatted_messages)


@app.post("/webhook/alertmanager")
async def receive_alert(request: Request):
    # receive_alert 接收来自 Alertmanager 的 Webhook 告警并转发至 PVE Agent
    # @param request: FastAPI 的 Request 对象，用于获取原始请求体
    # @note 函数内部使用 httpx 异步客户端向 Agent 服务发起 POST 请求，模拟用户消息
    # @return 返回一个 JSONResponse，指示告警转发的成功或失败状态
    try:
        alert_data = await request.json()

        formatted_msg = format_alert_for_agent(alert_data)

        payload = {
            "message": f"紧急告警通知，请注意:\n{formatted_msg}",
            "thread_id": 999 
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(PVE_AGENT_ALERT_URL, json=payload)
            response.raise_for_status() 

        return JSONResponse({"status": "success", "message": "Alert forwarded to PVE Agent."}, status_code=200)

    except httpx.HTTPStatusError as e:
        return JSONResponse({"status": "error", "message": f"PVE Agent returned error: {e}"}, status_code=500)
    except Exception as e:
        print(f"处理告警时发生错误: {e}")
        return JSONResponse({"status": "error", "message": f"Internal server error: {e}"}, status_code=500)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9095)
