#!/usr/bin/env python3
"""启动模块化 Electron UI verifier service。"""

from __future__ import annotations

from electron_verifier.service import main


if __name__ == "__main__":
    raise SystemExit(main())
