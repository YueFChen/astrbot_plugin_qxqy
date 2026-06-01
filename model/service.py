import asyncio
import csv
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import astrbot.api.message_components as Comp
from astrbot.api import logger

from .api_client import MiyousheAPIClient


class QxqyService:
    """千星奇域服务层"""

    DEFAULT_PRAISE = "非常优秀的奇域，推荐大家游玩~"

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
        全量导出关卡评论为CSV文件

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

        import tempfile

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

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for reply in reply_list:
                user_info = reply.get("user_info", {}) or {}
                reply_stat = reply.get("reply_stat", {}) or {}
                writer.writerow({
                    "floor_id": reply.get("floor_id", ""),
                    "reply_id": reply.get("reply_id", ""),
                    "uid": user_info.get("uid", ""),
                    "nickname": user_info.get("nickname", ""),
                    "is_recommend": "是" if reply.get("is_recommend") else "否",
                    "content": reply.get("content", ""),
                    "created_at": self._format_timestamp(reply.get("created_at", 0)),
                    "client_ip": reply.get("client_ip", ""),
                    "like_count": reply_stat.get("like_count", "0"),
                    "reply_count": reply_stat.get("reply_count", "0"),
                })

        total = len(reply_list)
        praise = sum(1 for r in reply_list if r.get("is_recommend"))
        criticism = total - praise
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