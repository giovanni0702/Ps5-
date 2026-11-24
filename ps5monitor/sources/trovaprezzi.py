"""Trovaprezzi.it (www.trovaprezzi.it): aggregatore di prezzi, usato solo in modalità "ricerca".

ATTENZIONE: fonte NON verificata dal vivo (sito non raggiungibile dall'ambiente di sviluppo).
"""
from .aggregator import AggregatorSource


class TrovaprezziSource(AggregatorSource):
    id = "trovaprezzi"
    nome = "Trovaprezzi.it"
    dominio = "www.trovaprezzi.it"
