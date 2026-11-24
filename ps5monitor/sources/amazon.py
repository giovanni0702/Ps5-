"""Amazon.it. Le pagine di Amazon non espongono JSON-LD: si leggono gli elementi HTML noti.

ATTENZIONE: selettori presi dalla struttura pubblica nota delle pagine Amazon, NON provati dal vivo
(il sito non era raggiungibile dall'ambiente di sviluppo). Lo stato reale si vede con "diagnostica".
"""
from __future__ import annotations

import re

from ..models import Offer, utcnow
from ..pricing import parse_price
from . import structured as st
from .base import Source

ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})")


def dp_url(asin: str) -> str:
    return f"https://www.amazon.it/dp/{asin}"


def cart_url(asin: str) -> str:
    return f"https://www.amazon.it/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=1"


def _txt(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def availability_from_text(text: str, button: bool) -> tuple[str, int | None]:
    t = text.lower()
    m = re.search(r"(?:solo|only)\s+(\d+)", t)
    if "preordin" in t or "pre-order" in t or "uscita" in t:
        return "in_arrivo", None
    if "non disponibile" in t or "currently unavailable" in t or "attualmente non" in t:
        return "non_disponibile", None
    if not button:
        return "sconosciuta", None
    if m:
        return "ultime_unita", int(m.group(1))
    return "disponibile", None


class AmazonSource(Source):
    id = "amazon"
    nome = "Amazon.it"
    tipo = "marketplace"
    solo_nuovo = False
    dominio = "www.amazon.it"
    venditore_tipo_predefinito = "amazon"

    def offer_id_from_url(self, url: str) -> str:
        m = ASIN_RE.search(url)
        return m.group(1) if m else super().offer_id_from_url(url)

    def product_url(self, offer: Offer) -> str:
        return dp_url(offer.offer_id)

    def parse_search(self, html: str, url: str) -> list[Offer]:
        soup = st.soup_of(html)
        out = []
        for card in soup.select('div[data-component-type="s-search-result"][data-asin]'):
            asin = card.get("data-asin", "").strip()
            if not re.fullmatch(r"[A-Z0-9]{10}", asin):
                continue
            title = _txt(card.select_one("h2 span")) or _txt(card.select_one("h2"))
            price = card.select_one(".a-price:not(.a-text-price) .a-offscreen")
            strike = card.select_one(".a-price.a-text-price .a-offscreen")
            button = bool(card.select_one('[name="submit.addToCart"]:not([disabled])'))
            offer = Offer(
                source_id=self.id, offer_id=asin, url_canonico=dp_url(asin), titolo=title,
                prezzo=parse_price(_txt(price)), prezzo_barrato=parse_price(_txt(strike)),
                disponibilita="disponibile" if button else "sconosciuta",
                venditore="", venditore_tipo="terzo", rilevata_il=utcnow(),
            )
            out.append(self.finalize(offer))
        return out

    def parse_product(self, html: str, url: str) -> list[Offer]:
        soup = st.soup_of(html)
        title = _txt(soup.select_one("#productTitle"))
        if not title:
            return []
        asin_tag = soup.select_one('input#ASIN, input[name="ASIN"]')
        asin = asin_tag.get("value") if asin_tag else self.offer_id_from_url(url)
        core = soup.select_one("#corePriceDisplay_desktop_feature_div, #corePrice_feature_div, #apex_desktop") or soup
        price = core.select_one(".priceToPay .a-offscreen, .a-price:not(.a-text-price) .a-offscreen")
        strike = core.select_one(".basisPrice .a-offscreen, .a-price.a-text-price .a-offscreen")
        button_tag = soup.select_one("#add-to-cart-button, #buy-now-button")
        button = bool(button_tag) and not button_tag.has_attr("disabled")
        disp, qty = availability_from_text(_txt(soup.select_one("#availability")), button)
        sold_by = _txt(soup.select_one("#merchantInfoFeature_feature_div .offer-display-feature-text, #sellerProfileTriggerId"))
        shipped_by = _txt(soup.select_one("#fulfillerInfoFeature_feature_div .offer-display-feature-text"))
        merchant_info = _txt(soup.select_one("#merchant-info, #tabular-buybox"))
        if not sold_by and merchant_info:
            sold_by = merchant_info
        is_amazon = "amazon" in sold_by.lower() and ("amazon" in shipped_by.lower() or not shipped_by)
        delivery = _txt(soup.select_one("#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE, #deliveryBlockMessage"))
        ship = None
        if re.search(r"(consegna|spedizione)\s+gratuita", delivery, re.I):
            ship = parse_price("0")
        crumbs = soup.select("#wayfinding-breadcrumbs_feature_div li a")
        offer = Offer(
            source_id=self.id, offer_id=asin, url_canonico=dp_url(asin), titolo=title,
            prezzo=parse_price(_txt(price)), prezzo_barrato=parse_price(_txt(strike)), spedizione_eur=ship,
            disponibilita=disp, quantita_disponibile=qty,
            venditore="Amazon" if is_amazon else (_txt(soup.select_one("#sellerProfileTriggerId")) or sold_by[:60]),
            venditore_tipo="amazon" if is_amazon else "terzo",
            categoria=_txt(crumbs[-1]) if crumbs else "", consegna_testo=delivery[:160],
            verificata_su_pagina_prodotto=True, rilevata_il=utcnow(),
        )
        return [self.finalize(offer)]
