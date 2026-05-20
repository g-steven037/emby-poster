# Emby Cover Generator (Emby 媒体库封面自动生成器)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Docker Support](https://img.shields.io/badge/Docker-Supported-2496ED.svg)](https://www.docker.com/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)

## 📖 项目简介

**Emby Cover Generator** 是一款专为 Emby 媒体服务器设计的全自动化封面生成与同步工具。该项目通过调用 Emby REST API，自动抓取指定媒体库中最新入库的影视元数据与图像素材，利用底层图像处理技术（PIL）将背景图与海报墙进行无缝融合，最终生成极具现代感与画廊风格的 16:9 媒体库主封面。

本项目全面适配 Docker 容器化部署，采用“即用即毁（Run-and-Exit）”的无状态设计理念，完美契合宿主机的系统级 Cron 定时任务，实现极低资源占用的全自动化运维。

---

## ✨ 核心特性

* **全自动元数据提取**
  无需人工干预，系统自动连接 Emby 服务端，按入库时间倒序检索最新影视项目，智能区分并拉取横版背景图（Backdrop）与竖版海报（Primary）。
* **高级图像合成引擎**
  * **动态视觉层**：自动对背景图应用高斯模糊处理，突出前景主体。
  * **几何与排版算法**：支持动态计算海报墙间距，精准应用圆角遮罩（Alpha Masking），在标准 1080P 画布上实现等距、居中的完美排列。
  * **对比度增强**：内置由深至浅的线性渐变遮罩（Gradient Overlay），确保亮色背景下的文字具备高可读性。
  * **粒子特效生成**：可选开启随机雪花粒子特效，通过数学模型在特定图层生成半透明噪点，提升画面空间层次感。
* **企业级高可用与容错机制**
  * **资源顺延（Fallback）机制**：建立超额备用数据池。若首选背景图或海报存在格式损坏、体积过大或服务端响应超时的情况，系统将自动丢弃坏点并顺延抓取次优数据，确保封面生成的绝对完整性。
  * **防网络阻断传输**：在 API 图像回传环节，采用 Base64 编码方式替代传统的二进制流直推，有效规避 Emby 服务端因解析大体积图像流而导致的 `500 Internal Server Error` 崩溃问题。
* **安全性与敏捷配置**
  * 采用 `.env` 环境隔离机制管理敏感凭证（API Key 等），彻底杜绝代码仓库中的密钥泄漏风险。

---

## 🏗️ 架构与工作流

本工具的工作流遵循单向数据流的原则，分为以下四个生命周期：

1. **鉴权与检索**：读取 `.env` 凭证，向 Emby API 发起请求，获取目标媒体库的 `ItemId` 及最新 20 部影视的图像标签。
2. **素材下发**：基于防死锁机制（严格控制读取超时阈值），将所需素材分块下载至本地临时目录。
3. **内存渲染**：在内存中构建 RGBA 图像通道，依次叠加背景层、特效层（模糊/粒子）、遮罩层（渐变）、文字层与前景层（海报墙），最终压制为 RGB 格式。
4. **编码与回传**：将生成的 JPG 图像转换为 Base64 字符串，通过 POST 请求覆写 Emby 服务端的 Primary 图像节点。

---

## 🚀 部署指南

### 1. 环境准备
* 具备有效网络访问权限的 Emby 服务器（建议开启 HTTPS）。
* 已在 Emby 控制台中生成有效的 **API 密钥**。
* 部署环境已安装 `Docker` 与 `Docker Compose`。

### 2. 目录初始化
在宿主机中克隆或创建项目目录，并构建如下基本结构：

```text
emby-cover-generator/
├── .env                 # 环境变量文件 (需手动创建)
├── fonts/               # 字体挂载目录
│   ├── zh_font.ttf      # 自定义中文字体
│   └── en_font.otf      # 自定义英文字体
├── input/               # 临时运行缓存 (自动生成)
└── output/              # 封面输出目录 (自动生成)

```

### 3. 配置安全凭证 (.env)

在项目根目录创建隐藏文件 `.env`，填入您的真实信息（请确保该文件已被加入 `.gitignore`）：

```ini
EMBY_URL=http://your-emby-server-ip:8096
EMBY_API_KEY=your_emby_api_key_here

### 4. 个性化参数配置 (config.py)

项目附带 `config.py` 文件，您可以基于字典 `LIBRARY_MAP` 定义需要处理的媒体库名称及中英文映射。您还可以在 `CONFIG` 字典中微调以下视觉参数：

* 输出分辨率 (`output_size`)
* 海报尺寸与间距 (`poster_size`, `poster_spacing`)
* 模糊强度与粒子密度 (`blur_percent`, `snow_density`)

### 5. 启动与测试

首次运行，建议将配置中的 `UPLOAD_TO_EMBY` 设为 `False` 以开启**预览模式**。
在终端执行以下命令构建镜像并运行：

```bash
docker-compose up --build

```

> **提示**：配置中已注入 `PYTHONUNBUFFERED=1` 环境变量，运行日志将在控制台实时打印。运行结束后，请前往 `output/` 文件夹检查生成的图片排版是否符合预期。

---

## ⏱️ 自动化调度 (最佳实践)

为了最小化系统资源占用，本工具默认采用**单次执行模式**（运行完毕即释放容器内存）。建议将定时任务的控制权交由宿主机的操作系统管理。

确认预览效果无误后，将 `UPLOAD_TO_EMBY` 修改为 `True`，并在您的宿主机系统（如 Linux `crontab` 或群晖“任务计划”）中添加定时触发指令。

**示例：每天凌晨 2:00 自动触发更新**

```bash
0 2 * * * docker start emby-cover-generator

```

*容器唤醒后将自动完成抓取、合成与上传的全流程，随后再次自动休眠。*

---

## 🛡️ 安全合规说明

1. **最小权限原则**：建议在 Emby 中为本工具创建一个专门的 API 密钥，一旦发生泄漏可随时单独吊销。
2. **网络隔离**：尽量在 Emby 服务器所在的同一局域网（或同一 Docker 网络桥接）内部署本容器，避免通过公网明文传输 API 凭证。
3. **依赖更新**：请定期关注项目中 `Pillow` 与 `requests` 等第三方依赖库的 CVE 漏洞通报并适时更新。

```

```
