## 启动说明
### 在根目录下运行make启动或停止服务
``` 启动文件服务
make infra-up
```

``` 启动MCP和监控服务
make app-up
```

``` 停止服务
make clean
```
### NFS配置
- nfs服务需要手动配置并在pve平台挂载nfs，且选择片段才能识别
```
sudo echo "/pve-k3s-management/deploy/k3s_deployment *(rw)"
sudo systemctl restart nfs-server
```

### cloud-init配置
- user-data文件中定义manager地址
```
export MANAGER_IP="192.168.116.100" 
```

### 监控服务env文件配置
- 需要手动定义env中的参数

### prometheus配置
- prometheus.yml中定义集群控制节点地址
```
api_server: '{{K8S_API_SERVER}}'
```
- token值需要到控制节点运行deploy/cloud_init/promtoken/set_prom_token.sh获取