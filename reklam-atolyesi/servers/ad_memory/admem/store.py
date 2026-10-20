"""ad-memory Store: bütün profil verisi işlemlerinin tek kodu (MCP sunucusu, doctor ve cost_guard aynı kodu kullanır; 7.4)."""
from __future__ import annotations

import os
from pathlib import Path

from .s_base import BaseStore
from .s_coach import CoachMixin
from .s_comp import CompMixin
from .s_conn import ConnMixin
from .s_creative import CreativeMixin
from .s_dm import DMMixin
from .s_legal import LegalMixin
from .s_memory import MemoryMixin
from .s_meta import MetaMixin
from .s_stage import StageMixin
from .util import AdMemoryError


class Store(StageMixin, MetaMixin, CreativeMixin, CompMixin, CoachMixin, MemoryMixin, LegalMixin, DMMixin, ConnMixin, BaseStore):
    pass


def from_env() -> Store:
    db = os.environ.get("AD_MEMORY_DB", "")
    data = os.environ.get("AD_MEMORY_DATA_DIR", "")
    for name, val in (("AD_MEMORY_DB", db), ("AD_MEMORY_DATA_DIR", data)):
        if not val or "${" in val:
            raise AdMemoryError(f"{name} çözülmedi ({val!r}); plugin userConfig'te data_dir verilmeli (12.8)")
    dd = Path(data)
    if not dd.is_dir():
        raise AdMemoryError(f"data_dir yok: {dd}")
    return Store(db, dd)
