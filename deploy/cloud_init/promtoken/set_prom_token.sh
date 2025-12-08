kubectl apply -f http://${MANAGER_IP}:8080/promtoken/prometheus_rbac.yaml
LONG_LIVED_TOKEN=$(kubectl get secret prometheus-k8s-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)

echo "新获得的长期 Token: $LONG_LIVED_TOKEN"
