"""Classe base degli adapter (R1.1) e lettore generico basato su schema.org."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from ..classify import detect_bundle, detect_condition, detect_model, normalize_title
from ..geo import haversine_km
from ..models import NegozioMilano, Offer, utcnow
from ..pricing import parse_price
from . import structured as st

TRACKING_PARAMS = re.compile(
    r"^(utm_.*|ref|ref_|tag|gclid|fbclid|msclkid|mc_.*|aff.*|cmpid|srsltid|_trk.*|hash|campid|customid|mkevt|"
    r"mkcid|mkrid|toolid|linkcode|linkid|camp|creative|creativeasin|ascsubtag|psc|spm|sr|qid|keywords|crid|"
    r"sprefix|dib|dib_tag|th|smid|pf_rd_.*|pd_rd_.*|content-id|source|from|trk|cid|_ga|icid|ns|epik)$",
    re.I,
)


def canonical_url(url: str) -> str:
    """URL senza parametri di tracciamento né frammento (R5.2)."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING_PARAMS.match(k)]
    return urlunsplit((parts.scheme or "https", parts.netloc.lower(), parts.path, urlencode(query), ""))


def short_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


@dataclass
class PlannedRequest:
    mode: str   # "prodotto" oppure "ricerca"
    url: str


class Source:
    """Metadati e logica comune di una fonte. Le sottoclassi cambiano solo ciò che serve."""

    id = ""
    nome = ""
    tipo = "retailer"               # retailer, marketplace, aggregatore, classificati
    ha_negozi_fisici = False
    spedisce_italia = True
    solo_nuovo = True
    abilitata = True                # valore predefinito; config.yaml decide
    dominio = ""
    venditore_tipo_predefinito = "negozio"
    condizione_predefinita: str | None = None
    catena: str | None = None       # chiave in data/negozi.yaml

    def __init__(self, cfg, fetcher, stores: dict | None = None):
        self.cfg = cfg
        self.fetcher = fetcher
        self.stores = (stores or {}).get(self.catena or self.id, [])

    # --- pianificazione (R1.3, R6.9) ---------------------------------------
    @property
    def sc(self):
        return self.cfg.fonti.get(self.id)

    def enabled(self) -> bool:
        return bool(self.sc and self.sc.abilitata)

    def plan(self, cycle: int, rr_index: int) -> PlannedRequest | None:
        sc = self.sc
        if sc is None:
            return None
        if self.tipo == "aggregatore" or not sc.prodotti:
            return PlannedRequest("ricerca", sc.ricerca) if sc.ricerca else None
        if sc.ricerca and cycle % sc.ricerca_ogni_cicli == sc.ricerca_ogni_cicli - 1:
            return PlannedRequest("ricerca", sc.ricerca)
        return PlannedRequest("prodotto", sc.prodotti[rr_index % len(sc.prodotti)])

    # --- interfaccia R1.1 ---------------------------------------------------
    def fetch_offers(self, config=None, cycle: int = 0, rr_index: int = 0, deadline: float | None = None) -> list[Offer]:
        req = self.plan(cycle, rr_index)
        if req is None:
            return []
        resp = self.fetcher.get(req.url, deadline)
        self.last_ms = resp.ms
        if req.mode == "prodotto":
            return self.parse_product(resp.text, resp.url)
        return self.parse_search(resp.text, resp.url)

    def can_verify(self, offer: Offer) -> bool:
        return self.tipo != "aggregatore" and offer.url_canonico.startswith("http")

    def verify(self, offer: Offer, deadline: float | None = None) -> Offer | None:
        """Ricarica la pagina prodotto (R4.5) e restituisce l'offerta letta lì, oppure None."""
        resp = self.fetcher.get(self.product_url(offer), deadline)
        found = self.parse_product(resp.text, resp.url)
        for o in found:
            if o.offer_id == offer.offer_id:
                return o
        return found[0] if len(found) == 1 else None

    def product_url(self, offer: Offer) -> str:
        return offer.url_canonico

    # --- parsing generico ---------------------------------------------------
    def parse_search(self, html: str, url: str) -> list[Offer]:
        return self.parse_structured(html, url, verified=False)

    def parse_product(self, html: str, url: str) -> list[Offer]:
        return self.parse_structured(html, url, verified=True)

    def offer_id_from_url(self, url: str) -> str:
        path = urlsplit(url).path.rstrip("/")
        m = re.search(r"(\d{5,})(?:\.html?)?$", path)
        return m.group(1) if m else short_id(path or url)

    def finalize(self, o: Offer, dichiarata: str | None = None) -> Offer:
        o.titolo = normalize_title(o.titolo)
        o.modello = detect_model(o.titolo)
        o.condizione = detect_condition(o.titolo, self.solo_nuovo, o.venditore_tipo,
                                        dichiarata or self.condizione_predefinita)
        o.bundle = detect_bundle(o.titolo)
        o.url_canonico = canonical_url(o.url_canonico)
        if self.tipo == "aggregatore":
            o.add_flag("da_verificare_sul_negozio")
        return o

    def _availability(self, schema: str | None, button: bool, verified: bool) -> str:
        if schema == "preorder":
            return "in_arrivo"
        if schema == "outofstock":
            return "non_disponibile"
        if schema in ("instock", "limited"):
            # R3.4: "disponibile" solo con un'azione di acquisto attiva visibile.
            # Per gli aggregatori l'azione è il link all'offerta del negozio.
            if self.tipo == "aggregatore" or (verified and button):
                return "ultime_unita" if schema == "limited" else "disponibile"
        return "sconosciuta"

    def _stores_from_offers(self, offers: list[dict]) -> list[NegozioMilano]:
        out = []
        for of in offers:
            place = of.get("availableAtOrFrom")
            if not isinstance(place, dict):
                continue
            if st.schema_availability(of.get("availability")) not in ("instock", "limited"):
                continue
            geo = place.get("geo") or {}
            try:
                lat, lon = float(geo.get("latitude")), float(geo.get("longitude"))
            except (TypeError, ValueError):
                continue
            dist = haversine_km(self.cfg.lat, self.cfg.lon, lat, lon)
            if dist > Decimal(str(self.cfg.raggio_km)):
                continue
            addr = place.get("address") or {}
            out.append(NegozioMilano(
                nome=st.text_of(place.get("name")), comune=st.text_of(addr.get("addressLocality")) if isinstance(addr, dict) else "",
                telefono=st.text_of(place.get("telephone")), distanza_km=dist,
                tempi_ritiro=st.text_of(of.get("description")) or st.text_of(of.get("deliveryLeadTime")),
            ))
        out.sort(key=lambda n: n.distanza_km)
        return out

    def _seller_type(self, seller_name: str) -> str:
        return self.venditore_tipo_predefinito

    def parse_structured(self, html: str, url: str, verified: bool) -> list[Offer]:
        soup = st.soup_of(html)
        objs = st.jsonld_objects(soup)
        products = st.find_products(objs)
        if not products:
            og = st.og_product(soup)
            products = [og] if og else []
        leaf = st.breadcrumb_leaf(objs)
        button = st.has_active_buy_button(soup) if verified else False
        out: list[Offer] = []
        for p in products:
            name = st.text_of(p.get("name")).strip()
            if not name:
                continue
            offers = [o for o in st.as_list(p.get("offers")) if isinstance(o, dict)]
            expanded = []
            for o in offers:
                if "aggregateoffer" in st.types_of(o) and o.get("offers"):
                    expanded.extend(x for x in st.as_list(o["offers"]) if isinstance(x, dict))
                else:
                    expanded.append(o)
            online = [o for o in expanded if not isinstance(o.get("availableAtOrFrom"), dict)] or expanded[:1]
            negozi = self._stores_from_offers(expanded)
            pid = st.text_of(p.get("sku") or p.get("productID") or p.get("gtin13") or p.get("gtin") or p.get("mpn"))
            purl = st.text_of(p.get("url")) or url
            targets = online if self.tipo == "aggregatore" else online[:1]
            for of in targets:
                seller = st.text_of(of.get("seller")).strip()
                o_url = urljoin(url, st.text_of(of.get("url")) or purl)
                oid = pid or self.offer_id_from_url(urljoin(url, purl))
                if self.tipo == "aggregatore":
                    oid = f"{oid}-{short_id(seller or o_url)}"
                price_raw = st.offer_price(of)
                avail = self._availability(st.schema_availability(of.get("availability")), button, verified)
                ship = st.shipping_cost(of)
                qty = of.get("inventoryLevel")
                qty_val = None
                if isinstance(qty, dict):
                    try:
                        qty_val = int(float(qty.get("value")))
                    except (TypeError, ValueError):
                        qty_val = None
                offer = Offer(
                    source_id=self.id, offer_id=str(oid), url_canonico=o_url, titolo=name,
                    prezzo=parse_price(price_raw), prezzo_barrato=parse_price(st.strike_price(of)),
                    spedizione_eur=parse_price(ship) if ship is not None else None,
                    disponibilita=avail, venditore=seller or self.nome,
                    venditore_tipo=self._seller_type(seller), valuta=(st.text_of(of.get("priceCurrency")) or "EUR").upper(),
                    categoria=leaf or st.text_of(p.get("category")).split(">")[-1].strip(),
                    quantita_disponibile=qty_val, garanzia_testo=st.text_of(p.get("warranty") or of.get("warranty")),
                    verificata_su_pagina_prodotto=verified and self.tipo != "aggregatore",
                    rilevata_il=utcnow(), ha_foto=bool(p.get("image")) if "image" in p else None,
                )
                if negozi:
                    offer.negozi_milano = negozi
                    offer.canale = "entrambi" if avail in ("disponibile", "ultime_unita") else "ritiro_milano"
                    if offer.canale == "ritiro_milano" and avail in ("sconosciuta", "non_disponibile") and verified:
                        offer.disponibilita = "disponibile" if button else offer.disponibilita
                out.append(self.finalize(offer, st.schema_condition(of.get("itemCondition"))))
        return out
