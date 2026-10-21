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

- **出网代理**：本机无直连外网，`ssrf_proxy`(squid) 通过
  `SSRF_PROXY_UPSTREAM_HOST` / `SSRF_PROXY_UPSTREAM_PORT` 走宿主机 sing-box
  （`172.17.0.1:7890`）。`ssrf_proxy/docker-entrypoint.sh` 会据此生成
  `/etc/squid/dify_upstream.conf`（`cache_peer` + `never_direct allow all`），
  否则插件市场下载会 `TCP_TUNNEL/503` 并在 3 次重试后失败。

- `local_sandbox` 官方 `1.17.1` 镜像尚未实现 `--require-auth-token` 参数，
  override 中去掉了该参数；`SHELLCTL_AUTH_TOKEN` 仍会生效。
- `plugin_daemon` 暴露 `5003`（插件调试端口）。
- 数据卷位于 `docker/volumes/`，升级/迁移前请备份。
- `docker-compose.yaml` 由 `generate_docker_compose` 生成，请勿直接修改；
  二开定制写入 `docker-compose.override.yaml`。
## 6. 品牌资源（UnionFlow 一期）

前端 logo / favicon 全部由品牌源图生成，源图放在仓库根的 `images/new/`：

```bash
# 重新生成（宿主机无 Pillow，用 dify-api 镜像跑，自带 Pillow 12）
docker run --rm --user "$(id -u):$(id -g)" --entrypoint /bin/bash \
  -v "$PWD":/repo -v /usr/share/fonts/truetype/dejavu:/fonts:ro \
  -w /repo dify-api:1.17.1-custom \
  -c "python3 scripts/brand/generate_brand_assets.py"
```

产物：`web/public/logo/` 下 7 个文件（横版 lockup 浅/深、嵌入对话头像与头部 1x/2x/3x、
`logo.svg`）+ `web/public/favicon.ico`（16/32/48/64/128）。

约定与已知限制：

- 源图是 **1254×1254 栅格**，`logo.svg` 是"内嵌 base64 PNG 的 SVG"外壳，
  **待补矢量源**；拿到 SVG/AI 源文件后把该文件替换成真正的 path 即可，无需改组件。
- 横版 lockup 宽高比约 **3.86:1**（图形 168px + "UnionFlow" 文字），所以
  `dify-logo.tsx` 的尺寸变体改用 `h-* w-auto`，别的页面传 `w-*` 固定宽会导致留白。
- 深色模式沿用组件里的 `brightness-0 invert` 滤镜（与官方行为一致）；
  若想深色下保留图形细节，可改用 `web/public/logo/logo-site-dark.png`。
- 关掉的对外依赖：`CHECK_UPDATE_URL` 置空、`DISABLE_TELEMETRY=true`、
  `DO_NOT_TRACK=true`，因此不再请求 `updates.dify.ai` 与 `otel.dify.ai`。
- 内部标识符（`LangGeniusVersionInfo` 等类型名、市场插件 `org: 'LangGenius'` 测试数据）
  按协议/数据范畴保留，未随品牌替换。
