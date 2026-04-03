# TinyLLM Platform - AI模型微调与部署平台

## 项目简介

TinyLLM Platform 是一个功能完整的AI模型微调与部署平台，支持用户上传训练数据、微调自己的大语言模型，并提供分布式训练和推理服务。平台采用三层架构设计，包括后端服务、前端界面和设备客户端，支持普通模式和FRP内网穿透模式，让用户可以轻松管理和部署自己的AI模型。

## 核心功能

### 用户端功能
- 用户注册与登录（支持邮箱验证码登录和密码登录）
- 数据集管理：上传JSONL格式的训练数据
- 训练任务：创建微调任务，支持多种基础模型（如Qwen、Llama等）
- 模型管理：查看、删除训练完成的模型
- 部署管理：部署模型，提供OpenAI兼容的API接口
- 积分系统：通过充值和签到获取积分，用于训练和部署
- 社区功能：分享模型和API，与其他用户交流

### 管理端功能
- 用户管理：查看和管理注册用户
- 设备管理：监控和管理连接的训练设备
- 任务管理：查看和管理训练任务状态
- 部署管理：查看和管理模型部署情况
- 日志查看：查看系统运行日志

## 系统架构

平台采用三层架构设计：

### 1. 后端服务
- 技术栈：FastAPI + SQLAlchemy + MySQL
- 主要功能：
  - RESTful API接口
  - WebSocket实时通信（与设备端通信）
  - 用户认证与授权（JWT Token）
  - 数据库管理
  - 任务调度与分发
  - OpenAI API转发

### 2. 前端界面
- 技术栈：Vue.js 3 + Element Plus
- 主要功能：
  - 用户友好的Web界面
  - 数据集上传与管理
  - 训练任务创建与监控
  - 模型部署与管理
  - API测试与调试
  - 社区交流平台

### 3. 设备客户端
- 技术栈：Python + WebSocket + Transformers + PyTorch
- 主要功能：
  - 自动注册到服务端
  - 接收训练和推理任务
  - 执行模型微调
  - 启动API服务
  - 心跳保活与状态上报

## 设备端运行模式

设备客户端支持两种运行模式：

### 普通模式
- 适用场景：设备有公网IP或在内网环境中
- 特点：
  - 直接使用设备本地地址提供服务
  - 配置简单，无需额外服务
  - 适合局域网或公网环境

启动命令：
```bash
python client.py --server http://localhost:8000 --name device-1 --port 9000 --mode normal
```

### FRP内网穿透模式
- 适用场景：设备在内网环境，需要通过公网访问
- 特点：
  - 通过FRP服务实现内网穿透
  - 支持远程访问部署的模型
  - 自动配置FRP客户端

启动命令：
```bash
python client.py --server http://localhost:8000 --name device-1 --port 9000 --mode frp --frp_server 38.150.4.149:7000
```

FRP配置说明：
- `frp_server`: FRP服务器地址（如：38.150.4.149:7000）
- 远程端口计算：32000 + deployment_id
- 例如：部署ID为3，远程端口为32003，访问地址为 `http://38.150.4.149:32003/v1`

## 快速开始

### 环境要求
- Python 3.8+
- MySQL 5.7+ 或 8.0+
- CUDA 11.8+ (设备端需要GPU)

### 1. 安装依赖

服务端依赖：
```bash
pip install -r requirements.txt
```

设备端依赖：
```bash
cd device_client
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
python backend/models/init_db.py
```

这将创建所有必要的表，并创建管理员账号：
- 用户名: `admin`
- 密码: `admin123`

### 3. 启动后端服务

```bash
python main.py
```

服务将在 `http://0.0.0.0:8000` 启动

### 4. 启动设备客户端

普通模式：
```bash
cd device_client
python client.py --server http://localhost:8000 --name device-1 --port 9000 --mode normal
```

FRP模式：
```bash
cd device_client
python client.py --server http://localhost:8000 --name device-1 --port 9000 --mode frp --frp_server 38.150.4.149:7000
```

## 使用指南

### 用户端使用流程

1. 访问平台：打开浏览器访问 `http://localhost:8000`
2. 注册账号：填写邮箱和密码，通过验证码验证
3. 上传数据集：上传JSONL格式的训练数据
4. 创建训练任务：
   - 选择基础模型（如Qwen、Llama等）
   - 选择数据集
   - 设置训练参数（epochs等）
   - 提交任务
5. 等待训练完成：实时查看训练进度和日志
6. 部署模型：
   - 选择训练完成的模型
   - 选择在线设备
   - 设置部署时长
   - 提交部署
7. 使用API：
   - 获取API地址和密钥
   - 使用OpenAI兼容的API调用模型

### 管理端使用流程

1. 使用管理员账号登录（admin/admin123）
2. 访问管理后台：`http://localhost:8000/admin`
3. 管理功能：
   - 查看和管理用户
   - 监控设备状态
   - 查看训练任务
   - 管理模型部署
   - 查看系统日志

