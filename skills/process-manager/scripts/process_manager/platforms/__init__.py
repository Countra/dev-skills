"""仅供 process-manager 内部使用的平台适配层。"""

from .dispatcher import select_platform_adapter

__all__ = ["select_platform_adapter"]
