# 定时更新：把 update 模块登记到 AstrBot 的调度器
#
# 使用 context.cron_manager 的 basic job（回调支持 async），
# 插件重载后旧 handler 会失效，因此每次加载先清理同名旧任务再注册。

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class UpdateSchedule:
    # 负责「定时更新」这一个 cron 任务的登记与清理

    def __init__(
        self,
        context,
        plugin_name: str,
        handler: Callable[[], Awaitable[None]],
    ) -> None:
        self._context = context
        self._name = f"{plugin_name}:update"
        self._handler = handler

    def _manager(self):
        return getattr(self._context, "cron_manager", None)

    async def sync(self, enabled: bool, cron_expression: str) -> None:
        # 先清掉旧任务，再按当前配置注册；失败不影响插件加载
        await self.clear()

        if not enabled:
            return

        expression = (cron_expression or "").strip()
        if not expression:
            logger.warning("[update] 已启用定时更新但 cron 表达式为空，跳过注册")
            return

        manager = self._manager()
        if manager is None:
            logger.warning("[update] AstrBot 未提供 cron_manager，跳过定时更新")
            return

        try:
            await manager.add_basic_job(
                name=self._name,
                cron_expression=expression,
                handler=self._handler,
                persistent=False,
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"[update] 注册定时更新失败（{expression}）: {e}")

    async def clear(self) -> None:
        manager = self._manager()
        if manager is None:
            return

        try:
            jobs = await manager.list_jobs(job_type="basic")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[update] 读取定时任务失败: {e}")
            return

        for job in jobs:
            if getattr(job, "name", "") != self._name:
                continue
            try:
                await manager.delete_job(job.job_id)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[update] 清理旧定时任务失败: {e}")
