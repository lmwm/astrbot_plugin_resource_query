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
| `/jm <漫画ID>` | 下载漫画并生成 PDF（**仅私聊**） |
| `/query update` | 检查并更新插件自身（总是强制重装） |

> 出问题时先查 AstrBot 日志（`data/logs/`），或到本仓库提 Issue。

## 功能模块

| 模块 | 标识 | 功能 | 账号 | 模板 |
|------|------|------|------|------|
| 小米 MiMo | `mimo` | 余额、Token 用量、费用、限额查询 | 多账号 | 支持 |
| 华数广电 | `wasu` | 流量、通话、余额查询 | 多账号 | 支持 |
| JMComic | `jm` | 漫画下载并生成 PDF（仅私聊） | — | 支持（消息模板） |
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
        ├── jm/             JM 下载（module / service / option / paths / cache / pdf）
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
| `/jm <漫画ID> [redownload]` | 下载漫画 PDF（仅私聊） |

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
│   │   ├── config.json        # 发送 / 模板 / 画质 / 任务数
│   │   └── option.yml         # 下载参数（jmcomic 原生 option，由 Views 维护）
│   └── update/
│       └── config.json        # 代理、重试、自动更新、消息模板
└── JMDownload/                # JM 下载产物（见下）
```

默认值、字段定义（label/type/hint）、默认模板与变量说明写在插件目录的 `modules/<模块>/config.py`；`config.json` 只保存值，缺少的项自动回退默认值，删除该文件即恢复全部默认。旧版本的 `config.yaml` 与 `var_config.json` 会在首次读取时自动迁移为 `config.json` 并删除。

日志统一写入 AstrBot：`data/logs/astrbot.log` 与 WebUI 实时日志，记录带 `[astrbot_plugin_resource_query]` 标记；插件不再创建自己的日志文件。

页面内每个模块按能力显示对应区块：

- **账号管理**（`mimo` / `wasu`）：添加、编辑、删除账号；支持登录与凭据测试的模块会显示相应按钮
- **模块设置**：该模块自己的配置项；JM 的下载参数单独一页「下载参数」，其余在「发送与文件」
- **消息模板**（`jm` / `update`）：按流程阶段分开的文案，可逐条修改、实时预览并恢复默认；每个模板只能使用该阶段已产生的变量，保存时后端会拒绝不可用变量
- **模板变量**：变量的中文说明、预览示例值与是否在快捷插入区显示
- 账号编辑窗内可编辑该账号的**消息模板**并实时预览

JM 下载产物位于插件数据目录（`plugin_data/astrbot_plugin_resource_query/`）下。
命名规则统一：图片目录恒为 `JM<ID>-P<章节序号:03>-<标题>/`，单章节本子的序号是
`P001`；PDF 与 `info.json` 放在 `JM <ID>/` 根：

```
JMDownload/
└── JM <ID>/                          # 第一层目录带空格
    ├── JM<ID>-P001-<名称>/           # 图片目录（单章节也只有这一个）
    │   ├── 00001.webp
    │   └── 00002.webp …
    ├── JM<ID>-P002-<名称>/           # 多章节时逐章递增
    │   └── 00001.webp …
    ├── JM<ID>-<名称>.pdf             # 生成的 PDF
    └── info.json                     # 漫画信息缓存 + 最近一次 PDF 文件名/大小
```

> 旧版本把下载内容放在 AstrBot 数据根目录的 `JMDownload/` 下（目录名为 `JM<ID>`）；
> 升级后会自动搬移到新位置并给第一层目录加空格。旧版直接堆在根目录的扁平图片
> （`00001.webp` 等）与旧命名的图片目录会在重新下载成功后自动清理。

### JM 下载参数（option.yml）

JM 的下载参数写进 jmcomic 原生的 `option.yml`，由库自己解释全部字段。文件在
`config/jm/option.yml`（与 `config.json` 同目录），首次加载时自动生成；**Views 的
「JM 下载 → 下载参数」页直接编辑它**：下载路径、下载日志、目录繁简转换、并发、缓存、
解码、图片后缀、客户端类型、重试、超时、代理、Cookie 都会写入对应键，
`config.json` 不再保存这些下载参数。

```yaml
log: true                     # 输出 jmcomic 下载日志（写入 AstrBot 日志）
dir_rule:
  rule: Bd                      # 运行时替换为按章节数生成的目录规则
  base_dir: plugin_data/astrbot_plugin_resource_query/JMDownload   # 相对 AstrBot 数据根
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

