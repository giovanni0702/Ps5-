# Fixture dei test

Queste pagine HTML sono **sintetiche**: scritte a mano durante la costruzione, perché i siti
dei negozi non erano raggiungibili dall'ambiente di sviluppo (vedi FONTI.md).

- Seguono formati standard (schema.org JSON-LD, Open Graph) o la struttura pubblica nota di
  Amazon, eBay e Subito.
- **Non sono copie di pagine reali** e non contengono dati personali: nomi di venditori,
  negozi, località e codici sono inventati (per esempio ASIN `B0TEST0001`).
- Servono a verificare la logica del monitor senza rete (G8), non a dimostrare che i
  selettori funzionino sui siti veri. Quello lo dice la "diagnostica" su GitHub.

`fixtures.yaml` collega gli URL usati con `--fixture` ai file di questa cartella.
