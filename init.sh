#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ============================================================
# 参数解析
#   $1 = ghp          GitHub Personal Access Token (必需)
#   $2 = github_user  GitHub 用户名 (可选, 默认 cjqbj)
#   剩余参数原样传给 debug.sh
# ============================================================
GHP="${1:-}"
if [[ -z "$GHP" ]]; then
    cat >&2 <<'EOF'
错误: 缺少必需参数 <ghp>

用法:
    ./init.sh <ghp> [github_user] [debug.sh 参数...]

参数:
    ghp          GitHub Personal Access Token (必需)
    github_user  GitHub 用户名 (可选, 默认: cjqbj)

示例:
    ./init.sh ghp_xxxxxxxxxxxxxxxxxxxx
    ./init.sh ghp_xxxxxxxxxxxxxxxxxxxx myname
    ./init.sh ghp_xxxxxxxxxxxxxxxxxxxx myname release
EOF
    exit 1
fi
shift   # 吃掉 ghp

GH_USER="cjqbj"
if [[ $# -gt 0 ]]; then
    GH_USER="$1"
    shift
fi

export GHP GH_USER

# 统一认证前缀，所有 GitHub URL 复用
GIT_CRED="${GH_USER}:${GHP}"

echo "GitHub 用户: $GH_USER"

# ============================================================
# Codespaces hook 处理
# ============================================================
disable_codespaces_hook() {
    local hook_path="${1:-}"
    [[ -n "$hook_path" ]] || return 0

    local backup="${hook_path}.codespaces-disabled"
    if [[ -f "$hook_path" ]] && grep -Eqi 'codespaces|fork_repo|GITHUB_REPOSITORY' "$hook_path" 2>/dev/null; then
        if [[ ! -e "$backup" ]]; then
            echo "检测到 Codespaces hook，临时禁用: $hook_path"
            mv "$hook_path" "$backup"
        fi
    fi
}

restore_codespaces_hook() {
    local hook_path="${1:-}"
    [[ -n "$hook_path" ]] || return 0

    local backup="${hook_path}.codespaces-disabled"
    if [[ -f "$backup" ]] && [[ ! -f "$hook_path" ]]; then
        echo "恢复 Codespaces hook: $hook_path"
        mv "$backup" "$hook_path"
        chmod +x "$hook_path" 2>/dev/null || true
    fi
}

# Codespaces 会在 .git/hooks/post-commit 中注入一个 fork 仓库钩子；
# 这个钩子会和 git lfs install --local 发生冲突，导致一键初始化失败。
# 先禁用它，完成初始化后再恢复，避免干扰 Codespaces 原有行为。
disable_codespaces_hook "$ROOT_DIR/.git/hooks/post-commit"
#trap 'restore_codespaces_hook "$ROOT_DIR/.git/hooks/post-commit"' EXIT

if command -v git >/dev/null 2>&1 && git lfs version >/dev/null 2>&1; then
    echo "初始化 Git LFS hook（忽略 Codespaces 冲突）..."
    git lfs install --local || true
fi

# ============================================================
# 通用 clone 包装：任何失败只警告，不打断
# ============================================================
try_clone() {
    # 用法: try_clone <cmd...>
    echo "▶ $*"
    if "$@"; then
        return 0
    else
        echo "警告: clone 失败或目标已存在，继续执行: $*" >&2
        return 0
    fi
}

# ============================================================
# 拉取主仓库 / 子仓库（统一使用同一个 ghp + user）
# ============================================================
./git.py pull -v 3 "https://${GIT_CRED}@github.com/${GH_USER}/build_xime_home" || {
    echo "警告: 主仓库 pull 失败，继续。" >&2
}
#git lfs pull

# 这是真正需要拉取/构建的项目代码，不要在上层仓库里反复执行全量 git pull。

# multi_mqtt
try_clone git clone https://github.com/wxsb-web/multi_mqtt

try_clone git clone --depth=1 https://github.com/cjqbj/client_mqtt-cjqbj client
# xime
xime_repo="xime"
try_clone ./git.py clone --depth=1 -b main "https://${GIT_CRED}@github.com/${GH_USER}/${xime_repo}"
#try_clone ./git.py clone --depth=1 -b main "https://github.com/qgbcs/${xime_repo}"

if [[ -d "$xime_repo" ]]; then
    cd "$xime_repo"
    #git submodule update --init --recursive
    echo "第一次执行耗时约 2+11 分钟，后续执行耗时约几十秒钟"
    ./debug_build_secexp.sh  "$@"
else
    echo "错误: 目录不存在，无法进入并执行 debug_build_secexp.sh: $xime_repo" >&2
    exit 1
fi