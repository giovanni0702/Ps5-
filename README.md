# Monitor PS5 Italia

Controlla di continuo i siti italiani (negozi con punti vendita in Italia, negozi online che
spediscono in Italia, Amazon, marketplace, comparatori di prezzo) e ti avvisa sul telefono appena
trova una **console PlayStation 5 vera**, di qualsiasi modello e condizione, con **prezzo totale
(prezzo + spedizione) pari o inferiore a 700 €**. Le offerte **in sconto** hanno la precedenza assoluta.

Gira **gratis su GitHub Actions**: nessun server, nessun PC acceso.

Per attivarlo segui **[SETUP.md](SETUP.md)** (circa 20 minuti, non serve saper programmare).

## Cosa ricevi

Notifiche sull'app **ntfy** del telefono (gratuita, senza account):

| Messaggio | Quando | Priorità |
|---|---|---|
| `[SCONTO -14,7%] PS5 Digital a 469,00 € su Amazon.it` | offerta disponibile e in sconto (P1 negozio/Amazon, P2 venditore terzo o privato); parte subito, da sola | alta |
| `[DISPONIBILE] PS5 Digital a 499,00 € su MediaWorld` | offerte disponibili non in sconto (P3, P4), raccolte a fine ciclo, al massimo 10 per messaggio | normale |
| `[AVVIO] Monitor avviato` | una volta, alla prima esecuzione | normale |
| `[REPORT] Monitor PS5 – data` | ogni giorno dopo le 09:00 (ora di Roma): stato delle fonti, offerte migliori, avvisi del giorno | bassa |
| `[ALLARME] Monitor cieco` | se nessuna fonte funziona da più di 60 minuti (al massimo ogni 6 ore) | alta |

Ogni avviso contiene: priorità, titolo, negozio, modello e condizione, bundle, prezzo, prezzo di
riferimento e sconto, spedizione e totale, disponibilità, consegna, garanzia, venditore, ritiro a
Milano, avvertenze di rischio, data e ora, **link diretto** alla pagina (per Amazon anche il link
"aggiungi al carrello"). Il monitor **non compra nulla** e non scrive mai ai venditori.

## Come funziona

1. Ogni 5 minuti GitHub avvia il workflow `monitor`, che resta attivo circa 4,5 minuti e ripete
   un ciclo di controllo ogni minuto circa.
2. In ogni ciclo legge le pagine di ricerca (o le pagine prodotto) delle fonti abilitate, rispettando
   i siti: al massimo una richiesta ogni 30-40 secondi per sito, nessun login, nessun captcha.
3. Scarta accessori, giochi, abbonamenti, annunci "per ricambi" o "scatola vuota" (oltre 60 titoli di prova nei test).
4. Calcola prezzo totale, sconto e priorità; prima di avvisare ricarica la pagina prodotto per
   confermare prezzo e disponibilità.
5. Confronta con lo stato salvato (branch `stato` del repository) e avvisa solo per novità:
   offerta nuova, tornata disponibile, nuovo sconto, prezzo sceso di almeno 5 € o 2%, priorità migliorata.
   La stessa offerta non viene ripetuta prima di 2 ore, salvo un nuovo calo o il passaggio a P1/P2.

## Niente limiti di Claude

Il monitor è un normale programma Python: mentre gira **non usa Claude né altri modelli di
intelligenza artificiale**. Per questo non ha alcun limite di ricerche o di utilizzo di Claude e
può restare acceso tutto il giorno, tutti i giorni.

## Perché il repository è pubblico (e perché non c'è nessun dato personale)

I minuti di GitHub Actions sono **gratuiti e illimitati solo sui repository pubblici**. In un
repository privato il piano gratuito dà 2.000 minuti al mese: con un'esecuzione di circa 4,5 minuti
(fatturata 5) ogni 5 minuti si consumano circa 1.440 minuti al giorno, quindi i minuti finirebbero
**in meno di due giorni**.

Pubblico non vuol dire esposto: nel repository **non c'è alcun dato personale**. Il nome segreto del
tuo canale ntfy (e gli eventuali token Telegram o dati email) stanno solo nei **Secrets** di GitHub,
che nessuno può leggere, e non compaiono mai nei log. Un test automatico controlla a ogni modifica che
nel codice non finiscano indirizzi email, token o stringhe segrete.

## Limiti, detti chiaramente

- **Orario non garantito.** GitHub non garantisce l'orario delle esecuzioni programmate: nei momenti
  di carico possono partire con alcuni minuti di ritardo o essere saltate. Nessun evento va perso
  (gli avvisi nascono dal confronto con lo stato salvato), ma può arrivare più tardi.
