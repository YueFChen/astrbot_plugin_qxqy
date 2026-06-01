import aiohttp
import asyncio
from typing import Dict, Any, List

from astrbot.api import logger

MIYOUSHE_BASE_URL = "https://bbs-api.miyoushe.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin": "https://act.miyoushe.com",
    "Referer": "https://act.miyoushe.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "x-rpc-client_type": "5",
    "x-rpc-language": "zh-cn",
    "DNT": "1",
    "Sec-GPC": "1"
}

PAGE_SIZE = 20
PAGE_DELAY = 0.5
MAX_PAGES = 500


class MiyousheAPIClient:
    """米游社 API 客户端"""

    DEFAULT_TIMEOUT = 10

    def __init__(self, request_timeout: int = DEFAULT_TIMEOUT):
        self.base_url = MIYOUSHE_BASE_URL
        self.headers = HEADERS
        self.request_timeout = request_timeout

    async def get_level_detail(self, level_id: str) -> Dict[str, Any]:
        """
        获取关卡详情

        Args:
            level_id: 关卡ID

        Returns:
            API响应数据

        Raises:
            asyncio.TimeoutError: 请求超时
            aiohttp.ClientError: 网络请求失败
            Exception: 其他错误
        """
        url = f"{self.base_url}/community/ugc_community/web/api/level/detail"
        params = {
            "level_id": level_id,
            "uid": "",
            "region": "cn_gf01",
            "lang": "zh-cn"
        }

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(
                url,
                headers=self.headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.request_timeout)
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP状态码: {resp.status}")
                return await resp.json()

    def _make_initial_cursor(self, size: int, sort_type: str) -> Dict[str, Any]:
        return {
            "next": "",
            "size": size,
            "sort_type": sort_type,
            "has_more": True
        }

    async def _get_comments_page(
        self,
        level_id: str,
        cursor: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        获取单页评论数据

        Args:
            level_id: 关卡ID
            cursor: 分页游标对象

        Returns:
            单页API响应数据
        """
        url = f"{self.base_url}/community/ugc_community/web/api/reply/list?lang=zh-cn"
        payload = {
            "uid": "",
            "region": "cn_gf01",
            "level_id": level_id,
            "cursor": cursor
        }

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.request_timeout)
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP状态码: {resp.status}")
                return await resp.json()

    async def get_level_comments(
        self,
        level_id: str,
        target_count: int = 30,
        sort_type: str = "SORT_TYPE_FLOOR_DESC"
    ) -> List[Dict[str, Any]]:
        """
        分页获取关卡评论，收集到 target_count 条或翻到底为止

        Args:
            level_id: 关卡ID
            target_count: 目标获取数量
            sort_type: 排序类型

        Returns:
            评论列表

        Raises:
            asyncio.TimeoutError: 请求超时
            aiohttp.ClientError: 网络请求失败
            Exception: 其他错误
        """
        all_replies = []
        cursor = self._make_initial_cursor(PAGE_SIZE, sort_type)
        page = 0

        while len(all_replies) < target_count:
            page += 1
            data = await self._get_comments_page(level_id, cursor)

            retcode = data.get("retcode")
            if retcode != 0:
                raise Exception(
                    f"API返回错误: retcode={retcode}, {data.get('message', '')}"
                )

            page_data = data.get("data", {})
            reply_list = page_data.get("reply_list", [])
            if not reply_list:
                logger.warning(f"[分页抓取] 关卡{level_id} 第{page}页返回空列表，终止抓取")
                break

            all_replies.extend(reply_list)
            logger.info(f"[分页抓取] 关卡{level_id} 第{page}页 +{len(reply_list)}条，已累计 {len(all_replies)}/{target_count}")

            cursor = page_data.get("cursor", {})
            if not cursor.get("has_more", False):
                break

            await asyncio.sleep(PAGE_DELAY)

        return all_replies[:target_count]

    async def get_all_comments(
        self,
        level_id: str,
        sort_type: str = "SORT_TYPE_HOT"
    ) -> List[Dict[str, Any]]:
        """
        全量获取关卡所有评论

        Args:
            level_id: 关卡ID
            sort_type: 排序类型

        Returns:
            全部评论列表

        Raises:
            asyncio.TimeoutError: 请求超时
            aiohttp.ClientError: 网络请求失败
            Exception: 其他错误
        """
        all_replies = []
        cursor = self._make_initial_cursor(PAGE_SIZE, sort_type)
        page = 0

        while page < MAX_PAGES:
            page += 1
            data = await self._get_comments_page(level_id, cursor)

            retcode = data.get("retcode")
            if retcode != 0:
                raise Exception(
                    f"API返回错误: retcode={retcode}, {data.get('message', '')}"
                )

            page_data = data.get("data", {})
            reply_list = page_data.get("reply_list", [])
            if not reply_list:
                logger.warning(f"[全量抓取] 关卡{level_id} 第{page}页返回空列表，终止抓取")
                break

            all_replies.extend(reply_list)

            cursor = page_data.get("cursor", {})
            has_more = cursor.get("has_more", False)
            logger.info(f"[全量抓取] 关卡{level_id} 第{page}页 +{len(reply_list)}条，已累计 {len(all_replies)} 条{' (已到底)' if not has_more else ''}")

            if not has_more:
                break

            await asyncio.sleep(PAGE_DELAY)
        else:
            logger.warning(f"[全量抓取] 关卡{level_id} 已达最大页数 {MAX_PAGES}，强制终止")

        return all_replies
