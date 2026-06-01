from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

from .model import QxqyService


@register("qxqy", "Yuef", "千星奇域-关卡查询插件", "1.0.0")
class QxqyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.config = config
        self.service = QxqyService(config)

    async def initialize(self):
        """插件初始化"""
        logger.info("千星奇域关卡查询插件已加载")

    @filter.command("qx")
    async def query_level_detail(self, event: AstrMessageEvent):
        """
        查询关卡详情 - 用法: /qx {level_id}

        Args:
            event: 消息事件对象
        """
        args = event.message_str.strip().split(maxsplit=1)
        if len(args) < 2:
            yield event.plain_result("请提供关卡ID，用法: /qx {level_id}")
            return

        level_id = args[1].strip()
        if not level_id:
            yield event.plain_result("关卡ID不能为空，用法: /qx {level_id}")
            return

        success, message, chain = await self.service.query_level_detail(level_id)
        if not success:
            yield event.plain_result(message)
            return

        if chain is None:
            yield event.plain_result("获取结果为空")
            return
        yield event.chain_result(chain)

    @filter.command("qc")
    async def query_level_comments(self, event: AstrMessageEvent):
        """
        查询关卡评论 - 用法: /qc {level_id}

        Args:
            event: 消息事件对象
        """
        args = event.message_str.strip().split(maxsplit=1)
        if len(args) < 2:
            yield event.plain_result("请提供关卡ID，用法: /qc {level_id}")
            return

        level_id = args[1].strip()
        if not level_id:
            yield event.plain_result("关卡ID不能为空，用法: /qc {level_id}")
            return

        success, message, chain = await self.service.query_level_comments(level_id)
        if not success:
            yield event.plain_result(message)
            return

        if chain is None:
            yield event.plain_result("获取结果为空")
            return
        yield event.chain_result(chain)

    @filter.command("qce")
    async def export_level_comments(self, event: AstrMessageEvent):
        """
        导出全量评论为CSV - 用法: /qce {level_id}

        Args:
            event: 消息事件对象
        """
        args = event.message_str.strip().split(maxsplit=1)
        if len(args) < 2:
            yield event.plain_result("请提供关卡ID，用法: /qce {level_id}")
            return

        level_id = args[1].strip()
        if not level_id:
            yield event.plain_result("关卡ID不能为空，用法: /qce {level_id}")
            return

        yield event.plain_result("正在抓取全量评论，请稍候...")

        success, message, filepath, filename = await self.service.export_comments_csv(level_id)
        if not success or filepath is None or filename is None:
            yield event.plain_result(message)
            return

        chain = [Comp.Plain(message + "\n"), Comp.File(file=filepath, name=filename)]
        yield event.chain_result(chain)

    async def terminate(self):
        """插件销毁"""
        logger.info("千星奇域查询插件已卸载")