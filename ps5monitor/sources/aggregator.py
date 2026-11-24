"""Base comune degli aggregatori di prezzi (Trovaprezzi, Idealo): solo modalità "ricerca" (R1.3).

Le offerte degli aggregatori portano a un negozio esterno: non c'è una pagina prodotto leggibile
dal monitor, quindi gli avvisi partono con l'etichetta "da verificare sul negozio" (R4.5).
"""
from __future__ import annotations

from .base import Source

MARKETPLACE_HINTS = ("ebay", "marketplace", "subito")


class AggregatorSource(Source):
    tipo = "aggregatore"
    solo_nuovo = False

    def _seller_type(self, seller_name: str) -> str:
        low = (seller_name or "").lower()
        return "terzo" if any(h in low for h in MARKETPLACE_HINTS) else "negozio"

    def parse_product(self, html: str, url: str):
        return self.parse_search(html, url)
