import asyncio
import csv
import os
import random
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import astrbot.api.message_components as Comp
from astrbot.api import logger

from .api_client import MiyousheAPIClient
from .image_renderer import get_image_renderer


class QxqyService:
    """千星奇域服务层"""

    DEFAULT_PRAISE = "非常优秀的奇域，推荐大家游玩~"
    TEMP_FILE_CLEANUP_DELAY = 300  # 临时文件清理延迟（秒），默认5分钟

    DEFAULT_CONFIG = {
        "comments_count": 30,
        "intro_max_length": 240,
        "comment_max_length": 150,
        "request_timeout": 10,
    }

    def __init__(self, config=None):
        self.config = config if config is not None else {}
        self.api_client = MiyousheAPIClient(
            request_timeout=self._get_config("request_timeout")
        )

    def _get_config(self, key):
        """获取配置项，优先使用用户配置，否则使用默认值"""
        if isinstance(self.config, dict):
            return self.config.get(key, self.DEFAULT_CONFIG[key])
        return self.DEFAULT_CONFIG[key]

    def _safe_get(self, data: Optional[dict], key: str, default="") -> Any:
        """
        安全获取字典值，统一处理None和空字典情况
        
        Args:
            data: 字典数据，可能为None或空字典
            key: 要获取的键名
            default: 默认值，默认为空字符串
        
        Returns:
            字典中对应键的值，如果不存在或data为None则返回默认值
        """
        if data is None:
            return default
        value = data.get(key, default)
        return value if value is not None else default

    async def _schedule_file_cleanup(self, filepath: str, delay: Optional[int] = None):
        """
        延迟清理临时文件
        
        Args:
            filepath: 要清理的文件路径
            delay: 延迟时间（秒），默认为TEMP_FILE_CLEANUP_DELAY
        """
        if delay is None:
            delay = self.TEMP_FILE_CLEANUP_DELAY
        
        await asyncio.sleep(delay)
        
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                logger.info(f"已自动清理临时文件: {filepath}")
            except Exception as e:
                logger.warning(f"清理临时文件失败: {filepath}, 错误: {str(e)}")

    async def query_level_detail(self, level_id: str) -> Tuple[bool, str, Optional[List]]:
        """
        查询关卡详情

        Args:
            level_id: 关卡ID

        Returns:
            (成功状态, 消息, 消息链)
        """
        try:
            data = await self.api_client.get_level_detail(level_id)
            logger.info(f"API响应: {data}")
        except asyncio.TimeoutError:
            return False, "请求超时，请稍后重试", None
        except Exception as e:
            return False, f"网络请求失败: {str(e)}", None

        retcode = data.get("retcode")
        if retcode != 0:
            err_msg = data.get("message", "Unknown error")
            logger.error(f"API错误: retcode={retcode}, message={err_msg}, level_id={level_id}")
            return False, f"API返回错误: retcode={retcode}, {err_msg}", None

        level_info = data.get("data", {}).get("level_info", {})
        if not level_info:
            return False, "未找到该关卡的信息", None

        chain = self._build_level_detail_chain(level_info)
        return True, "", chain

    def _build_level_detail_chain(self, level_info: Dict[str, Any]) -> List:
        """
        构建关卡详情消息链

        Args:
            level_info: 关卡信息字典

        Returns:
            消息链列表
        """
        intro_max_length = self._get_config("intro_max_length")

        level_name = level_info.get("level_name", "未知")
        level_intro = level_info.get("level_intro", "无")
        hot_score = level_info.get("hot_score", "0")
        good_rate = level_info.get("good_rate", "0%")
        cover_url = level_info.get("cover_img", {}).get("url", "")

        chain = []

        if cover_url:
            chain.append(Comp.Image.fromURL(cover_url))

        chain.extend([
            Comp.Plain(f"\n {level_name}\n"),
            Comp.Plain(f"├─ 热度：{hot_score}\n"),
            Comp.Plain(f"├─ 好评率：{good_rate}\n"),
        ])

        if level_intro and level_intro != "无":
            if len(level_intro) > intro_max_length:
                level_intro = level_intro[:intro_max_length] + "..."
            chain.append(Comp.Plain(f"└─ {level_intro}"))

        return chain

    async def query_level_comments(self, level_id: str) -> Tuple[bool, str, Optional[List]]:
        """
        查询关卡评论

        Args:
            level_id: 关卡ID

        Returns:
            (成功状态, 消息, 消息链)
        """
        try:
            comments_count = self._get_config("comments_count")
            reply_list = await self.api_client.get_level_comments(
                level_id, target_count=comments_count
            )
            logger.info(f"评论获取完成，共{len(reply_list)}条")
        except asyncio.TimeoutError:
            return False, "请求超时，请稍后重试", None
        except Exception as e:
            return False, f"网络请求失败: {str(e)}", None

        if not reply_list:
            return False, "该关卡暂无评论", None

        filtered_replies, default_praise_count = self._filter_replies(reply_list)

        if not filtered_replies and default_praise_count == 0:
            return False, "该关卡暂无评论", None

        praise_count = sum(1 for reply in filtered_replies if reply.get("is_recommend", False))
        criticism_count = len(filtered_replies) - praise_count
        total_count = len(filtered_replies) + default_praise_count

        chain = self._build_comments_chain(
            filtered_replies,
            default_praise_count,
            praise_count,
            criticism_count,
            total_count,
            display_count=comments_count
        )
        return True, "", chain

    async def export_comments_csv(self, level_id: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        全量导出关卡评论为CSV文件（流式写入，支持超大文件）

        Args:
            level_id: 关卡ID

        Returns:
            (成功状态, 消息, csv文件路径, 文件名)
        """
        try:
            reply_list = await self.api_client.get_all_comments(level_id)
            logger.info(f"评论全量获取完成，共{len(reply_list)}条")
        except asyncio.TimeoutError:
            return False, "请求超时，请稍后重试", None, None
        except Exception as e:
            return False, f"网络请求失败: {str(e)}", None, None

        if not reply_list:
            return False, "该关卡暂无评论", None, None

        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"qxqy_comments_{level_id}_{timestamp}.csv"
        filepath = os.path.join(temp_dir, filename)

        fieldnames = [
            "floor_id",
            "reply_id",
            "uid",
            "nickname",
            "is_recommend",
            "content",
            "created_at",
            "client_ip",
            "like_count",
            "reply_count",
        ]

        # 流式写入CSV文件，支持超大文件
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for reply in reply_list:
                user_info = self._safe_get(reply, "user_info") or {}
                reply_stat = self._safe_get(reply, "reply_stat") or {}
                
                writer.writerow({
                    "floor_id": self._safe_get(reply, "floor_id"),
                    "reply_id": self._safe_get(reply, "reply_id"),
                    "uid": self._safe_get(user_info, "uid"),
                    "nickname": self._safe_get(user_info, "nickname"),
                    "is_recommend": "是" if self._safe_get(reply, "is_recommend") or False else "否",
                    "content": self._safe_get(reply, "content"),
                    "created_at": self._format_timestamp(self._safe_get(reply, "created_at") or 0),
                    "client_ip": self._safe_get(reply, "client_ip"),
                    "like_count": self._safe_get(reply_stat, "like_count", "0"),
                    "reply_count": self._safe_get(reply_stat, "reply_count", "0"),
                })

        total = len(reply_list)
        praise = sum(1 for r in reply_list if self._safe_get(r, "is_recommend") or False)
        criticism = total - praise

        # 调度临时文件自动清理（异步执行，不阻塞当前流程）
        asyncio.create_task(self._schedule_file_cleanup(filepath,180))
        logger.info(f"已调度临时文件自动清理: {filepath}")

        return True, (
            f"全量评论导出完成\n"
            f"关卡ID：{level_id}\n"
            f"总计：{total} 条（好评 {praise} / 差评 {criticism}）"
        ), filepath, filename

    def _filter_replies(self, reply_list: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """
        过滤评论，排除默认好评

        Args:
            reply_list: 原始评论列表

        Returns:
            (过滤后的评论列表, 默认好评数量)
        """
        filtered_replies = []
        default_praise_count = 0

        for reply in reply_list:
            content = reply.get("content", "").strip()

            if content == self.DEFAULT_PRAISE:
                default_praise_count += 1
                continue

            filtered_replies.append(reply)

        return filtered_replies, default_praise_count

    def _build_comments_chain(
        self,
        filtered_replies: List[Dict[str, Any]],
        default_praise_count: int,
        praise_count: int,
        criticism_count: int,
        total_count: int,
        display_count: int = 30
    ) -> List:
        """
        构建评论消息链

        Args:
            filtered_replies: 过滤后的评论列表
            default_praise_count: 默认好评数量
            praise_count: 好评数量
            criticism_count: 差评数量
            total_count: 总评论数
            display_count: 显示评论数量上限

        Returns:
            消息链列表
        """
        comment_max_length = self._get_config("comment_max_length")

        chain = []
        chain.append(
            Comp.Plain(
                f"最近的{total_count}条评论（好评{praise_count + default_praise_count}条，差评{criticism_count}条）\n\n"
            )
        )

        for idx, reply in enumerate(filtered_replies[:display_count], 1):
            user_info = reply.get("user_info", {})
            nickname = user_info.get("nickname", "匿名用户") if user_info else "匿名用户"
            uid = user_info.get("uid", "0") if user_info else "0"
            content = reply.get("content", "")
            created_at = reply.get("created_at", 0)
            is_recommend = reply.get("is_recommend", False)

            time_str = self._format_timestamp(created_at)

            if len(content) > comment_max_length:
                content = content[:comment_max_length] + "..."

            recommend_icon = "👍" if is_recommend else "👎"
            if idx > 1:
                chain.append(Comp.Plain("\n"))
            chain.append(Comp.Plain(f"{recommend_icon} {idx}. {nickname} | UID:{uid} | {time_str}\n"))
            chain.append(Comp.Plain(f"   {content}\n"))

        if default_praise_count > 0:
            chain.append(Comp.Plain(f"[默认好评 x{default_praise_count}] {self.DEFAULT_PRAISE}"))

        return chain

    def _format_timestamp(self, timestamp: int) -> str:
        """
        格式化时间戳

        Args:
            timestamp: 时间戳

        Returns:
            格式化后的时间字符串
        """
        if timestamp > 0:
            try:
                return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
            except Exception:
                return ""
        return ""

    async def generate_level_image(self, level_id: str) -> Tuple[bool, str, Optional[str]]:
        """
        生成关卡详情图片

        Args:
            level_id: 关卡ID

        Returns:
            (成功状态, 消息, 图片文件路径)
        """
        logger.info(f"[图片生成] 开始处理关卡ID: {level_id}")
        
        try:
            logger.info(f"[图片生成] 步骤1: 调用API获取关卡详情")
            data = await self.api_client.get_level_detail(level_id)
            logger.info(f"[图片生成] 步骤1完成: API响应状态码: {data.get('retcode')}")
        except asyncio.TimeoutError:
            logger.error(f"[图片生成] 步骤1失败: 请求超时")
            return False, "请求超时，请稍后重试", None
        except Exception as e:
            logger.error(f"[图片生成] 步骤1失败: 网络请求失败 - {str(e)}")
            return False, f"网络请求失败: {str(e)}", None

        retcode = data.get("retcode")
        if retcode != 0:
            err_msg = data.get("message", "Unknown error")
            logger.error(f"[图片生成] API错误: retcode={retcode}, message={err_msg}, level_id={level_id}")
            return False, f"API返回错误: retcode={retcode}, {err_msg}", None

        level_info = data.get("data", {}).get("level_info", {})
        if not level_info:
            logger.warning(f"[图片生成] 未找到关卡ID {level_id} 的信息")
            return False, "未找到该关卡的信息", None

        try:
            logger.info(f"[图片生成] 步骤2: 读取HTML模板")
            # 获取插件目录
            plugin_dir = Path(__file__).parent.parent
            template_path = plugin_dir / "templates" / "level_card.html"

            if not template_path.exists():
                logger.error(f"[图片生成] 步骤2失败: 模板文件不存在 - {template_path}")
                return False, f"模板文件不存在: {template_path}", None

            # 读取模板
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            logger.info(f"[图片生成] 步骤2完成: 模板文件读取成功，大小: {len(template)} 字符")

            logger.info(f"[图片生成] 步骤3: 准备模板变量")
            # 准备模板变量
            level_name = self._safe_get(level_info, "level_name", "未知关卡")
            level_intro = self._safe_get(level_info, "level_intro", "暂无简介")
            hot_score = str(self._safe_get(level_info, "hot_score", "0"))
            good_rate = self._safe_get(level_info, "good_rate", "0%")
            cover_img = self._safe_get(level_info, "cover_img") or {}
            cover_url = cover_img.get("url", "") if isinstance(cover_img, dict) else ""

            # 截断过长的简介
            intro_max_length = self._get_config("intro_max_length")
            if len(level_intro) > intro_max_length:
                level_intro = level_intro[:intro_max_length] + "..."

            # 随机背景图和主题色
            bg_url = self._get_background_url(cover_url)
            theme_color = self._get_theme_color()
            bg_x = random.randint(0, 100)
            bg_y = random.randint(0, 100)
            bg_position = f"{bg_x}% {bg_y}%"
            logger.info(f"[图片生成] 步骤3完成: 关卡名称={level_name}, 热度={hot_score}, 好评率={good_rate}")

            logger.info(f"[图片生成] 步骤4: 替换模板变量")
            # 替换模板变量
            html_content = template.replace("{{level_id}}", level_id)
            html_content = html_content.replace("{{level_name}}", level_name)
            html_content = html_content.replace("{{level_intro}}", level_intro)
            html_content = html_content.replace("{{hot_score}}", hot_score)
            html_content = html_content.replace("{{good_rate}}", good_rate)
            html_content = html_content.replace("{{bg_url}}", bg_url)
            html_content = html_content.replace("{{theme_color}}", theme_color)
            html_content = html_content.replace("{{bg_position}}", bg_position)
            logger.info(f"[图片生成] 步骤4完成: HTML内容生成成功，大小: {len(html_content)} 字符")

            logger.info(f"[图片生成] 步骤5: 生成临时图片文件")
            # 生成临时图片文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"qxqy_level_{level_id}_{timestamp}.png"
            output_path = os.path.join(tempfile.gettempdir(), filename)
            logger.info(f"[图片生成] 输出路径: {output_path}")

            logger.info(f"[图片生成] 步骤6: 使用Playwright渲染图片")
            # 使用图片渲染器生成图片（横版 16:9，4K 分辨率）
            renderer = get_image_renderer()
            await renderer.render_to_file(
                html_content=html_content,
                output_path=output_path
            )
            logger.info(f"[图片生成] 步骤6完成: 图片渲染成功")

            # 调度临时文件自动清理
            asyncio.create_task(self._schedule_file_cleanup(output_path, 300))
            logger.info(f"[图片生成] 已调度临时图片自动清理（5分钟后）: {output_path}")

            logger.info(f"[图片生成] 完成: 关卡ID={level_id}, 图片路径={output_path}")
            return True, "关卡图片生成成功", output_path

        except Exception as e:
            logger.error(f"[图片生成] 失败: {str(e)}")
            logger.error(f"[图片生成] 异常堆栈:\n{traceback.format_exc()}")
            return False, f"生成图片失败: {str(e)}", None

    def _get_background_url(self, cover_url: str) -> str:
        """
        获取背景图 URL

        Args:
            cover_url: 关卡封面图 URL

        Returns:
            背景图 URL
        """
        # 优先使用关卡封面图
        if cover_url:
            return cover_url

        # 回退到默认背景图（使用横版渐变 SVG，16:9 比例）
        return "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%221280%22 height=%22720%22%3E%3Cdefs%3E%3ClinearGradient id=%22grad%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 style=%22stop-color:%231a1a2e;stop-opacity:1%22/%3E%3Cstop offset=%22100%25%22 style=%22stop-color:%2316213e;stop-opacity:1%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect fill=%22url(%23grad)%22 width=%22100%25%22 height=%22100%25%22/%3E%3C/svg%3E"

    def _get_theme_color(self) -> str:
        """
        获取随机主题色

        Returns:
            主题色十六进制值
        """
        theme_colors = [
            "#2F4F4F",  # 深石板灰
            "#4B0082",  # 靛蓝
            "#006400",  # 深绿
            "#8B0000",  # 深红
            "#2F2F4F",  # 深紫蓝
            "#4A4A6A",  # 灰紫
            "#1a1a2e",  # 深夜蓝
            "#16213e",  # 海军蓝
            "#0f3460",  # 深蓝
            "#533483",  # 紫罗兰
        ]
        return random.choice(theme_colors)