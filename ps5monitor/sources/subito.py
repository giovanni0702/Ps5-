"""Subito.it: annunci di privati e aziende, letti dal JSON incorporato (__NEXT_DATA__).

ATTENZIONE: struttura del JSON non provata dal vivo (sito non raggiungibile dall'ambiente di sviluppo).
Il lettore cerca in modo tollerante gli oggetti annuncio (campi "subject" e "urls").
Il monitor non scrive mai ai venditori (R9.3).
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator

from ..models import Offer, utcnow
from ..pricing import parse_price
from . import structured as st
from .base import Source


def _walk(obj: Any) -> Iterator[dict]:
    if isinstance(obj, dict):
        if "subject" in obj and ("urls" in obj or "urn" in obj):
            yield obj
            return
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _features(ad: dict) -> dict[str, str]:
    """Normalizza le "features" (lista o dizionario) in {uri: valore}."""
    feats = ad.get("features") or {}
    items = feats.values() if isinstance(feats, dict) else feats
    out = {}
    for f in items:
        if not isinstance(f, dict):
            continue
        uri = f.get("uri") or f.get("label") or ""
        vals = f.get("values") or []
        if vals and isinstance(vals[0], dict):
            out[uri] = str(vals[0].get("key") or vals[0].get("value") or "")
            out[uri + "#value"] = str(vals[0].get("value") or "")
    return out


class SubitoSource(Source):
    id = "subito"
    nome = "Subito.it"
    tipo = "classificati"
    solo_nuovo = False
    dominio = "www.subito.it"
    venditore_tipo_predefinito = "privato"

    def can_verify(self, offer: Offer) -> bool:
        return False  # la pagina di ricerca contiene già tutti i dati dell'annuncio

    def parse_search(self, html: str, url: str) -> list[Offer]:
        soup = st.soup_of(html)
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not (tag.string or "").strip():
            return []
        data = json.loads(tag.string)
        out = []
        seen = set()
        for ad in _walk(data):
            urn = str(ad.get("urn") or "")
            ad_id = (re.search(r"(\d+)$", urn) or re.search(r"(\d+)", urn))
            urls = ad.get("urls") or {}
            link = urls.get("default") if isinstance(urls, dict) else None
            if not link:
                continue
            oid = ad_id.group(1) if ad_id else self.offer_id_from_url(link)
            if oid in seen:
                continue
            seen.add(oid)
            feats = _features(ad)
            price = parse_price(feats.get("/price"))
            shipping_ok = feats.get("/item_shipping_allowed", "").lower() in ("1", "true", "sì", "si") \
                or "spedizione" in feats.get("/item_shipping_allowed#value", "").lower()
            ship_cost = parse_price(feats.get("/item_shipping_cost")) if feats.get("/item_shipping_cost") else None
            geo = ad.get("geo") or {}
            town = st.text_of((geo.get("town") or {}).get("value") if isinstance(geo.get("town"), dict) else geo.get("town"))
            city = st.text_of((geo.get("city") or {}).get("short_name") if isinstance(geo.get("city"), dict) else geo.get("city"))
            coords = geo.get("map") or geo.get("coordinates") or {}
            lat = coords.get("latitude") if isinstance(coords, dict) else None
            lon = coords.get("longitude") if isinstance(coords, dict) else None
            advertiser = ad.get("advertiser") or {}
            company = bool(advertiser.get("company")) if isinstance(advertiser, dict) else False
            images = ad.get("images") or []
            offer = Offer(
                source_id=self.id, offer_id=oid, url_canonico=link, titolo=str(ad.get("subject", "")),
                prezzo=price, spedizione_eur=ship_cost if shipping_ok else None,
                disponibilita="disponibile" if price else "sconosciuta",
                venditore=st.text_of(advertiser.get("name")) if isinstance(advertiser, dict) else "",
                venditore_tipo="terzo" if company else "privato",
                localita_annuncio=", ".join(x for x in (town, city) if x),
                localita_lat=float(lat) if lat is not None else None,
                localita_lon=float(lon) if lon is not None else None,
                solo_ritiro=not shipping_ok, ha_foto=bool(images), verificata_su_pagina_prodotto=True,
                consegna_testo="spedizione possibile" if shipping_ok else "solo ritiro di persona",
                rilevata_il=utcnow(),
            )
            if offer.solo_ritiro:
                offer.spedizione_eur = parse_price("0")
            out.append(self.finalize(offer))
        return out

    def parse_product(self, html: str, url: str) -> list[Offer]:
        return self.parse_search(html, url)
