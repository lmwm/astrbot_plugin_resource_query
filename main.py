"""
资源查询 AstrBot 插件（模块化架构）

支持平台：
  - MiMo：小米 MiMo 平台用量查询
  - 华数广电：流量/通话/余额查询
  - JMComic：漫画下载（仅私聊）

指令：
  /query                    — 查询帮助
  /mimo                     — 查询所有 MiMo 账号
  /mimo <序号或名称>        — 查询指定 MiMo 账号
  /mimo ls                  — 列出所有 MiMo 账号
  /mimo del <序号或名称>    — 删除 MiMo 账号
  /wasu                     — 查询所有华数账号
  /wasu <序号或名称>        — 查询指定华数账号
  /wasu ls                  — 列出所有华数账号
  /wasu del <序号或名称>    — 删除华数账号
  /query update             — 更新插件
  /jm <ID>                  — 下载 JMComic 漫画 PDF（仅私聊）

架构设计：
  本插件采用模块化架构，各功能模块独立管理自己的配置和逻辑。
  总管理模块（PluginManager）负责协调模块与 AstrBot 之间的通信。

  ┌─────────────────────────────────────────────────────────────┐
  │                    main.py (总管理模块)                      │
  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
  │  │  MiMo模块   │  │  华数模块   │  │  JM模块     │        │
  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
  │         │                │                │                │
  │         └────────────────┼────────────────┘                │
  │                          │                                 │
  │                    ┌─────┴─────┐                           │
  │                    │ 模块注册中心 │                          │
  │                    └───────────┘                           │
  └─────────────────────────────────────────────────────────────┘
"""

import asyncio
import json
import os
from pathlib import Path

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import File
from astrbot.api.star import Context, Star

from .core.manager import PluginManager
from .modules.mimo import MimoModule, MimoResult
from .modules.wasu import WasuModule
from .modules.jm import JMModule, normalize_album_id
from .updater import check_update, do_update, reload_plugin

_PLUGIN_NAME = "astrbot_plugin_resource_query"


