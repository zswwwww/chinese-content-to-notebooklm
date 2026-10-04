---
name: chinese-content-to-notebooklm
description: 将B站视频、微信公众号文章或本地MD/TXT/PDF提取为文本，导入用户的NotebookLM并生成带来源引用的中文总结；也支持音频缓存清理。适用于“把这个链接放进NotebookLM并总结”。微信视频号未验证支持。
---

# 中文内容到 NotebookLM

依赖本机安装的 `chinese-content-to-notebooklm` Python 包，命令为 `chinese-notebooklm`。先运行 `chinese-notebooklm doctor` 检查依赖；找不到命令时，检查安装环境或用该环境的 `python -m notebooklm_combo`。安装指南：https://github.com/zswwwww/chinese-content-to-notebooklm 。

用户提供具体来源并要求导入总结后执行：

```text
chinese-notebooklm ingest "<链接、BV号或本地文件>" --output "<当前任务输出根目录>"
```

只要求提取时加 `--extract-only`，不要上传。缺少来源时向用户索取，不自动选取任意内容。用户指定笔记本时加 `--notebook <ID>`；多账户使用 `--profile <名称>`。自定义总结使用 `--question`。配置文件用 `--config <文件>` 或环境变量 `NLM_COMBO_CONFIG` 指定。

每个来源在独立子目录保存 `source.md`、`result.json`、`summary.md` 和 `answer.json`。给用户展示返回的真实路径和笔记本链接。总结由 NotebookLM 生成；本机只做提取和连接，不能把助手自行写的内容说成 NotebookLM 返回结果。

## 提取、认证和继续处理

- B站先尝试字幕，无字幕时下载音频并运行 SenseVoice-Small。缺少音频转写依赖时按 README 安装 `[asr]` 和 ffmpeg；首用会下载模型。`--subtitle-only` 可在无字幕时停止。识别文本未逐字校对，不能声称已分析画面。
- 公众号若出现验证页面、没有有效正文或正文过短，停止上传，可改用用户保存的正文或PDF。PDF需要 `[pdf]`，只读文字层；扫描件需另做OCR。微信视频号不在已验证范围。
- NotebookLM认证由上游 `nlm` 管理；需要时让用户执行 `nlm login --storage protected`。若专用浏览器无法访问而日常浏览器可以，检查后台代理配置，不能假定它继承浏览器扩展。用户主动提供本地登录文件时，使用 `nlm login --manual --file <本地文件> --storage protected`。不要读取或显示Cookie、密钥、解密的登录文件，也不要要求在聊天里粘贴凭据。
- B站与NotebookLM代理分别配置。连接失败不能直接认定登录过期；不要擅自切换系统代理或节点。配置中的空代理字符串表示直连，null表示继承进程环境。
- 相同来源在相同输出目录重跑会复用已保存的结果和远端ID。若stage为creating/uploading而没有对应ID，先到远端核实并修复本地记录，避免不确定操作重复创建或上传。上传后等待来源可查询，再只用本次source_id总结。

## 音频缓存

`chinese-notebooklm cleanup` 仅预览；加 `--apply` 删除超过保留期限的缓存。默认保留7天，仅清理配置缓存根目录下的 `<来源哈希>/audio.mp3`；不清理文本、模型、凭据或NotebookLM远端内容。下载与转写共用音频锁，清理跳过正在使用的文件。定时任务由安装者另行设置；用户明确要求定期清理时，可安排现有清理命令。每周检查且保留7天意味着实际保留约7～14天。
