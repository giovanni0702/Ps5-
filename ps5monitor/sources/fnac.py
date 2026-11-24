"""Fnac (www.fnac.it). Disattivata: vedi FONTI.md.

Lettura basata sui dati strutturati schema.org (JSON-LD / Open Graph) della pagina.
ATTENZIONE: fonte NON verificata dal vivo (sito non raggiungibile dall'ambiente di sviluppo):
lo stato reale si vede con il workflow "monitor" lanciato con l'opzione "diagnostica".
"""
from .base import Source


class FnacSource(Source):
    id = "fnac"
    nome = "Fnac"
    tipo = "retailer"
    ha_negozi_fisici = True
    solo_nuovo = True
    dominio = "www.fnac.it"
    venditore_tipo_predefinito = "negozio"
    condizione_predefinita = None
    catena = "fnac"
