# Attivazione del monitor PS5 (circa 20 minuti)

Ti servono: un account GitHub (gratuito) e lo smartphone. Non serve saper programmare.
Ogni passo dice come capire che è andato bene.

---

## 1. Metti il codice nel ramo principale di un repository pubblico

GitHub fa partire i workflow programmati **solo dal ramo principale** (`main`) di un repository.

**Se il codice è già nel tuo repository su un altro ramo** (per esempio un ramo che inizia con `claude/`):

1. Apri il repository su github.com.
2. Se compare la striscia gialla con il pulsante **Compare & pull request**, premilo; altrimenti vai
   nella scheda **Pull requests** → **New pull request**, scegli come "compare" il ramo con il codice.
3. Premi **Create pull request**, poi **Merge pull request** e **Confirm merge**.

**Se parti da zero:** in alto a destra **+** → **New repository**, scegli un nome, seleziona
**Public**, premi **Create repository**, poi **uploading an existing file** e trascina tutti i file
del progetto (comprese le cartelle `.github`, `ps5monitor`, `tests`, `data`) e premi **Commit changes**.

Il repository deve essere **pubblico** (Settings → General → in fondo "Danger Zone" → visibilità
"Public"): solo così i minuti di GitHub Actions sono gratuiti e illimitati. Non c'è nessun dato
personale nel codice.

✅ **Come capisci che è andato bene:** nella pagina principale del repository, con il ramo `main`
selezionato, vedi i file `README.md`, `SETUP.md`, `config.yaml` e la cartella `.github`.

---

## 2. Crea il nome segreto del canale e installa ntfy sul telefono

Il "topic" è il nome del tuo canale di notifiche: chi lo conosce può leggere le tue notifiche,
quindi deve essere lungo e casuale, come una password.

- **Con Claude Code:** apri Claude Code nella cartella del progetto e scrivi
  *"esegui genera-topic e mostrami il valore"*. Ti mostrerà qualcosa come `ps5-` seguito da 24 caratteri.
- **Senza Claude Code:** inventa una stringa casuale di **almeno 24 lettere e numeri**, per esempio con
  un generatore di password online (solo lettere minuscole e numeri, senza spazi né simboli).

Scrivilo da qualche parte per i prossimi due minuti. Poi:

1. Installa l'app **ntfy** (Android: Google Play o F-Droid; iPhone: App Store). È gratuita e non chiede account.
2. Apri l'app, premi **+** (Iscriviti a un topic / Subscribe to topic), incolla il tuo topic,
   lascia il server **ntfy.sh**, premi **Iscriviti**.
3. Consenti le notifiche all'app. Per non perdere gli sconti, consenti le notifiche anche
   in modalità silenziosa / "Non disturbare":
   - Android: Impostazioni → App → ntfy → Notifiche → consenti tutte; apri la categoria delle notifiche
     a priorità massima ("Max priority") e attiva "Ignora Non disturbare". Gli sconti arrivano con priorità massima.
   - iPhone: Impostazioni → Notifiche → ntfy → Consenti; in Full immersion / Non disturbare aggiungi ntfy alle app consentite.

✅ **Come capisci che è andato bene:** nell'app ntfy vedi il tuo topic nell'elenco (ancora senza messaggi).

---

## 3. Salva il topic nei Secrets di GitHub

1. Nel repository: **Settings** → **Secrets and variables** → **Actions**.
2. Premi **New repository secret**.
3. **Name:** `NTFY_TOPIC` (esattamente così, in maiuscolo).
4. **Secret:** lo stesso valore del topic che hai messo nell'app, **senza spazi** prima o dopo.
5. Premi **Add secret**.

✅ **Come capisci che è andato bene:** nell'elenco "Repository secrets" compare `NTFY_TOPIC`
(il valore non si vede più: è normale).

---

## 4. Abilita GitHub Actions

1. Apri la scheda **Actions** del repository.
2. Se vedi un messaggio con il pulsante **I understand my workflows, go ahead and enable them**
   (o **Enable Actions**), premilo.
3. Se un workflow è indicato come disattivato, aprilo e premi **Enable workflow**.

✅ **Come capisci che è andato bene:** a sinistra, nella scheda Actions, vedi i workflow
**monitor**, **test** e **test-notifica**.

---

## 5. Invia la notifica di prova

1. Scheda **Actions** → a sinistra **test-notifica** → a destra **Run workflow** → di nuovo **Run workflow**.
2. Aspetta circa un minuto: la riga dell'esecuzione diventa verde.

✅ **Come capisci che è andato bene:** sul telefono arriva la notifica
**"[PROVA] Notifica di prova del monitor PS5"**. Se la riga è rossa, aprila: il riepilogo dice il motivo
(per esempio "manca il secret NTFY_TOPIC": torna al passo 3).

---

## 6. Controlla le fonti con la diagnostica

