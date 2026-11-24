"""Rebuy (www.rebuy.it). Usato e ricondizionato professionale.

Lettura basata sui dati strutturati schema.org (JSON-LD / Open Graph) della pagina.
ATTENZIONE: fonte NON verificata dal vivo (sito non raggiungibile dall'ambiente di sviluppo):
lo stato reale si vede con il workflow "monitor" lanciato con l'opzione "diagnostica".
"""
from .base import Source


class RebuySource(Source):
    id = "rebuy"
    nome = "Rebuy"
    tipo = "marketplace"
    ha_negozi_fisici = False
    solo_nuovo = False
    dominio = "www.rebuy.it"
    venditore_tipo_predefinito = "terzo"
    condizione_predefinita = "usato"
    catena = None
