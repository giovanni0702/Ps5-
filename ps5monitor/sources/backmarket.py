"""Back Market (www.backmarket.it). Marketplace di ricondizionati.

Lettura basata sui dati strutturati schema.org (JSON-LD / Open Graph) della pagina.
ATTENZIONE: fonte NON verificata dal vivo (sito non raggiungibile dall'ambiente di sviluppo):
lo stato reale si vede con il workflow "monitor" lanciato con l'opzione "diagnostica".
"""
from .base import Source


class BackMarketSource(Source):
    id = "backmarket"
    nome = "Back Market"
    tipo = "marketplace"
    ha_negozi_fisici = False
    solo_nuovo = False
    dominio = "www.backmarket.it"
    venditore_tipo_predefinito = "terzo"
    condizione_predefinita = "ricondizionato"
    catena = None
