"""Remove only expired audio from the NotebookLM workflow's explicit cache."""
from pathlib import Path
import re
import time

from filelock import FileLock, Timeout



def unlinked(path):
    path = path.absolute()
    return path.resolve() == path and not any(
        item.is_symlink() or item.is_junction() for item in (path, *path.parents)
    )


def cleanup(root, retention_days=7, apply=False, now=None):
    if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days < 1:
        raise ValueError("retention_days must be a positive integer")
    cutoff = (time.time() if now is None else now) - retention_days * 86400
    candidates = []
    root = Path(root).absolute()
    if root.exists() and unlinked(root):
        for folder in root.iterdir():
            if re.fullmatch(r"[0-9a-f]{16}", folder.name) and folder.is_dir() and unlinked(folder):
                candidates.append(folder / "audio.mp3")
    result = {"apply": apply, "retention_days": retention_days,
              "deleted": [], "eligible": [], "kept": [], "skipped": [],
              "errors": [], "bytes_deleted": 0, "bytes_eligible": 0}
    for path in dict.fromkeys(candidates):
        if not unlinked(path):
            result["skipped"].append({"path": str(path), "reason": "linked_path"})
            continue
        if not path.is_file():
            continue
        try:
            with FileLock(str(path.parent / ".audio.lock"), timeout=0):
                if not path.is_file():
                    continue
                info = path.stat()
                if info.st_mtime >= cutoff:
                    result["kept"].append(str(path))
                    continue
                item = {"path": str(path), "bytes": info.st_size}
                result["eligible"].append(item)
                result["bytes_eligible"] += info.st_size
                if apply:
                    # Recheck after taking the same lock used by extraction.
                    if not unlinked(path):
                        raise RuntimeError("Audio target became a linked path")
                    path.unlink()
                    result["deleted"].append(item)
                    result["bytes_deleted"] += info.st_size
        except Timeout:
            result["skipped"].append({"path": str(path), "reason": "in_use"})
        except (OSError, RuntimeError) as exc:
            result["errors"].append({"path": str(path), "message": str(exc)})
    return result
