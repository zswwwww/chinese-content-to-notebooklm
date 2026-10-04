"""Connect ChubbySkills extraction to NotebookLM; retain resumable local results."""
import argparse
from contextlib import contextmanager, redirect_stdout
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlencode, urlparse

from .config import load_config, process_environment, nlm_executable

CONFIG = load_config()

PROMPT = "请仅依据所选来源用简体中文总结。先用一段话概括，再列出核心观点、支持观点的证据或例子、结论和适用条件。区分作者观点、来源中的事实陈述与推断，保留来源引用。证据不足时明确说明；不要补造来源没有的内容。"


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def normalize_source(source):
    if re.fullmatch(r"BV[0-9A-Za-z]+", source):
        return "bilibili", "https://www.bilibili.com/video/" + source + "/"
    parsed = urlparse(source)
    if parsed.hostname == "b23.tv":
        import httpx
        with httpx.Client(follow_redirects=True, timeout=30, proxy=CONFIG.get("bilibili_proxy") or None, trust_env=CONFIG.get("bilibili_proxy") is None) as client:
            response = client.get(source)
            response.raise_for_status()
            source = str(response.url)
        parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        if parsed.hostname in ("www.bilibili.com", "bilibili.com", "m.bilibili.com"):
            match = re.search(r"/video/(BV[0-9A-Za-z]+)", parsed.path)
            if not match and parsed.path.rstrip("/") == "/list/watchlater":
                candidate = parse_qs(parsed.query).get("bvid", [""])[0]
                if re.fullmatch(r"BV[0-9A-Za-z]+", candidate):
                    match = re.fullmatch(r"(BV[0-9A-Za-z]+)", candidate)
            if not match:
                raise ValueError("需要具体的 B 站视频链接或 BV 号。")
            part = parse_qs(parsed.query).get("p", ["1"])[0]
            if not part.isdigit() or int(part) < 1:
                raise ValueError("B 站分 P 参数必须是正整数。")
            canonical = "https://www.bilibili.com/video/" + match.group(1) + "/"
            if int(part) > 1:
                canonical += "?" + urlencode({"p": part})
            return "bilibili", canonical
        if parsed.hostname == "mp.weixin.qq.com":
            return "wechat", source
        raise ValueError("此入口支持微信公众号文章、B 站视频和本地 MD/TXT/PDF；微信视频号需另行处理。")
    path = Path(source).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in (".md", ".txt", ".pdf"):
        raise ValueError("找不到支持的本地 MD/TXT/PDF 文件。")
    return "local", str(path)


@contextmanager
def bilibili_adapter(config):
    from dataclasses import replace
    from ._vendor.chubbyskills import bilibili
    previous = bilibili.CFG
    proxy = config.get("bilibili_proxy")
    extra = () if proxy is None else ("--proxy", proxy)
    bilibili.CFG = replace(previous, extra_ydl_args=previous.extra_ydl_args + extra)
    try:
        yield bilibili
    finally:
        bilibili.CFG = previous


