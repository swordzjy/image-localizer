# image-localizer

一个端到端的图片本地化工具：从网页抓取产品图、下载原图、提取图中文字、翻译成目标语言，并把翻译后的文字写回图片。

## 功能

- **网页抓取**：支持 Amazon 等电商页面。提供 HTTP（`amazon` / `generic`）和可选的 Playwright（`playwright`）抓取后端，用于需要渲染 JS 或绕过 bot 检测的页面。
- **图片下载**：异步下载高清原图，也支持 `file://` 本地路径（便于测试）。
- **OCR 文字提取**：默认 EasyOCR（本地运行），并自动合并重叠/重复的检测框；可选 Tesseract。
- **LLM 翻译**：默认 Claude / OpenAI，保留营销文案语气。
- **图片编辑**：自动采样原文字颜色和背景色，**从原文字包围盒宽度还原原始字号**（比按高度估算更准确，保证译文字号与原图一致），把译文锚定在原文字位置渲染，超长时换行而非无限缩小字号，并保证文字不被裁剪、不会漂移出图片。
- **双语文本导出**：与图片同步输出 `texts.txt`，逐行对照源语言原文与目标语言译文，方便校对翻译和核对 OCR 覆盖率。
- **多语言支持**：支持日语、意大利语、西班牙语、法语、德语等；CJK 文本自动使用系统中日韩字体并逐字换行。

## 安装

```bash
cd /Users/jianyu/Workspace/image-localizer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

> 需要设置环境变量 `ANTHROPIC_API_KEY`（或 `OPENAI_API_KEY`）才能使用 LLM 翻译。
> 程序启动时会**自动从项目根目录（或其上层目录）的 `.env` 文件读取环境变量**，因此把密钥写进 `.env` 即可，无需手动 `export`。已存在的进程环境变量优先，`.env` 不会覆盖它们。
>
> `.env` 示例：
>
> ```dotenv
> ANTHROPIC_API_KEY=sk-ant-...
> ANTHROPIC_MODEL=claude-sonnet-5
> ```
>
> `ANTHROPIC_MODEL` 可选；不设置时会回退到内置模型列表。

## 用法

命令格式为 `image-localizer localize <目标语言> [选项]`，其中目标语言是**位置参数**（如 `fr`、`es`、`de`、`ja`），`--url` 和 `--image-dir 二选一`。

### 从本地图片目录运行

```bash
image-localizer localize fr \
  --image-dir ./MC100S \
  --output ./out
```

### 从网页 URL 运行

```bash
image-localizer localize fr \
  --url "https://www.amazon.com/dp/B0CMT5SNFQ" \
  --output ./out \
  --scraper amazon
```

常用选项：
- `--url` / `-u`：产品页面 URL（和 `--image-dir` 二选一）
- `--image-dir` / `-d`：本地源图片目录，跳过抓取和下载
- `--output` / `-o`：输出目录（默认 `./out`）
- `--scraper` / `-s`：`amazon`、`generic`、`playwright` 或 `auto`（默认）
- `--ocr`：`easyocr`（默认）、`tesseract`、`google`（Google Cloud Vision，付费云 OCR，识别浅色小字更准）
- `--translator` / `-t`：`claude`（默认）、`openai`
- `--source-lang`：可选的源语言提示

查看可用的抓取器 / OCR / 翻译引擎：

```bash
image-localizer list-plugins
```

如果 Amazon 返回验证码或空白页，可换用 Playwright 后端：

```bash
pip install playwright
playwright install chromium
image-localizer localize fr --url "https://www.amazon.com/dp/B0CMT5SNFQ" --scraper playwright
```

### 使用 Google Cloud Vision OCR（可选）

对浅色、低对比、小字号的营销文案，Google Cloud Vision 通常比本地 EasyOCR 识别更全。启用方式：

```bash
pip install google-cloud-vision
```

配置凭据（二选一，均可写进 `.env`，程序会自动读取）：

```dotenv
# 方式一：服务账号 JSON（推荐）
GOOGLE_APPLICATION_CREDENTIALS=/configs/airecorder-ecc4a-8bd56422b862.json
# 方式二：API Key
GOOGLE_API_KEY=your-api-key
```

然后指定 `--ocr google`：

```bash
image-localizer localize fr --image-dir ./MC100S --ocr google
```

输出结构：

```
out/
└── fr/
    ├── originals/      # 原图
    ├── edited/         # 翻译后的图片
    ├── manifest.json   # 结构化清单（含每个文字块的坐标、原文、译文）
    └── texts.txt       # 双语文本导出：逐行对照源语言原文与目标语言译文
```

`texts.txt` 与图片**同步输出**，按图片分组，每个逻辑行给出 `[src]`（源语言原文）和 `[<lang>]`（目标语言译文）两行，便于快速校对翻译、核对 OCR 覆盖率（例如发现某段文字未被 OCR 识别、残留在图中）。

## Claude Code skill

同时提供 Claude Code skill，安装后可通过自然语言调用：

```
/localize-images https://www.amazon.com/dp/B0CMT5SNFQ fr
```

skill 文件位于 `~/.claude/skills/image-localizer/SKILL.md`。

## 限制

- OCR 质量决定了残留英文的多少。默认的 EasyOCR 已针对**浅色、低对比度、小字号**的营销文案调参（放大识别、降低文本检测阈值、对低对比区域增强对比重识别），能捕获免责声明等易漏检的文字；Tesseract 覆盖率较低。若仍有个别文字未被识别，会以原文残留在图中。
- 背景复杂的图片（渐变、纹理、产品表面文字）修复效果有限。
- 弧形、竖排或艺术字无法完美还原。
