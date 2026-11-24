"""Riconoscimento di una console PS5 vera e classificazione di modello, condizione, bundle (R2)."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Iterable

# (a) pattern console: playstation 5, playstation5, ps5, ps 5, ps-5 e codici CFI-1xxx/2xxx/7xxx
CONSOLE_RE = re.compile(
    r"(?<![\w])(?:playstation[\s-]?5|ps[\s-]?5|cfi[\s-]?[127]\d{3}[a-z]?)(?![\w])",
    re.IGNORECASE,
)
# Parole che, subito prima del pattern console, indicano un accessorio "per PS5"
_ACCESSORY_PREFIX_RE = re.compile(
    r"(?:(?<![\w])(?:per|for|compatibile\s+con|compatible\s+with|compatibili\s+con)"
    r"(?:\s+(?:la|il|le|i|console|consolle|sony|playstation|the))*\s*)$",
    re.IGNORECASE,
)
_CONSOLE_WORD_RE = re.compile(r"(?<![\w])(?:console|consolle)(?![\w])", re.IGNORECASE)
_STRONG_INTRO_RE = re.compile(
    r"(?:(?<![\w])(?:con|include|incluso|inclusa|inclusi|più|bundle|pack|e)(?![\w]))|\+",
    re.IGNORECASE,
)
_WEAK_INTRO_RE = re.compile(
    r"(?:(?<![\w])(?:con|include|incluso|inclusa|inclusi|bundle)(?![\w]))|\+",
    re.IGNORECASE,
)
_STORAGE_WORDS = {"ssd", "hdd", "hard disk"}
_CATEGORY_BAD_RE = re.compile(r"(?<![\w])(?:accessori|giochi|videogiochi|controller)(?![\w])", re.IGNORECASE)


def _phrase_re(phrase: str) -> re.Pattern:
    parts = [re.escape(p) for p in phrase.lower().split()]
    return re.compile(r"(?<![\w])" + r"[\s-]+".join(parts) + r"(?![\w])", re.IGNORECASE)


def _valid_console_positions(title: str) -> list[int]:
    """Posizioni del pattern console non precedute da 'per', 'for', 'compatibile con'."""
    out = []
    for m in CONSOLE_RE.finditer(title):
        before = title[: m.start()]
        if _ACCESSORY_PREFIX_RE.search(before):
            continue
        out.append(m.start())
    return out


def _console_word_ok(title: str) -> bool:
    for m in _CONSOLE_WORD_RE.finditer(title):
        if not _ACCESSORY_PREFIX_RE.search(title[: m.start()]):
            return True
    return False


def _introduced(title: str, pos: int, consoles: list[int], intro_re: re.Pattern) -> bool:
    """True se prima di `pos` c'è un'introduzione (con, +, bundle...) preceduta da una console valida."""
    intros = [m.start() for m in intro_re.finditer(title, 0, pos)]
    if not intros:
        return False
    return any(c < i for i in intros for c in consoles)


def normalize_title(titolo: str) -> str:
    """Toglie simboli ®/™ e spazi multipli."""
    t = (titolo or "").replace("®", "").replace("™", "").replace("©", "")
    return " ".join(t.split())


def has_defect(title: str, parole_difetto: Iterable[str]) -> str | None:
    for w in parole_difetto:
        if _phrase_re(w).search(title):
            return w
    return None


def is_console(
    titolo: str,
    prezzo: Decimal | None,
    categoria: str = "",
    *,
    forti: Iterable[str],
    deboli: Iterable[str],
    difetto: Iterable[str] = (),
    prezzo_min: Decimal = Decimal("250"),
) -> tuple[bool, str]:
    """Restituisce (è_console, motivo). Il motivo è sempre valorizzato (R2.2)."""
    title = normalize_title(titolo)
    if not title:
        return False, "esclusa: titolo vuoto"
    if not CONSOLE_RE.search(title):
        return False, "esclusa: nessun riferimento a PS5 nel titolo"
    consoles = _valid_console_positions(title)
    d = has_defect(title, difetto)
    if d:
        return False, f"esclusa: difetto dichiarato ('{d}')"
    # (b) esclusioni forti
    for word in forti:
        for m in _phrase_re(word).finditer(title):
            w = word.lower()
            if w in _STORAGE_WORDS:
                if any(c < m.start() for c in consoles):
                    continue
                return False, f"esclusa: parola '{w}'"
            if _introduced(title, m.start(), consoles, _STRONG_INTRO_RE):
                continue
            return False, f"esclusa: parola '{w}'"
    # (c) esclusioni deboli
    console_word = _console_word_ok(title)
    for word in deboli:
        for m in _phrase_re(word).finditer(title):
            if console_word or _introduced(title, m.start(), consoles, _WEAK_INTRO_RE):
                continue
            return False, f"esclusa: parola '{word.lower()}' senza 'console'"
    if not consoles:
        return False, "esclusa: PS5 citata solo come compatibilità ('per PS5')"
    # (d) prezzo minimo
    if prezzo is None or prezzo <= 0:
        return False, "esclusa: prezzo_non_leggibile"
    if prezzo < prezzo_min:
        return False, f"esclusa: prezzo {prezzo} sotto il minimo per una console ({prezzo_min})"
    # (e) categoria foglia
    cat = (categoria or "").strip()
    if cat:
        m = _CATEGORY_BAD_RE.search(cat)
        if m and not _CONSOLE_WORD_RE.search(cat):
            return False, f"esclusa: categoria '{cat}'"
    return True, "console"


def is_console_cfg(titolo: str, prezzo: Decimal | None, categoria: str, cfg) -> tuple[bool, str]:
    return is_console(
        titolo, prezzo, categoria,
        forti=cfg.parole_escluse_forti, deboli=cfg.parole_escluse_deboli,
        difetto=cfg.parole_difetto, prezzo_min=cfg.prezzo_min_console_eur,
    )


_MULTI_MODEL_RE = re.compile(
    r"(?<![\w])(digital|standard|pro|disc|disco|lettore)(?![\w])\s*(?:o|/|oppure|or|\|)\s*"
    r"(?<![\w])(digital|standard|pro|disc|disco|con\s+lettore|lettore)(?![\w])",
    re.IGNORECASE,
)
_SPECIAL_RE = re.compile(r"(?<![\w])(edition|edizione|limited|limitata|anniversary|anniversario)(?![\w])", re.I)


def _has(title: str, word: str) -> bool:
    return bool(_phrase_re(word).search(title))


def detect_model(titolo: str) -> str:
    t = normalize_title(titolo)
    m = _MULTI_MODEL_RE.search(t)
    if m and m.group(1).lower() != m.group(2).lower().replace("con ", ""):
        return "sconosciuto"
    if _has(t, "pro") or re.search(r"(?<![\w])cfi[\s-]?7\d{3}", t, re.I):
        return "pro"
    if _has(t, "digital") and not _has(t, "lettore"):
        return "digital"
    if not _has(t, "digital") and any(_has(t, w) for w in ("standard", "disc", "disco", "con lettore", "slim")):
        return "standard_disc"
    if _has(t, "digital") and _has(t, "lettore"):
        return "standard_disc"
    if _SPECIAL_RE.search(t):
        return "altro_console"
    return "sconosciuto"


def detect_condition(titolo: str, solo_nuovo: bool, venditore_tipo: str = "negozio",
                     dichiarata: str | None = None) -> str:
    t = titolo or ""
    if any(_has(t, w) for w in ("ricondizionato", "ricondizionata", "renewed", "refurbished", "rigenerato", "rigenerata")):
        return "ricondizionato"
    if any(_has(t, w) for w in ("usato", "usata", "seconda mano", "used")):
        return "usato"
    if _has(t, "come nuovo") or _has(t, "come nuova"):
        return "usato" if venditore_tipo == "privato" else (dichiarata or "sconosciuta")
    if dichiarata in ("nuovo", "ricondizionato", "usato"):
        return dichiarata
    if _has(t, "nuovo") or _has(t, "nuova") or _has(t, "new"):
        return "nuovo"
    if solo_nuovo:
        return "nuovo"
    if venditore_tipo == "privato":
        return "usato"
    return "sconosciuta"


_BUNDLE_RE = re.compile(r"(?:\+|(?<![\w])(?:con|bundle|include|incluso|inclusa|pack)(?![\w]))\s*(.+)$", re.I)
_NOT_BUNDLE = re.compile(r"^(?:lettore|disco|unità|unita)\b", re.I)


def detect_bundle(titolo: str) -> str:
    """Descrive cosa è incluso oltre alla console (gioco, controller aggiuntivo...)."""
    t = normalize_title(titolo)
    consoles = [m.end() for m in CONSOLE_RE.finditer(t)]
    if not consoles:
        return ""
    tail = t[consoles[0]:]
    for m in _BUNDLE_RE.finditer(tail):
        content = m.group(1).strip(" -–,.")
        if _NOT_BUNDLE.match(content):
            continue
        if content:
            return content[:120]
    if re.search(r"(?<![\w])bundle(?![\w])", t, re.I):
        return "bundle"
    return ""
