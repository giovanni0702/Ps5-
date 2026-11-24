"""Registro delle fonti (R1.1)."""
from __future__ import annotations

from .amazon import AmazonSource
from .backmarket import BackMarketSource
from .base import Source
from .carrefour import CarrefourSource
from .ebay import EbaySource
from .eprice import EpriceSource
from .euronics import EuronicsSource
from .expert import ExpertSource
from .fnac import FnacSource
from .gamestop import GameStopSource
from .idealo import IdealoSource
from .mediaworld import MediaWorldSource
from .psdirect import PlayStationDirectSource
from .rebuy import RebuySource
from .subito import SubitoSource
from .trony import TronySource
from .trovaprezzi import TrovaprezziSource
from .unieuro import UnieuroSource

ALL_SOURCES: dict[str, type[Source]] = {cls.id: cls for cls in (
    AmazonSource, MediaWorldSource, UnieuroSource, EuronicsSource, ExpertSource, TronySource, FnacSource,
    EpriceSource, GameStopSource, PlayStationDirectSource, CarrefourSource, RebuySource, BackMarketSource,
    EbaySource, SubitoSource, TrovaprezziSource, IdealoSource,
)}


def build_sources(cfg, fetcher, stores=None, only: str | None = None) -> list[Source]:
    out = []
    for sid, cls in ALL_SOURCES.items():
        if only and sid != only:
            continue
        if sid not in cfg.fonti:
            continue
        out.append(cls(cfg, fetcher, stores))
    return out
