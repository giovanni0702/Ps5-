"""eBay.it: risultati di ricerca (HTML) e pagina dell'oggetto (JSON-LD + HTML).

ATTENZIONE: selettori non provati dal vivo (sito non raggiungibile dall'ambiente di sviluppo).
Sono supportati sia il layout "s-item" sia quello più recente "s-card".
"""
from __future__ import annotations

import re
from decimal import Decimal

from ..models import Offer, utcnow
from ..pricing import parse_price
from . import structured as st
from .base import Source

ITEM_RE = re.compile(r"/itm/(?:[^/?]+/)?(\d{9,15})")
FEEDBACK_RE = re.compile(r"\(?([\d.]+)\)?\s*([\d,]+)\s*%")


def _txt(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def currency_of(text: str) -> str:
    t = text.upper()
    if "£" in text or "GBP" in t:
        return "GBP"
    if "$" in text or "USD" in t:
        return "USD"
    return "EUR"


def parse_shipping(text: str) -> Decimal | None:
    low = text.lower()
    if not low:
        return None
    if "gratuit" in low or "free" in low:
        return Decimal("0.00")
    if "spedizione" in low or "shipping" in low:
        return parse_price(text)
    return None


class EbaySource(Source):
    id = "ebay"
    nome = "eBay.it"
    tipo = "marketplace"
    solo_nuovo = False
    dominio = "www.ebay.it"
    venditore_tipo_predefinito = "terzo"

    def offer_id_from_url(self, url: str) -> str:
        m = ITEM_RE.search(url)
        return m.group(1) if m else super().offer_id_from_url(url)

    def product_url(self, offer: Offer) -> str:
        return f"https://www.ebay.it/itm/{offer.offer_id}"

    def parse_search(self, html: str, url: str) -> list[Offer]:
        soup = st.soup_of(html)
        out = []
        for card in soup.select("li.s-item, li.s-card"):
            link = card.select_one("a.s-item__link, a.su-link, a[href*='/itm/']")
            if not link or not ITEM_RE.search(link.get("href", "")):
                continue
            item_id = ITEM_RE.search(link["href"]).group(1)
            title = _txt(card.select_one(".s-item__title, .s-card__title"))
            title = re.sub(r"^(Nuova inserzione|New listing)\s*", "", title, flags=re.I)
            price_txt = _txt(card.select_one(".s-item__price, .s-card__price"))
            if " a " in price_txt.lower():   # intervallo di prezzi (varianti): prezzo non univoco
                continue
            ship_txt = _txt(card.select_one(".s-item__shipping, .s-item__logisticsCost, .s-card__shipping"))
            seller_txt = _txt(card.select_one(".s-item__seller-info-text, .s-card__seller-info"))
            fb = FEEDBACK_RE.search(seller_txt)
            privato = bool(re.search(r"\bprivato\b", _txt(card), re.I))
            location = _txt(card.select_one(".s-item__location, .s-card__location"))
            offer = Offer(
                source_id=self.id, offer_id=item_id, url_canonico=f"https://www.ebay.it/itm/{item_id}",
                titolo=title, prezzo=parse_price(price_txt), valuta=currency_of(price_txt),
                spedizione_eur=parse_shipping(ship_txt),
                disponibilita="sconosciuta",
                venditore=seller_txt.split(" ")[0] if seller_txt else "",
                venditore_tipo="privato" if privato else "terzo",
                feedback_pct=Decimal(fb.group(2).replace(",", ".")) if fb else None,
                feedback_n=int(fb.group(1).replace(".", "")) if fb else None,
                ha_foto=bool(card.select_one("img")), localita_annuncio=location.replace("da ", "", 1),
                rilevata_il=utcnow(),
            )
            out.append(self.finalize(offer))
        return out

    def parse_product(self, html: str, url: str) -> list[Offer]:
        offers = self.parse_structured(html, url, verified=True)
        soup = st.soup_of(html)
        seller_box = soup.select_one(".x-sellercard-atf, [data-testid='x-sellercard-atf']")
        seller_txt = _txt(seller_box)
        page_txt = _txt(soup.select_one("body"))[:20000]
        privato = bool(re.search(r"venditore privato|privato", seller_txt or page_txt, re.I))
        fb = FEEDBACK_RE.search(seller_txt)
        name = _txt(soup.select_one(".x-sellercard-atf__info__about-seller a span, .x-sellercard-atf__info__about-seller"))
        ship_txt = _txt(soup.select_one(".ux-labels-values--shipping, [data-testid='ux-labels-values--shipping']"))
        for o in offers:
            o.offer_id = self.offer_id_from_url(url) if ITEM_RE.search(url) else o.offer_id
            o.url_canonico = f"https://www.ebay.it/itm/{o.offer_id}"
            o.venditore_tipo = "privato" if privato else "terzo"
            if name:
                o.venditore = name
            if fb:
                o.feedback_n = int(fb.group(1).replace(".", ""))
                o.feedback_pct = Decimal(fb.group(2).replace(",", "."))
            if o.spedizione_eur is None:
                o.spedizione_eur = parse_shipping(ship_txt)
            self.finalize(o, o.condizione if o.condizione != "sconosciuta" else None)
        return offers
