from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

from .model import QxqyService


@register("qxqy", "Yuef", "千星奇域-关卡查询插件", "1.0.0")
class QxqyPlugin(Star):
    """千星奇域关卡查询插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.config = config
        self.service = QxqyService(config)

    async def initialize(self):
        """插件初始化"""
        logger.info("千星奇域关卡查询插件已加载")

    @filter.command("qx.i")
    async def query_level_info(self, event: AstrMessageEvent):
        """
        查询关卡详情 - /qx.i {level_id} [-p]

        Args:
            level_id: 关卡ID
            -p: 生成图片输出（无参默认文本输出）
        """
        args = event.message_str.strip().split(maxsplit=2)
        if len(args) < 2:
            yield event.plain_result("请提供关卡ID")
            yield event.plain_result("用法: /qx.i <关卡ID> [-p]")
            yield event.plain_result("示例: /qx.i 1001 或 /qx.i 1001 -p")
            return

        level_id = args[1].strip()
        if not level_id:
            yield event.plain_result("关卡ID不能为空")
            return

        # 解析可选参数
        generate_image = False
        if len(args) >= 3:
            opt_arg = args[2].strip()
            if opt_arg == "-p":
                generate_image = True

        if generate_image:
            # 图片模式 - 直接输出图片或报错
            success, message, image_path = await self.service.generate_level_image(level_id)
            if not success or image_path is None:
                yield event.plain_result(message)
                return
            yield event.chain_result([Comp.Image.fromFileSystem(image_path)])
        else:
            # 文本模式
            success, message, chain = await self.service.query_level_detail(level_id)
            if not success:
                yield event.plain_result(message)
                return
            if chain is None:
                yield event.plain_result("获取结果为空")
                return
            yield event.chain_result(chain)

    @filter.command("qx.c")
    async def query_level_comments(self, event: AstrMessageEvent):
        """
        查询关卡评论 - /qx.c {level_id} [-ae]

        Args:
            level_id: 关卡ID
            -ae: 导出所有评论为CSV文件（无参默认文本查看）
        """
        args = event.message_str.strip().split(maxsplit=2)
        if len(args) < 2:
            yield event.plain_result("请提供关卡ID")
            yield event.plain_result("用法: /qx.c <关卡ID> [-ae]")
            yield event.plain_result("示例: /qx.c 1001 或 /qx.c 1001 -ae")
            return

        level_id = args[1].strip()
        if not level_id:
            yield event.plain_result("关卡ID不能为空")
            return

        # 解析可选参数
        export_all = False
        if len(args) >= 3:
            opt_arg = args[2].strip()
            if opt_arg == "-ae":
                export_all = True

        if export_all:
            # 导出模式 - 直接输出CSV文件或报错
            success, message, filepath, filename = await self.service.export_comments_csv(level_id)
            if not success or filepath is None or filename is None:
                yield event.plain_result(message)
                return
            yield event.chain_result([Comp.File(file=filepath, name=filename)])
        else:
            # 文本查看模式
            success, message, chain = await self.service.query_level_comments(level_id)
            if not success:
                yield event.plain_result(message)
                return
            if chain is None:
                yield event.plain_result("获取结果为空")
                return
            yield event.chain_result(chain)

    async def terminate(self):
        """插件销毁"""
        logger.info("千星奇域查询插件已卸载")