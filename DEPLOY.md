# 部署指南

## 项目架构概览

```
用户浏览器
    │
    ▼
Nginx (80/443)
    ├── / → 静态文件 (trip-front/dist/)
    └── /api/* → 反向代理 → Node.js (端口 3000)
                                  │
                                  ▼
                              MySQL (3306)
```

- 前端：Vue 3 SPA，构建为纯静态文件，由 Nginx 直接托管
- 后端：Express API 服务，Node.js 运行，监听 3000 端口
- 数据库：MySQL，Prisma ORM 管理
- AI：通过 HTTPS 调用外部 API（DeepSeek/Kimi），无需自建

---

## 方案对比

| 维度 | VPS / 云服务器 | PaaS（Zeabur / Railway） | Docker + 云主机 |
|---|---|---|---|
| **费用** | 50-200 元/月 | 按量计费，约 5-20 刀/月 | ≈ VPS + 额外运维 |
| **运维复杂度** | ⭐⭐⭐ 需要自己配 Nginx、MySQL、PM2、SSL | ⭐ 自动部署、SSL、日志 | ⭐⭐⭐ 需 Docker 基础 |
| **弹性伸缩** | 手动升配 | 自动 | 手动 |
| **适合场景** | 生产环境，需要完全控制 | 中小项目、快速上线 | 标准化交付 |

**推荐：初期用 PaaS 快速上线，流量上来后迁到 VPS。**

---

## 方案一：VPS (推荐生产环境)

### 1. 服务器环境配置

**系统：Ubuntu 22.04 LTS**

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v   # 确认 ≥ 20

# 安装 MySQL 8.0
sudo apt install -y mysql-server
sudo mysql_secure_installation

# 安装 Nginx
sudo apt install -y nginx

# 安装 PM2（进程管理）
sudo npm install -g pm2

# 安装 Git
sudo apt install -y git
```

### 2. 数据库配置

```bash
# 登录 MySQL
sudo mysql

# 创建数据库和用户
CREATE DATABASE trip_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'trip_user'@'localhost' IDENTIFIED BY 'your-strong-password';
GRANT ALL PRIVILEGES ON trip_db.* TO 'trip_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 3. 拉取代码与编译

```bash
# 创建项目目录
mkdir -p /var/www/trip && cd /var/www/trip

# 克隆仓库（替换为你的仓库地址）
git clone https://github.com/wpy2580536181-stack/trip-ai.git .

# 安装后端依赖并编译
cd trip-server
npm install --production
npx prisma generate
NODE_ENV=production npm run build

# 安装前端依赖并构建
cd ../trip-front
npm install
npm run build
```

### 4. 配置环境变量

```bash
cd /var/www/trip/trip-server
cp .env.example .env
```

编辑 `.env`：

```env
# 数据库 — 使用上一步创建的用户
DATABASE_URL="mysql://trip_user:your-strong-password@localhost:3306/trip_db"

# JWT
JWT_SECRET=<生成一个随机字符串，建议 64 位>
JWT_EXPIRES_IN=7d

# 服务
PORT=3000
CORS_ORIGIN=https://your-domain.com     # 你的域名

# AI — 填入真实密钥
MODEL_PROVIDER=DEEPSEEK
DEEPSEEK_API_KEY=sk-your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

NODE_ENV=production
```

生成 JWT_SECRET 的命令：

```bash
openssl rand -hex 32
```

### 5. 初始化数据库表

```bash
cd /var/www/trip/trip-server
npx prisma db push
```

注意：如果使用 `prisma db push`，需在服务器上安装 Prisma CLI：

```bash
npm install -g prisma
# 或者用 npx
npx prisma db push
```

### 6. 启动后端服务

```bash
cd /var/www/trip/trip-server

# 用 PM2 启动
pm2 start dist/index.js --name trip-server

# 设置开机自启
pm2 startup
pm2 save

# 检查状态
pm2 status
pm2 logs trip-server    # 查看日志
```

### 7. 配置 Nginx

创建配置文件：

```bash
sudo nano /etc/nginx/sites-available/trip
```

写入：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 证书（见第 8 步）
    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # 前端静态文件
    root /var/www/trip/trip-front/dist;
    index index.html;

    # Gzip 压缩
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 256;

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # SSE 支持（聊天流式接口需要）
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }

    # SPA 路由：所有非文件请求指向 index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 安全头
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/trip /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default   # 移除默认站点
sudo nginx -t   # 测试配置
sudo systemctl reload nginx
```

### 8. HTTPS（Let's Encrypt）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

自动续期（默认已配置定时任务）：

```bash
# 测试续期
sudo certbot renew --dry-run
```

### 9. 防火墙

```bash
sudo ufw allow 22/tcp       # SSH
sudo ufw allow 80/tcp       # HTTP
sudo ufw allow 443/tcp      # HTTPS
sudo ufw deny 3000          # 禁止直接访问后端端口
sudo ufw enable
```

### 10. 验证部署

```bash
# 后端 API
curl https://your-domain.com/api/test

