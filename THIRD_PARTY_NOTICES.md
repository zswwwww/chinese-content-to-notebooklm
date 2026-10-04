# Third-party sources and modifications

## ChubbySkills — included extraction helpers

Source: https://github.com/chubbyguan/chubbyskills

Base revision: `1dad2882303249312807d41f11d5d230a096569f`.

Copyright (c) 2026 Chubby. MIT License. The complete upstream license is retained at `src/notebooklm_combo/_vendor/chubbyskills/LICENSE` and included in built distributions.

Included source files derive from `bilibili-transcribe/scripts/transcribe.py`, `wechat-article-ingest/scripts/fetch_article.py`, and `chubby_common/{__init__,config,deps,funasr,markdown,vtt,ytdlp}.py`.

Local modifications:

- Package-relative imports and installation instructions; no dependency on another locally installed skill directory.
- yt-dlp captured failures checked and stderr preserved, as submitted upstream in https://github.com/chubbyguan/chubbyskills/pull/35 ; UTF-8 subprocess decoding added for Windows.
- TLS certificate checking kept enabled for yt-dlp calls.
- WeChat HTTP retrieval uses httpx instead of an external curl process; Markdown metadata uses the existing escaped common formatter.
- Optional PDF text extraction uses pypdf instead of MarkItDown/PyMuPDF. No OCR is added.

The original authors remain credited for the extraction and transcription helpers. Wrapper configuration, orchestration, resumable state, cache locking and cleanup are maintained in this project.

## notebooklm-mcp-cli — installed dependency

Source: https://github.com/jacob-bd/gemini-notebook-mcp-cli

Distribution: `notebooklm-mcp-cli==0.15.1`. Source license: MIT, Copyright (c) 2025 Jacob Ben David. This repository does not bundle its source, credentials, or browser profiles; pip installs the upstream distribution with its own license. Its CLI and source service provide NotebookLM access and authentication.

## Other runtime dependencies

yt-dlp, httpx, filelock, beautifulsoup4 and optional pypdf/FunASR/ModelScope/PyTorch/torchaudio are separately installed distributions with their own licenses. ffmpeg is an external executable and is not bundled. SenseVoice and VAD model files are fetched by the upstream transcription library on first use and are not redistributed here. Dependency and model licenses remain applicable to their respective components.