### 设备端使用流程

1. 启动设备客户端
2. 自动注册到服务端
3. 保持在线状态
4. 自动接收和处理任务
5. 上报任务进度和状态

## API文档

部署模型后，可以使用OpenAI兼容的API：

```python
import openai

openai.api_base = "http://localhost:8000/v1"
openai.api_key = "YOUR_TOKEN"

response = openai.ChatCompletion.create(
    model="your-model-name",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

## 目录结构

```
tinlyllmWeb/
├── main.py                 # 主服务端入口
├── requirements.txt         # 服务端依赖
├── backend/
│   ├── config.py          # 配置文件
│   ├── models/
│   │   ├── database.py    # 数据库模型
│   │   └── init_db.py    # 数据库初始化
│   ├── api/
│   │   ├── auth.py       # 认证API
│   │   ├── user.py       # 用户API
│   │   ├── dataset.py    # 数据集API
│   │   ├── training.py   # 训练API
│   │   ├── model.py      # 模型API
│   │   ├── deployment.py # 部署API
│   │   ├── admin.py      # 管理API
│   │   ├── device.py     # 设备API
│   │   ├── openai.py     # OpenAI API转发
│   │   ├── community.py  # 社区API
│   │   └── payment.py    # 支付API
│   ├── services/
│   │   ├── user_service.py
│   │   ├── dataset_service.py
│   │   ├── training_service.py
│   │   ├── model_service.py
│   │   ├── deployment_service.py
│   │   ├── device_service.py
│   │   └── email_service.py
│   └── utils/
│       ├── auth.py
│       ├── jwt.py
│       └── response.py
├── frontend/
│   ├── templates/
│   │   ├── login.html   # 登录页面
│   │   ├── app.html     # 用户主界面
│   │   ├── admin.html   # 管理后台
│   │   └── community.html # 社区页面
│   └── static/
│       ├── css/
│       │   ├── style.css
│       │   ├── app.css
│       │   └── admin.css
│       └── js/
│           ├── login.js
│           ├── app.js
│           ├── admin.js
│           └── community.js
└── device_client/
    ├── client.py        # 设备客户端主程序
    ├── fine_tune.py     # 模型微调脚本
    ├── apiServer.py     # API服务器
    └── frpc.exe        # FRP客户端
```

## 配置说明

编辑 `backend/config.py` 修改配置：

```python
# 数据库配置
DATABASE_HOST = "127.0.0.1"
DATABASE_PORT = 3306
DATABASE_USER = "root"
DATABASE_PASSWORD = "root"
DATABASE_NAME = "tinyllm"

# JWT配置
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

# 积分配置
INITIAL_POINTS = 10.0
CHECKIN_REWARD = 1.0
TRAINING_COST_MIN = 30.0
TRAINING_COST_MAX = 100.0
DEPLOY_COST_PER_DAY_MIN = 2.0
DEPLOY_COST_PER_DAY_MAX = 10.0

# CORS配置
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "http://38.150.4.149:39999",
    "http://38.150.4.149:*",
    "*"
]

# 设备配置
DEVICE_HEARTBEAT_INTERVAL = 30
API_PORT_START = 8001
API_PORT_END = 8999
```

## 积分规则

- 初始积分：10积分
- 每日签到：1积分
- 训练模型：30-100积分/次
- 部署模型：2-10积分/天
- 充值：支持微信支付充值

## 注意事项

1. 确保MySQL服务已启动
2. 设备客户端需要GPU支持
3. 训练数据必须是JSONL格式
4. 部署模型需要足够的积分
5. 设备离线时，相关部署会标记为不可用
6. FRP模式需要FRP服务器支持

## 技术栈

- **后端**：FastAPI + SQLAlchemy + MySQL + WebSocket
- **前端**：Vue.js 3 + Element Plus
- **设备端**：Python + WebSocket + Transformers + PEFT + PyTorch
- **AI框架**：Transformers + PEFT + PyTorch
- **内网穿透**：FRP

## 常见问题

### Q: 如何切换设备端运行模式？
A: 使用 `--mode` 参数指定模式：`normal`（普通模式）或 `frp`（FRP模式）

### Q: FRP模式如何配置？
A: 使用 `--frp_server` 参数指定FRP服务器地址，如：`38.150.4.149:7000`

### Q: 如何访问FRP部署的模型？
A: 访问地址为 `http://FRP服务器IP:32000+部署ID/v1`

### Q: 训练任务一直处于pending状态？
A: 确保至少有一个设备客户端在线并注册到服务端

### Q: 如何查看训练日志？
A: 在用户界面点击训练任务的"查看日志"按钮

## 许可证

本项目仅供学习和研究使用。

## 联系方式

如有问题或建议，请联系：2151335401@qq.com