1. Scheda **Actions** → **monitor** → **Run workflow** → spunta **diagnostica** → **Run workflow**.
2. Quando la riga è verde (1-2 minuti), aprila e guarda il **riepilogo** (Summary).

✅ **Come capisci che è andato bene:** vedi la tabella *Fonte · Stato · Offerte trovate · Tempo di risposta*.
Le fonti con stato **ok** e offerte trovate maggiori di zero funzionano da GitHub. Le fonti
**bloccate** o con **errore** non funzionano da GitHub: puoi spegnerle in `config.yaml`
(`abilitata: false`), oppure lasciarle, perché il monitor si ferma da solo e riprova più tardi.
Non è un passo da superare "a tutti i costi": serve a sapere quali siti stai davvero controllando.

---

## 7. Attendi il messaggio "Monitor avviato"

Non devi fare niente: entro 5-15 minuti GitHub avvia da solo il workflow **monitor**.

✅ **Come capisci che è andato bene:** sul telefono arriva **"[AVVIO] Monitor avviato"**, con le offerte
attuali sotto i 700 € oppure la frase *"Nessuna offerta sotto il prezzo massimo al momento"*.
Da qui in poi ricevi solo le novità, più il report ogni mattina dopo le 9.

---

## Se qualcosa non va

| Sintomo | Cosa fare |
|---|---|
| **Non arriva nessuna notifica** (nemmeno la prova) | Controlla che il topic nell'app ntfy e il secret `NTFY_TOPIC` siano identici, senza spazi (puoi ricreare il secret con lo stesso nome). Controlla che le notifiche di ntfy siano consentite sul telefono. Rilancia **test-notifica** e leggi il riepilogo: dice "inviato" o il motivo dell'errore. |
| **Una fonte risulta "bloccata"** nel report o nella diagnostica | Il sito ha rifiutato i server di GitHub (errore 403/429 o pagina di verifica). Il monitor riprova da solo dopo 30, 60, 120, 240 minuti senza insistere. Se resta bloccata per giorni, metti `abilitata: false` per quella fonte in `config.yaml`. |
| **Il report giornaliero non arriva più** | Probabilmente GitHub ha disattivato il workflow dopo 60 giorni senza attività. Scheda **Actions** → **monitor** → **Enable workflow**. Poi fai una piccola modifica a un file (per esempio un commento in `config.yaml`) per segnare attività. |
| **Troppe notifiche** | In `config.yaml` aumenta `cooldown_minuti` (es. 360), `delta_prezzo_min_eur` (es. 15) o abbassa `prezzo_max_eur`. Per ricevere solo offerte nuove da negozi: `marketplace: privati: false` e `venditori_terzi: false`. |
| **Notifiche di accessori o giochi** (non console) | Aggiungi la parola che li distingue a `parole_escluse_forti` in `config.yaml` (una riga con `- parola`). Esempio: se arriva un "dock", aggiungi `- dock`. |
| **Il workflow "monitor" è disattivato o non parte** | Scheda **Actions**: se compare "This scheduled workflow is disabled", premi **Enable workflow**. Controlla che il codice sia nel ramo `main` (passo 1): i workflow programmati partono solo da lì. |
| **Riga rossa con "Errore in config.yaml"** | Hai scritto un valore non valido: il messaggio dice quale chiave e quale valore. Correggilo (attenzione a rientri e due punti) e salva. |
| **Arriva "[ALLARME] Monitor cieco"** | Nessuna fonte risponde da oltre un'ora. Lancia la diagnostica (passo 6) per vedere quali siti bloccano GitHub. |
| **Le notifiche arrivano con qualche minuto di ritardo** | È un limite di GitHub (le esecuzioni programmate possono slittare di alcuni minuti nei momenti di carico). Nessun avviso va perso. |

---

## Canali aggiuntivi (facoltativi)

Telegram ed email funzionano ma sono spenti. Per attivarli:

**Telegram**
1. In Telegram scrivi a **@BotFather** → `/newbot` → scegli un nome: ricevi il **token** del bot.
2. Scrivi un messaggio qualsiasi al tuo nuovo bot. Poi apri nel browser
   `https://api.telegram.org/bot<TOKEN>/getUpdates` (sostituisci `<TOKEN>`): il numero dopo `"chat":{"id":` è il tuo **chat id**.
3. Aggiungi i secret `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` (passo 3).
4. In `config.yaml` cambia `canali: [ntfy]` in `canali: [ntfy, telegram]`.

**Email**
1. Aggiungi i secret `SMTP_HOST`, `SMTP_PORT` (di solito 587 oppure 465), `SMTP_USER`,
   `SMTP_PASSWORD` (per Gmail serve una "password per le app") ed `EMAIL_TO` (il tuo indirizzo:
   **solo nel secret**, mai nei file del repository).
2. In `config.yaml` aggiungi `email` alla lista `canali`.

Dopo ogni attivazione rilancia **test-notifica** (passo 5): il riepilogo indica l'esito per ogni canale.
