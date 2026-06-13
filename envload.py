"""自动把同目录下 secret.env 里的 KEY=VALUE 读进环境变量。
这样你不用懂"环境变量"，把密钥写进 secret.env 即可。"""
import os
from pathlib import Path


def load(path=None):
    here = Path(__file__).parent
    if path:
        p = Path(path)
    else:   # secret.env 优先；secret.txt 作为 Mac 上更省事的备选
        p = next((here / n for n in ("secret.env", "secret.txt")
                  if (here / n).exists()), here / "secret.env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:   # 已在真·环境变量里则不覆盖
            os.environ[k] = v
