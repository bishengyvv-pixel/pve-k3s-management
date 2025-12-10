## manager监控服务搭建
- 确保项目文件夹在根目录下

## 安装docker
```
apt -y install docker.io docker-compose-v2
```
```
echo '{"insecure-registries":["k3m6f90oiarhbg.xuanyuan.run"],"registry-mirrors":["https://k3m6f90oiarhbg.xuanyuan.run"]}' | sudo tee /etc/docker/daemon.json > /dev/null
```
```
systemctl daemon-reload
systemctl restart docker
```

## 上传github私钥到用户目录.ssh/下

## 克隆github项目
```
cd /
git clone git@github.com:bishengyvv-pixel/pve-k3s-management.git
```

## 设置环境变量
```
cd /pve-k3s-management/src/monitoring
cp .env.example .env
```

```
# Proxmox VE API Configuration
PVE_HOST=""
PVE_PORT="8006"
PVE_TOKEN_ID=""
PVE_TOKEN_SECRET=""

# FastMCP Server Configuration
MCP_HOST=""
MCP_PORT="8000"

DEEPSEEK_API_KEY=""
```
- PVE_TOKEN_ID和PVE_TOKEN_SECERT在pve中手动获取
- MCP_HOST为manager主机地址

## 设置Prometheus
```
cd /pve-k3s-management/src/monitoring/prometheus
```
```
vim prometheus.yml
...
    api_server: 'https://{控制节点地址}:6443'
...
```
```
vim token
```
- token在集群中手动获取

## 启动服务
```
cd /pve-k3s-management/src/monitoring/prometheus
docker compose up -v
```