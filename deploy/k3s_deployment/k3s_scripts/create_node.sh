#!/bin/bash

# ==============================================================================
# 变量定义
# ==============================================================================
# REGISTRY_ENDPOINT 私有镜像仓库地址，用于配置 registries.yaml
REGISTRY_ENDPOINT="http://${MANAGER_IP}:5000"
K3S_BIN="k3s"
INSTALL_SCRIPT="k3s_install.sh"
REGISTRIES_CONFIG_PATH="/etc/rancher/k3s/registries.yaml"
K3S_CONFIG_DIR="/etc/rancher/k3s"
CONFIG_FILE="k3s_config.conf"
# ==============================================================================

prepare_k3s_files() {
    # prepare_k3s_files 检查并准备 k3s 二进制文件和安装脚本
    # @param K3S_BIN: K3s 二进制文件名 (期望存在于当前目录)
    # @param INSTALL_SCRIPT: K3s 安装脚本文件名 (期望存在于当前目录)
    # @note 假设当前目录为 NFS 挂载点，且文件已存在
    # @return 成功返回 0，失败返回 1
    echo "|preparing k3s binary and registries config|"

    if [ ! -f "$K3S_BIN" ] || [ ! -f "$INSTALL_SCRIPT" ]; then
        echo "Error: K3s binary or install script not found in the current directory (NFS mount point)."
        return 1
    fi

    chmod +x "${K3S_BIN}" || { echo "Error: Failed to set executable permission on ${K3S_BIN}"; return 1; }
    mv "${K3S_BIN}" /usr/local/bin/ || { echo "Error: Failed to move ${K3S_BIN} to /usr/local/bin/"; return 1; }
    
    return 0
}

configure_registry_yaml() {
    # configure_registry_yaml 创建 K3s 的 registries.yaml 配置文件
    # @param K3S_CONFIG_DIR: K3s 配置目录的路径 (/etc/rancher/k3s)
    # @param REGISTRIES_CONFIG_PATH: registries.yaml 文件的完整路径
    # @param REGISTRY_ENDPOINT: 私有镜像仓库的 HTTP 地址
    # @return 成功返回 0，失败返回 1
    mkdir -p "${K3S_CONFIG_DIR}" || { echo "Error: Failed to create K3s config directory"; return 1; }

    cat << EOF > "${REGISTRIES_CONFIG_PATH}"
mirrors:
  "docker.io":
    endpoint:
      - "${REGISTRY_ENDPOINT}"
      - "http://k3m6f90oiarhbg.xuanyuan.run"
EOF

    if [ $? -ne 0 ]; then
        echo "Error: Failed to write ${REGISTRIES_CONFIG_PATH}"
        return 1
    fi
    
    return 0
}

install_control_node() {
    # install_control_node 执行 Master 节点的安装和 Token 复制
    # @param INSTALL_SCRIPT: K3s 安装脚本文件名
    # @param CONFIG_FILE: 存储 K3s IP 和 Token 的配置文件 (位于当前 NFS 挂载点)
    # @note K3s 安装脚本的执行结果通过 $? 检查
    # @return 成功返回 0，失败返回 1
    local INSTALL_CMD="INSTALL_K3S_SKIP_DOWNLOAD=true bash ./${INSTALL_SCRIPT}"
    
    eval "${INSTALL_CMD}"
    
    if [ $? -ne 0 ]; then
        echo "Error: K3s installation failed (control_node)"
        return 1
    fi
}

install_work_node() {
    # install_work_node 执行 Worker 节点的加入集群操作
    # @param INSTALL_SCRIPT: K3s 安装脚本文件名
    # @param MASTER_IP: Master 节点的 IP 地址
    # @param CONFIG_FILE: 存储 K3s IP 和 Token 的配置文件 (位于当前 NFS 挂载点)
    # @return 成功返回 0，失败返回 1
    echo "|reading token from shared file: ${CONFIG_FILE}|"
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Error: Token file ${CONFIG_FILE} not found on shared drive. Ensure Master is installed first."
        return 1
    fi

    source "$CONFIG_FILE"
    
    if [ -z "$MASTER_IP" ] || [ -z "$TOKEN" ]; then
        echo "Error: Failed to load Master IP or Token from configuration file."
        exit 1
    fi
    
    local INSTALL_CMD="INSTALL_K3S_SKIP_DOWNLOAD=true bash ./${INSTALL_SCRIPT}"

    local FULL_INSTALL_CMD="K3S_URL=https://${MASTER_IP}:6443 K3S_TOKEN=${TOKEN} ${INSTALL_CMD}"
    eval "${FULL_INSTALL_CMD}"

    if [ $? -ne 0 ]; then
        echo "Error: K3s installation failed (work_node)"
        return 1
    fi

    return 0
}

main() {
    # main 程序主入口
    # @note 脚本执行的流程控制
    # @return 成功返回 0，失败返回 1
    prepare_k3s_files || return 1
    
    configure_registry_yaml || return 1

    echo "|install k3s cluster|"
    
    if [[ "$K3S_TYPE" == "control_node" ]]; then
        install_control_node || return 1
    elif [[ "$K3S_TYPE" == "work_node" ]]; then
        install_work_node || return 1
    else
        echo "Error: Invalid K3S_TYPE value."
        return 1
    fi

    echo "K3s installation successful for role: $K3S_TYPE"
    return 0
}

main
