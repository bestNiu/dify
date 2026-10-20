# Unionflow 二开部署说明

本目录在官方 `docker-compose.yaml` 之上通过 `docker-compose.override.yaml`
使用**从本仓库源码构建**的 `dify-api` / `dify-web` 镜像，其余中间件
（PostgreSQL、Redis、Weaviate、sandbox、plugin_daemon 等）仍使用官方镜像。

- 来源分支：`custom/unionflow`（基于 `main`，Dify 1.17.1）
- 镜像标签：`dify-api:1.17.1-custom`、`dify-web:1.17.1-custom`

## 1. 环境变量

```bash
cd docker
cp .env.example .env
# 修改至少以下项（不要使用示例值）：
#   SECRET_KEY / INIT_PASSWORD / DB_PASSWORD / REDIS_PASSWORD
#   SANDBOX_API_KEY / PLUGIN_DAEMON_KEY
#   DIFY_AGENT_SERVER_SECRET_KEY   # 必须是无填充 base64url（32 字节）
#   CELERY_BROKER_URL              # 必须与 REDIS_PASSWORD 保持一致
```

> `CELERY_BROKER_URL` 不会自动跟随 `REDIS_PASSWORD`，两者必须手动保持一致，
> 否则 worker / worker_beat 会报 `invalid username-password pair`。

## 2. 构建二开镜像

在**仓库根目录**执行（`api/Dockerfile`、`web/Dockerfile` 的构建上下文都是仓库根目录）：

```bash
docker build -f api/Dockerfile -t dify-api:1.17.1-custom .
docker build -f web/Dockerfile -t dify-web:1.17.1-custom .
```

若构建环境需要 HTTP 代理（容器内无法直连外网时）：

```bash
P=http://<proxy-host>:<port>
docker build -f api/Dockerfile -t dify-api:1.17.1-custom \
  --build-arg HTTP_PROXY=$P --build-arg HTTPS_PROXY=$P \
  --build-arg http_proxy=$P --build-arg https_proxy=$P \
  --build-arg NO_PROXY=localhost,127.0.0.1,::1 \
  --build-arg NLTK_ALLOW_PROXIED_URLOPEN=1 .

docker build -f web/Dockerfile -t dify-web:1.17.1-custom \
  --build-arg HTTP_PROXY=$P --build-arg HTTPS_PROXY=$P \
  --build-arg http_proxy=$P --build-arg https_proxy=$P \
  --build-arg NO_PROXY=localhost,127.0.0.1,::1 \
  --build-arg NODE_USE_ENV_PROXY=1 .
```

两个 Dockerfile 中的 `NLTK_ALLOW_PROXIED_URLOPEN`、`NODE_USE_ENV_PROXY`
均为可选开关，默认为空，不影响无代理环境。

## 3. 启动 / 更新

```bash
cd docker
docker compose up -d --no-build

# 二开代码改动后：重新构建镜像并滚动重启
docker build -f ../api/Dockerfile -t dify-api:1.17.1-custom ..
docker build -f ../web/Dockerfile -t dify-web:1.17.1-custom ..
docker compose up -d --no-build api api_websocket worker worker_beat web
```

## 4. 访问与初始化

- 控制台：`http://<host>:9099/`（Nginx 容器内仍监听 80/443，宿主机映射由 `.env` 的 `EXPOSE_NGINX_PORT` 控制）
- 首次初始化：
  - 使用 `INIT_PASSWORD` 通过初始化校验；
  - 设置管理员邮箱/密码；
  - 服务端 API 的 `password` 字段是 **base64** 编码（不是加密）。
- 初始化完成后 `GET /console/api/setup` 返回 `{"step":"finished"}`。

## 5. 已知差异与注意事项

- `local_sandbox` 官方 `1.17.1` 镜像尚未实现 `--require-auth-token` 参数，
  override 中去掉了该参数；`SHELLCTL_AUTH_TOKEN` 仍会生效。
- `plugin_daemon` 暴露 `5003`（插件调试端口）。
- 数据卷位于 `docker/volumes/`，升级/迁移前请备份。
- `docker-compose.yaml` 由 `generate_docker_compose` 生成，请勿直接修改；
  二开定制写入 `docker-compose.override.yaml`。