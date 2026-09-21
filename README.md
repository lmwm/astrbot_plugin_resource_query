# 资源查询插件 (astrbot_plugin_resource_query)

多平台资源查询 AstrBot 插件，采用「一个功能一个模块」的模块化架构。

## 功能模块

| 模块 | 标识 | 功能 | 账号 | 模板 |
|------|------|------|------|------|
| 小米 MiMo | `mimo` | 余额、Token 用量、费用、限额查询 | 多账号 | 支持 |
| 华数广电 | `wasu` | 流量、通话、余额查询 | 多账号 | 支持 |
| JMComic | `jm` | 漫画下载并生成 PDF（仅私聊） | — | — |
| 插件更新 | `update` | 从 GitHub 检查并更新插件自身 | — | — |

## 架构设计

```
main.py                     插件入口：只做「注册 + 分发」
  └── core/                 核心框架层
        ├── module.py       ModuleBase：统一的模块契约
        ├── registry.py     模块注册中心
        ├── manager.py      总管理器：账号汇总 / 页面 schema 汇总
        └── result.py       QueryResult：统一的模板渲染
  └── modules/              功能模块层（每个功能一个包）
        ├── mimo/           MiMo 查询
        ├── wasu/           华数查询
        ├── jm/             JM 下载（downloader 适配层 + core 下载核心）
        └── update/         插件更新
  └── common/               通用工具层：路径、文件读写、YAML 解析
  └── pages/template-editor/  管理界面（schema 驱动，2 个文件）
```

### 设计原则

1. **模块自治**：每个模块管理自己的配置、账号、模板、查询与指令
2. **模块隔离**：模块之间不直接依赖，需要协作时通过注册中心按名称取用
3. **契约统一**：所有模块继承 `ModuleBase`，实现同一套接口
4. **界面驱动**：Pages 按模块声明的 schema 自动渲染，新增模块无需改前端

## 指令

| 指令 | 说明 |
|------|------|
| `/query` | 显示帮助信息 |
| `/query <模块名> [参数]` | 分发到指定模块，如 `/query mimo ls` |
| `/query update` | 检查并更新插件 |
| `/mimo` | 查询所有 MiMo 账号 |
| `/mimo <序号或名称>` | 查询指定 MiMo 账号 |
| `/mimo ls` / `/mimo del <名称>` | 列出 / 删除 MiMo 账号 |
| `/mimo otp <验证码>` | 提交登录短信验证码 |
| `/wasu` / `/wasu <名称>` | 查询全部 / 指定华数账号 |
| `/wasu ls` / `/wasu del <名称>` | 列出 / 删除华数账号 |
| `/jm <漫画ID> [redownload]` | 下载漫画 PDF（仅私聊） |

模块被禁用时，其指令会提示「模块未启用」。

## 配置

配置分成两层，各司其职。

### 1. AstrBot 原生配置（插件配置界面）

只放**模块启用开关**，关闭的模块不会加载，其指令与 Pages 配置页一并隐藏：

| 配置项 | 说明 | 默认 |
|--------|------|------|
| `modules.mimo_enabled` | 启用 MiMo 查询 | 开 |
| `modules.wasu_enabled` | 启用华数查询 | 开 |
| `modules.jm_enabled` | 启用 JM 下载 | 开 |
| `modules.update_enabled` | 启用插件更新 | 开 |

### 2. 插件 Pages（管理界面）

每个模块的配置在各自的页面中管理，保存在插件数据目录，重装插件不会丢失：

```
plugin_data/astrbot_plugin_resource_query/config/
├── mimo/
│   ├── config.json        # 模块设置（默认设备标识 / User-Agent）
│   ├── var_config.json    # 模板变量配置
│   └── mimo_<名称>.json   # 账号
├── wasu/
│   ├── config.json        # 模块设置（接口地址）
│   ├── var_config.json
│   └── <名称>.json        # 账号
├── jm/
│   └── config.json        # 下载配置（并发 / 代理 / Cookie / 超时 / 重试等）
└── update/
    └── config.json        # GitHub 代理、重试次数
```

页面内每个模块按能力显示对应区块：

