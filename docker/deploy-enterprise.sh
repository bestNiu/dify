#!/usr/bin/env bash
# 企业二开分支部署：本地源码构建镜像 + 完整栈启动。
#
#   docker/deploy-enterprise.sh          # 构建并启动
#   docker/deploy-enterprise.sh up       # 只启动（镜像已构建）
#   docker/deploy-enterprise.sh logs     # 跟踪 api 日志
#
# 复用 -p dify 项目名，数据在 docker/volumes/ 下（其中 db 见下方前置条件）。
set -uo pipefail

cd "$(dirname "$(realpath "$0")")"

COMPOSE=(docker compose -p dify -f docker-compose.yaml -f docker-compose.build.yaml)
step() { printf '\n\033[1;36m=== %s ===\033[0m\n' "$*"; }

case "${1:-deploy}" in
  up)   "${COMPOSE[@]}" up -d; "${COMPOSE[@]}" ps; exit $? ;;
  down) "${COMPOSE[@]}" down; exit $? ;;
  logs) exec docker logs -f dify-api-1 ;;
  ps)   "${COMPOSE[@]}" ps; exit $? ;;
esac

# 前置条件：postgres 数据目录必须能被构建用户读取，否则 web 镜像的
# `COPY . .` 遍历上下文时会 EACCES 失败。本仓库已把 db 数据移到仓库外：
#   docker/volumes/db -> /home/ulyy/dify-data/db
if [ ! -L volumes/db ]; then
  echo "警告: docker/volumes/db 不是软链接，web 构建可能因 pgdata 权限失败。" >&2
fi

step "1/4 构建 api"
"${COMPOSE[@]}" build api || exit 1
step "2/4 构建 web"
"${COMPOSE[@]}" build web || exit 1
step "3/4 构建 agent_backend"
"${COMPOSE[@]}" build agent_backend || exit 1

step "4/4 启动"
"${COMPOSE[@]}" up -d || exit 1
"${COMPOSE[@]}" ps

cat <<'EOF'

部署完成。入口: http://localhost/  （首次访问会跳到 /install 创建管理员）

镜像源说明（本机 Docker Hub / files.pythonhosted.org / github.com 受限）：
  - 基础镜像走 public.ecr.aws 与 docker.1panel.live 预拉取后重打官方 tag，
    BuildKit 会直接用本地镜像。
  - Python 依赖与 github 依赖的镜像由 docker-compose.build.yaml 的
    UV_LOCK_FILE_MIRROR / UV_DEFAULT_INDEX / GIT_INSTEADOF_* 构建参数控制，
    置空即恢复上游行为。
EOF