「下载路径」填相对 AstrBot 数据根（`data/`）的目录。输入框显示的是**真实路径**
（如 `plugin_data/astrbot_plugin_resource_query/JMDownload`），配置文件里实际保存
`{plugin}` 占位符，插件改名后自动跟随、无需改配置；填绝对路径时只有在数据根内
才会转成相对，越界或含 `..` 会回退默认并记日志。

**目录与命名规则**：`dir_rule.rule` 在 Views「下载参数 → 目录规则」里配置。**表单里省略
开头的 `Bd/`**，只填后半段（默认 `JM{Aid}-P{Pindex:03}-{title}`），保存时自动补回：

- 每个章节一个图片目录，单章节也是 `JM<ID>-P001-<标题>/`；
- 图片文件名保持站点原样（`00001.webp`）；
- 章节序号来自站点的 `photo_index`，不保证从 1 开始（站点给 81 就是 `P081`）。

可用的占位符：`{title}`（模块解析，优先含中文的 `oname` 并做繁简转换）、章节
`{Pid}`/`{Pindex}`/`{Pname}`/`{Ptitle}`/`{Psort}`、本子 `{Aid}`/`{Aname}`/`{Aoname}`/`{Atitle}`/`{Aauthor}`。
点字段名后的 **「? 可用参数」** 可查看完整字段说明与示例；输入框下方有中文快捷按钮
（如「本子ID-章节-标题」），点击追加对应规则。填 `Bd` 或留空表示图片直接放 `JM <ID>` 根目录。
保存时会校验：未知占位符、Windows 非法字符、空层级、结尾斜杠、层级过多、非数字补零格式
都会被拒绝并提示可用字段。多章节本子的首章 `Ptitle` 常为空，建议用 `{title}` 而不是 `{Ptitle}`。

PDF 名固定 `JM<ID>-<标题>.pdf`，放在 `JM <ID>/` 根目录。目录名与 PDF 名里的空格会保留
（jmcomic 只替换 Windows 非法字符 `\ / : * ? " < > |`，不动空格）。

表单没有覆盖的键（`client.domain`、`plugins` 等）仍可手工加进文件并保留；
可用的全部字段见 jmcomic 的
[配置文件文档](https://jmcomic.readthedocs.io/zh-cn/latest/option_file_syntax/)。
源码里的 `Scripts/gen_option.py` 可按默认值重新生成一份
（`python Scripts/gen_option.py` 写 `modules/jm/option.default.yml`，
`--stdout` 直接打印，`--base-dir` 指定目录）；删除 `config/jm/option.yml` 后重载也会恢复默认。

> 图片按站点原格式（多为 webp）保留在图片目录作为存档；生成 PDF 时才把非 JPEG
> 转码成目标画质（默认 75）。jmcomic 自带的 `img2pdf` 插件不做这层转码，直接嵌入
> webp 会按无损重编码、体积膨胀数倍，所以 PDF 合成仍由本模块完成。
> 缓存命中时只读 `info.json`，不请求站点。

> 插件的运行依赖由**模块声明、插件初始化时统一检查**：每个模块用 `required_packages`（导入名 → 安装名）声明，`initialize()` 汇总后若有缺失、**或 requirements.txt 里 `==` 锁定的版本与已装版本不一致**，就用 AstrBot 的 `pip_installer` 按插件 `requirements.txt` 补装一次（AstrBot 本身只在安装插件、它自己的更新、失败恢复、导入报 `ModuleNotFoundError` 时装依赖，普通重载与本插件自更新不触发；pip 的 `only-if-needed` 策略也不会升级已满足下限的旧包）。JM 声明 `jmcomic`、`img2pdf`、`Pillow`、`zhconv`（目录繁简转换），并把 `jmcomic` 锁定为 `2.7.10`；补装失败时 `/jm` 会按「缺少运行依赖」模板提示（Views 可改），日志记录缺失模块名。以后新增模块只需声明自己的依赖。

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
│   ├── jm/                  # module / service / paths / cache / pdf / models / utils / config.py
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
