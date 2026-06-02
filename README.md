# 千星助手 (astrbot_plugin_qxqy)

基于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的奇域（原神·千星奇域）关卡查询插件。查询关卡详情、评论，并支持全量评论 CSV 导出和关卡图片生成。

## 功能

| 功能 | 命令 | 参数 | 说明 |
|------|------|------|------|
| 关卡详情 | `/qx.i {level_id}` | `-p` | 查看关卡详情，-p 参数生成图片输出 |
| 评论预览 | `/qx.c {level_id}` | `-ae` | 查看最新评论，-ae 参数导出 CSV |

### 命令参数说明

- `-p`：生成关卡图片（配合 `/qx.i` 使用）
- `-ae`：导出全量评论为 CSV 文件（配合 `/qx.c` 使用）

### 使用示例

```bash
# 查询关卡详情（文本模式）
/qx.i 1001

# 查询关卡详情（图片模式）
/qx.i 1001 -p

# 查看关卡评论（文本模式）
/qx.c 1001

# 导出全量评论（CSV模式）
/qx.c 1001 -ae
```

### 全量导出 CSV 字段

| 列名 | 说明 |
|------|------|
| floor_id | 楼层号 |
| reply_id | 评论 ID |
| uid | 用户 UID |
| nickname | 用户昵称 |
| is_recommend | 推荐（是/否） |
| content | 评论内容 |
| created_at | 创建时间 |
| client_ip | IP 归属地 |
| like_count | 点赞数 |
| reply_count | 回复数 |

## 配置

插件支持在 AstrBot WebUI 管理面板中直接配置：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| comments_count | int | 30 | 每次预览获取评论数量 |
| intro_max_length | int | 240 | 关卡简介最大显示长度 |
| comment_max_length | int | 150 | 每条评论最大显示长度 |
| request_timeout | int | 10 | API 请求超时时间（秒） |

## 安装

在 AstrBot WebUI 插件市场搜索 `astrbot_plugin_qxqy` 安装，或手动克隆到 `data/plugins/` 目录：

```bash
cd data/plugins
git clone https://github.com/YueFChen/astrbot_plugin_qxqy.git
```

首次运行会自动安装 Chromium 浏览器用于图片渲染。

## 项目结构

```
astrbot_plugin_qxqy/
├── main.py               # 插件入口（命令声明与调度）
├── _conf_schema.json     # 插件配置 Schema
├── command.json          # 命令定义（用于插件市场展示）
├── metadata.yaml         # 插件元数据
├── requirements.txt      # Python 依赖声明
├── model/
│   ├── __init__.py       # 模块导出
│   ├── api_client.py     # 米游社 API 客户端（HTTP 请求）
│   ├── service.py        # 业务逻辑层（数据处理与消息构建）
│   └── image_renderer.py # 图片渲染器（使用 Playwright）
└── templates/
    └── level_card.html   # 关卡卡片 HTML 模板
```

## 数据来源

数据来自 [米游社](https://m.bbs.miyoushe.com) 奇域 UGC 社区 API。

## License

AGPL-3.0-or-later