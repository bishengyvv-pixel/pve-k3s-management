# manager文件服务搭建
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


## 安装http服务
```
cd /pve-k3s-management/deploy/cloud_init
```
```
docker compose up -d
```
```
curl localhost:8080/index.html
```

## 安装私有镜像源
```
cd /pve-k3s-management/deploy/registeries/
```
```
docker compose up -d
```
```
curl localhost:5000/v2/_catalog
```

## 安装NFS服务
```
apt -y install nfs-server
```
```
echo "/pve-k3s-management/deploy/k3s_deployment 192.168.0.0/16(rw,no_root_squash)" > /etc/exports
```
```
exportfs -arv
systemctl restart nfs-server
```
在pve设置存储NFS卷，ID为 **cloud-init** ，export为 **/pve-k3s-management/deploy/k3s_deployment** ，内容为 **片段**