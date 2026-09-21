"""插件自动更新实现

包含三部分：
  - `check_update`：读取远端 metadata.yaml 并比较版本号
  - `do_update`：下载远端压缩包并覆盖插件目录
  - `reload_plugin`：调用 Dashboard API 让新版本生效

注意：`do_update` 采用「先清空再覆盖」策略，会删除插件目录下除
`.git` / `.github` / `__pycache__` / `.gitignore` / `tests` 之外的所有文件。
"""

from __future__ import annotations

import asyncio
import datetime
import io
import json
import os
import shutil
import zipfile
from pathlib import Path
from urllib.request import Request

import jwt

from ...http_utils import new_opener, proxy_url, retry

_REPO_OWNER = "lmwm"
_REPO_NAME = "astrbot_plugin_resource_query"
_GITHUB_API = f"https://api.github.com/repos/{_REPO_OWNER}/{_REPO_NAME}"
_USER_AGENT = "astrbot-plugin-resource-query-updater"

# 插件根目录（modules/update/updater.py 的上两级）
_PLUGIN_DIR = Path(__file__).resolve().parents[2]

# 更新时保留的内容
_EXCLUDE = {".git", ".github", "__pycache__", ".gitignore", "tests"}

# 未配置代理时使用的默认加速前缀
_DEFAULT_PROXY = "https://gh-proxy.cn/"


def get_current_version() -> str:
    """读取当前插件版本号

    Returns:
        metadata.yaml 中的 version 字段；读取失败时返回 "0.0.0"。
    """
    try:
        content = (_PLUGIN_DIR / "metadata.yaml").read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")

    return "0.0.0"


async def check_update(proxy: str = "", max_retries: int = 3, force: bool = False) -> dict:
    """检查远端是否有新版本

    Args:
        proxy: GitHub 代理前缀；留空使用内置默认代理。
        max_retries: 网络请求重试次数。
        force: 是否强制视为需要更新。

    Returns:
        含 latest / current / has_update / force / error 字段的字典。
    """
    current_version = get_current_version()
    proxy = proxy or _DEFAULT_PROXY

    def _fetch() -> dict:
        def _do() -> dict:
            opener, _ = new_opener()
            raw_url = (
                f"https://raw.githubusercontent.com/{_REPO_OWNER}/{_REPO_NAME}"
                "/main/metadata.yaml"
            )
            request = Request(
                proxy_url(raw_url, proxy),
                headers={"User-Agent": _USER_AGENT},
            )
            with opener.open(request, timeout=15) as response:
                content = response.read().decode("utf-8")

            for line in content.splitlines():
                line = line.strip()
                if line.startswith("version:"):
                    latest = line.split(":", 1)[1].strip().strip('"').strip("'")
                    return {"latest": latest, "current": current_version, "error": ""}

            return {
                "latest": "",
                "current": current_version,
                "error": "远端 metadata.yaml 中未找到 version",
            }

        try:
            return retry(_do, max_retries)
        except (OSError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            return {"latest": "", "current": current_version, "error": str(e)}

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _fetch)
    result["has_update"] = bool(
        force or (result["latest"] and result["latest"] != current_version)
    )
    result["force"] = force
    return result


async def do_update(proxy: str = "", max_retries: int = 3) -> str:
    """下载远端最新版本并覆盖插件文件

    Args:
        proxy: GitHub 代理前缀；留空使用内置默认代理。
        max_retries: 网络请求重试次数。

    Returns:
        面向用户的更新结果文本。
    """
    proxy = proxy or _DEFAULT_PROXY

    def _download_and_extract() -> str:
        try:

            def _get_sha() -> str:
                opener, _ = new_opener()
                request = Request(
                    proxy_url(f"{_GITHUB_API}/commits/main", proxy),
                    headers={
                        "User-Agent": _USER_AGENT,
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                with opener.open(request, timeout=15) as response:
                    return json.loads(response.read())["sha"]

            sha = retry(_get_sha, max_retries)

            def _download_zip() -> bytes:
                opener, _ = new_opener()
                zip_url = proxy_url(
                    f"https://github.com/{_REPO_OWNER}/{_REPO_NAME}/archive/{sha}.zip",
                    proxy,
                )
                request = Request(zip_url, headers={"User-Agent": _USER_AGENT})
                with opener.open(request, timeout=30) as response:
                    return response.read()

            zip_data = retry(_download_zip, max_retries)

            tmp_dir = _PLUGIN_DIR.parent / f"{_REPO_NAME}_tmp_update"
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)

            with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:
                archive.extractall(tmp_dir)

            extracted = [d for d in tmp_dir.iterdir() if d.is_dir()]
            if not extracted:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return "❌ 解压失败：未找到插件目录"

            source_dir = extracted[0]

            # 清空插件目录（保留版本控制与缓存目录）
            for item in _PLUGIN_DIR.iterdir():
                if item.name in _EXCLUDE:
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)

            # 覆盖为新版本
            for item in source_dir.iterdir():
                if item.name in _EXCLUDE:
                    continue
                destination = _PLUGIN_DIR / item.name
                if item.is_dir():
                    shutil.copytree(item, destination)
                else:
                    shutil.copy2(item, destination)

            shutil.rmtree(tmp_dir, ignore_errors=True)
            return f"✅ 更新完成，新版本已下载（commit: {sha[:7]}）"

        except (OSError, TimeoutError, zipfile.BadZipFile, shutil.Error) as e:
            return f"❌ 更新失败: {e}"

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _download_and_extract)


async def reload_plugin(context) -> str:
    """调用 Dashboard API 重载插件，使新版本生效

    Args:
        context: AstrBot 的 Context 实例。

    Returns:
        面向用户的重载结果文本。
    """

    def _do_reload() -> str:
        try:
            dashboard = (context.get_config() or {}).get("dashboard", {})
            host = dashboard.get("host", "127.0.0.1")
            if host == "0.0.0.0":
                host = "127.0.0.1"

            port = int(os.environ.get("DASHBOARD_PORT") or dashboard.get("port", 6185))
            username = dashboard.get("username")
            jwt_secret = dashboard.get("jwt_secret")

            if not username or not jwt_secret:
                return "⚠️ Dashboard 未配置账号密钥，请手动在 WebUI 重载插件"

            payload = {
                "username": username,
                "exp": datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=5),
            }
            token = jwt.encode(payload, jwt_secret, algorithm="HS256")
            if isinstance(token, bytes):
                token = token.decode("utf-8")

            opener, _ = new_opener()
            request = Request(
                f"http://{host}:{port}/api/plugin/reload",
                data=json.dumps({"name": _REPO_NAME}).encode(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with opener.open(request, timeout=15) as response:
                result = json.loads(response.read())

            if result.get("status") == "ok":
                return "✅ 插件已自动重载，新版本已生效"

            return f"⚠️ 重载返回: {result.get('message', result)}"

        except (OSError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            return f"⚠️ 自动重载失败: {e}，请手动在 WebUI 重载插件"

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do_reload)
