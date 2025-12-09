#!/bin/bash
# 严格模式：遇到任何错误立即退出 (-e)，使用未设置的变量时出错 (-u)，管道中的任何命令失败时返回失败码 (-o pipefail)
set -euo pipefail

# ==============================================================================
# 变量定义 (Configuration Variables)
# ==============================================================================
# SCRIPT_NAME 脚本文件名，用于错误信息
SCRIPT_NAME=$(basename "$0")
# NFS_SERVER NFS 服务器的 IP 地址
NFS_SERVER=${MANAGER_IP}
# NFS_EXPORT NFS 服务器导出的路径
NFS_EXPORT="/pve-k3s-management/deploy/k3s_deployment/k3s_scripts"
# MOUNT_POINT 本地用于挂载 NFS 的目录
MOUNT_POINT="/mnt/nfs"
# APT_SOURCE_LIST 新的 apt 源配置内容
APT_SOURCE_LIST="
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble main restricted universe multiverse
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble-updates main restricted universe multiverse
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble-backports main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu/ noble-security main restricted universe multiverse
"
# REQUIRED_FILES 必须从 NFS 复制到家目录的文件列表
REQUIRED_FILES=("create_node.sh" "k3s" "k3s_install.sh" "k3s_config.conf")

# ==============================================================================
# 全局参数设置 (Global Parameters Setup)
# ==============================================================================
# K3S_TYPE K3s 节点类型 (control_node 或 work_node)
export K3S_TYPE="${1:-}"

# ==============================================================================
# 函数定义 (Function Definitions)
# ==============================================================================

set_unique_hostname() {
    # set_unique_hostname 根据 K3S_TYPE 和 machine-id 后四位设置唯一主机名
    # @param K3S_TYPE: 主机角色类型 (全局变量)
    # @note 设置的主机名格式为: [control|worker]-[machine-id后四位]
    # @return 成功返回 0，失败返回 1
    
    echo "正在设置唯一主机名..."
    
    if [ ! -f /etc/machine-id ]; then
        echo "Error: /etc/machine-id 文件不存在，无法生成唯一主机名。" >&2
        return 1
    fi
    
    local MACHINE_ID_SUFFIX
    MACHINE_ID_SUFFIX=$(cat /etc/machine-id | tail -c 5) 
    
    local NODE_PREFIX
    if [ "${K3S_TYPE}" == "control_node" ]; then
        NODE_PREFIX="control"
    elif [ "${K3S_TYPE}" == "work_node" ]; then
        NODE_PREFIX="worker"
    else
        echo "Error: K3S_TYPE 设置错误，无法确定主机名前缀。" >&2
        return 1
    fi

    local NEW_HOSTNAME="${NODE_PREFIX}-${MACHINE_ID_SUFFIX}"

    echo "新主机名将被设置为: ${NEW_HOSTNAME}"
    if hostnamectl set-hostname "${NEW_HOSTNAME}"; then
        echo "主机名设置成功。"
        return 0
    else
        echo "Error: hostnamectl 设置失败。" >&2
        return 1
    fi
}


check_prerequisites() {
    # check_prerequisites 检查脚本运行的环境要求和输入参数
    # @param K3S_TYPE: 主机角色类型 (control_node 或 work_node)
    # @param K3S_MASTER_IP: Master 节点的 IP 地址 (仅 work_node 需要)
    # @note 检查运行用户是否为 root，并验证 K3S_TYPE 和 K3S_MASTER_IP 参数的合法性。
    # @return 成功返回 0，失败返回 1
    
    if [ "$(id -u)" -ne 0 ]; then
        echo "Error: 请以 root 用户运行此脚本" >&2
        return 1
    fi
    
    if [ -z "${K3S_TYPE}" ]; then
        echo "Error: K3S_TYPE (\$1) 必须设置为 'control_node' 或 'work_node'." >&2
        return 1
    fi

    return 0
}

configure_apt_source() {
    # configure_apt_source 备份原 apt 源并写入新的清华镜像源
    # @param APT_SOURCE_LIST: 包含新 apt 源配置内容的字符串 (全局变量)
    # @note 使用清华大学的镜像源，适用于 noble (Ubuntu 24.04 LTS)。
    # @return 成功返回 0，失败返回非 0 (来自 apt-get update)
    
    echo "备份原有 apt 源并写入新镜像源..."
    if [ -f /etc/apt/sources.list ]; then
        cp -a /etc/apt/sources.list /etc/apt/sources.list.bak.$(date +%s)
    fi
    
    echo "${APT_SOURCE_LIST}" | tee /etc/apt/sources.list > /dev/null
    
    apt-get update -y
    
    return $?
}

install_nfs_client() {
    # install_nfs_client 安装 NFS 客户端软件包
    # @note 安装 nfs-common，这是 NFS 挂载所必需的。
    # @return 成功返回 0，失败返回 1
    
    echo "安装 NFS 客户端 (nfs-common)..."
    if ! apt-get install -y nfs-common; then
        echo "Error: nfs-common 安装失败。" >&2
        return 1
    fi
    
    return 0
}