def extract(platform, source, output, subtitle_only=False):
    if platform == "bilibili":
        with bilibili_adapter(CONFIG) as module:
            bvid = module.extract_bvid(source)
            title, author = module.get_info(source, bvid)
            with tempfile.TemporaryDirectory(prefix="notebooklm-bilibili-") as temporary:
                sub = module.try_subtitles(source, temporary)
                if sub:
                    text, language = sub
                    method = "字幕"
                else:
                    if subtitle_only:
                        raise ValueError("未取得字幕；尚未进行音频下载或转写。")
                    cache = Path(CONFIG["cache_dir"]) / hashlib.sha256(source.encode()).hexdigest()[:16]
                    from .cleanup import unlinked
                    if not unlinked(cache):
                        raise RuntimeError("音频缓存路径包含符号链接或目录连接")
                    cache.mkdir(parents=True, exist_ok=True)
                    audio = cache / "audio.mp3"
                    from filelock import FileLock
                    with FileLock(str(cache / ".audio.lock"), timeout=1):
                        if not unlinked(audio):
                            raise RuntimeError("音频缓存文件是链接，已停止处理")
                        if not audio.is_file() or audio.stat().st_size == 0:
                            module.ytdlp.download_audio(module.CFG, source, str(cache), filename="audio.mp3")
                        audio.touch()
                        try:
                            text = module.transcribe_audio(str(audio))
                        finally:
                            if audio.is_file():
                                audio.touch()
                    language, method = "zh", "SenseVoice-Small"
            if len(text.strip()) < 50:
                raise ValueError("视频文本为空或过短，未上传。")
            content = module.build_markdown(title, text, source, author, method, language)
    elif platform == "wechat" or Path(source).suffix.lower() == ".pdf":
        from ._vendor.chubbyskills import wechat as module
        if platform == "wechat":
            title, author, text = module.fetch_from_url(source)
        else:
            title, author, text = module.extract_from_pdf(source)
        if not text:
            raise ValueError("没有提取到有效文章正文。若公众号出现验证页面，可保存正文或 PDF 后导入。")
        method = "公众号正文" if platform == "wechat" else "PDF文字层"
        content = module.generate_markdown(title, author, text, source)
    else:
        path = Path(source)
        text = path.read_text(encoding="utf-8-sig")
        if not text.strip():
            raise ValueError("本地文件为空，未上传。")
        title, method, content = path.stem, "本地文本", text
    destination = output / "source.md"
    destination.write_text(content, encoding="utf-8")
    return {"title": title, "method": method, "source_file": str(destination), "characters": len(text)}


def notebooklm_environment():
    env = os.environ.copy()
    proxy = CONFIG.get("notebooklm_proxy")
    if proxy is not None:
        env.update(HTTP_PROXY=proxy, HTTPS_PROXY=proxy, http_proxy=proxy, https_proxy=proxy,
                   ALL_PROXY="", all_proxy="", NO_PROXY="localhost,127.0.0.1,::1",
                   no_proxy="localhost,127.0.0.1,::1")
    return env


@contextmanager
def notebooklm_proxy():
    keys = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy", "ALL_PROXY", "all_proxy")
    previous = {key: os.environ.get(key) for key in keys}
    env = notebooklm_environment()
    for key in keys:
        if key in env:
            os.environ[key] = env[key]
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def nlm(*arguments, profile=None, timeout=240):
    command = [nlm_executable(CONFIG), *arguments]
    if profile:
        command.extend(["--profile", profile])
    result = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=timeout, env=notebooklm_environment())
    if result.returncode:
        # CLI diagnostics may include account metadata; never read credential files.
        raise RuntimeError((result.stdout + "\n" + result.stderr).strip()[-2000:])
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("NotebookLM 未返回有效 JSON；检查 CLI 版本和连接。") from exc
    if isinstance(value, dict) and (value.get("error") or value.get("success") is False):
        raise RuntimeError("NotebookLM 报告错误：" + str(value.get("error", value)))
    return value


def wait_source(source_id, profile):
    from notebooklm_tools.cli.utils import get_client
    from notebooklm_tools.services.sources import get_source_content
    with notebooklm_proxy(), get_client(profile) as client:
        get_source_content(client, source_id, wait=True, wait_timeout=180)


