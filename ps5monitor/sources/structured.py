"""Lettura dei dati strutturati standard (schema.org JSON-LD, meta Open Graph) e pulsanti di acquisto.

Questi formati sono standard pubblici e non dipendono dal layout del singolo negozio:
sono la base di quasi tutti gli adapter.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup

# --- JSON-LD ----------------------------------------------------------------


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _flatten(obj: Any, out: list[dict]) -> None:
    if isinstance(obj, list):
        for o in obj:
            _flatten(o, out)
    elif isinstance(obj, dict):
        out.append(obj)
        if "@graph" in obj:
            _flatten(obj["@graph"], out)


def jsonld_objects(soup: BeautifulSoup) -> list[dict]:
    out: list[dict] = []
    for tag in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:
                data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
            except json.JSONDecodeError:
                continue
        _flatten(data, out)
    return out


def types_of(obj: dict) -> set[str]:
    t = obj.get("@type", [])
    if isinstance(t, str):
        t = [t]
    return {str(x).split("/")[-1].lower() for x in t}


def as_list(v: Any) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def text_of(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return str(v.get("name") or v.get("@value") or "")
    if isinstance(v, list):
        return text_of(v[0]) if v else ""
    return str(v)


def find_products(objs: Iterable[dict]) -> list[dict]:
    """Prodotti dichiarati nella pagina, inclusi quelli dentro ItemList e ProductGroup."""
    products: list[dict] = []
    seen: set[int] = set()

    def add(p: dict) -> None:
        if id(p) not in seen:
            seen.add(id(p))
            products.append(p)

    for o in objs:
        t = types_of(o)
        if "product" in t or "individualproduct" in t:
            add(o)
        if "productgroup" in t:
            for v in as_list(o.get("hasVariant")):
                if isinstance(v, dict):
                    v.setdefault("name", o.get("name"))
                    add(v)
        if "itemlist" in t:
            for el in as_list(o.get("itemListElement")):
                if isinstance(el, dict):
                    item = el.get("item", el)
                    if isinstance(item, dict) and types_of(item) & {"product", "individualproduct"}:
                        add(item)
    return products


def breadcrumb_leaf(objs: Iterable[dict]) -> str:
    """Ultimo livello del BreadcrumbList (la categoria foglia), escludendo il prodotto stesso."""
    for o in objs:
        if "breadcrumblist" in types_of(o):
            items = []
            for el in as_list(o.get("itemListElement")):
                if isinstance(el, dict):
                    pos = el.get("position", 0)
                    name = el.get("name") or text_of(el.get("item"))
                    try:
                        pos = int(pos)
                    except (TypeError, ValueError):
                        pos = 0
                    items.append((pos, str(name).strip()))
            items.sort()
            names = [n for _, n in items if n]
            if names:
                return names[-1]
    return ""


AVAIL_MAP = {
    "instock": "instock", "onlineonly": "instock", "instoreonly": "instock",
    "limitedavailability": "limited",
    "preorder": "preorder", "presale": "preorder", "backorder": "preorder",
    "outofstock": "outofstock", "soldout": "outofstock", "discontinued": "outofstock",
}


def schema_availability(v: Any) -> str | None:
    s = text_of(v).strip()
    if not s:
        return None
    return AVAIL_MAP.get(s.rstrip("/").split("/")[-1].lower())


def schema_condition(v: Any) -> str | None:
    s = text_of(v).lower()
    if "refurbished" in s:
        return "ricondizionato"
    if "used" in s or "damaged" in s:
        return "usato"
    if "new" in s:
        return "nuovo"
    return None


def strike_price(offer: dict) -> Any:
    for spec in as_list(offer.get("priceSpecification")):
        if isinstance(spec, dict):
            pt = text_of(spec.get("priceType")).lower()
            if "strikethrough" in pt or "listprice" in pt or "msrp" in pt:
                return spec.get("price")
    return None


def offer_price(offer: dict) -> Any:
    for key in ("price", "lowPrice"):
        if offer.get(key) not in (None, ""):
            return offer[key]
    for spec in as_list(offer.get("priceSpecification")):
        if isinstance(spec, dict) and spec.get("price") is not None:
            pt = text_of(spec.get("priceType")).lower()
            if "strikethrough" not in pt and "listprice" not in pt:
                return spec["price"]
    return None


def shipping_cost(offer: dict) -> Any:
    for sd in as_list(offer.get("shippingDetails")):
        if isinstance(sd, dict):
            rate = sd.get("shippingRate")
            if isinstance(rate, dict) and rate.get("value") is not None:
                return rate["value"]
    return None


# --- Open Graph fallback ----------------------------------------------------


def og_product(soup: BeautifulSoup) -> dict | None:
    def meta(prop: str) -> str | None:
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        return tag.get("content") if tag and tag.get("content") else None

    price = meta("product:price:amount") or meta("og:price:amount")
    title = meta("og:title")
    if not price or not title:
        return None
    return {
        "@type": "Product", "name": title, "url": meta("og:url"),
        "offers": {"price": price, "priceCurrency": meta("product:price:currency") or "EUR",
                   "availability": meta("product:availability") or meta("og:availability")},
    }


# --- Pulsante di acquisto attivo (R3.4) ------------------------------------

BUY_TEXT_RE = re.compile(
    r"(aggiungi\s+al\s+carrello|aggiungi\s+al\s+cestino|acquista(\s+ora|\s+subito)?$|compra(\s+ora|\s+subito)?$|"
    r"add\s+to\s+(cart|basket)|buy\s+now|metti\s+nel\s+carrello)",
    re.I,
)


def _is_disabled(tag) -> bool:
    for t in [tag, *list(tag.parents)[:2]]:
        if t is None or not hasattr(t, "attrs"):
            continue
        if t.has_attr("disabled") or str(t.get("aria-disabled", "")).lower() == "true":
            return True
        cls = " ".join(t.get("class", [])) if isinstance(t.get("class"), list) else str(t.get("class", ""))
        if re.search(r"(^|[\s_-])(disabled|is-disabled|unavailable|out-of-stock|soldout)($|[\s_-])", cls, re.I):
            return True
    return False


def has_active_buy_button(root) -> bool:
    for tag in root.find_all(["button", "input", "a"]):
        label = tag.get("value", "") if tag.name == "input" else tag.get_text(" ", strip=True)
        label = (label or tag.get("aria-label", "") or "").strip()
        if label and BUY_TEXT_RE.search(label) and not _is_disabled(tag):
            return True
    return False