# 前端页面
curl -s https://your-domain.com/ | head -5
```

---

## 方案二：PaaS（Zeabur — 推荐快速部署）

Zeabur 对中文用户友好，支持直接连接 GitHub 仓库自动部署。

### 1. 后端部署

1. 在 [Zeabur](https://zeabur.com) 创建项目
2. 添加服务 → 选择 `trip-server` 目录
3. 构建命令：`npm install && npx prisma generate && npm run build`
4. 启动命令：`npm start`
5. 环境变量（参考 `.env.example`）：
   - `DATABASE_URL` → 使用 Zeabur 的 MySQL 插件
   - `JWT_SECRET` → 随机字符串
   - `CORS_ORIGIN` → 前端部署后的域名
   - `DEEPSEEK_API_KEY` → 你的密钥
   - `NODE_ENV` → `production`
6. 添加 MySQL 插件，会自动生成 `DATABASE_URL`
7. 部署后，在终端执行 `npx prisma db push`（可通过 Zeabur 的 Web Console）

### 2. 前端部署

1. 添加新服务 → 选择 `trip-front` 目录
2. 构建命令：`npm install && npm run build`
3. 启动命令：留空（Zeabur 会自动识别为静态站点）
4. 输出目录：`dist`
5. 环境变量：无需设置（构建时 Vite proxy 仅在开发环境使用，生产环境走 Nginx 或 Zeabur 自动路由）

### 3. 自定义域名

1. 在 Zeabur 项目设置中绑定域名
2. 按提示在 DNS 添加 CNAME 记录
3. HTTPS 自动配置

### 4. 验证

同上。

---

## 方案三：Docker + Docker Compose

### `docker-compose.yml`

在项目根目录创建：

```yaml
version: '3.8'

services:
  db:
    image: mysql:8.0
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: root123
      MYSQL_DATABASE: trip_db
      MYSQL_USER: trip_user
      MYSQL_PASSWORD: trip_pass
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  server:
    build: ./trip-server
    restart: always
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: "mysql://trip_user:trip_pass@db:3306/trip_db"
      JWT_SECRET: <随机字符串>
      JWT_EXPIRES_IN: 7d
      PORT: 3000
      CORS_ORIGIN: https://your-domain.com
      MODEL_PROVIDER: DEEPSEEK
      DEEPSEEK_API_KEY: sk-your-key
      DEEPSEEK_BASE_URL: https://api.deepseek.com/v1
      DEEPSEEK_MODEL: deepseek-chat
      NODE_ENV: production
    ports:
      - "3000:3000"

  front:
    build: ./trip-front
    restart: always
    depends_on:
      - server
    ports:
      - "80:80"
      - "443:443"

volumes:
  mysql_data:
```

### `trip-server/Dockerfile`

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --production
RUN npx prisma generate

COPY . .
RUN npm run build

EXPOSE 3000
CMD ["node", "dist/index.js"]
```

### `trip-front/Dockerfile`

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### `trip-front/nginx.conf`

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://server:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 部署

```bash
# 在服务器上
git clone <你的仓库>
cd trip-ai
docker compose up -d

# 初始化数据库
docker compose exec server npx prisma db push
```

---

## 域名与 DNS

无论选哪种方案，域名流程一致：

1. **购买域名**：阿里云 / 腾讯云 / Namecheap / Cloudflare
2. **DNS 解析**：

   | 记录类型 | 主机记录 | 记录值 | 说明 |
   |---|---|---|---|
   | A | `@` | 服务器 IP | 根域名 → 服务器 |
   | A | `www` | 服务器 IP | www 子域名 |
   | CNAME | `@` | zeabur 提供的域名 | 如果用 PaaS |

3. **TTL**：600 秒（调试时可设为 60）
4. **生效时间**：修改后通常 1-10 分钟

如果使用 Cloudflare 管理 DNS，还可以开启 CDN + DDoS 防护。

---

## 安全清单

- [x] **HTTPS** — Let's Encrypt / Cloudflare / PaaS 内置
- [x] **JWT_SECRET** — 不小于 32 位随机字符串，无硬编码
- [x] **数据库** — 单独用户、强密码、非 root
- [x] **端口隔离** — Nginx 只暴露 80/443，3000 仅在内部访问
- [x] **防火墙** — ufw 仅开放 22/80/443
- [x] **自动更新** — `sudo apt unattended-upgrades`
- [x] **日志轮转** — PM2 自带，Nginx 默认
- [x] **Rate Limiting** — 已内置（15 分钟 10 次）
- [x] **密钥管理** — `.env` 不在 git 中，服务器上手动创建

---

## 更新部署

```bash
# VPS 方案
cd /var/www/trip
git pull origin main

# 后端
cd trip-server
npm install --production
npx prisma generate
npm run build
pm2 restart trip-server

# 前端
cd ../trip-front
npm install
npm run build
# Nginx 自动使用新文件，无需重启

# PaaS 方案
# 推送到 GitHub 主分支即可自动部署
```
