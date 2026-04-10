# todaydevotional scraper

中文说明和 English guide are both included below.

## 中文说明

### 项目简介

这个项目用于抓取灵修内容并生成统一 JSON 资源文件。

当前支持 3 种语言：

- `en`: `todaydevotional.com`
- `es`: `ministerioreforma.com/cadadia`
- `pt`: `presentediario.transmundial.org.br`

生成后的资源文件默认放在 `resource/` 目录下。

### 脚本说明

- `scraper_en.py`: 英文抓取脚本
- `scraper_es.py`: 西班牙语抓取脚本
- `scraper_pt.py`: 葡萄牙语抓取脚本
- `scraper_common.py`: 公共工具函数

### 依赖安装

建议使用 Python 3.11+。

```bash
pip install requests beautifulsoup4
```

### 使用方式

每个语言脚本都支持两种模式：

1. 按最新条数下载
2. 按日期范围下载

#### 1. 按最新条数下载

下载最新 20 条：

```bash
python scraper_en.py --limit 20
python scraper_es.py --limit 20
python scraper_pt.py --limit 20
```

如果需要指定“最新”的参考日期，可以传入 `--today`：

```bash
python scraper_es.py --limit 20 --today 20260410
```

`--today` 格式必须是 `YYYYMMDD`。

#### 2. 按日期范围下载

下载 2025 年整年数据：

```bash
python scraper_en.py --start 20250101 --end 20251231
python scraper_es.py --start 20250101 --end 20251231
python scraper_pt.py --start 20250101 --end 20251231
```

下载指定时间段：

```bash
python scraper_es.py --start 20250401 --end 20250430
python scraper_pt.py --start 20250701 --end 20250731
```

日期范围是闭区间，`--start` 和 `--end` 都会包含在结果中。

### 输出文件

默认输出路径：

- `resource/daily_devotion_en.json`
- `resource/daily_devotion_es.json`
- `resource/daily_devotion_pt.json`

也可以通过 `--output` 指定自定义路径：

```bash
python scraper_pt.py --start 20250101 --end 20251231 --output resource/daily_devotion_pt_2025.json
```

### JSON 结构

三个语言脚本都会输出统一字段：

```json
{
  "date_o": "December 31, 2025",
  "date": "1231",
  "reference": "John 3:16",
  "ari": "John 3:1-21",
  "title": "Sample Title",
  "inspiration": "...",
  "prayer": "...",
  "quote": "...",
  "author": {
    "name": "...",
    "avatar": "..."
  },
  "introduce": "...",
  "original_link": "...",
  "audio": "...",
  "id": 1
}
```

### 说明

- 根目录下的 `daily_devotion_en.json`、`daily_devotion_es.json`、`daily_devotion_pt.json` 是旧样例文件。
- 当前脚本默认写入 `resource/` 目录，不会自动覆盖根目录旧样例，除非你手动指定 `--output`。
- `pt` 数据源的音频字段取决于源站是否直接提供；如果源站没有返回音频地址，`audio` 可能为空字符串。

## English

### Overview

This project scrapes daily devotional content and exports it as normalized JSON files.

Currently supported languages:

- `en`: `todaydevotional.com`
- `es`: `ministerioreforma.com/cadadia`
- `pt`: `presentediario.transmundial.org.br`

Generated resources are written to the `resource/` directory by default.

### Scripts

- `scraper_en.py`: English scraper
- `scraper_es.py`: Spanish scraper
- `scraper_pt.py`: Portuguese scraper
- `scraper_common.py`: shared helpers

### Requirements

Python 3.11+ is recommended.

```bash
pip install requests beautifulsoup4
```

### Usage

Each language-specific scraper supports two modes:

1. Download the latest N records
2. Download records within a date range

#### 1. Latest N records

Download the latest 20 items:

```bash
python scraper_en.py --limit 20
python scraper_es.py --limit 20
python scraper_pt.py --limit 20
```

You can also define the reference date for "latest" mode:

```bash
python scraper_es.py --limit 20 --today 20260410
```

The `--today` format must be `YYYYMMDD`.

#### 2. Date range

Download the full year 2025:

```bash
python scraper_en.py --start 20250101 --end 20251231
python scraper_es.py --start 20250101 --end 20251231
python scraper_pt.py --start 20250101 --end 20251231
```

Download a custom range:

```bash
python scraper_es.py --start 20250401 --end 20250430
python scraper_pt.py --start 20250701 --end 20250731
```

The range is inclusive: both `--start` and `--end` are included.

### Output files

Default output paths:

- `resource/daily_devotion_en.json`
- `resource/daily_devotion_es.json`
- `resource/daily_devotion_pt.json`

You can override the destination with `--output`:

```bash
python scraper_pt.py --start 20250101 --end 20251231 --output resource/daily_devotion_pt_2025.json
```

### JSON schema

All three scripts export the same JSON shape:

```json
{
  "date_o": "December 31, 2025",
  "date": "1231",
  "reference": "John 3:16",
  "ari": "John 3:1-21",
  "title": "Sample Title",
  "inspiration": "...",
  "prayer": "...",
  "quote": "...",
  "author": {
    "name": "...",
    "avatar": "..."
  },
  "introduce": "...",
  "original_link": "...",
  "audio": "...",
  "id": 1
}
```

### Notes

- The root-level `daily_devotion_en.json`, `daily_devotion_es.json`, and `daily_devotion_pt.json` are legacy sample files.
- Current scripts write to `resource/` by default and do not overwrite those root-level samples unless you explicitly pass `--output`.
- For `pt`, the `audio` field may be empty if the source does not directly return an audio URL.
