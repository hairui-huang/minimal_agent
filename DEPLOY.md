# 部署指南

## 架构

```
┌─────────────────────┐         ┌─────────────────────┐
│  Cloudflare Pages   │  ──→    │  Railway (Python)    │
│  前端 index.html     │  API    │  FastAPI 后端         │
│  免费静态托管         │         │  DeepSeek API 调用    │
└─────────────────────┘         └─────────────────────┘
```

## 第一步：部署后端到 Railway

### 1.1 安装 Railway CLI

```bash
npm install -g @railway/cli
```

或用 brew：

```bash
brew install railway
```

### 1.2 登录

```bash
railway login
```

### 1.3 初始化项目

```bash
cd D:/minimal-agent-runtime
railway init
# 选择 "Empty Project"
# 输入项目名: minimal-agent-runtime
```

### 1.4 设置环境变量

```bash
railway variables set DEEPSEEK_API_KEY=sk-你的key
railway variables set DEEPSEEK_API_BASE=https://api.deepseek.com
railway variables set DEEPSEEK_MODEL=deepseek-chat
```

### 1.5 部署

```bash
railway up
```

### 1.6 获取后端 URL

```bash
railway status
# 记下输出的 URL，类似: https://minimal-agent-runtime-xxxx.up.railway.app
```

或在 Railway Dashboard 中查看。

---

## 第二步：部署前端到 Cloudflare Pages

### 2.1 安装 Wrangler CLI

```bash
npm install -g wrangler
```

### 2.2 登录 Cloudflare

```bash
wrangler login
```

### 2.3 创建 Pages 项目

```bash
wrangler pages project create minimal-agent-runtime
```

### 2.4 部署前端

```bash
cd D:/minimal-agent-runtime
wrangler pages deploy public --project-name minimal-agent-runtime
```

### 2.5 访问

部署成功后会给你一个 URL，类似：

```
https://minimal-agent-runtime.pages.dev
```

打开后在 URL 后面加上后端地址：

```
https://minimal-agent-runtime.pages.dev?api=https://minimal-agent-runtime-xxxx.up.railway.app
```

---

## 本地开发

```bash
# 终端 1：启动后端
cd D:/minimal-agent-runtime
python web.py

# 终端 2：或直接用 CLI
python main.py
```

浏览器打开 http://localhost:8000

---

## 更新部署

### 更新后端

```bash
cd D:/minimal-agent-runtime
railway up
```

### 更新前端

```bash
cp index.html public/index.html
wrangler pages deploy public --project-name minimal-agent-runtime
```

---

## 常见问题

### Q: 前端显示"连接失败"

A: 检查 URL 参数 `?api=xxx` 是否正确，后端是否在运行。

### Q: CORS 错误

A: 后端已配置 `allow_origins=["*"]`，如果仍有问题检查 Railway 日志。

### Q: Railway 部署失败

A: 检查 `requirements.txt` 是否完整，`Procfile` 是否正确。