mount_nfs_share() {
    # mount_nfs_share 挂载 NFS 共享目录到本地路径
    # @param NFS_SERVER: NFS 服务器 IP 地址 (全局变量)
    # @param NFS_EXPORT: NFS 导出路径 (全局变量)
    # @param MOUNT_POINT: 本地挂载目录 (全局变量)
    # @note 检查挂载点是否已挂载，若未挂载则尝试执行挂载操作。
    # @return 挂载成功或已挂载返回 0，挂载失败返回 2
    
    echo "创建挂载目录：${MOUNT_POINT}"
    mkdir -p "${MOUNT_POINT}"
    
    if mountpoint -q "${MOUNT_POINT}"; then
        echo "${MOUNT_POINT} 已经被挂载，跳过挂载。"
        return 0
    else
        echo "尝试挂载 ${NFS_SERVER}:${NFS_EXPORT} 到 ${MOUNT_POINT}..."
        if mount -t nfs "${NFS_SERVER}:${NFS_EXPORT}" "${MOUNT_POINT}"; then
            echo "挂载成功。"
            return 0
        else
            echo "Error: 挂载失败，请检查 NFS 服务器和导出路径。" >&2
            return 2
        fi
    fi
}

copy_files_and_run_script() {
    # copy_files_and_run_script 复制共享文件到家目录并执行 create_node.sh
    # @param MOUNT_POINT: NFS 挂载点路径 (全局变量)
    # @param REQUIRED_FILES: 需复制的文件列表 (全局变量)
    # @note 确定目标用户和家目录 (优先 SUDO_USER)，然后复制文件并执行 create_node.sh。
    # @return create_node.sh 执行成功返回 0，文件复制或脚本执行失败返回非 0
    
    local HOME_DIR="/root"
    local RUN_AS_USER="root"
    local CREATE_NODE_SCRIPT="create_node.sh"
    
    if [ -n "${SUDO_USER-}" ] && [ "${SUDO_USER}" != "root" ]; then
        HOME_DIR=$(getent passwd "${SUDO_USER}" | cut -d: -f6) || HOME_DIR="/home/${SUDO_USER}"
        RUN_AS_USER="${SUDO_USER}"
    fi

    echo "目标家目录：${HOME_DIR}，执行用户：${RUN_AS_USER}"

    for f in "${REQUIRED_FILES[@]}"; do
        local SRC="${MOUNT_POINT}/${f}"
        local DST="${HOME_DIR}/${f}"
        if [ -e "${SRC}" ]; then
            echo "复制 ${SRC} -> ${DST}"
            cp -f "${SRC}" "${DST}"
            chmod +x "${DST}" || true
            if [ "${RUN_AS_USER}" != "root" ]; then
                chown "${RUN_AS_USER}:${RUN_AS_USER}" "${DST}" || true
            fi
        else
            echo "Warning: ${SRC} 不存在，跳过复制。"
        fi
    done

    local SCRIPT_PATH="${HOME_DIR}/${CREATE_NODE_SCRIPT}"
    if [ -e "${SCRIPT_PATH}" ]; then
        echo "执行 ${SCRIPT_PATH} ..."
        if cd "${HOME_DIR}"; then
            echo "当前工作目录已切换到: $(pwd)"
            bash "${SCRIPT_PATH}"
            local RET=$?
        else
            echo "Error: 无法切换到 ${HOME_DIR} 目录。" >&2
            return 4
        fi
        return $RET
    else
        echo "Error: ${SCRIPT_PATH} 不存在，无法执行。" >&2
        return 3
    fi

}

finalize_and_cleanup() {
    # finalize_and_cleanup 根据节点类型执行收尾工作，并输出完成信息
    # @param K3S_TYPE: 主机角色类型 (全局变量)
    # @param MOUNT_POINT: NFS 挂载点路径 (全局变量)
    # @note control_node 需要获取 IP 和 Token 并写入配置文件。
    # @return 成功返回 0
    
    if [ "${K3S_TYPE}" = "control_node" ]; then
        local K3S_MASTER_IP_FOUND
        K3S_MASTER_IP_FOUND=$(hostname -I | awk '{print $1}')
        local K3S_TOKEN
        K3S_TOKEN=$(cat /var/lib/rancher/k3s/server/token) || true
        
        (
            echo "MASTER_IP=\"${K3S_MASTER_IP_FOUND}\""
            echo "TOKEN=\"${K3S_TOKEN}\""
        ) | tee "${MOUNT_POINT}/k3s_config.conf" > /dev/null
        
        echo "Create Control node complete. Master IP and Token saved to NFS."
        
    elif [ "${K3S_TYPE}" = "work_node" ]; then
        echo "Create Worker node complete."
    fi
    
    return 0
}

main() {
    # main 程序主入口
    # @note 脚本执行的流程控制，使用短路逻辑确保任何步骤失败时立即退出。
    # @return 成功返回 0，失败返回非 0
    
    check_prerequisites        || return 1
    set_unique_hostname        || return 1
    install_nfs_client         || return 1
    mount_nfs_share            || return 2
    copy_files_and_run_script  || return 3
    finalize_and_cleanup       || return 0
    
    return 0
}

main
