# emby-poster (Emby 媒体库封面自动化引擎)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Docker Support](https://img.shields.io/badge/Docker-Supported-2496ED.svg)](https://www.docker.com/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)

## 📖 项目简介

**emby-poster** 是一款针对 Emby 媒体服务器深度定制的封面自动化排版与同步引擎。该项目旨在解决 Emby 媒体库主视觉单调的问题，通过调用 Emby REST API，自动检索媒体库最新入库的影视元数据。

引擎利用底层图像处理技术，将提取的背景图与海报进行无缝融合，动态生成极具现代画廊风格的 16:9 主封面，并通过 Base64 编码安全地回传至 Emby 服务器。项目采用“无状态容器（Run-and-Exit）”设计理念，完美适配宿主机系统级 Cron 定时任务，实现极低资源占用的“零维护”全自动美化体验。

---

## 🏗️ 架构与核心特性

* **自动化数据流闭环**：鉴权检索 -> 素材分块下载 -> 内存图层渲染 -> Base64 编码回传，全过程零人工干预。
* **高容错顺延机制 (Fallback)**：内置超额备用数据池（默认 20 部），智能识别并跳过损坏、过大或超时的图像源，保证封面产出的绝对完整性。
* **专业级视觉合成引擎**：
  * **动态底层渲染**：自适应提取横版/竖版素材，应用高斯模糊剥离背景干扰。
  * **几何排版算法**：在 1920x1080 坐标系内，实现海报等距、垂直对齐、15px 圆角裁剪及极限边距控制。
  * **UI 增强层**：叠加线性渐变遮罩（Gradient Overlay）与随机半透明粒子（Snow Effect）特效。
* **极简容器化部署**：核心代码已打包至 Docker Hub，用户仅需维护一份配置文件即可开箱即用。
* **企业级安全实践**：采用 `.env` 环境变量隔离敏感 API 凭证，防止泄漏。

---

## 🚀 详细部署与运行指南

推荐使用 `docker-compose` 进行部署。

### 1. 初始化项目目录
在您的宿主机（如 Linux VPS、群晖 NAS）中创建一个空目录作为项目根目录，并进入该目录：
```bash
mkdir emby-poster && cd emby-poster
mkdir fonts input output

```

最终的项目目录结构如下：

```text
emby-poster/
├── .env                 # 环境变量文件 (存放 API Key)
├── docker-compose.yml   # 容器编排文件
├── config.py            # 核心排版与媒体库配置文件
├── fonts/               # 字体目录 (需手动放入字体文件)
│   ├── zh_font.ttf      
│   └── en_font.otf      
├── input/               # 运行时素材缓存 (自动生成内容)
└── output/              # 预览封面输出目录 (自动生成内容)

```

### 2. 配置安全凭证 (.env)

在项目根目录新建隐藏文件 `.env`，填入您的真实服务器信息：

```ini
EMBY_URL=http://your-emby-server-ip:8096
EMBY_API_KEY=your_emby_api_key_here

```

### 3. 创建容器编排文件 (docker-compose.yml)

在根目录创建 `docker-compose.yml` 文件，直接拉取官方云端镜像：

```yaml
version: '3.8'

services:
  cover-generator:
    image: steven03799/emby-poster:latest
    container_name: emby-poster
    environment:
      - PYTHONUNBUFFERED=1       # 强制控制台实时打印日志
      - EMBY_URL=${EMBY_URL}
      - EMBY_API_KEY=${EMBY_API_KEY}
    volumes:
      - ./fonts:/app/fonts       # 挂载字体文件
      - ./input:/app/input       # 挂载输入缓存
      - ./output:/app/output     # 挂载输出目录
      - ./config.py:/app/config.py # 挂载自定义配置文件

```

### 4. 准备字体文件与配置文件

1. **准备字体**：请准备两款您喜欢的字体文件，分别重命名为 `zh_font.ttf` (中文字体) 和 `en_font.otf` (英文字体)，并将它们放入 `./fonts/` 文件夹中。
2. **准备配置**：将项目源码中的 `config.py` 文件下载或创建到当前项目根目录中，并根据您的实际媒体库名称修改 `LIBRARY_MAP`（详见下文配置解析）。

### 5. 首次预览运行 (Preview Mode)

为了校验视觉排版效果，建议首次运行时关闭 API 上传功能。
打开 `config.py`，确保：

```python
UPLOAD_TO_EMBY = False

```

在终端执行容器启动命令：

```bash
docker-compose up -d

```

> **提示**：系统会自动拉取镜像并执行任务，运行日志将在控制台流式输出。完成后容器会自动退出（Exited）。此时，请前往 `./output` 文件夹查看生成的 `cover_xxx.jpg` 预览图是否符合预期。

### 6. 生产上线与自动化调度 (Production Mode)

当确认排版无误后，打开 `config.py`，启用上传功能：

```python
UPLOAD_TO_EMBY = True

```

**【系统级极简调度方案】**
本引擎采用单次执行模式（运行完毕即释放内存）。您只需在宿主机系统（如 Linux `crontab` 或群晖“任务计划”）中配置定时唤醒指令。

**Crontab 示例（每天凌晨 02:00 自动触发全库更新并覆盖 Emby 封面）：**

```bash
0 2 * * * docker start emby-poster

```

---

## ⚙️ 核心参数字典解析 (`config.py`)

本工具提供高自由度的自定义配置选项，通过修改宿主机的 `config.py` 即可实时生效。

### 核心控制变量

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| `UPLOAD_TO_EMBY` | `bool` | **触发动作开关**。<br>

<br>`True`: 生成后直接调用 API 覆写服务端封面。<br>

<br>`False`: 仅在本地 `./output` 生成测试图。 |
| `UPDATE_INTERVAL_HOURS` | `int` | **运行模式选择**。<br>

