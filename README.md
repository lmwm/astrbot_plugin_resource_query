# 资源查询插件 (astrbot_plugin_resource_query)

多平台资源查询 AstrBot 插件，采用「一个功能一个模块」的模块化架构。

## 快速开始

1. **安装**：AstrBot WebUI → 插件管理 → 安装 `astrbot_plugin_resource_query`（或从本仓库安装）。
2. **开模块**：插件配置界面里按需开关 `modules.mimo_enabled`（MiMo 用量）、`modules.wasu_enabled`（华数流量话费）、`modules.jm_enabled`（JM 下载，仅私聊）、`modules.update_enabled`（自我更新）。关闭的模块不会加载，其指令与配置页一并隐藏。
3. **配账号**：打开插件管理页面 → 对应模块页 → 添加账号 → 点「测试」验证 → 保存。凭据填法与注意事项见下方[首次使用](#首次使用)。
4. **开始用**：

| 指令 | 说明 |
|------|------|
| `/query` | 显示帮助 |
| `/mimo` · `/mimo <序号或名称>` | 查询 MiMo 余额与用量 |
| `/wasu` · `/wasu <名称>` | 查询华数流量、通话、余额 |
| `/jm <漫画ID>` | 下载漫画（**仅私聊**） |
| `/query update` | 检查并更新插件自身（总是强制重装） |

> 出问题时先查 AstrBot 日志（`data/logs/`），或到本仓库提 Issue。

## 功能模块

| 模块 | 标识 | 功能 | 账号 | 模板 |
|------|------|------|------|------|
| 小米 MiMo | `mimo` | 余额、Token 用量、费用、限额查询 | 多账号 | 支持 |
| 华数广电 | `wasu` | 流量、通话、余额查询 | 多账号 | 支持 |
| JMComic | `jm` | 漫画下载（仅私聊） | — | 支持（消息模板） |
| 插件更新 | `update` | 从 GitHub 检查并更新插件自身 | — | 支持（消息模板） |

## 架构设计

```
main.py                     插件入口：只做「注册 + 分发」
  └── core/                 核心框架层
        ├── module.py       ModuleBase：统一的模块契约
        ├── accounts.py     AccountStore：账号增删改
        ├── config_store.py ConfigStore：模块配置读写
        ├── registry.py     模块注册中心
        ├── web.py          GlobalWebApi：Views 全局接口
        ├── commands.py     参数解析与帮助文本
        └── result.py       QueryResult：统一的模板渲染
  └── modules/              功能模块层（每个功能一个包）
        ├── mimo/           MiMo 查询
        ├── wasu/           华数查询
        ├── jm/             JM 下载（module / service / option / paths / cache）
        └── update/         插件更新
  └── common/               通用工具层：路径、文件读写、YAML 解析与写入
  └── views/template-editor/  管理界面（schema 驱动，单文件入口，脚本内联）
  └── .astrbot-plugin/i18n/   视图元数据（标题 / 描述）
```

### 设计原则

1. **模块自治**：每个模块管理自己的配置、账号、模板、查询与指令
2. **模块隔离**：模块之间不直接依赖，需要协作时通过注册中心按名称取用
3. **契约统一**：所有模块继承 `ModuleBase`，实现同一套接口
4. **界面驱动**：Views 按模块声明的 schema 自动渲染，新增模块无需改前端

## 指令

| 指令 | 说明 |
|------|------|
| `/query` | 显示帮助信息 |
| `/query <模块名> [参数]` | 分发到指定模块，如 `/query mimo ls` |
| `/query update` | 检查并更新插件（总是强制重装） |
| `/mimo` | 查询所有 MiMo 账号 |
| `/mimo <序号或名称>` | 查询指定 MiMo 账号 |
| `/mimo ls` / `/mimo del <名称>` | 列出 / 删除 MiMo 账号 |
| `/mimo otp <验证码>` | 提交登录短信验证码 |
| `/wasu` / `/wasu <名称>` | 查询全部 / 指定华数账号 |
| `/wasu ls` / `/wasu del <名称>` | 列出 / 删除华数账号 |
| `/jm <漫画ID>` | 下载漫画（**仅私聊**） |
| `/jm -F <漫画ID>` | `-F`（不区分大小写）忽略已下载内容，强制重新下载 |
| `/jm LS` | `LS`（不区分大小写）查看当前下载任务与章节页数进度 |

模块被禁用时，其指令会提示「模块未启用」。

## 配置

配置分成两层，各司其职。

### 1. AstrBot 原生配置（插件配置界面）

只放**模块启用开关**，关闭的模块不会加载，其指令与 Views 配置页一并隐藏：

| 配置项 | 说明 | 默认 |
|--------|------|------|
| `modules.mimo_enabled` | 启用 MiMo 查询 | 开 |
| `modules.wasu_enabled` | 启用华数查询 | 开 |
| `modules.jm_enabled` | 启用 JM 下载 | 开 |
| `modules.update_enabled` | 启用插件更新 | 开 |

### 2. 插件 Views（管理界面）

每个模块的配置在各自的页面中管理，保存在插件数据目录，重装插件不会丢失：

```
plugin_data/astrbot_plugin_resource_query/
├── config/
│   ├── mimo/
│   │   ├── config.json        # 模块设置（只存值）
│   │   └── mimo_<名称>.json   # 账号
│   ├── wasu/
│   │   ├── config.json
│   │   └── <名称>.json        # 账号
│   ├── jm/
│   │   ├── config.json        # 模板 / 任务数
│   │   └── option.yaml         # 下载参数（jmcomic 原生 option，由 Views 维护）
│   └── update/
│       └── config.json        # 代理、重试、自动更新、消息模板
└── JMDownload/                # JM 下载产物（见下）
```

默认值、字段定义（label/type/hint）、默认模板与变量说明写在插件目录的 `modules/<模块>/config.py`；`config.json` 只保存值，缺少的项自动回退默认值，删除该文件即恢复全部默认。旧版本的 `config.yaml` 与 `var_config.json` 会在首次读取时自动迁移为 `config.json` 并删除。

日志统一写入 AstrBot：`data/logs/astrbot.log` 与 WebUI 实时日志，记录带 `[astrbot_plugin_resource_query]` 标记；插件不再创建自己的日志文件。

页面内每个模块按能力显示对应区块：

- **账号管理**（`mimo` / `wasu`）：添加、编辑、删除账号；支持登录与凭据测试的模块会显示相应按钮
- **模块设置**：该模块自己的配置项；JM 的下载参数与「同时下载任务数」都在「模块设置」页
- **消息模板**（`jm` / `update`）：按流程阶段分开的文案，可逐条修改、实时预览并恢复默认；每个模板只能使用该阶段已产生的变量，保存时后端会拒绝不可用变量
- **恢复默认按页生效**：每个配置页的「恢复本页默认」只重置当前页字段，不影响其他页；JM「模块设置」页会同时重置任务数与 `option.yaml` 的表单字段，手工添加的其它键保留
- **模板变量**：变量的中文说明、预览示例值与是否在快捷插入区显示
- 账号编辑窗内可编辑该账号的**消息模板**并实时预览

JM 下载产物位于插件数据目录（`plugin_data/astrbot_plugin_resource_query/`）下。
命名规则统一：图片目录恒为 `JM<ID>-P<章节序号:03>-<标题>/`，单章节本子的序号是
`P001`；`info.json` 放在 `JM <ID>/` 根：

```
JMDownload/
└── JM <ID>/                          # 第一层目录带空格
    ├── JM<ID>-P001-<名称>/           # 图片目录（单章节也只有这一个）
    │   ├── 00001.webp
    │   └── 00002.webp …
    ├── JM<ID>-P002-<名称>/           # 多章节时逐章递增
    │   └── 00001.webp …
    └── info.json                     # 漫画信息缓存 + 下载完成标记
```

> **`info.json`（schema 2）是每部漫画的权威档案**：保存标题、作者、标签、总页数，以及
> `chapters` 列表——每章的 `id / index / name / pages / images / downloaded`。文件完整时
> `/jm` 直接读它、不再联网；文件缺失或为旧格式时从站点拉取并生成；`-F` 会强制重建并清除
> 下载标记。页数只预取前 5 章，其余章节在下载完成后补齐实际页数。

> 旧版本把下载内容放在 AstrBot 数据根目录的 `JMDownload/` 下（目录名为 `JM<ID>`）；
> 升级后会自动搬移到新位置并给第一层目录加空格。旧版直接堆在根目录的扁平图片
> （`00001.webp` 等）与旧命名的图片目录会在重新下载成功后自动清理。

> **指令流程**：收到指令先回复「正在查询 JM{id}…」→ 查询并发送漫画信息（每章行尾标记
> `[√]` 已下载 / `[×]` 未下载）→ 已下载时这条就是最后一条；未下载时继续下载，完成后
> 再次发送同一条漫画信息（章节行尾全部变为 `[√]`）。多条消息之间固定间隔 1 秒，避免
> 扎堆。`info.json` 完整时查询不联网；缺失或旧格式时从站点拉取生成。已下载判定以下载成功
> 时写入的完成标记为准；没有标记的旧目录按图片数是否达到总页数判定。`-F` 跳过判定、强制
> 重建 `info.json` 并重新下载。

> **漫画信息**：默认发送 `ID  JM{id}`、`{chapter}` 与 `{chapter_summary}`。`{chapter}` 每出现
> 一次依次输出下一章（第 1、2、3…章），模板里写几个就显示几章；超出实际章节数留空。每章
> 一行：`[√]第001章 - 010页 标题（id: 123）`（页数固定 3 位、不足补 0；`[√]` 已下载 /
> `[×]` 未下载，标记在行首与 ID 行左对齐）。单章节本子用 `oname` 优先的简短名（与下载
> 目录名一致），多章节用每章自己的标题；最后一行「共 N 章 · M 页」（页数同样补足 3 位）；
> 章节 ID 也在章节行里。单章节直接用本子总页数，多章节只为前 5 章各请求一次章节详情。
> 其它字段仍可作为模板变量自行添加；旧缓存缺分章页数时单章节会回退到总页数，多章节可用
> `-F` 重下补全。默认模板不使用 emoji 图标，需要图形标记时可用文字或 `【】` 包裹的符号。

> 下载过程**不自动发送进度消息**，需要看进度时发 `/jm LS`，会列出当前任务、章节页数与
> 已用时。插件不再生成或发送 PDF，只保留站点原图；重新下载成功后会清理旧 PDF 与旧版
> 目录结构。

### JM 下载参数（option.yaml）

JM 的下载参数写进 jmcomic 原生的 `option.yaml`，由库自己解释全部字段。文件在
`config/jm/option.yaml`（与 `config.json` 同目录），首次加载时自动生成；**Views 的
「JM 下载 → 模块设置」页直接编辑它**：下载日志、目录繁简转换、并发、缓存、解码、
图片后缀、客户端类型、重试、超时、代理、Cookie 都会写入对应键，
`config.json` 不再保存这些下载参数；「同时下载任务数」属插件调度，仍存在 `config.json`。

```yaml
log: true                     # 输出 jmcomic 下载日志（写入 AstrBot 日志）
dir_rule:
  rule: Bd/JM{Aid}-P{Pindex:03}-{title}   # 固定值，加载时强制写回
  base_dir: plugin_data/astrbot_plugin_resource_query/JMDownload   # 固定值，相对 AstrBot 数据根
  normalize_zh: zh-cn           # 目录名统一为简体（zh-tw 繁体，留空不转换）
download:
  cache: true
  image: {decode: true, suffix: null}   # suffix 为 null 时保留站点原图（webp/jpg）
  threading: {image: 10, photo: 2}
client:
  impl: api
  retry_times: 3
  timeout: 20
  postman:
    meta_data:
      proxies: ...    # 留空时不写，沿用库默认（系统代理）
      cookies: ...
```

**下载路径与目录规则是固定值**，不提供配置项：

- 下载根：`data/plugin_data/<插件目录名>/JMDownload`（插件改名后自动跟随）；
- 目录规则：`Bd/JM{Aid}-P{Pindex:03}-{title}`，每个章节一个图片目录，单章节也是
  `JM<ID>-P001-<标题>/`；图片文件名保持站点原样（`00001.webp`）；章节序号来自站点的
  `photo_index`，不保证从 1 开始（站点给 81 就是 `P081`）。

`option.yaml` 里的 `dir_rule.base_dir` / `dir_rule.rule` 若被手工改动，加载时会强制写回固定值
并记日志，避免改坏后找不到旧文件。`base_dir` 写的是展开插件名后的实际值
（`plugin_data/astrbot_plugin_resource_query/JMDownload`）；6.27.0 及更早版本误生成的
`plugin_data/{plugin}/` 空目录会在加载时自动清理。`{title}` 由模块解析：优先含中文的
`oname`，并按「目录繁简转换」统一简繁（多章节本子首章 `Ptitle` 常为空，所以不用 `{Ptitle}`）。

目录名里的空格会保留（jmcomic 只替换 Windows 非法字符 `\ / : * ? " < > |`，不动空格）。

表单没有覆盖的键（`client.domain`、`plugins` 等）仍可手工加进文件并保留；
可用的全部字段见 jmcomic 的
[配置文件文档](https://jmcomic.readthedocs.io/zh-cn/latest/option_file_syntax/)。
默认模板在 `modules/jm/option.default.yaml`（唯一默认值来源）；删除
`config/jm/option.yaml` 后重载会按它重新生成。

> 图片按站点原格式（多为 webp/jpg）保留在图片目录，插件不做转码与 PDF 合成。
> 缓存优先读 `info.json`，不请求站点。

> 插件的运行依赖由**模块声明、插件初始化时统一检查**：每个模块用 `required_packages`（导入名 → 安装名）声明，`initialize()` 汇总后若有缺失、**或 requirements.txt 里 `==` 锁定的版本与已装版本不一致**，就用 AstrBot 的 `pip_installer` 按插件 `requirements.txt` 补装一次（AstrBot 本身只在安装插件、它自己的更新、失败恢复、导入报 `ModuleNotFoundError` 时装依赖，普通重载与本插件自更新不触发；pip 的 `only-if-needed` 策略也不会升级已满足下限的旧包）。JM 声明 `jmcomic`、`Pillow`、`zhconv`（目录繁简转换），并把 `jmcomic` 锁定为 `2.7.11`；补装失败时 `/jm` 会按「缺少运行依赖」模板提示（Views 可改），日志记录缺失模块名。以后新增模块只需声明自己的依赖。

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
    "demo": DemoModule,  # 新增
}
```

3. 在 `_conf_schema.json` 的 `modules` 下加一个 `demo_enabled` 开关。

完成后：模块的配置页、导航标签、配置持久化都会自动出现，**无需改动前端代码**。

需要账号管理就覆盖 `supports_accounts = True` 并实现 `get_account_fields()`；
需要消息模板则覆盖 `supports_template = True`，并在模块的 `config.py` 提供默认模板与变量说明
（或设置类属性 `default_template` / `variable_defaults`）。

## 项目结构

```
astrbot_plugin_resource_query/
├── main.py                  # 插件入口（注册与分发）
├── metadata.yaml            # 插件元数据
├── _conf_schema.json        # AstrBot 原生配置（模块开关）
├── requirements.txt         # 依赖声明
├── core/                    # 核心框架层
│   ├── module.py            # 模块基类
│   ├── accounts.py          # 账号存储
│   ├── config_store.py      # 模块配置存储
│   ├── registry.py          # 注册中心
│   ├── web.py               # Views 全局接口
│   ├── commands.py          # 参数解析与帮助文本
│   └── result.py            # 查询结果基类
├── common/                  # 通用工具层
│   ├── utils.py             # 路径与文件读写
│   ├── module_log.py        # 模块日志（统一写 AstrBot）
│   └── yaml_utils.py        # 旧 YAML 解析（仅供配置迁移）
├── modules/                 # 功能模块层
│   ├── mimo/                # module / manager / account / query / result / utils / config.py
│   ├── wasu/                # module / result / constants / utils / config.py
│   ├── jm/                  # module / service / paths / cache / models / utils / config.py
│   └── update/              # module / updater / schedule / config.py
├── views/template-editor/   # 管理界面（单文件入口，脚本内联）
│   └── index.html
├── .astrbot-plugin/i18n/    # 视图元数据（zh-CN / en-US 的标题与描述）
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
