# 插件自动更新实现
#
# 包含三部分：
#   - `check_update`：读取远端 metadata.yaml 并比较版本号
#   - `do_update`：下载远端源码归档 zip 并整体替换插件目录
#   - `reload_plugin`：调用 Dashboard API 让新版本生效
#
# 当前版本读插件目录的 metadata.yaml；不保存、也不读取任何提交号状态。
# 更新时清空插件目录后解压归档；临时目录在 plugin_data/<插件>/tmp/update，
# 成功或失败都会清理。

from __future__ import annotations

import asyncio
import datetime
import io
import json
import os
import shutil
import stat
import zipfile
from pathlib import Path
from urllib.request import Request

import jwt

from ...common.utils import get_data_path
from ...http_utils import new_opener, proxy_url, retry

_REPO_OWNER = "lmwm"
_REPO_NAME = "astrbot_plugin_resource_query"
_GITHUB_API = f"https://api.github.com/repos/{_REPO_OWNER}/{_REPO_NAME}"
_USER_AGENT = "astrbot-plugin-resource-query-updater"

# 插件根目录（modules/update/updater.py 的上两级）
_PLUGIN_DIR = Path(__file__).resolve().parents[2]


def _proxy_candidates(proxy: str) -> tuple[str, ...]:
    # 返回本次请求要依次尝试的代理前缀
    #
    #     只用配置里的代理；留空或该代理失败时直连，不再内置额外镜像。
    proxy = proxy.strip().rstrip("/")
    return (proxy, "") if proxy else ("",)


def get_current_version() -> str:
    # 读取当前插件版本号
    try:
        content = (_PLUGIN_DIR / "metadata.yaml").read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")

    return "0.0.0"


def _remove_tree(path: Path) -> None:
    # 删除目录；git 对象文件在 Windows 上是只读的，失败时去掉只读再删
    if not path.exists():
        return

    def _on_error(func, target, _exc_info):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    shutil.rmtree(path, onerror=_on_error)


def _replace_plugin_dir(source_dir: Path) -> None:
    # 用 source_dir 的内容整体替换插件目录（旧的 .git 等残留一并删除）
    for item in _PLUGIN_DIR.iterdir():
        if item.is_dir():
            _remove_tree(item)
        else:
            item.unlink()

    for item in source_dir.iterdir():
        shutil.move(str(item), str(_PLUGIN_DIR / item.name))


def decide_update(current_version: str, latest_version: str, force: bool) -> bool:
    # 判断是否需要更新：强制更新，或远端版本号与插件目录不同
    if force:
        return True
    if not latest_version:
        return False
    return latest_version != current_version


