#!/bin/bash
# -----------------------------------------------------------
# K3s Node Exporter 远程部署脚本 (函数化版本)
# 作用: 从 HTTP 服务器下载 YAML 文件并部署 Node Exporter。
# -----------------------------------------------------------

set -e

# --- 全局常量定义 ---
YAML_FILENAME="node_exporter.yaml"
DOWNLOAD_URL="http://${MANAGER_IP}:8080/nodeexporter/${YAML_FILENAME}"
NAMESPACE="kube-system"
TIMEOUT_SECONDS=120

# check_dependency 检查脚本运行所需的基本依赖
# @param command_name: 待检查的命令名称，例如 "curl" 或 "kubectl"
# @param error_message: 如果命令未找到时打印的错误提示信息
# @note 检查指定的命令是否存在于系统路径中，如果不存在则打印错误信息并退出脚本
# @return 成功返回 0，失败时脚本退出
function check_dependency() {
    local command_name=$1
    local error_message=$2
    if ! command -v "${command_name}" &> /dev/null
    then
        echo "❌ 错误: ${command_name} 命令未找到。${error_message}"
        exit 1
    fi
}

# download_yaml 从远程地址下载 Kubernetes YAML 配置文件
# @param yaml_filename: 要下载并保存到的本地文件名
# @param download_url: 远程 YAML 文件的完整 HTTP URL
# @note 检查文件下载后是否非空，如果失败则删除残留文件并退出
# @return 成功返回 0
function download_yaml() {
    local yaml_filename=$1
    local download_url=$2
    
    echo "1. 正在从 ${download_url} 下载配置文件..."
    curl -s -o "${yaml_filename}" "${download_url}"

    if [ ! -s "${yaml_filename}" ]; then
        echo "❌ 错误: 配置文件下载失败或文件为空。请检查远程服务器 (${download_url}) 是否可访问且文件存在。"
        rm -f "${yaml_filename}"
        exit 1
    fi
    echo "✅ 配置文件 ${yaml_filename} 下载完成。"
}

# apply_and_verify_deployment 应用配置文件并验证 DaemonSet 状态
# @param yaml_filename: 本地 YAML 配置文件名
# @param namespace: 部署的命名空间
# @param timeout: 等待部署完成的最大时间（秒）
# @note 使用 kubectl apply 部署，并使用 kubectl rollout status 验证状态。如果验证失败则退出
# @return 成功返回 0
function apply_and_verify_deployment() {
    local yaml_filename=$1
    local namespace=$2
    local timeout=$3

    echo "2. 正在使用 kubectl 部署 Node Exporter 到 ${namespace} 命名空间..."
    kubectl apply -f "${yaml_filename}"

    echo "=========================================================="
    echo "🎉 Node Exporter DaemonSet 部署成功！"
    echo "=========================================================="
    echo "🎯 部署概览 (DaemonSet):"
    kubectl get ds -n "${namespace}" -l app=node-exporter
    echo ""
    echo "🎯 部署概览 (Pod 状态):"
    kubectl get pods -n "${namespace}" -l app=node-exporter
}

# cleanup 清理本地下载的 YAML 配置文件
# @param yaml_filename: 要删除的本地文件名
# @note 仅删除文件，忽略文件不存在的错误
# @return 返回 0
function cleanup() {
    local yaml_filename=$1
    
    rm -f "${yaml_filename}"
    echo ""
    echo "清理完成。本地文件 ${yaml_filename} 已删除。"
}

# main 脚本主入口，负责协调部署流程
# @param : 无参数
# @note 依次执行依赖检查、下载、部署验证和清理步骤
# @return 成功返回 0
function main() {
    echo "=========================================================="
    echo "🚀 正在启动 Prometheus Node Exporter 部署流程..."
    echo "=========================================================="

    check_dependency "curl" "请安装 curl 后重试"
    check_dependency "kubectl" "请确保您在 K3s Master 节点上执行，并且 kubectl 已安装并配置正确"
    
    download_yaml "${YAML_FILENAME}" "${DOWNLOAD_URL}"
    
    apply_and_verify_deployment "${YAML_FILENAME}" "${NAMESPACE}" "${TIMEOUT_SECONDS}"
    
    cleanup "${YAML_FILENAME}"
    
    echo "=========================================================="
    echo "✅ 所有步骤执行完毕。"
}

main "$@"