def main(argv=None):
    parser = argparse.ArgumentParser(description="公众号/B站 → NotebookLM → 中文总结")
    parser.add_argument("source", help="公众号链接、B站链接/BV号，或本地MD/TXT/PDF")
    parser.add_argument("--output", default="outputs", help="输出根目录；每个来源生成独立子目录")
    parser.add_argument("--extract-only", action="store_true", help="只保存正文，不连接NotebookLM")
    parser.add_argument("--subtitle-only", action="store_true", help="没有字幕时停止")
    parser.add_argument("--notebook", help="既有笔记本ID；默认创建来源专用笔记本")
    parser.add_argument("--profile", help="NotebookLM账户配置名")
    parser.add_argument("--question", default=PROMPT, help="自定义总结要求")
    parser.add_argument("--config", help="JSON配置路径；或设置NLM_COMBO_CONFIG")
    args = parser.parse_args(argv)
    global CONFIG
    CONFIG = load_config(args.config)
    platform, source = normalize_source(args.source.strip())
    run_key = source
    if platform == "local":
        run_key += hashlib.sha256(Path(source).read_bytes()).hexdigest()
    run_key += "|" + (args.notebook or "new") + "|" + (args.profile or "default")
    digest = hashlib.sha256(run_key.encode()).hexdigest()[:16]
    output = Path(args.output).expanduser().resolve() / digest
    output.mkdir(parents=True, exist_ok=True)
    # Avoid simultaneous runs for the same source creating duplicate notebooks.
    from filelock import FileLock
    with FileLock(str(output / ".run.lock"), timeout=1):
        state_path = output / "result.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"source": source, "platform": platform}
        if not state.get("source_file") or not Path(state["source_file"]).is_file():
            with redirect_stdout(sys.stderr), process_environment(CONFIG):
                state.update(extract(platform, source, output, args.subtitle_only))
            state.setdefault("stage", "extracted")
            save_json(state_path, state)
        if args.extract_only:
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0
        # Read-only auth check before any notebook creation or upload.
        nlm("notebook", "list", "--json", profile=args.profile)
        if not state.get("notebook_id"):
            if args.notebook:
                state["notebook_id"] = args.notebook
            else:
                if state.get("stage") == "creating":
                    raise RuntimeError("上次创建结果不确定；先检查NotebookLM是否已有该笔记本，再用--notebook指定，避免重复创建。")
                state["stage"] = "creating"
                save_json(state_path, state)
                created = nlm("notebook", "create", state["title"], "--json", profile=args.profile)
                state["notebook_id"] = created["notebook_id"]
                state["notebook_url"] = created.get("url") or "https://notebook.google.com/notebook/" + state["notebook_id"]
            state["stage"] = "notebook_created"
            save_json(state_path, state)
        if not state.get("source_id"):
            if state.get("stage") == "uploading":
                raise RuntimeError("上次上传结果不确定；先检查笔记本的来源列表并补全result.json中的source_id，避免重复上传。")
            # Save the remote ID immediately; a failed processing wait must not duplicate uploads.
            state["stage"] = "uploading"
            save_json(state_path, state)
            added = nlm("source", "add", state["notebook_id"], "--file", state["source_file"], "--title", state["title"], "--json", profile=args.profile)
            state["source_id"] = added["source_id"]
            state["stage"] = "uploaded"
            save_json(state_path, state)
        if state.get("stage") != "complete" or state.get("question") != args.question:
            # Wait for indexed text before querying. Failure preserves IDs for retry.
            wait_source(state["source_id"], args.profile)
            answer = nlm("notebook", "query", state["notebook_id"], args.question, "--source-ids", state["source_id"], "--new-conversation", "--json", profile=args.profile)
            summary = answer.get("answer", answer.get("response"))
            if not isinstance(summary, str) or not summary.strip():
                raise RuntimeError("NotebookLM没有返回总结文本；导入记录已保留。")
            save_json(output / "answer.json", answer)
            summary_file = output / "summary.md"
            summary_file.write_text("# " + state["title"] + "\n\n来源：" + source + "\n\n提取方式：" + state["method"] + "。视频文字不包含画面分析；音频转写可能存在识别错误。以下总结由NotebookLM依据所选来源生成。\n\n" + summary + "\n", encoding="utf-8")
            state.update(stage="complete", question=args.question, summary_file=str(summary_file))
            save_json(state_path, state)
        print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0