- **账号管理**（`mimo` / `wasu`）：添加、编辑、删除账号；支持登录与凭据测试的模块会显示相应按钮
- **模块设置**：该模块自己的配置项
- **模板变量**：变量的中文说明、预览示例值与是否在快捷插入区显示
- 账号编辑窗内可编辑该账号的**消息模板**并实时预览

JM 下载产物位于 AstrBot 数据目录：

```
JMDownload/
├── cache/<漫画ID>/     # 下载的图片与原信息
└── ready/JM<ID>-<名称>.pdf   # 生成的 PDF
```

> 兼容旧版结构：`JMDownload/<jmID>/*.pdf` 也会被识别为已下载。

## 首次使用

### MiMo

1. WebUI → 插件管理 → 资源查询 → 打开管理页面
2. 「MiMo 查询」页 → 添加账号 → 填写小米账号与密码
3. 点「测试」验证；若提示需要验证码，填入短信验证码后再点「测试」
4. 点「保存」

凭据优先级：`serviceToken` → `passToken` → 账号密码（自动降级）。

### 华数广电

1. 从华数微信小程序获取 `user_key`、`token`、`phone`、`sign`
2. 「华数查询」页 → 添加账号 → 填入上述字段
3. 点「测试」验证凭据是否有效（token 会过期，失效时测试会直接提示）
4. 点「保存」

## 扩展开发：新增一个功能模块

1. 在 `modules/` 下新建包，实现模块类：

```python
from ...core.module import ModuleBase


class DemoModule(ModuleBase):
    """示例模块"""

    @property
    def module_name(self) -> str:
        return "demo"

    @property
    def module_title(self) -> str:
        return "示例功能"

    @property
    def module_icon(self) -> str:
        return "▧"

    def get_config_fields(self) -> list[dict]:
        return [{"key": "api_key", "label": "接口密钥", "type": "password"}]

    def get_commands(self) -> list[dict]:
        return [{"name": "demo", "desc": "示例指令"}]

    async def handle_command(self, command, args, event):
        yield event.plain_result("示例模块已就绪")
```

2. 在 `main.py` 的 `_MODULE_CLASSES` 中登记：

```python
_MODULE_CLASSES = {
    "mimo": MimoModule,
    "wasu": WasuModule,
    "jm": JMModule,
    "update": UpdateModule,
    "demo": DemoModule,      # 新增
}
```

3. 在 `_conf_schema.json` 的 `modules` 下加一个 `demo_enabled` 开关。

完成后：模块的配置页、导航标签、配置持久化都会自动出现，**无需改动前端代码**。

需要账号管理就覆盖 `supports_accounts = True` 并实现 `get_account_fields()`；
需要消息模板则覆盖 `supports_template = True` 并实现 `get_default_template()` 与 `get_var_definitions()`。

## 项目结构

```
astrbot_plugin_resource_query/
├── main.py                  # 插件入口（注册与分发）
├── metadata.yaml            # 插件元数据
├── _conf_schema.json        # AstrBot 原生配置（模块开关）
├── requirements.txt         # 依赖声明
├── core/                    # 核心框架层
│   ├── module.py            # 模块基类
│   ├── registry.py          # 注册中心
│   ├── manager.py           # 总管理器
│   └── result.py            # 查询结果基类
├── common/                  # 通用工具层
│   ├── utils.py             # 路径与文件读写
│   └── yaml_utils.py        # 简易 YAML 解析
├── modules/                 # 功能模块层
│   ├── mimo/                # module / manager / account / query / result / utils / config.yaml
│   ├── wasu/                # module / result / constants / utils / config.yaml
│   ├── jm/                  # module / downloader / utils + core(manager / models)
│   └── update/              # module / updater
├── pages/template-editor/   # 管理界面（schema 驱动）
│   ├── index.html
│   └── core.js
└── http_utils.py            # HTTP 工具（Cookie / opener / 代理 / 重试）
```

## MiMo 登录流程

参考 [MiService](https://github.com/Yonsm/MiService) 的 `miaccount.py` 实现：

```
1. serviceLogin      → 获取 qs/sid/_sign/callback
2. serviceLoginAuth2 → 提交账号密码（MD5）
3. 若需 OTP          → 缓存在线会话，触发短信验证码
4. PassToken         → STS 换取 serviceToken
```

## 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)。
