# Fonti del monitor

## Esito della verifica dal vivo (R1.2)

Verifica tentata il **24/11/2026** dall'ambiente in cui è stato costruito il monitor.

**Nessuna fonte è stata raggiungibile da quell'ambiente.** La rete del container di sviluppo
permette solo i registri dei pacchetti: ogni richiesta ai negozi è stata rifiutata dal proxy
dell'ambiente (`CONNECT tunnel failed, response 403`) e anche lo strumento di lettura web non ha
risolto i nomi dei siti (`getaddrinfo ENOTFOUND`). È un limite dell'ambiente di sviluppo, non un
problema dei siti: **non dice niente su come si comportano con GitHub Actions.**

Per questo:

- nessun esito qui sotto è "funziona": la colonna "Esito" dice solo che la verifica non è stata possibile;
- gli adapter leggono soprattutto dati standard (schema.org JSON-LD, Open Graph), che non dipendono
  dal layout del singolo sito; per Amazon, eBay e Subito usano la struttura pubblica nota delle pagine,
  **non provata dal vivo**;
- gli URL di ricerca in `config.yaml` sono quelli noti pubblicamente, **non verificati**;
- nessun URL fisso di pagina prodotto è configurato (`prodotti: []`), perché non è stato possibile
  verificarne nessuno;
- le fonti restano abilitate (tranne Fnac): il monitor stesso fa da verifica. Una fonte che non risponde
  diventa "degradata" o "bloccata" e si ferma da sola, senza insistere (R1.5).

**Il vero esito si vede con la prima esecuzione del workflow `monitor` con l'opzione `diagnostica`**
(SETUP.md, passo 6). Dopo quella, aggiorna questa tabella: per ogni fonte che risulta "bloccata"
o con "0 offerte lette", metti `abilitata: false` in `config.yaml` e scrivi qui il motivo.

| Fonte | Tipo | Abilitata | Esito della verifica | Data | Motivo |
|---|---|---|---|---|---|
| Amazon.it | marketplace | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo (proxy 403); selettori HTML noti, non provati |
| MediaWorld | retailer | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; lettura schema.org |
| Unieuro | retailer | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; lettura schema.org |
| Euronics | retailer | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; lettura schema.org |
| Expert | retailer | sì | non verificata | 24/11/2026 | non raggiungibile; dominio usato `www.expertonline.it`, da confermare |
| Trony | retailer | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; lettura schema.org |
| Fnac.it | retailer | **no** | non verificata | 24/11/2026 | non raggiungibile; inoltre, per quanto noto pubblicamente, Fnac ha lasciato l'Italia nel 2014 (negozi passati a Trony): da confermare con la diagnostica prima di riattivarla |
| ePRICE | retailer | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; l'attività del sito va confermata |
| GameStop.it | retailer | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; lettura schema.org |
| PlayStation Direct Italia | retailer | sì | non verificata | 24/11/2026 | non raggiungibile; pagina `direct.playstation.com/it-it/buy-consoles`; listino non letto (vedi sotto) |
| Carrefour.it | retailer | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; lettura schema.org |
| Rebuy.it | marketplace | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; lettura schema.org |
| Backmarket.it | marketplace | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; lettura schema.org |
| eBay.it | marketplace | sì | non verificata | 24/11/2026 | non raggiungibile; selettori `s-item`/`s-card` noti, non provati |
| Subito.it | classificati | sì | non verificata | 24/11/2026 | non raggiungibile; lettura del JSON `__NEXT_DATA__`, struttura non provata |
| Trovaprezzi.it | aggregatore | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; lettura schema.org |
| Idealo.it | aggregatore | sì | non verificata | 24/11/2026 | non raggiungibile dall'ambiente di sviluppo; lettura schema.org |

### Listino ufficiale (R3.6)

I prezzi di listino di PlayStation Direct Italia **non sono stati letti** (sito non raggiungibile).
In `config.yaml` restano `null`: lo sconto rispetto al listino non si calcola. Lo sconto si valuta
comunque con il prezzo barrato dichiarato dal negozio e, dopo qualche giorno, con lo storico dei prezzi.
Se conosci i prezzi correnti, scrivili in `listino_ufficiale`.

### Negozi di Milano (R8.3)

`data/negozi.yaml` è vuoto per lo stesso motivo: nessun indirizzo o telefono è stato verificato,
quindi nessuno è stato inventato. Gli avvisi delle catene con negozi fisici riportano la frase
"Disponibilità nei negozi di Milano non verificabile dal sito: verifica per telefono".
Se una pagina prodotto dichiara la disponibilità per negozio nel formato standard schema.org
(`availableAtOrFrom`), il monitor la legge e calcola le distanze da Milano.

## Come vengono controllate (R1.3, R6.9)

- Ogni sito riceve al massimo **1 richiesta ogni 30-40 secondi** e ogni URL al massimo una volta al minuto.
- Per sito e per ciclo (circa 60 s): 1 richiesta per la pagina di ricerca o prodotto, più 1 riservata
  alla verifica della pagina prodotto prima di un avviso (R4.5).
- Siti diversi vengono controllati in parallelo (fino a 8 alla volta).

### Frequenza reale per URL

| Configurazione della fonte | Frequenza reale |
|---|---|
| Solo `ricerca` (come ora per tutte le fonti) | la ricerca ogni ciclo, circa ogni 60 s |
| `prodotti` con N URL e `ricerca_ogni_cicli: 5` | ogni URL prodotto circa ogni N × 75 s; la ricerca ogni 5 cicli (circa 5 minuti) |
| Aggregatori (Trovaprezzi, Idealo) | solo ricerca, circa ogni 60 s |

Tra un'esecuzione di GitHub e la successiva possono passare alcuni minuti (vedi README, "Limiti").
