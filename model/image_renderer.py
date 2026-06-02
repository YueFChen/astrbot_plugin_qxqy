# -*- coding: utf-8 -*-
"""
图片渲染器 - 使用 Playwright 将 HTML 转换为图片

纯 pip 依赖，首次运行自动安装 Chromium 浏览器。
"""

import subprocess
import tempfile
import logging
import asyncio
from pathlib import Path
from typing import Optional, Tuple
from threading import Lock

logger = logging.getLogger(__name__)

# 渲染器常量配置
RENDERER_DEFAULT_WIDTH = 1280
RENDERER_DEFAULT_HEIGHT = 720
RENDERER_DEFAULT_SCALE = 2
RENDERER_LOAD_TIMEOUT = 15000
RENDERER_WAIT_DELAY = 2000

# 浏览器安装标记和锁
_browser_installed = False
_browser_install_lock = Lock()


async def _ensure_browser_installed() -> None:
    """确保 Chromium 浏览器已安装（内部函数，线程安全）"""
    global _browser_installed
    if _browser_installed:
        return

    # 使用锁防止并发安装
    with _browser_install_lock:
        # 双重检查锁定
        if _browser_installed:
            return

        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                await browser.close()
            _browser_installed = True
            logger.info("Chromium 浏览器已就绪")
        except Exception:
            logger.info("首次运行，正在安装 Chromium 浏览器...")
            try:
                process = await asyncio.create_subprocess_exec(
                    "playwright", "install", "chromium",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.wait()
                _browser_installed = True
                logger.info("Chromium 浏览器安装完成")
            except Exception as e:
                logger.error(f"安装 Chromium 失败: {e}")
                raise RuntimeError(
                    "无法安装 Chromium 浏览器，请手动运行: playwright install chromium"
                )


class ImageRenderer:
    """
    图片渲染器

    使用 Playwright (Chromium) 将 HTML 渲染为 PNG 图片。
    纯 pip 依赖，首次运行自动安装浏览器。

    示例用法:
        renderer = ImageRenderer()
        await renderer.render_to_file(html_content, output_path)
    """

    def __init__(self) -> None:
        """初始化渲染器"""
        logger.info("ImageRenderer 初始化完成 (Playwright Async)")

    async def render_to_file(
        self,
        html_content: str,
        output_path: str,
        width: int = RENDERER_DEFAULT_WIDTH,
        height: int = RENDERER_DEFAULT_HEIGHT,
        scale: int = RENDERER_DEFAULT_SCALE
    ) -> str:
        """
        将 HTML 渲染为 PNG 图片文件

        Args:
            html_content: HTML 内容字符串
            output_path: 输出图片路径
            width: 渲染宽度（像素），默认 1280（横版 16:9）
            height: 渲染高度（像素），默认 720（横版 16:9）
            scale: 设备像素比，默认 2（生成 2560x1440 4K 图片）

        Returns:
            输出图片的绝对路径
        """
        logger.info(f"[渲染器] 开始渲染图片: width={width}, height={height}, scale={scale}")
        
        logger.info(f"[渲染器] 步骤1: 确保浏览器已安装")
        await _ensure_browser_installed()
        from playwright.async_api import async_playwright
        logger.info(f"[渲染器] 步骤1完成: 浏览器就绪")

        # 写入临时 HTML 文件
        try:
            logger.info(f"[渲染器] 步骤2: 创建临时HTML文件")
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.html', delete=True, encoding='utf-8'
            ) as f:
                f.write(html_content)
                f.flush()
                temp_file_path = f.name
                logger.info(f"[渲染器] 步骤2完成: 临时文件创建成功 - {temp_file_path}")

                browser = None
                try:
                    logger.info(f"[渲染器] 步骤3: 启动Chromium浏览器")
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(headless=True)
                        logger.info(f"[渲染器] 步骤3完成: 浏览器启动成功")

                        logger.info(f"[渲染器] 步骤4: 创建新页面")
                        page = await browser.new_page(
                            viewport={"width": width, "height": height},
                            device_scale_factor=scale
                        )
                        logger.info(f"[渲染器] 步骤4完成: 页面创建成功")

                        logger.info(f"[渲染器] 步骤5: 加载HTML内容")
                        await page.goto(Path(temp_file_path).as_uri())
                        logger.info(f"[渲染器] 步骤5完成: HTML加载成功")

                        # 等待页面和资源加载完成
                        logger.info(f"[渲染器] 步骤6: 等待页面加载完成")
                        await self._wait_for_page_load(page)
                        logger.info(f"[渲染器] 步骤6完成: 页面加载完成")

                        # 截图保存到文件
                        logger.info(f"[渲染器] 步骤7: 截图并保存到文件 - {output_path}")
                        await page.screenshot(path=output_path, type="png", scale="device")
                        logger.info(f"[渲染器] 步骤7完成: 截图成功")

                    logger.info(f"[渲染器] 渲染完成: {output_path}")
                    return output_path
                except Exception as e:
                    logger.error(f"[渲染器] 渲染图片失败: {e}")
                    raise
                finally:
                    # 确保浏览器实例被正确关闭
                    if browser:
                        try:
                            logger.info(f"[渲染器] 关闭浏览器实例")
                            await browser.close()
                            logger.info(f"[渲染器] 浏览器关闭成功")
                        except Exception as close_e:
                            logger.error(f"[渲染器] 关闭浏览器失败: {close_e}")
        except Exception as e:
            logger.error(f"[渲染器] 创建临时HTML文件失败: {e}")
            raise

    async def render_to_bytes(
        self,
        html_content: str,
        width: int = RENDERER_DEFAULT_WIDTH,
        height: int = RENDERER_DEFAULT_HEIGHT,
        scale: int = RENDERER_DEFAULT_SCALE
    ) -> bytes:
        """
        将 HTML 渲染为 PNG 图片字节

        Args:
            html_content: HTML 内容字符串
            width: 渲染宽度（像素），默认 1280（横版 16:9）
            height: 渲染高度（像素），默认 720（横版 16:9）
            scale: 设备像素比，默认 2（生成 2560x1440 4K 图片）

        Returns:
            PNG 图片字节数据
        """
        await _ensure_browser_installed()
        from playwright.async_api import async_playwright

        temp_html = None
        try:
            # 写入临时 HTML 文件
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.html', delete=False, encoding='utf-8'
            ) as f:
                f.write(html_content)
                temp_html = Path(f.name)

            browser = None
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page(
                        viewport={"width": width, "height": height},
                        device_scale_factor=scale
                    )
                    await page.goto(temp_html.as_uri())

                    # 等待页面和资源加载完成
                    await self._wait_for_page_load(page)

                    # 截图返回字节
                    image_bytes = await page.screenshot(type="png", scale="device")

                return image_bytes
            except Exception as e:
                logger.error(f"渲染图片失败: {e}")
                raise
            finally:
                # 确保浏览器实例被正确关闭
                if browser:
                    try:
                        await browser.close()
                    except Exception as close_e:
                        logger.error(f"关闭浏览器失败: {close_e}")
        except Exception as e:
            logger.error(f"创建临时HTML文件失败: {e}")
            raise
        finally:
            # 确保临时文件被清理
            if temp_html and temp_html.exists():
                try:
                    temp_html.unlink()
                except Exception as unlink_e:
                    logger.error(f"删除临时文件失败: {unlink_e}")

    async def _wait_for_page_load(self, page) -> None:
        """
        等待页面加载完成（内部方法）

        Args:
            page: Playwright Page 对象
        """
        try:
            await page.wait_for_load_state("networkidle", timeout=RENDERER_LOAD_TIMEOUT)
        except Exception as e:
            logger.debug(f"网络空闲等待超时: {e}")
        await page.wait_for_timeout(RENDERER_WAIT_DELAY)


# 全局单例实例（延迟初始化）
_renderer_instance: Optional[ImageRenderer] = None


def get_image_renderer() -> ImageRenderer:
    """
    获取全局图片渲染器实例（单例模式）

    Returns:
        ImageRenderer 单例实例
    """
    global _renderer_instance
    if _renderer_instance is None:
        _renderer_instance = ImageRenderer()
    return _renderer_instance


def create_image_renderer() -> ImageRenderer:
    """
    创建新的图片渲染器实例（非单例）

    Returns:
        新的 ImageRenderer 实例
    """
    return ImageRenderer()