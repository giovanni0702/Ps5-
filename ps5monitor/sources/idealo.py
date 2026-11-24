"""Idealo.it (www.idealo.it): aggregatore di prezzi, usato solo in modalità "ricerca".

ATTENZIONE: fonte NON verificata dal vivo (sito non raggiungibile dall'ambiente di sviluppo).
"""
from .aggregator import AggregatorSource


class IdealoSource(AggregatorSource):
    id = "idealo"
    nome = "Idealo.it"
    dominio = "www.idealo.it"
