# 资源查询插件 (astrbot_plugin_resource_query)

多平台资源查询 AstrBot 插件，支持小米 MiMo 用量查询、华数广电流量/话费查询等。

## 支持平台

| 平台 | 功能 | 状态 |
|------|------|------|
| 小米 MiMo | 余额、Token 用量、费用、限额查询 | ✅ 已支持 |
| 华数广电 | 流量、通话、余额查询 | ✅ 已支持 |

## 功能特性

### MiMo 平台
- 查询余额、Token 用量、费用和限额
- 多账号支持，每个账号可独立配置
- 支持 serviceToken / passToken / 账号密码三级凭据自动降级
- 凭据自动持久化，重启后无需重新登录
- 支持 OTP 验证码验证（通过 WebUI Pages）

### 华数广电
- 查询流量使用情况
- 查询通话分钟数
- 查询话费余额
- 支持多账号管理

### JMComic 下载
- 下载 JMComic 漫画并生成 PDF
- 仅支持私聊使用
- PDF 文件统一存放在 `JMDownload/PDF/` 目录
- PDF 文件使用规范命名（如 `JM123456-漫画名.pdf`）
- 支持本地缓存，避免重复下载
- 支持下载进度显示
- 可配置 Cookie、代理、超时、重试等参数

## 指令

### 通用指令

| 指令 | 说明 |
|------|------|
| `/query` | 显示帮助信息 |
| `/query update` | 检查并更新插件 |

### MiMo 指令

| 指令 | 说明 |
|------|------|
| `/mimo` | 查询所有 MiMo 账号 |
| `/mimo <名称>` | 查询指定 MiMo 账号 |
| `/mimo ls` | 列出所有 MiMo 账号 |
| `/mimo del <名称>` | 删除指定 MiMo 账号 |
| `/mimo otp <验证码>` | 提交 OTP 验证码 |

### 华数广电指令

| 指令 | 说明 |
|------|------|
| `/wasu` | 查询所有华数账号 |
| `/wasu <序号或名称>` | 查询指定华数账号 |
| `/wasu ls` | 列出所有华数账号 |
| `/wasu del <序号或名称>` | 删除指定华数账号 |

## 首次使用

### MiMo 配置

#### 通过 WebUI Pages 管理界面（推荐）

1. 打开 AstrBot WebUI，进入插件管理页面
2. 点击"添加 MiMo 账号"
3. 填写小米账号和密码
4. 点击"测试"按钮
5. 如果需要 OTP 验证，输入收到的验证码后再次点击"测试"
6. 测试成功后点击"保存"

#### 登录方式说明

MiMo 支持三种登录方式：

| 登录方式 | 说明 |
|----------|------|
| 账号密码 | 输入小米账号和密码，支持 OTP 验证 |
| PassToken | 输入 PassToken 和 User ID |
| ServiceToken | 输入 ServiceToken 和 User ID |

### 华数广电配置

1. 打开华数广电微信小程序
2. 获取 `user_key`、`token`、`phone`、`sign` 参数
3. 在 WebUI Pages 管理界面添加账号

## 配置（WebUI）

### MiMo 全局配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| device_id | 全局设备标识 | wb_MIQUERY000001 |
| ua | 全局 User-Agent | APP/com.xiaomi.mihome... |

### MiMo 账号配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| name | 账号显示名称 | 空（显示账号） |
| account | 小米账号 | 空 |
| password | 小米账号密码 | 空 |
| device_id | 设备标识（留空用全局） | 空 |
| ua | User-Agent（留空用全局） | 空 |
| userId | 用户 ID（自动填入） | 空 |
| passToken | 通行令牌（自动填入） | 空 |
| serviceToken | serviceToken（自动填入） | 空 |

### 华数广电账号配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| name | 账号显示名称 | 空（显示手机号） |
| user_key | User Key | 空 |
| token | Token | 空 |
| phone | 手机号 | 空 |
| sign | 签名 | 空 |

### 其他配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| proxy | GitHub 更新代理 | https://gh-proxy.cn/ |
| update_max_retries | 更新重试次数 | 3 |

## 部署

```bash
# 复制到 AstrBot 插件目录
cp -r astrbot_plugin_resource_query /path/to/AstrBot/data/plugins/

# 重启 AstrBot 或在 WebUI 热重载插件
```

## 扩展开发

本插件采用模块化设计，添加新平台只需：

