"""Portable configuration with no account credentials or workstation paths."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import sysconfig


def default_cache():
    explicit = os.environ.get("NLM_COMBO_CACHE_DIR")
    if explicit:
        return Path(explicit).expanduser().absolute()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "chinese-content-to-notebooklm/audio"


def load_config(filename=None):
    config = {"cache_dir": str(default_cache()), "retention_days": 7,
              "bilibili_proxy": "", "notebooklm_proxy": None,
              "ffmpeg_dir": None, "nlm_executable": None}
    filename = filename or os.environ.get("NLM_COMBO_CONFIG")
    base = Path.cwd()
    if filename:
        path = Path(filename).expanduser().absolute()
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError("配置必须是JSON对象")
        unknown = value.keys() - config.keys()
        if unknown:
            raise ValueError("未知配置项：" + ", ".join(sorted(unknown)))
        config.update(value)
        base = path.parent
    if config["cache_dir"] is None:
        config["cache_dir"] = str(default_cache())
    for key in ("cache_dir", "ffmpeg_dir", "nlm_executable"):
        value = config[key]
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(key + " 必须是非空路径或null")
            path = Path(value).expanduser()
            config[key] = str((base / path).absolute() if not path.is_absolute() else path)
    days = config["retention_days"]
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError("retention_days 必须是正整数")
    for key in ("bilibili_proxy", "notebooklm_proxy"):
        value = config[key]
        if value is not None and not isinstance(value, str):
            raise ValueError(key + " 必须是字符串或null")
    return config


def nlm_executable(config):
    explicit = config.get("nlm_executable")
    if explicit:
        if not Path(explicit).is_file():
            raise RuntimeError("配置的nlm_executable不存在")
        return explicit
    local = Path(sysconfig.get_path("scripts")) / ("nlm.exe" if os.name == "nt" else "nlm")
    if local.is_file():
        return str(local)
    found = shutil.which("nlm")
    if found:
        return found
    raise RuntimeError("未找到nlm；请在当前Python环境安装本项目及其依赖")


@contextmanager
def process_environment(config):
    previous = os.environ.get("PATH")
    directories = [sysconfig.get_path("scripts")]
    if config.get("ffmpeg_dir"):
        directories.insert(0, config["ffmpeg_dir"])
    os.environ["PATH"] = os.pathsep.join(directories + [previous or ""])
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = previous
