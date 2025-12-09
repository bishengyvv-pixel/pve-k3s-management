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