# MANAGER主机服务
+ file_server
  - http:8080
  - nfs
  - registries:5000
+ monitor_server
  - agent:9999
  - prometheus:9090
  - alertmanager:9093
  - prometheus_pusher:9095
- mcp:8000

# 环境定义规则
- 所有shell脚本中的manager主机地址都读取环境变量*MANAGER_IP*
```
export MANAGER_IP = {{your_manager_ip}}
```

# 脚本配置说明
## snippets
### control/work
- 在runcmd块中定义的MANAGER_IP

### test
- 该脚本仅用于测试

## init.sh/k3s_scripts/nodeexporter/promtoken
- 带环境变量MANAGER_IP时才能正常运行！

# 服务配置说明
## file_server
### http
- 配置deploy/cloud-init/为访问目录
- 访问端口: 8080

### nfs
- 配置deploy/k3s_deployment/为共享目录

### registeries
- 挂载deploy/registeries/docker/registry/v2
- 访问端口: 5000

## monitor_server
### agent
- 在compose中定义环境变量

### prometheus
- 在token文件中设置k3s集群token

### altermanager
- 在altermanager.yml文件中定义pusher_host

### pusher
- 在compose中定义环境变量

## mcp
- 在env文件中定义环境变量