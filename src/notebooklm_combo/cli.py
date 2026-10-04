import argparse
from importlib import metadata, util
import json
import os
from pathlib import Path
import shutil
import sys

from . import __version__, ingest
from .cleanup import cleanup
from .config import load_config, nlm_executable, process_environment


def doctor(config, check_login=False):
    result = {"version": __version__, "python": sys.version.split()[0],
              "cache_dir": config["cache_dir"], "retention_days": config["retention_days"],
              "dependencies": {}, "commands": {}}
    with process_environment(config):
        result["commands"]["ffmpeg"] = shutil.which("ffmpeg")
        result["commands"]["nlm"] = nlm_executable(config)
        result["commands"]["yt-dlp"] = shutil.which("yt-dlp")
    for name in ("notebooklm-mcp-cli", "yt-dlp", "httpx", "filelock", "beautifulsoup4"):
        try:
            result["dependencies"][name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result["dependencies"][name] = None
    result["optional"] = {name: util.find_spec(name) is not None for name in ("funasr", "pypdf")}
    if check_login:
        ingest.CONFIG = config
        ingest.nlm("notebook", "list", "--json")
        result["login"] = "verified"
    else:
        result["login"] = "not_checked"
    return result


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        if argv and argv[0] == "ingest":
            return ingest.main(argv[1:])
        parser = argparse.ArgumentParser(description="中文内容 → NotebookLM → 有引用的总结")
        parser.add_argument("--version", action="version", version=__version__)
        commands = parser.add_subparsers(dest="command", required=True)
        commands.add_parser("ingest", help="导入B站、公众号或本地文件；使用ingest --help查看参数")
        check = commands.add_parser("doctor", help="检查依赖；默认不连接账户")
        check.add_argument("--config")
        check.add_argument("--check-login", action="store_true")
        clean = commands.add_parser("cleanup", help="预览或删除过期音频缓存")
        clean.add_argument("--config")
        clean.add_argument("--apply", action="store_true", help="执行删除；默认仅预览")
        clean.add_argument("--retention-days", type=int)
        skill = commands.add_parser("install-skill", help="将随包Skill安装到Codex的技能目录")
        skill.add_argument("--destination", help="替代Codex skills根目录")
        skill.add_argument("--force", action="store_true", help="更新已经存在的同名Skill")
        args = parser.parse_args(argv)
        if args.command == "install-skill":
            base = Path(args.destination) if args.destination else Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills"
            target = base.expanduser().absolute() / "chinese-content-to-notebooklm"
            if target.exists() and not args.force:
                raise RuntimeError("同名Skill已存在；确认更新后使用--force")
            if target.is_symlink() or target.is_junction():
                raise RuntimeError("Skill目标包含链接，请选择普通目录")
            source = Path(__file__).parent / "skills/chinese-content-to-notebooklm"
            shutil.copytree(source, target, dirs_exist_ok=args.force)
            installed = target / "SKILL.md"
            installed.write_text(installed.read_text(encoding="utf-8") +
                                 "\n## 本机安装环境\n\n安装环境的Python路径：" + json.dumps(sys.executable, ensure_ascii=False) +
                                 "。执行此技能时优先用该Python加 `-m notebooklm_combo`，避免依赖GUI进程的PATH。Windows PowerShell调用带路径的程序需使用 `&`。\n",
                                 encoding="utf-8")
            print(json.dumps({"skill_directory": str(target)}, ensure_ascii=False))
            return 0
        config = load_config(args.config)
        if args.command == "doctor":
            result = doctor(config, args.check_login)
        else:
            result = cleanup(Path(config["cache_dir"]),
                             retention_days=args.retention_days if args.retention_days is not None else config["retention_days"],
                             apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("errors") else 0
    except Exception as exc:
        print("处理未完成：" + str(exc), file=sys.stderr)
        return 1