- **5 minuti è il minimo.** GitHub non permette esecuzioni programmate più frequenti di una ogni 5 minuti;
  per questo ogni esecuzione resta attiva circa 4,5 minuti e controlla le fonti ogni minuto circa.
- **Disattivazione dopo 60 giorni.** Nei repository pubblici GitHub disattiva i workflow programmati
  dopo 60 giorni senza attività nel repository. Il segnale per accorgertene è che **il report giornaliero
  smette di arrivare**. Per riattivarli: apri il repository su GitHub, scheda **Actions**, scegli il
  workflow **monitor** e premi **Enable workflow**. Per evitarlo basta una piccola modifica al repository
  (per esempio a config.yaml) almeno una volta ogni due mesi.
- **Siti che bloccano GitHub.** Alcuni siti possono bloccare i server di GitHub (pagine di verifica,
  errore 403 o 429). In quel caso la fonte risulta **"bloccata"** nel report e il monitor smette di
  interrogarla per 30, 60, 120 e poi 240 minuti, senza mai tentare di aggirare il blocco.
- **Fonti non verificate dal vivo.** Durante la costruzione i siti non erano raggiungibili dall'ambiente
  di sviluppo: nessuna fonte è stata provata sul sito vero (dettagli in [FONTI.md](FONTI.md)).
  Lo stato reale lo vedi con la diagnostica (SETUP.md, passo 6).
- **Trova solo quello che le fonti mostrano.** Il monitor non trova "ogni console in Italia": trova le
  offerte che le fonti abilitate mostrano nelle pagine che legge.
- **Listino ufficiale non impostato.** I prezzi di listino (`listino_ufficiale` in config.yaml) sono
  vuoti perché non è stato possibile leggerli dal vivo: lo sconto si calcola sul prezzo barrato del
  negozio e, dopo qualche giorno, sullo storico dei prezzi.

## Configurazione

Tutto ciò che puoi voler cambiare è in **[config.yaml](config.yaml)**, con un commento in italiano per
ogni voce: prezzo massimo, modelli e condizioni, venditori terzi e privati, soglia di sconto, listino,
anti-spam, zona di Milano, canali di notifica, parole escluse, fonti. Se scrivi un valore sbagliato,
il monitor si ferma e scrive quale chiave e quale valore correggere.

Canali di notifica: `ntfy` (predefinito), `telegram`, `email` (vedi SETUP.md, "Canali aggiuntivi").

## Comandi (per chi usa il terminale o Claude Code)

```
python -m ps5monitor run                 # avvia il monitor (quello che fa GitHub)
python -m ps5monitor run --once --dry-run --fixture   # prova completa sulle pagine di prova, senza rete né invii
python -m ps5monitor diagnostica         # tabella: fonte, stato, offerte trovate, tempo di risposta
python -m ps5monitor prova-notifica      # invia un messaggio di prova
python -m ps5monitor scopri              # cerca nuovi negozi sugli aggregatori → FONTI_CANDIDATE.md
python -m ps5monitor genera-topic        # crea il valore per il secret NTFY_TOPIC
python -m ps5monitor report --dry-run    # mostra il report giornaliero
```

Opzioni comuni: `--dry-run` (stampa invece di inviare), `--once` (un solo ciclo), `--fonte ID`
(solo una fonte, es. `amazon`), `--fixture` (pagine di prova). Ogni comando ha `--help` in italiano.

## Struttura

```
config.yaml              impostazioni (modificabili)
data/negozi.yaml         negozi delle catene nel raggio di Milano (vuoto: da compilare)
ps5monitor/              il programma
  cli.py                 comandi
  config.py              lettura e controllo di config.yaml
  models.py              struttura di un'offerta
  classify.py            riconoscimento console vera, modello, condizione, bundle
  pricing.py             prezzi, sconto, priorità, ordinamento
  alerts.py              ammissione, eventi, anti-spam
  messages.py, report.py testo degli avvisi e del report
  state.py, publish.py   stato e salvataggio sul branch "stato"
  runner.py              ciclo di controllo
  http.py                richieste rispettose dei siti
  notify/                ntfy, telegram, email
  sources/               un adapter per ogni fonte
tests/                   test automatici (pytest) e pagine di prova in tests/fixtures
.github/workflows/       monitor.yml, test.yml, test-notifica.yml
```

## Sviluppo

```
pip install -r requirements.txt
python -m pytest -q
yamllint .github/workflows config.yaml
```