1. 继承 `BasePlatform` 基类
2. 实现 `query()` 方法
3. 在 `main.py` 中注册新平台

```python
from .base import BasePlatform, QueryResult

class NewPlatform(BasePlatform):
    @property
    def platform_name(self) -> str:
        return "新平台"

    @property
    def platform_icon(self) -> str:
        return "🆕"

    async def query(self, account: dict) -> QueryResult:
        # 实现查询逻辑
        pass
```

## 项目结构

```
astrbot_plugin_resource_query/
├── main.py                  # 插件主入口
├── base.py                  # 基类定义
├── http_utils.py            # HTTP 工具函数
├── updater.py               # 更新模块
├── __init__.py              # 模块初始化
├── requirements.txt         # 依赖声明
├── metadata.yaml            # 插件元数据
├── README.md                # 说明文档
├── CHANGELOG.md             # 更新日志
├── logo.png                 # 插件图标
├── .gitignore               # Git 忽略规则
├── _conf_schema.json        # AstrBot 配置模式
├── common/                  # 通用模块
│   ├── __init__.py          # 模块导出
│   ├── account.py           # 账号管理器
│   └── utils.py             # 通用工具函数
├── mimo/                    # MiMo 平台模块
│   ├── __init__.py          # 模块导出
│   ├── account.py           # 小米账号登录（参考 MiService）
│   ├── manager.py           # MiMo 管理器
│   ├── query.py             # 查询逻辑
│   ├── result.py            # 查询结果格式化
│   ├── exceptions.py        # 异常类定义
│   ├── constants.py         # 常量定义
│   ├── utils.py             # 工具函数
│   ├── config.json          # MiMo 配置文件
│   └── default_template.txt # 默认模板
├── wasu/                    # 华数广电平台模块
│   ├── __init__.py          # 模块导出
│   ├── manager.py           # 华数管理器
│   ├── result.py            # 查询结果格式化
│   ├── constants.py         # 常量定义
│   ├── utils.py             # 工具函数
│   └── default_template.txt # 默认模板
├── jm/                      # JMComic 下载模块
│   ├── __init__.py          # 模块导出
│   ├── downloader.py        # 下载管理器（适配器）
│   ├── constants.py         # 常量定义
│   ├── utils.py             # 工具函数
│   └── core/                # 下载器核心
│       ├── __init__.py      # 核心模块导出
│       ├── manager.py       # JM 管理器
│       ├── models.py        # 数据模型
│       ├── config.py        # 配置管理
│       ├── utils.py         # 核心工具函数
│       ├── README.md        # 核心模块说明
│       ├── cache/           # 缓存管理
│       ├── converters/      # PDF 转换器
│       └── downloaders/     # 下载器实现
└── pages/                   # WebUI Pages
    └── template-editor/
        └── index.html       # 配置管理界面
```

## MiMo 登录流程

MiMo 登录参考 [MiService](https://github.com/Yonsm/MiService) 的 `miaccount.py` 实现。

### 账号密码登录（无 OTP）

```
1. serviceLogin → 获取 qs/sid/_sign/callback
2. serviceLoginAuth2 → 提交账号密码（MD5哈希）
3. 获取 userId/passToken/location/nonce/ssecurity
4. STS → 换取 serviceToken
```

### 账号密码登录（需要 OTP）

```
1. serviceLogin → 获取 qs/sid/_sign/callback
2. serviceLoginAuth2 → 提交账号密码 → 返回 notificationUrl
3. _trigger_otp_send → 发送验证码
   - GET notificationUrl → 建立验证会话
   - GET /identity/list → 获取验证方式
   - GET /identity/auth/verifyPhone → 触发发送
   - POST /identity/auth/sendPhoneTicket → 发送短信
4. 等待用户输入验证码
5. _submit_otp_code → 提交验证码
   - POST /identity/auth/verifyPhone + ticket
   - GET location → 设置认证 cookies
6. serviceLogin → 获取完整认证响应
7. STS → 换取 serviceToken
```

### 凭据优先级

查询时自动降级：
1. serviceToken（最快，直接查询）
2. passToken（自动换取 serviceToken）
3. 账号密码（自动登录，可能需要 OTP）

## 更新日志

- 2025-01: 网络连接测试提交
- 2025-08: 重构 MiMo 登录模块，参考 MiService 实现 OTP 验证流程
