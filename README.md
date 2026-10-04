# Chinese Content to NotebookLM

把 **B站视频、微信公众号文章、本地 MD/TXT/PDF** 提取成文本，导入你自己的 NotebookLM，生成带来源引用的中文总结。提供可安装的 Python 命令和 Codex Skill，支持保存进度、音频缓存复用及过期缓存清理。

这是一个连接项目：提取能力来自 [ChubbySkills](https://github.com/chubbyguan/chubbyskills)，NotebookLM 操作使用 [notebooklm-mcp-cli](https://github.com/jacob-bd/gemini-notebook-mcp-cli)。连接、配置、状态保存和清理由本项目实现。上游来源和本地修改见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

```text
B站 / 公众号 / 本地文档
        ↓ 提取字幕、正文或音频转写
     source.md
        ↓ 上传并等待来源处理
    NotebookLM
        ↓ 仅查询本次来源
summary.md + answer.json
```

## 首版范围

- B站字幕优先，无字幕时使用 SenseVoice-Small 在 CPU 上转写；支持 BV 号、分P、稍后再看及短链接。
- 公众号正文提取；本地 Markdown/TXT；PDF 文字层提取。验证页面、空正文和扫描件不会当作有效资料上传。
- 默认每个来源创建专用笔记本，可指定已有笔记本与账户 profile。
- 相同来源在相同输出根目录重跑时复用结果及已保存的远端ID；上传后等待可查询再总结。
- B站和NotebookLM分别配置代理；登录由上游 `nlm` 保存和管理。
- 音频保留天数可配置；默认7天，清理跳过处理中音频及链接路径。

实际验证范围见 [docs/VALIDATION.md](docs/VALIDATION.md)。Windows 是首个实际使用环境；跨平台离线测试由CI验证。微信视频号、画面理解、扫描PDF OCR均不在首版范围。普通网页聊天环境不能直接运行这些本机命令；Skill需要能够执行本地命令的代理环境。

## 安装

需要 **Python 3.12+**。只有音频下载/转写需要 [ffmpeg](https://ffmpeg.org/download.html)；将ffmpeg放在PATH，或通过配置的 `ffmpeg_dir` 指定其可执行文件目录。

Windows PowerShell：

```powershell
git clone https://github.com/zswwwww/chinese-content-to-notebooklm.git
cd chinese-content-to-notebooklm
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\chinese-notebooklm.exe doctor
```

macOS/Linux：

```sh
git clone https://github.com/zswwwww/chinese-content-to-notebooklm.git
cd chinese-content-to-notebooklm
python3.12 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/chinese-notebooklm doctor
```

无字幕视频需要可选的音频转写依赖，PDF需要可选PDF依赖。在同一环境安装：

```powershell
.\.venv\Scripts\python.exe -m pip install ".[asr,pdf]"
```

macOS/Linux把Python路径替换成 `.venv/bin/python`。PyTorch及转写模型体积较大，首次转写还会下载SenseVoice-Small和VAD模型；它们不会打包进本仓库，音频清理也不删除这些模型。若只用字幕或文本，可保留轻量安装。

下文的 `chinese-notebooklm` 与 `nlm` 都指当前安装环境的命令。没有激活环境时，Windows使用 `.\.venv\Scripts\chinese-notebooklm.exe` / `nlm.exe`，macOS/Linux使用 `.venv/bin/chinese-notebooklm` / `nlm`。

## 登录与网络

首次使用NotebookLM前，在自己的电脑登录：

```text
nlm login --storage protected
nlm notebook list --json
```

账号资料由上游工具保存在仓库之外。登录和网络处理详见 [docs/AUTH_AND_NETWORK.md](docs/AUTH_AND_NETWORK.md)。专用登录浏览器可能不继承日常浏览器扩展；后台工具需要可用的网络出口。不要把Cookie或登录文件提交到GitHub。

## 配置

没有配置文件也能运行。需要自定义时，复制 `config.example.json` 为 `config.local.json`，通过 `--config config.local.json` 或环境变量 `NLM_COMBO_CONFIG` 指定。相对路径相对于配置文件目录解析。

| 配置项 | 默认值与含义 |
|---|---|
| `cache_dir` | `null` 使用系统用户缓存目录；也可设置 `NLM_COMBO_CACHE_DIR` |
| `retention_days` | `7`，音频最后使用后保留的天数 |
| `bilibili_proxy` | `""`，B站直连；`null`继承环境；字符串指定代理 |
| `notebooklm_proxy` | `null`，继承环境；`""`直连；字符串指定代理 |
| `ffmpeg_dir` | `null`使用PATH，或指定ffmpeg可执行文件目录 |
| `nlm_executable` | `null`自动寻找当前Python环境的nlm，或指定可执行文件路径 |

本项目配置只控制自己的执行流程。直接使用 `nlm login` 等上游命令时，代理需通过它的进程环境设置。

## 使用

导入并总结：

```text
chinese-notebooklm ingest "https://www.bilibili.com/video/BV1kEVV6yEYf/" --output ./outputs
chinese-notebooklm ingest "https://mp.weixin.qq.com/s/<文章ID>" --output ./outputs
chinese-notebooklm ingest ./my-notes.md --output ./outputs
```

只提取、不连接NotebookLM：

```text
chinese-notebooklm ingest "BV1kEVV6yEYf" --extract-only --output ./outputs
chinese-notebooklm ingest "BV1kEVV6yEYf" --subtitle-only --extract-only --output ./outputs
```

自定义目标及总结：

```text
chinese-notebooklm ingest ./my-notes.md --notebook <笔记本ID> --profile <账户名称> --question "只总结论据与适用条件，保留引用" --output ./outputs
```

每个来源生成一个子目录，其中有 `source.md`、`result.json`；完成总结后增加 `summary.md` 与原始 `answer.json`。这些是用户数据，默认不跟踪。文本中的作者观点和事实陈述并不等于已经独立核实；音频识别可能有错字，提取文字不包含画面中的图表或板书。

重复运行请保留同一个输出根目录。若请求中断导致 `creating` 或 `uploading` 状态没有远端ID，程序会停止，需先核对远端结果；恢复办法见 [docs/RECOVERY.md](docs/RECOVERY.md)。本项目不会无限保证未知请求的“恰好一次”执行。

## 在Codex里使用Skill

安装同一Python包后执行：

```text
chinese-notebooklm install-skill
```

它会把随包Skill复制到 `CODEX_HOME/skills`，未设置时使用用户的 `.codex/skills`，并在本机Skill副本里记录安装环境的Python入口；公开源码不包含安装者的路径。已有同名Skill时会停止，确认要更新后可以加 `--force`。自定义目标使用 `--destination <skills根目录>`。然后在Codex的新对话中调用：

```text
$chinese-content-to-notebooklm 把这个B站链接导入NotebookLM，总结核心观点与论据，保留引用：<链接>
```

## 音频缓存清理

```text
chinese-notebooklm cleanup
chinese-notebooklm cleanup --apply
chinese-notebooklm cleanup --retention-days 30 --apply
```

第一条预览；第二条按配置删除过期缓存。只删除 `cache_dir/<16位来源哈希>/audio.mp3`，不会递归清空目录；保留转写、总结、登录资料、模型和NotebookLM内容。正在下载或转写的缓存被锁保护；复用会刷新最后使用时间。

安装不会自动创建定时任务。可以在本机Codex中要求“每7天运行一次音频清理命令，保留7天”，或使用操作系统的任务计划功能。每周检查且保留7天意味着实际保留约7～14天。本机调度运行时需要机器及调度程序可用；GitHub上的定时任务不能清理你的个人电脑。

## 开发与测试

```text
python -m pip install ".[dev,pdf]"
python -m unittest discover -s tests -v
python -m ruff check .
python -m build
```

离线测试不连接私人账户，也不上传来源。CI覆盖Windows、Linux、macOS的Python 3.12。真实联网验收需要安装者自己的账户；详细边界见验证记录。

## 来源与许可证

本项目连接代码采用MIT许可证，提取代码保留ChubbySkills的MIT声明。NotebookLM能力由独立上游依赖提供，并非官方Google集成。相关信息见 [LICENSE](LICENSE) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。只处理你有权访问和使用的内容；发布程序不意味着获得转载源视频、文章或转写全文的权限。
