# 插件自动更新实现
#
# 包含三部分：
#   - `check_update`：读取远端 metadata.yaml 并比较版本号
#   - `do_update`：下载远端压缩包并覆盖插件目录
#   - `reload_plugin`：调用 Dashboard API 让新版本生效
#
# 注意：`do_update` 采用「先清空再覆盖」策略，会删除插件目录下除
# `.git` / `.github` / `__pycache__` / `.gitignore` / `tests` 之外的所有文件。

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


def _proxy_candidates(proxy: str) -> tuple[str, ...]:
    # 返回本次请求要依次尝试的代理前缀
    #
    #     用户配置的代理排在最前；若它不可用，再回退到默认镜像与直连，
    #     避免一个失效代理让整个更新流程不可用。
    proxy = proxy.strip().rstrip("/")

    candidates = [proxy] if proxy else []
    candidates.extend(["https://gh-proxy.com/", ""])

    seen: set[str] = set()
    result: list[str] = []
    for item in candidates:
        key = item.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(result)


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


def decide_update(
    current_version: str,
    current_commit: str,
    latest_version: str,
    remote_commit: str,
    force: bool,
) -> bool:
    # 判断是否需要更新：强制 > 版本号 > 提交号
    if force:
        return True
    if not latest_version:
        return False
    if latest_version != current_version:
        return True
    if remote_commit:
        # 版本相同再看提交号；没有本地基线时先更新一次建立基线
        return remote_commit != current_commit if current_commit else True
    return False


async def check_update(
    proxy: str = "",
    max_retries: int = 3,
    force: bool = False,
    current_commit: str = "",
) -> dict:
    # 检查远端是否有新版本；版本相同且非强制时再比较提交号
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
                if not force and result["latest"] == current_version:
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
    result["current_commit"] = current_commit
    result["has_update"] = decide_update(
        current_version,
        current_commit,
        str(result.get("latest") or ""),
        str(result.get("remote_commit") or ""),
        force,
    )
    result["force"] = force
    return result


async def do_update(proxy: str = "", max_retries: int = 3, sha: str = "") -> dict:
    # 下载远端最新版本并覆盖插件文件；sha 非空时跳过提交号请求
    # 返回 {"ok": bool, "sha": str, "message": str}

    def _download_with(prefix: str) -> dict:
        def _get_sha() -> str:
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

        commit = sha or retry(_get_sha, max_retries)

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

        tmp_dir = _PLUGIN_DIR.parent / f"{_REPO_NAME}_tmp_update"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)

        with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:
            archive.extractall(tmp_dir)

        extracted = [d for d in tmp_dir.iterdir() if d.is_dir()]
        if not extracted:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise RuntimeError("解压失败：未找到插件目录")

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
        return {
            "ok": True,
            "sha": commit,
            "message": f"√ 更新完成，新版本已下载（commit: {commit[:7]}）",
        }

    def _download_and_extract() -> dict:
        last_error = "没有可用的下载地址"

        for prefix in _proxy_candidates(proxy):
            try:
                return _download_with(prefix)
            except (
                OSError,
                TimeoutError,
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