async def check_update(
    proxy: str = "",
    max_retries: int = 3,
    force: bool = False,
) -> dict:
    # 检查远端是否有新版本；只比较版本号（force 时忽略版本）
    current_version = get_current_version()

    def _fetch_sha(prefix: str) -> str:
        def _do() -> str:
            opener, _ = new_opener()
            request = Request(
                proxy_url(f"{_GITHUB_API}/commits/main", prefix),
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            with opener.open(request, timeout=15) as response:
                return json.loads(response.read())["sha"]

        try:
            return retry(_do, max_retries)
        except (OSError, TimeoutError, json.JSONDecodeError, KeyError):
            return ""

    def _fetch_one(prefix: str) -> dict:
        def _do() -> dict:
            opener, _ = new_opener()
            raw_url = (
                f"https://raw.githubusercontent.com/{_REPO_OWNER}/{_REPO_NAME}"
                "/main/metadata.yaml"
            )
            request = Request(
                proxy_url(raw_url, prefix),
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

    def _fetch() -> dict:
        last: dict | None = None
        for prefix in _proxy_candidates(proxy):
            result = _fetch_one(prefix)
            if result["latest"] or not result["error"]:
                # 版本一致且非强制时才需要提交号
                if result["latest"]:
                    # 取远端提交号，供消息变量与后续下载复用
                    result["remote_commit"] = _fetch_sha(prefix)
                return result
            last = result

        return last or {
            "latest": "",
            "current": current_version,
            "error": "没有可用的下载地址",
        }

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _fetch)
    result.setdefault("remote_commit", "")
    result["has_update"] = decide_update(
        current_version,
        str(result.get("latest") or ""),
        force,
    )
    result["force"] = force
    return result


async def do_update(proxy: str = "", max_retries: int = 3, sha: str = "") -> dict:
    # 下载远端源码归档 zip 并整目录替换插件目录；sha 非空时跳过提交号请求
    # 返回 {"ok": bool, "sha": str, "message": str}

    def _get_sha(prefix: str) -> str:
        opener, _ = new_opener()
        request = Request(
            proxy_url(f"{_GITHUB_API}/commits/main", prefix),
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with opener.open(request, timeout=15) as response:
            return json.loads(response.read())["sha"]

    def _resolve_commit() -> str:
        # sha 已提供时直接复用；否则按代理候选依次查询远端提交
        if sha:
            return sha
        for prefix in _proxy_candidates(proxy):
            try:
                commit = retry(lambda p=prefix: _get_sha(p), max_retries)
            except (OSError, TimeoutError, json.JSONDecodeError, KeyError):
                continue
            if commit:
                return commit
        return ""

    def _download_with(prefix: str, commit: str) -> dict:
        # 下载源码归档 zip，解压后整目录替换插件目录
        if not commit:
            raise RuntimeError("无法获取远端提交号")

        def _download_zip() -> bytes:
            opener, _ = new_opener()
            zip_url = proxy_url(
                f"https://github.com/{_REPO_OWNER}/{_REPO_NAME}/archive/{commit}.zip",
                prefix,
            )
            request = Request(zip_url, headers={"User-Agent": _USER_AGENT})
            with opener.open(request, timeout=30) as response:
                return response.read()

        zip_data = retry(_download_zip, max_retries)

        # 临时解压目录放在 plugin_data 内，避免与插件目录/系统临时目录跨盘移动
        tmp_dir = get_data_path(_REPO_NAME) / "tmp" / "update"
        _remove_tree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:
                archive.extractall(tmp_dir)

            extracted = [d for d in tmp_dir.iterdir() if d.is_dir()]
            if not extracted:
                raise RuntimeError("解压失败：未找到插件目录")

            _replace_plugin_dir(extracted[0])
        finally:
            # 成功或失败都清理临时目录；tmp 目录空了也一并删除
            _remove_tree(tmp_dir)
            try:
                tmp_dir.parent.rmdir()
            except OSError:
                pass

        return {
            "ok": True,
            "sha": commit,
            "message": f"√ 更新完成，新版本已下载（commit: {commit[:7]}）",
        }

    def _download_and_extract() -> dict:
        # 下载源码归档并整目录替换；换代理/直连依次重试
        commit = _resolve_commit()
        last_error = "没有可用的下载地址"

        for prefix in _proxy_candidates(proxy):
            try:
                return _download_with(prefix, commit)
            except (
                OSError,
                TimeoutError,
                json.JSONDecodeError,
                zipfile.BadZipFile,
                shutil.Error,
                RuntimeError,
            ) as e:
                last_error = str(e)
                continue

        return {"ok": False, "sha": "", "message": f"× 更新失败: {last_error}"}

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _download_and_extract)


async def reload_plugin(context) -> str:
    # 调用 Dashboard API 重载插件，使新版本生效
    #
    #     优先使用 AstrBot 4.29+ 的 REST 路由 `/api/v1/plugins/{name}/reload`，
    #     失败时回退到旧路由 `/api/plugin/reload`（旧版 AstrBot 仍在使用）。

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
                return "! Dashboard 未配置账号密钥，请手动在 WebUI 重载插件"

            payload = {
                "username": username,
                "exp": datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=5),
            }
            token = jwt.encode(payload, jwt_secret, algorithm="HS256")
            if isinstance(token, bytes):
                token = token.decode("utf-8")

            base = f"http://{host}:{port}"
            routes = (
                (f"{base}/api/v1/plugins/{_REPO_NAME}/reload", None),
                (f"{base}/api/plugin/reload", {"name": _REPO_NAME}),
            )

            opener, _ = new_opener()
            last_error = ""

            for url, body in routes:
                request = Request(
                    url,
                    data=json.dumps(body).encode() if body else None,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                try:
                    with opener.open(request, timeout=15) as response:
                        result = json.loads(response.read())
                except (OSError, TimeoutError, json.JSONDecodeError) as e:
                    last_error = str(e)
                    continue

                if result.get("status") == "ok":
                    return "√ 插件已自动重载，新版本已生效"

                last_error = f"重载返回: {result.get('message', result)}"

            return f"! 自动重载失败: {last_error}，请手动在 WebUI 重载插件"

        except (OSError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            return f"! 自动重载失败: {e}，请手动在 WebUI 重载插件"

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do_reload)