<br>建议保持为 `0`：单次任务模式，执行完毕后容器自动退出，搭配宿主机 Cron 使用，极致节省内存。 |

### 数据映射表 (`LIBRARY_MAP`)

用于定义目标媒体库及其中英文标题映射。系统启动后将**自动遍历**该字典内的所有项目进行批量处理。

```python
LIBRARY_MAP = {
    "动画电影": {"zh": "动画电影", "en": "ANIME\nMovies"},
    # 键名 ("动画电影"): 必须与 Emby 服务器中显示的媒体库名称完全一致。
    # "zh": 生成封面的左侧大标题。
    # "en": 生成封面的英文小标题，支持使用 \n 强制换行排版。
}

```

### 图像视觉引擎参数 (`CONFIG`)

## ⚙️ 核心参数配置指南 (`config.py`)

本引擎所有的行为控制和视觉排版均通过外挂的 `config.py` 动态接管，修改保存后即刻生效，无需重新构建容器。

### 1. 运行与行为控制
| 参数名 | 类型 | 描述与建议 |
| :--- | :---: | :--- |
| `UPLOAD_TO_EMBY` | `bool` | **上传开关**。`True`: 直接调用 API 覆写服务端封面；`False`: 仅在本地 `./output` 目录生成测试图（强烈建议首次部署排版时设为 False）。 |
| `UPDATE_INTERVAL_HOURS` | `int` | **常驻运行间隔**。设为 `0` 代表**单次执行模式**（极力推荐，配合宿主机 Crontab 使用）；设为 `>0` 的整数，则容器将常驻内存，按该小时数循环执行。 |
| `COVER_STYLE` | `str` | **排版引擎切换**。可选 `"style_1"` (经典平铺瀑布流) 或 `"style_2"` (动感大画幅阶梯墙)。 |

### 2. 媒体库映射 (`LIBRARY_MAP`)
用于精准匹配 Emby 服务端与生成的封面标题。只有在此字典中定义的媒体库才会被引擎处理。

```python
LIBRARY_MAP = {
    "动画电影": {"zh": "动画电影", "en": "ANIME\nMOVIE"},
}

```

* **键名 (`"动画电影"`)**: 必须与您在 Emby 后台创建的媒体库名称**完全一致**。
* **`zh`**: 封面渲染的中文主标题。
* **`en`**: 封面渲染的英文副标题（支持使用 `\n` 进行强制换行以对齐排版）。

### 3. 双引擎视觉参数 (`CONFIG`)

#### 全局基础画幅

| 参数名 | 默认值 | 描述 |
| --- | --- | --- |
| `output_size` | `(1920, 1080)` | 最终合成封面的全局画布分辨率 (宽, 高)。 |
| `font_zh_path` | `"./fonts/zh_font.ttf"` | 中文主标题的字体挂载路径。 |
| `font_en_path` | `"./fonts/en_font.otf"` | 英文副标题的字体挂载路径。 |

#### [Style_1] 经典平铺瀑布流专属参数

*该模式将抓取横版剧照作为模糊背景，下方水平排列 6 张竖版海报。*

| 参数名 | 默认值 | 描述 |
| --- | --- | --- |
| `s1_text_pos_zh` | `(100, 100)` | 中文主标题的绝对坐标 (X, Y)。 |
| `s1_poster_size` | `(280, 420)` | 底部单张竖版海报的渲染尺寸。 |
| `s1_poster_spacing` | `20` | 海报之间的水平间距。 |
| `s1_poster_y_pos` | `610` | 整个海报矩阵顶端在画布上的垂直 Y 轴起始坐标。 |
| `s1_blur_percent` | `5` | 背景图的高斯模糊强度 (0-100)，数值越大背景越模糊。 |
| `s1_snow_enable` | `True` | 是否在背景层上方叠加随机雪花/噪点粒子特效。 |

#### [Style_2] 大画幅倾斜阶梯专属参数

*该模式将提取主色调作为背景，右侧渲染倾斜 15° 的 3x3 巨幅阶梯海报墙。*

| 参数名 | 默认值 | 描述 |
| --- | --- | --- |
| `s2_poster_size` | `(400, 600)` | 阶梯墙单张海报的渲染尺寸（默认设定为大画幅）。 |
| `s2_poster_stagger` | `180` | **阶梯落差**。每一列海报向下错位的垂直距离。 |
| `s2_poster_rotation` | `-15` | **全局倾斜度**。负数代表顺时针倾斜的角度。 |
| `s2_poster_center` | `(1600, 540)` | 🎯 **核心锚点**。定义海报墙绝对中心点在画布上的位置。可通过微调此数值移动整个海报墙（例如将 X 改为 1500 则整体左移）。 |
| `s2_accent_bar_enable` | `True` | 是否在英文标题左侧渲染起强调作用的亮色竖向装饰条。 |
| `s2_bg_auto_color` | `True` | **智能取色开关**。开启后自动从第一张海报提取主色并压暗作为背景。 |

### 4. 服务端连接凭证 (`EMBY_CONFIG`)

为保证极高的安全性，建议**不要**在此处直接硬编码明文，而是使用 `.env` 环境变量注入：

* `EMBY_URL`: 服务器 API 根地址 (例如: `http://192.168.1.100:8096`)
* `EMBY_API_KEY`: Emby 控制台生成的专用 API 令牌。


## 图片展示

<p align="center">
  <table border="0" cellspacing="0" cellpadding="0">
    <tr>
      <td align="center">
        <img src="./images/cover_外语电影.jpg" alt="封面演示1" width="90%">
      </td>
      <td align="center">
        <img src="./images/cover_外语剧集.jpg" alt="封面演示2" width="90%">
      </td>
    </tr>
  </table>
</p>
