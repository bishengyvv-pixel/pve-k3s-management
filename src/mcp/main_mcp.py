import os
import time
import requests
import json
from typing import Dict, Any, Optional
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse


# --- 1. PVE API CLIENT CLASS (核心 PVE 交互逻辑) ---

class PveApiClient:
    """
    PveApiClient Proxmox VE API 客户端
    封装了认证逻辑（获取is_authenticated）和通用请求方法。
    """
    def __init__(self, api_url: str, token_id: str, token_secret: str):
        # __init__ 初始化API客户端实例
        # @param api_url: Proxmox VE API 的基础 URL, 必须包含 '/api2/json'
        # @param token_id: 用于认证的 API 令牌 ID, 例如 'root@pam!tokenname'
        # @param token_secret: 对应的 API 令牌密钥
        # @note 此客户端使用 API Token 认证
        # @return None
        """初始化API客户端实例，设置基础URL和认证信息。"""
        self.base_url = api_url.rstrip('/')
        self.token_id = token_id
        self.token_secret = token_secret
        self.auth_header = f"PVEAPIToken {self.token_id}={self.token_secret}"
        self.is_authenticated = False
        
    def authenticate(self) -> bool:
        # authenticate 检查 API 令牌信息是否配置
        # @param self: PveApiClient 实例
        # @note API Token 认证是无状态的，此函数仅检查配置是否完整。
        # @return 认证成功返回 True, 失败返回 False
        """检查 API 令牌信息是否配置。"""
        if self.token_id and self.token_secret:
            self.is_authenticated = True
            print("INFO: API Token credentials loaded successfully.")
            return True
        self.is_authenticated = False
        print("ERROR: API Token credentials missing.")
        return False

    def api_request(self, method: str, path: str, data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        # api_request 通用PVE API请求方法
        # @param method: HTTP 请求方法 (GET, POST, PUT, DELETE)
        # @param path: API 资源的路径, 例如 '/nodes'
        # @param data: (可选) 包含请求体参数的字典
        # @note 使用 API Token 通过 Authorization Header 进行认证，无需 CSRF Token。
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """通用PVE API请求方法，使用 API Token 进行认证。"""
        
        if not self.is_authenticated:
            return {"error": "Authentication required. PVE API Token is missing or invalid."}

        url = f"{self.base_url}{path}"
        
        headers = {
            'Authorization': self.auth_header 
        }
        
        request_data = data if data else {}

        try:
            request_kwargs = {
                'headers': headers,
                'verify': False, 
                'data': request_data 
            }

            response = requests.request(method.upper(), url, **request_kwargs)
            response.raise_for_status() 

            return response.json()
            
        except requests.exceptions.HTTPError as e:
            status_code = response.status_code
            error_detail = response.text
            try:
                json_response = response.json()
                error_detail = json_response.get('data', json.dumps(json_response))
            except Exception:
                pass
            
            return {"error": f"HTTP error {status_code} for {url}. Details: {error_detail}. Check if API Token is valid and has sufficient permissions."}
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Request failed (Connection/Timeout) for {url}: {e}"}

    # ----------------------------------------------------
    # 以下是原始 PveApiClient 中的方法，供 Tool 函数调用
    # ----------------------------------------------------

    def get_vm_status_details(self, node: str, vmid: int) -> Optional[Dict[str, Any]]:
        # get_vm_status_details 获取特定 VM 的状态详情
        # @param self: PveApiClient 实例
        # @param node: PVE 节点名称 (例如 'pve')
        # @param vmid: 虚拟机的 ID
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """获取特定 VM 的状态详情。"""
        path = f"/nodes/{node}/qemu/{vmid}/status/current"
        return self.api_request("GET", path)

    def get_node_list(self) -> Optional[Dict[str, Any]]:
        # get_node_list 获取 PVE 集群中的所有节点列表
        # @param self: PveApiClient 实例
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """获取 PVE 集群中的所有节点列表。"""
        path = "/nodes"
        return self.api_request("GET", path)

    def get_vm_list_by_node(self, node: str) -> Optional[Dict[str, Any]]:
        # get_vm_list_by_node 获取特定节点上的所有虚拟机列表
        # @param self: PveApiClient 实例
        # @param node: PVE 节点名称 (例如 'pve')
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """获取特定节点上的所有虚拟机列表。"""
        path = f"/nodes/{node}/qemu"
        return self.api_request("GET", path)
    
    def create_vm(self, node: str, vmid: int, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # create_vm 创建新的虚拟机
        # @param self: PveApiClient 实例
        # @param node: PVE 节点名称
        # @param vmid: 新虚拟机的 ID
        # @param config: 包含虚拟机配置参数的字典
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """创建新的虚拟机。"""
        path = f"/nodes/{node}/qemu"
        config['vmid'] = vmid
        return self.api_request("POST", path, data=config)

    def delete_vm(self, node: str, vmid: int) -> Optional[Dict[str, Any]]:
        # delete_vm 删除指定的虚拟机
        # @param self: PveApiClient 实例
        # @param node: PVE 节点名称
        # @param vmid: 要删除的虚拟机的 ID
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """删除指定的虚拟机。"""
        path = f"/nodes/{node}/qemu/{vmid}"
        return self.api_request("DELETE", path)

    def clone_vm(self, node: str, source_vmid: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # clone_vm 克隆指定的虚拟机
        # @param self: PveApiClient 实例
        # @param node: PVE 节点名称
        # @param source_vmid: 源虚拟机 (模板) 的 ID
        # @param payload: 包含克隆参数 (例如 newid, name, full) 的字典
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """克隆指定的虚拟机。"""
        path = f"/nodes/{node}/qemu/{source_vmid}/clone"
        return self.api_request("POST", path, data=payload)

    def update_vm_config(self, node: str, vmid: int, config_updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # update_vm_config 更新虚拟机的配置
        # @param self: PveApiClient 实例
        # @param node: PVE 节点名称
        # @param vmid: 要更新的虚拟机的 ID
        # @param config_updates: 包含要修改的配置键值对的字典
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """更新虚拟机的配置。"""
        path = f"/nodes/{node}/qemu/{vmid}/config"
        return self.api_request("PUT", path, data=config_updates)
    
    def start_vm(self, node: str, vmid: int) -> Optional[Dict[str, Any]]:
        # start_vm 启动指定的虚拟机
        # @param self: PveApiClient 实例
        # @param node: PVE 节点名称
        # @param vmid: 要启动的虚拟机的 ID
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """启动指定的虚拟机。"""
        path = f"/nodes/{node}/qemu/{vmid}/status/start"
        return self.api_request("POST", path)

    def shutdown_vm(self, node: str, vmid: int) -> Optional[Dict[str, Any]]:
        # shutdown_vm 软关机指定的虚拟机
        # @param self: PveApiClient 实例
        # @param node: PVE 节点名称
        # @param vmid: 要关机的虚拟机的 ID
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """软关机指定的虚拟机。"""
        path = f"/nodes/{node}/qemu/{vmid}/status/shutdown"
        return self.api_request("POST", path)

    def reboot_vm(self, node: str, vmid: int) -> Optional[Dict[str, Any]]:
        # reboot_vm 重启指定的虚拟机
        # @param self: PveApiClient 实例
        # @param node: PVE 节点名称
        # @param vmid: 要重启的虚拟机的 ID
        # @return API 返回的 JSON 数据（字典类型）, 如果请求失败则返回包含 'error' 键的字典
        """重启指定的虚拟机。"""
        path = f"/nodes/{node}/qemu/{vmid}/status/reboot"
        return self.api_request("POST", path)

# --- 2. GLOBAL CONFIGURATION & INITIALIZATION ---

# load_dotenv()

PVE_HOST = os.getenv("PVE_HOST")
PVE_PORT = os.getenv("PVE_PORT")
PVE_TOKEN_ID = os.getenv("PVE_TOKEN_ID"
PVE_TOKEN_SECRET = os.getenv("PVE_TOKEN_SECRET")

MCP_HOST = os.getenv("MCP_HOST")
MCP_PORT = os.getenv("MCP_PORT")

if not PVE_HOST or not PVE_TOKEN_SECRET:
    raise ValueError("Critical environment variables (PVE_HOST, PVE_TOKEN_SECRET) are missing. Check your .env file.")

PVE_API_URL = f"https://{PVE_HOST}:{PVE_PORT}/api2/json"

mcp = FastMCP(name="pve-management-agent")
pve_client: Optional[PveApiClient] = None 


# --- 3. HELPER FUNCTIONS AND MCP TOOLS ---

def _handle_response(result: Optional[Dict[str, Any]], success_message: str) -> str:
    # _handle_response 格式化 API 响应或错误信息
    # @param result: PVE API 请求返回的原始字典结果, 可能为 None
    # @param success_message: 任务成功时要包含在返回字符串中的描述性消息
    # @note 检查结果中是否包含错误信息, 或是否返回 UPID, 否则报告通用失败
    # @return 格式化后的状态字符串 (SUCCESS, API ERROR 或 ERROR)
    """
    内部辅助函数：格式化 API 响应或错误信息。
    已修复：在调用 .startswith() 前进行类型检查，以避免 NoneType 错误。
    """
    if result is None:
        return "ERROR: PVE client internal error or request failed unexpectedly (result is None)."
    
    if isinstance(result, dict) and 'error' in result:
        return f"API ERROR: {result['error']}"

    data = result.get('data')
    
    if isinstance(data, str) and data.startswith('UPID'):
        upid = data
        return f"SUCCESS: {success_message} task started. UPID: {upid}. Use monitor_pve_task to track."
    
    if data is None or data == '':
         return f"SUCCESS: {success_message} completed successfully (synchronous operation)."
         
    return f"ERROR: API call failed with unexpected response structure. Response details: {result}"


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    # health_check 提供一个健康检查路由
    # @param request: Starlette 的请求对象
    # @return PlainTextResponse: 指示 PVE 认证状态的响应
    """提供一个健康检查路由，指示 PVE 认证状态。"""
    if pve_client and pve_client.is_authenticated:
        return PlainTextResponse("PVE Agent is authenticated and running.")
    return PlainTextResponse("PVE Agent is running, but PVE authentication failed.", status_code=503)


@mcp.tool
def monitor_pve_task(node: str, upid: str, timeout: int = 300) -> str:
    # monitor_pve_task 监控一个异步 Proxmox VE 任务直到它完成
    # @param node: 运行任务的 PVE 节点名称 (例如 'pve')
    # @param upid: 异步操作返回的唯一任务 ID (UPID)
    # @param timeout: (可选) 等待任务完成的最大时间, 单位秒, 默认 300 秒
    # @note 任务完成状态为 'stopped', 成功退出状态为 'OK'
    # @return 格式化字符串, 指示任务的最终状态和退出消息
    """
    Monitors an asynchronous Proxmox VE task by its UPID until it completes 
    (status is 'stopped' or 'error') or until the timeout reaches.
    """
    if not pve_client or not pve_client.is_authenticated:
        return "ERROR: PVE client is not initialized or authenticated."

    start_time = time.time()
    task_path = f"/nodes/{node}/tasks/{upid}/status"
    
    while time.time() - start_time < timeout:
        time.sleep(2)
        
        response = pve_client.api_request("GET", task_path)

        if response is None or (isinstance(response, dict) and 'error' in response):
            return f"ERROR: Failed to fetch task status for {upid}. Details: {response}"

        task_status = response.get('data', {})
        status = task_status.get('status')
        exitstatus = task_status.get('exitstatus', 'N/A')
        
        if status == 'stopped':
            if exitstatus == 'OK':
                return f"SUCCESS: Task {upid} completed successfully. Exit status: {exitstatus}"
            else:
                return f"FAILURE: Task {upid} finished with error. Exit status: {exitstatus}. Check PVE task log for details."
        
        if time.time() - start_time > timeout:
             return f"ERROR: Task {upid} timed out after {timeout} seconds. Current status: {status}"
        
    return f"ERROR: Task {upid} timed out after {timeout} seconds. Current status: {status}"


@mcp.tool
def get_vm_status(node: str, vmid: int) -> str:
    # get_vm_status 检索指定 QEMU 虚拟机的当前状态和基本配置
    # @param node: PVE 节点名称 (例如 'pve')
    # @param vmid: 虚拟机的 ID
    # @note 调用 get_vm_status_details 获取原始数据
    # @return 包含 VM 状态详情的 JSON 字符串或错误消息
    """
    Retrieves the current status (running, stopped, etc.) and basic configuration 
    for a specified QEMU virtual machine.
    """
    if not pve_client or not pve_client.is_authenticated:
        return "ERROR: PVE client is not authenticated."
        
    result = pve_client.get_vm_status_details(node, vmid)

    if result and 'error' in result:
        return f"API ERROR: Failed to retrieve status for VM {vmid} on node {node}. Details: {result['error']}"

    if result and 'data' in result:
        vm_data = result['data']

        simplified_data = {
            "vmid": vm_data.get("vmid"),
            "name": vm_data.get("name"),
            "status": vm_data.get("status"),
            "qmpstatus": vm_data.get("qmpstatus"),
            "cpu_usage": f"{vm_data.get('cpu', 0) * 100:.2f}%",
            "cpus": vm_data.get("cpus"),
            "maxmem_gb": round(vm_data.get("maxmem", 0) / (1024**3), 2),
            "mem_used_gb": round(vm_data.get("mem", 0) / (1024**3), 2),
            "maxdisk_gb": round(vm_data.get("maxdisk", 0) / (1024**3), 2),
            "uptime_seconds": vm_data.get("uptime"),
            "template": bool(vm_data.get("template", 0)),
        }
        
        return json.dumps(simplified_data, indent=2)
    
    return f"ERROR: Failed to retrieve status for VM {vmid} on node {node}. Details: {result}"


@mcp.tool
def list_nodes() -> str:
    # list_nodes 检索 PVE 集群中的所有节点名称和状态
    # @note 调用 PveApiClient 的 get_node_list 方法
    # @return 包含节点列表的 JSON 字符串或错误消息
    """
    Retrieves a list of all nodes in the PVE cluster along with their status.
    """
    if not pve_client or not pve_client.is_authenticated:
        return "ERROR: PVE client is not authenticated."
        
    result = pve_client.get_node_list()

    if result and 'data' in result and isinstance(result['data'], list):
        
        simplified_nodes = []
        for node_data in result['data']:
            simplified_nodes.append({
                "node": node_data.get("node"),          # 节点名称
                "status": node_data.get("status"),      # 状态 (online/offline)
                "id": node_data.get("id"),              # 完整 ID (node/pve-1)
                "cpu_usage": f"{node_data.get('cpu', 0) * 100:.2f}%", # CPU 使用率
                "maxcpu": node_data.get("maxcpu"),      # 总核心数
                "mem_used_gb": round(node_data.get("mem", 0) / (1024**3), 2), # 内存使用 (GB)
                "maxmem_gb": round(node_data.get("maxmem", 0) / (1024**3), 2), # 总内存 (GB)
                "disk_free_gb": round((node_data.get("maxdisk", 0) - node_data.get("disk", 0)) / (1024**3), 2), # 磁盘剩余 (GB)
            })
        
        return json.dumps(simplified_nodes, indent=2)
    
    return f"ERROR: Failed to retrieve node list. Details: {result}"


@mcp.tool
def list_vms_on_node(node: str) -> str:
    # list_vms_on_node 检索特定 PVE 节点上的所有虚拟机列表
    # @param node: PVE 节点名称 (例如 'pve')
    # @note 调用 PveApiClient 的 get_vm_list_by_node 方法
    # @return 包含虚拟机列表的 JSON 字符串或错误消息
    """
    Retrieves a list of all virtual machines (QEMU) on a specified PVE node.
    """
    if not pve_client or not pve_client.is_authenticated:
        return "ERROR: PVE client is not authenticated."
        
    result = pve_client.get_vm_list_by_node(node)

    # 检查结果是否包含有效的列表数据
    if result and 'data' in result and isinstance(result['data'], list):
        
        simplified_vms = []
        for vm_data in result['data']:
            simplified_vms.append({
                "vmid": vm_data.get("vmid"),           # 虚拟机 ID
                "name": vm_data.get("name"),           # 名称
                "status": vm_data.get("status"),       # 状态 (running/stopped)
                "template": bool(vm_data.get("template", 0)), # 是否为模板
                "cpu_usage": f"{vm_data.get('cpu', 0) * 100:.2f}%", # CPU 使用率
                "cpus": vm_data.get("cpus"),           # 核心数
                "maxmem_gb": round(vm_data.get("maxmem", 0) / (1024**3), 2), # 总内存 (GB)
                "disk_gb": round(vm_data.get("maxdisk", 0) / (1024**3), 2), # 总磁盘空间 (GB)
            })
            
        return json.dumps(simplified_vms, indent=2)
    
    return f"ERROR: Failed to retrieve VM list for node {node}. Details: {result}"


@mcp.tool
def create_new_vm(node: str, vmid: int, memory_mb: int, cores: int, vm_name: str) -> str:
    # create_new_vm 在指定节点上创建新的 KVM/QEMU 虚拟机
    # @param node: PVE 节点名称 (例如 'pve')
    # @param vmid: 新虚拟机的唯一 ID (例如 101)
    # @param memory_mb: 分配的内存量, 单位兆字节 (例如 2048)
    # @param cores: 分配的 CPU 核心数 (例如 2)
    # @param vm_name: 新虚拟机的显示名称
    # @note 存储和网络接口需要在 VM 创建后使用 update_vm_config 进行配置
    # @return 异步创建作业的任务 UPID 或错误消息
    """
    Creates a new KVM/QEMU virtual machine on the specified node with minimal configuration.
    Note: Storage and network must be configured via update_vm_config after creation.
    """
    if not pve_client or not pve_client.is_authenticated: return "ERROR: PVE client is not authenticated."
        
    config = {
        'memory': memory_mb,
        'cores': cores,
        'name': vm_name,
        'ostype': 'l26' 
    }
    
    result = pve_client.create_vm(node, vmid, config)
    return _handle_response(result, "VM creation")


@mcp.tool
def start_vm(node: str, vmid: int) -> str:
    # start_vm 启动指定的虚拟机
    # @param node: PVE 节点名称
    # @param vmid: 要启动的虚拟机的 ID
    # @return 任务 UPID 或错误消息
    """
    Starts a specified virtual machine.
    """
    if not pve_client or not pve_client.is_authenticated: return "ERROR: PVE client is not authenticated."
    result = pve_client.start_vm(node, vmid)
    return _handle_response(result, "VM start")


@mcp.tool
def shutdown_vm(node: str, vmid: int) -> str:
    # shutdown_vm 启动指定的虚拟机优雅关机
    # @param node: PVE 节点名称
    # @param vmid: 要关机的虚拟机的 ID
    # @return 任务 UPID 或错误消息
    """
    Initiates a graceful shutdown of the specified virtual machine.
    """
    if not pve_client or not pve_client.is_authenticated: return "ERROR: PVE client is not authenticated."
    result = pve_client.shutdown_vm(node, vmid)
    return _handle_response(result, "VM shutdown")


@mcp.tool
def reboot_vm(node: str, vmid: int) -> str:
    # reboot_vm 重启指定的虚拟机 (优雅重启)
    # @param node: PVE 节点名称
    # @param vmid: 要重启的虚拟机的 ID
    # @return 任务 UPID 或错误消息
    """
    Reboots the specified virtual machine (graceful reboot).
    """
    if not pve_client or not pve_client.is_authenticated: return "ERROR: PVE client is not authenticated."
    result = pve_client.reboot_vm(node, vmid)
    return _handle_response(result, "VM reboot")


@mcp.tool
def clone_vm(node: str, source_vmid: int, new_vmid: int, new_name: str, full_clone: bool = True) -> str:
    # clone_vm 克隆现有虚拟机 (模板) 到新的 ID 和名称
    # @param node: PVE 节点名称
    # @param source_vmid: 源虚拟机 (模板) 的 ID
    # @param new_vmid: 克隆机器的唯一 ID
    # @param new_name: 克隆机器的名称
    # @param full_clone: (可选) 是否执行完整克隆 (True) 或链接克隆 (False), 默认为 True
    # @return 任务 UPID 或错误消息
    """
    克隆现有的虚拟机或模板，创建新的虚拟机实例。
    
    相当于执行 'qm clone <source_vmid> <new_vmid> --name <new_name> [--full]' 命令。
    
    参数:
        node: PVE节点名称，例如 'pve'
        source_vmid: 源虚拟机（模板）的ID，例如 9000
        new_vmid: 新虚拟机的唯一ID，例如 101
        new_name: 新虚拟机的名称，例如 'worker-node-01'
        full_clone: 是否执行完整克隆（True）或链接克隆（False），默认为True
    
    克隆类型说明:
        - 完整克隆 (full_clone=True): 创建独立的磁盘副本，性能更好，但占用更多存储空间
        - 链接克隆 (full_clone=False): 共享源磁盘的只读副本，节省空间，但性能稍差
    
    使用示例:
        # 相当于: qm clone 9000 101 --name master
        clone_vm('pve', 9000, 101, 'master')
        
        # 相当于: qm clone 9000 102 --name worker-01 --full
        clone_vm('pve', 9000, 102, 'worker-01', full_clone=True)
        
        # 创建链接克隆（节省空间）
        clone_vm('pve', 9000, 103, 'test-vm', full_clone=False)
    
    注意事项:
        1. 源虚拟机必须处于停止状态或标记为模板
        2. 新虚拟机ID必须在集群中唯一
        3. 完整克隆需要足够的磁盘空间
        4. 克隆完成后通常需要配置网络和启动虚拟机
        
    典型工作流程:
        1. 克隆模板: clone_vm('pve', 9000, 101, 'master')
        2. 配置网络: update_vm_config('pve', 101, {'ipconfig0': 'ip=192.168.1.101/24,gw=192.168.1.1'})
        3. 配置cloud-init: update_vm_config('pve', 101, {'cicustom': 'user=cloud-init:snippets/config.yaml'})
        4. 启动虚拟机: start_vm('pve', 101)
    """
    if not pve_client or not pve_client.is_authenticated: return "ERROR: PVE client is not authenticated."
    payload = {
        'newid': new_vmid,
        'name': new_name,
        'full': 1 if full_clone else 0
    }
    result = pve_client.clone_vm(node, source_vmid, payload)
    return _handle_response(result, "VM clone")


@mcp.tool
def delete_vm(node: str, vmid: int) -> str:
    # delete_vm 永久删除指定的虚拟机
    # @param node: PVE 节点名称
    # @param vmid: 要删除的虚拟机的 ID
    # @note 此操作不可逆转, 请谨慎使用
    # @return 任务 UPID 或错误消息
    """
    Permanently deletes a specified virtual machine. USE WITH EXTREME CAUTION.
    """
    if not pve_client or not pve_client.is_authenticated: return "ERROR: PVE client is not authenticated."
    result = pve_client.delete_vm(node, vmid)
    return _handle_response(result, "VM deletion")


@mcp.tool
def update_vm_config(node: str, vmid: int, updates: Dict[str, Any]) -> str:
    # update_vm_config 更新虚拟机的配置
    # @param node: PVE 节点名称
    # @param vmid: 要更新的虚拟机的 ID
    # @param updates: 包含配置更改的字典 (例如 {'name': 'NewName', 'memory': 4096})
    # @return 任务 UPID 或错误消息
    """
    更新虚拟机的配置参数。
    
    这个函数相当于执行 'qm set <vmid> --<key> <value>' 命令，可以修改虚拟机的各种配置。
    
    参数:
        node: PVE 节点名称，例如 'pve'
        vmid: 虚拟机的 ID，例如 101
        updates: 包含要修改的配置键值对的字典
    
    支持的配置参数示例:
        - 修改名称: {'name': 'new-vm-name'}
        - 修改内存: {'memory': 4096}  (单位: MB)
        - 修改CPU核心: {'cores': 2}
        - 配置网络接口: {'net0': 'virtio,bridge=vmbr0'}
        - 配置IP地址: {'ipconfig0': 'ip=192.168.1.101/24,gw=192.168.1.1'}
        - 配置 cloud-init: {'cicustom': 'user=cloud-init:snippets/control_node.yaml'}
        - 添加磁盘: {'scsi0': 'local-lvm:10'}
        - 修改启动顺序: {'boot': 'order=virtio0'}
    
    使用示例:
        # 相当于: qm set 101 --ipconfig0 ip=192.168.116.150/24,gw=192.168.116.2
        update_vm_config('pve', 101, {'ipconfig0': 'ip=192.168.116.150/24,gw=192.168.116.2'})
        
        # 相当于: qm set 101 --cicustom "user=cloud-init:snippets/work_node.yaml"
        update_vm_config('pve', 101, {'cicustom': 'user=cloud-init:snippets/work_node.yaml'})
        
        # 同时修改多个配置
        update_vm_config('pve', 101, {
            'name': 'worker-node',
            'memory': 4096,
            'cores': 2,
            'ipconfig0': 'ip=192.168.1.102/24,gw=192.168.1.1',
            'net0': 'virtio,bridge=vmbr0',
            'cicustom': 'user=cloud-init:snippets/worker.yaml'
        })
    
    注意:
        - 某些配置修改需要虚拟机处于停止状态
        - 可以一次更新多个配置参数
        - 对于复杂的配置值（如ipconfig0），需要按照Proxmox的格式提供字符串
        - 使用前最好检查虚拟机的当前状态
    """
    if not pve_client or not pve_client.is_authenticated: return "ERROR: PVE client is not authenticated."
    result = pve_client.update_vm_config(node, vmid, updates)
    return _handle_response(result, "VM config update")


# --- 4. MAIN EXECUTION BLOCK ---

def initialize_pve_agent():
    # initialize_pve_agent 初始化并全局认证 PVE API 客户端
    # @param None: 无输入参数
    # @note 创建 PveApiClient 实例并尝试进行 API Token 认证。
    # @return None
    global pve_client
    
    print("-" * 50)
    print(f"INFO: PVE Host: {PVE_HOST}")
    print(f"INFO: PVE Token ID: {PVE_TOKEN_ID}")
    print(f"INFO: PVE API URL: {PVE_API_URL}")
    print("-" * 50)
    
    pve_client = PveApiClient(
        api_url=PVE_API_URL,
        token_id=PVE_TOKEN_ID,
        token_secret=PVE_TOKEN_SECRET
    )
    
    if not pve_client.authenticate():
        print("WARNING: Failed to initialize PVE API Token client.")


if __name__ == "__main__":
    initialize_pve_agent()
    print("INFO: Starting FastMCP server. Access tools via the FastMCP API.")
    
    try:
        mcp_port_int = int(MCP_PORT)
    except ValueError:
        print(f"ERROR: MCP_PORT environment variable is not a valid integer: {MCP_PORT}. Using default port 8000.")
        mcp_port_int = 8000
    
    mcp.run(transport="streamable-http", host=MCP_HOST, port=mcp_port_int)