class ResourceQueryPlugin(Star):
    """资源查询插件主类

    采用模块化架构，各功能模块独立管理自己的配置和逻辑。
    总管理模块负责协调模块与 AstrBot 之间的通信。
    """

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self._plugin_dir = Path(__file__).parent

        # 初始化总管理器
        self._manager = PluginManager(_PLUGIN_NAME, self._plugin_dir)

        # 注册功能模块
        self._register_modules()

        # 注册 Pages API
        self._register_web_apis(context)

    def _register_modules(self):
        """注册所有功能模块（根据配置决定是否启用）"""
        # 获取模块启用配置
        modules_config = self.config.get("modules", {})

        # 注册 MiMo 模块
        if modules_config.get("mimo_enabled", True):
            mimo_module = MimoModule(self._plugin_dir, _PLUGIN_NAME)
            self._manager.register_module(mimo_module)

        # 注册华数广电模块
        if modules_config.get("wasu_enabled", True):
            wasu_module = WasuModule(self._plugin_dir, _PLUGIN_NAME)
            self._manager.register_module(wasu_module)

        # 注册 JMComic 模块
        if modules_config.get("jm_enabled", True):
            jm_module = JMModule(self._plugin_dir, _PLUGIN_NAME)
            self._manager.register_module(jm_module)

    def _register_web_apis(self, context: Context):
        """注册 Web API"""
        # 注册全局配置 API
        context.register_web_api(
            f"/{_PLUGIN_NAME}/config", self.get_config, ["GET"], "获取插件配置"
        )
        context.register_web_api(
            f"/{_PLUGIN_NAME}/config", self.save_config, ["POST"], "保存插件配置"
        )
        context.register_web_api(
            f"/{_PLUGIN_NAME}/config/delete", self.delete_config, ["POST"], "删除账号配置"
        )
        context.register_web_api(
            f"/{_PLUGIN_NAME}/templates", self.get_templates, ["GET"], "获取默认模板"
        )
        context.register_web_api(
            f"/{_PLUGIN_NAME}/template-vars", self.get_template_vars, ["GET"], "获取模板变量定义"
        )
        context.register_web_api(
            f"/{_PLUGIN_NAME}/template-vars", self.save_template_vars, ["POST"], "保存模板变量定义"
        )
        context.register_web_api(
            f"/{_PLUGIN_NAME}/modules", self.get_modules_config, ["GET"], "获取模块启用配置"
        )

        # 注册模块特有的 Web API
        for module in self._manager.get_all_modules():
            module_apis = module.get_web_apis()
            for api in module_apis:
                path = api.get("path", "")
                handler = api.get("handler")
                methods = api.get("methods", ["GET"])
                desc = api.get("desc", "")

                # 添加模块前缀到路径
                full_path = f"/{_PLUGIN_NAME}/{module.module_name}/{path}"
                context.register_web_api(full_path, handler, methods, desc)

    # ══════════════════════════════════════════
    #  Pages API
    # ══════════════════════════════════════════

    async def get_modules_config(self):
        """获取模块启用配置"""
        from astrbot.api.web import json_response
        modules_config = self.config.get("modules", {})
        return json_response({
            "mimo": modules_config.get("mimo_enabled", True),
            "wasu": modules_config.get("wasu_enabled", True),
            "jm": modules_config.get("jm_enabled", True),
        })

    async def get_config(self):
        """获取配置"""
        from astrbot.api.web import json_response
        return json_response({"accounts": self._manager.get_all_accounts()})

    async def save_config(self):
        """保存配置"""
        from astrbot.api.web import json_response, request
        payload = await request.json(default={})
        if "accounts" in payload:
            # 按平台分组保存
            accounts_by_module = {}
            for acc in payload["accounts"]:
                module_name = acc.get("platform", "unknown")
                if module_name not in accounts_by_module:
                    accounts_by_module[module_name] = []
                accounts_by_module[module_name].append(acc)

            # 保存到各模块
            for module_name, accounts in accounts_by_module.items():
                module = self._manager.get_module(module_name)
                if module:
                    module.save_accounts(accounts)

        return json_response({"status": "ok"})

    async def delete_config(self):
        """删除指定账号"""
        from astrbot.api.web import error_response, json_response, request
        payload = await request.json(default={})
        platform = payload.get("platform", "").strip()
        index = payload.get("index")
        if not platform or index is None:
            return error_response("缺少 platform 或 index 参数")
        try:
            index = int(index)
        except (TypeError, ValueError):
            return error_response("index 必须是整数")

        deleted = self._manager.delete_account(platform, index)
        if deleted is None:
            return error_response("账号不存在或删除失败")

        name = deleted.get("name") or deleted.get("account") or deleted.get("phone") or "未知"
        return json_response({"status": "ok", "deleted": name})

    async def get_templates(self):
        """获取默认模板"""
        from astrbot.api.web import json_response
        templates = {}
        templates_dir = self._plugin_dir / "templates"
        if templates_dir.exists():
            for txt_file in templates_dir.glob("*.txt"):
                platform = txt_file.stem.replace("_default", "")
                try:
                    templates[platform] = txt_file.read_text(encoding="utf-8")
                except OSError:
                    pass
        return json_response(templates)

    async def get_template_vars(self):
        """获取模板变量定义"""
        import re
        from astrbot.api.web import json_response
        from .modules.mimo.utils import get_config_value

        # 变量描述映射
        var_descriptions = {
            "label": "账号名称",
            "balance": "余额",
            "gift_balance": "赠送余额",
            "input_token": "输入Token（自动格式化）",
            "output_token": "输出Token（自动格式化）",
            "cache_token": "缓存Token（自动格式化）",
            "monthly_cost": "本月费用",
            "total_cost": "累计费用",
            "tpm": "TPM 限额",
            "rpm": "RPM 限额",
            "concurrency": "并发限额",
            "month_fee": "当月话费",
            "arrears": "欠费",
            "total_used": "本月累计使用",
            "total": "总流量",
            "used": "已用流量",
            "remain": "剩余流量",
            "query_time": "查询时间",
            "traffic_detail": "流量详细信息（多行）",
            "voice_detail": "语音详细信息（多行）",
        }

        # 变量默认值
        var_defaults = {
            "mimo": {
                "label": "MiMo账号", "balance": "177.40", "gift_balance": "177.40",
                "input_token": "10.3亿", "output_token": "324.0万", "cache_token": "9.8亿",
                "monthly_cost": "120.93", "total_cost": "132.60",
                "tpm": "10.0万", "rpm": "1,200", "concurrency": "50"
            },
            "wasu": {
                "label": "138****8888", "balance": "¥56.80", "month_fee": "¥38.50",
                "arrears": "¥0.00", "total_used": "15.62 GB", "total": "30.00 GB",
                "used": "15.62 GB", "remain": "14.38 GB", "query_time": "2026-08-21 23:00",
                "traffic_detail": "\n     · 通用流量 结转: 20.00 GB (已用 12.50 GB / 剩 7.50 GB)",
                "voice_detail": "\n📞 语音: 通话套餐: 300分钟 | 剩余 215分钟"
            }
        }

        result = {}

        # 获取各模块的默认模板（从 config.yaml 或 templates 目录）
        templates = {}

        # 尝试从 templates 目录读取
        templates_dir = self._plugin_dir / "templates"
        if templates_dir.exists():
            for txt_file in templates_dir.glob("*.txt"):
                platform = txt_file.stem.replace("_default", "")
                try:
                    templates[platform] = txt_file.read_text(encoding="utf-8")
                except OSError:
                    pass

        # 如果 templates 目录没有模板，从模块获取默认模板
        for module in self._manager.get_all_modules():
            platform = module.module_name
            if platform not in templates:
                default_template = module.get_default_template()
                if default_template:
                    templates[platform] = default_template

        # 处理每个平台的变量
        for platform, content in templates.items():
            # 从模板中提取变量名
            vars_found = re.findall(r"\{(\w+)\}", content)
            if not vars_found:
                continue

            platform_defaults = var_defaults.get(platform, {})

            # 检查是否有用户自定义配置
            module = self._manager.get_module(platform)
            if module:
                var_config_path = module.get_config_path() / "var_config.json"
                user_vars = {}
                if var_config_path.exists():
                    try:
                        user_config = json.loads(var_config_path.read_text(encoding="utf-8"))
                        if user_config and "variables" in user_config:
                            for v in user_config["variables"]:
                                user_vars[v["name"]] = v
                    except (json.JSONDecodeError, OSError):
                        pass

                vars_list = []
                for v in dict.fromkeys(vars_found):  # 去重并保持顺序
                    if v in user_vars:
                        vars_list.append(user_vars[v])
                    else:
                        vars_list.append({
                            "name": v,
                            "desc": var_descriptions.get(v, v),
                            "default": platform_defaults.get(v, ""),
                            "show": True
                        })

                result[platform] = {
                    "variables": vars_list
                }

        return json_response(result)

    async def save_template_vars(self):
        """保存模板变量配置"""
        from astrbot.api.web import error_response, json_response, request
        payload = await request.json(default={})
        if not payload:
            return error_response("缺少配置数据")

        # 按平台分别保存到各自的目录
        for platform, config_data in payload.items():
            module = self._manager.get_module(platform)
            if module:
                var_config_path = module.get_config_path() / "var_config.json"
                try:
                    var_config_path.write_text(
                        json.dumps(config_data, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                except OSError as e:
                    return error_response(f"保存 {platform} 配置失败: {e}")

        return json_response({"status": "ok"})

    # ══════════════════════════════════════════
    #  主指令
    # ══════════════════════════════════════════

    @filter.command("query")
    async def query_cmd(self, event: AstrMessageEvent):
        """/query — 资源查询主指令"""
        args = event.get_message_str().strip().split()

        if len(args) == 1:
            # 显示帮助信息
            help_text = "📊 资源查询插件 v4.0.0（模块化架构）\n"
            help_text += "────────────────\n"
            help_text += "用法:\n"

            # 动态生成各模块的帮助信息
            for module in self._manager.get_all_modules():
                commands = module.get_commands()
                for cmd in commands:
                    help_text += f"  /{cmd['name']} — {cmd['desc']}\n"

            help_text += "  /query update — 更新插件"
            yield event.plain_result(help_text)
            return

        platform = args[1].lower()

        if platform == "update":
            yield event.plain_result("正在检查更新...")
            async for r in self._handle_update(event):
                yield r
        else:
            # 检查是否有对应的模块
            module = self._manager.get_module(platform)
            if module:
                # 委托给模块处理
                async for result in module.handle_command(platform, args[2:], event):
                    yield result
            else:
                supported = ", ".join(self._manager.get_module_names())
                yield event.plain_result(f"❌ 未知平台: {platform}\n支持: {supported}")

    # ══════════════════════════════════════════
    #  MiMo 指令
    # ══════════════════════════════════════════

    @filter.command("mimo")
    async def mimo_cmd(self, event: AstrMessageEvent):
        """/mimo — MiMo 查询指令"""
        args = event.get_message_str().strip().split()
        # 移除指令名本身
        if args and args[0].lower() == "mimo":
            args = args[1:]

        # 委托给 MiMo 模块处理
        mimo_module = self._manager.get_module("mimo")
        if mimo_module:
            async for result in mimo_module.handle_command("mimo", args, event):
                yield result
        else:
            yield event.plain_result("❌ MiMo 模块未加载")

    # ══════════════════════════════════════════
    #  华数指令
    # ══════════════════════════════════════════

    @filter.command("wasu")
    async def wasu_cmd(self, event: AstrMessageEvent):
        """/wasu — 华数广电查询指令"""
        args = event.get_message_str().strip().split()
        # 移除指令名本身
        if args and args[0].lower() == "wasu":
            args = args[1:]

        # 委托给华数模块处理
        wasu_module = self._manager.get_module("wasu")
        if wasu_module:
            async for result in wasu_module.handle_command("wasu", args, event):
                yield result
        else:
            yield event.plain_result("❌ 华数广电模块未加载")

    # ══════════════════════════════════════════
    #  JM 指令
    # ══════════════════════════════════════════

    @filter.command("jm", alias={"JM", "Jm", "jM"}, desc="下载 JMComic 漫画 PDF：/jm <数字ID> [redownload]")
    async def jm_command(self, event: AstrMessageEvent, jm_id: str = "", option: str = ""):
        """/jm — 下载 JMComic 漫画（仅私聊）"""
        # 委托给 JM 模块处理
        jm_module = self._manager.get_module("jm")
        if jm_module:
            args = []
            if jm_id:
                args.append(jm_id)
            if option:
                args.append(option)
            async for result in jm_module.handle_command("jm", args, event):
                yield result
        else:
            yield event.plain_result("❌ JMComic 模块未加载")

    # ══════════════════════════════════════════
    #  更新
    # ══════════════════════════════════════════

    async def _handle_update(self, event: AstrMessageEvent):
        """处理更新命令（始终执行更新）"""
        check = await check_update(self.config, force=True)
        if check.get("error"):
            yield event.plain_result(f"检查更新失败: {check['error']}")
            return

        yield event.plain_result(f"当前版本 v{check['current']}，正在重新安装...")
        result = await do_update(self.config)
        if "✅" in result:
            reload_result = await reload_plugin(self.context)
            yield event.plain_result(f"{result}\n{reload_result}")
        else:
            yield event.plain_result(result)
