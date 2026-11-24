"""Euronics (www.euronics.it). Catena con negozi fisici.

Lettura basata sui dati strutturati schema.org (JSON-LD / Open Graph) della pagina.
ATTENZIONE: fonte NON verificata dal vivo (sito non raggiungibile dall'ambiente di sviluppo):
lo stato reale si vede con il workflow "monitor" lanciato con l'opzione "diagnostica".
"""
from .base import Source


class EuronicsSource(Source):
    id = "euronics"
    nome = "Euronics"
    tipo = "retailer"
    ha_negozi_fisici = True
    solo_nuovo = True
    dominio = "www.euronics.it"
    venditore_tipo_predefinito = "negozio"
    condizione_predefinita = None
    catena = "euronics"
