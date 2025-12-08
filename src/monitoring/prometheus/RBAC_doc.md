**操作步骤（在 K3s Master 节点上执行）：**

1.  **创建 Service Account 和 RBAC 配置 (`prometheus-rbac.yaml`)**：

```yaml
# prometheus-rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: prometheus-k8s
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: prometheus-k8s
rules:
- apiGroups: [""]
  resources:
  - nodes
  - nodes/metrics
  - services
  - endpoints
  - pods
  verbs: ["get", "list", "watch"]
- apiGroups:
  - extensions
  resources:
  - ingresses
  verbs: ["get", "list", "watch"]
- nonResourceURLs: ["/metrics"]
  verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: prometheus-k8s
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: prometheus-k8s
subjects:
- kind: ServiceAccount
  name: prometheus-k8s
  namespace: kube-system
---
apiVersion: v1
kind: Secret
metadata:
  name: prometheus-k8s-token
  namespace: kube-system
  annotations:
    kubernetes.io/service-account.name: prometheus-k8s
type: kubernetes.io/service-account-token
```

2.  **应用 RBAC 配置：**

```bash
kubectl apply -f prometheus-rbac.yaml
```

3.  **获取新的 Service Account Token：**

  * **注意：** 从 Kubernetes v1.24 开始，Token 是由 Service Account Secret 自动生成的，但推荐使用 `kubectl create token` 命令获取长期有效的 Token：

<!-- end list -->

```
LONG_LIVED_TOKEN=$(kubectl get secret prometheus-k8s-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)

echo "新获得的长期 Token: $LONG_LIVED_TOKEN"
```

4.  **替换 Token：** 将您在步骤 3 中获得的 `NEW_TOKEN` 替换到您的 `k3s_token.txt` 文件中。

5.  **重启 Prometheus：**

```bash
docker compose restart prometheus
```

完成这些步骤后，Prometheus 将使用一个具备足够权限的 Token 来连接 K3s API Server，从而解决 **`Unauthorized`** 错误。