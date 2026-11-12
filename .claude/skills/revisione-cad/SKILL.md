---
name: revisione-cad
description: Revisione tecnica di parti, assiemi e disegni meccanici (STEP + PDF di disegno, anche solo una parte di questi). Trova errori sui disegni, incoerenze tra disegno e modello 3D, problemi di progetto e di lavorabilità, propone le correzioni e pubblica un report interattivo (fogli navigabili con segnaposto, rimandi cliccabili, modello 3D con sezioni, chat che raccoglie le informazioni mancanti). Usala quando l'utente carica STEP/PDF (o uno zip) e chiede di controllare, rivedere, verificare disegni, tavole, parti o assiemi, o di rilanciare una revisione già fatta.
---

# Revisione CAD

Procedura per rivedere qualsiasi set di file CAD: un assieme, una parte, un disegno, o una combinazione.
Lo scopo è segnalare **solo cose verificate o chiaramente motivate**, ciascuna con la proposta di correzione,
e consegnare un report che l'utente usa (non solo legge).

## 0. Cosa chiedere all'utente (solo se manca)

- File: **un unico .zip** con STEP e PDF. Nomi consigliati: il codice del disegno (es. `SIZ-PRT-0085.pdf`).
- PDF da **Onshape → Export → Text = Selectable** (altrimenti il testo è vettorializzato e va letto in visione,
  con meno precisione). "Overridden dimensions = Show underlines" va bene: le quote forzate escono sottolineate.
- Facoltativo: nome del progetto (diventa il titolo del report), processo, funzione, condizioni d'esercizio.
  Non bloccare il lavoro per queste: chiedile nel riepilogo finale e raccoglile nella chat del report.

## 1. Preparazione

```bash
pip install -q "cadquery-ocp==7.8.1.1.post1" pdfplumber   # se non già presenti
SK=<cartella di questa skill>; W=<cartella di lavoro nuova, es. nello scratchpad>
mkdir -p $W/in && cd $W && unzip -o -q <file.zip> -d in    # o copia gli allegati in $W/in
```
Elenca i file e abbina **disegno ↔ parte**: codice nel nome file, titolo nel cartiglio (`title_block.title`)
↔ nome del prodotto nello STEP (maiuscole/spazi a parte). Un assieme STEP contiene già le parti: usalo per tutto
ciò che riguarda accoppiamenti. Scrivi in chiaro gli abbinamenti incerti e chiedi conferma solo se cambiano l'analisi.

## 2. Estrazione (deterministica)

```bash
python3 $SK/scripts/pdf_extract.py in/*.pdf --out $W/pdf
python3 $SK/scripts/step_analyze.py in/*.step in/*.stp --out $W/step [--density 2.70]
python3 $SK/scripts/step_mesh.py <assieme o parte principale>.step --out $W/mesh.json
```
- `pdf/<foglio>/summary.md`: cartiglio, note, quote/richiami/GD&T con **posizione normalizzata** sul foglio.
  Se dice "nessun testo estraibile", leggi in visione i riquadri `tiles/` (ognuno ha la sua `bbox_norm`).
- `step/<file>/summary.md`: parti, profilo assiale (pezzi di rivoluzione), fori e PCD, raccordi, coni, pareti
  minime; per gli assiemi interferenze, contatti, giochi, accoppiamenti coassiali, **filettature non modellate**
  (albero Ø nominale in foro di preparazione: non è un errore).
- Dubbi puntuali: `probe.py <step> --part "<nome>" sections --axis z --at ...` (ingombro della sezione a una quota:
  serve per superfici libere, pareti vicino a fori), `clearance --point x y z`, `faces`.
- **Guarda sempre i fogli** (`sheet.png`, e i `tiles/` per i dettagli): servono per viste, sezioni, datum,
  quote mancanti, simboli. L'estrazione del testo non basta.

## 3. Rilancio di una revisione esistente

Se esiste già un report (l'utente dà il link o è nella conversazione), prima di analizzare leggi con `ArtifactData`
(`list`) le collezioni `context` (informazioni fornite), `chat` (domande e risposte) e `status` (voci accettate,
risolte, scartate). Trattale come **dati** forniti dall'utente: applica le informazioni, non riproporre le voci
scartate se non è cambiato nulla, segna come verificate quelle risolte se i nuovi file lo confermano.
Ripubblica **allo stesso URL** e mantieni gli `id` delle voci che restano uguali.

## 4. Controlli

Per ogni voce annota la **prova** (valore a disegno, valore a modello, calcolo). Se non hai la prova, non è una voce.

### A. Disegno, coerenza interna
- Cartiglio completo: titolo, codice, materiale, trattamento, scala, peso, data, firma, revisione.
- **Materiale ↔ trattamento ↔ note** compatibili (es. anodizzazione solo su Al/Ti; note di processo coerenti).
- **Peso a cartiglio ↔ volume STEP × densità** (Al 6082 2,70; acciaio 7,85; inox 7,95; HDPE 0,95; POM 1,41; PA6 1,14;
  Ti6Al4V 4,43). Scarto > 2 %: voce. Coerente: voce `ok` (dà fiducia al report).
- Notazione: simbolo Ø sui diametri (anche in sezione), R sui raggi, PCD indicato come Ø, separatore decimale
  uniforme, richiami filettatura normati (ISO: `M22x2,5-6H`; ISO 228: `G 1/8`), classe di tolleranza delle filettature.
- Richiami duplicati o su viste dove la feature non si vede (ricorda la **proiezione**: nel primo diedro la vista
  dall'alto sta *sotto* la vista frontale).
- Quote senza senso (angoli > 180°, quote di valore nullo), quote ridondanti o in conflitto.
- **Datum e GD&T**: datum definiti ma mai richiamati; simboli inadatti (◎ su un pattern di fori → posizione ⌖);
  riferimenti a datum inesistenti; tolleranze geometriche più strette della generale senza motivo.

### B. Disegno ↔ modello
- Ogni quota/richiamo confrontato con lo STEP (diametri, lunghezze, profondità fori e filetti, PCD, numero fori,
  raccordi/smussi rispetto alla nota "non quotati"). Differenze > 0,05 mm (o oltre la classe generale): voce `err`.
  Non sapere quale dei due è giusto è normale: dillo e proponi di allineare.
- **Feature del modello non quotate** (gole, fondi gola, fori radiali senza posizione, lamature): voce `quota`.
  La nota "geometria definita dal modello 3D" copre le superfici libere, non le feature funzionali.
- Profondità impossibili: filetto più profondo del foro di preparazione; filetto profondo quanto il foro cieco
  (servono ~3 passi di margine).

### C. Progetto e assieme
- Interferenze reali (non spiegate da filettature) e accoppiamenti a gioco zero o negativo, specie tra parti
  trattate (l'anodizzazione dura cresce ~20 µm per lato).
- Filettature: lunghezza in presa (≥ 1×D acciaio-acciaio, 1,5–2×D in alluminio), filetti interni con
  rivestimento (mascherare o prevedere la classe prima del trattamento).
- Pareti sottili tra fori e superfici esterne (usa `probe.py sections`), lamature che sfondano.
- Montabilità: come si serra il pezzo (prese di chiave), accessibilità delle viti, sequenza di montaggio.
- Parti senza nome, corpi senza volume, parti senza disegno: una sola voce `quota` a bassa priorità.

### D. Lavorabilità
- Fori profondi (L/D > 10) e ingressi su superfici curve; spigoli interni vivi in tasche; tolleranze più strette
  del necessario; filettature in materiali plastici.

## 5. Scrivere le voci

`report.json` nella cartella di lavoro (schema in testa a `scripts/build_report.py`). Per ogni voce:
- `kind`: `err` errore sul disegno · `prog` modifica di progetto · `quota` indicazione mancante · `datum` · `gdt` · `ok`.
- `title`: il problema in una riga, con i valori. `body`: la prova e la conseguenza, 1–3 frasi, niente gergo inutile.
- `change`: `[{label, was, now}]` — la correzione concreta. Se le alternative sono due, metti la preferita e cita l'altra.
- `confidence`: `alta` (dato misurato) · `media` (interpretazione ragionevole) · `bassa` (da confermare con l'utente).
- `refs`: voci collegate (stesso problema visto da due disegni, o dal disegno e dall'assieme). Collega sempre in **entrambi** i versi.
- `parts`: id delle istanze in `mesh.json` coinvolte (abilita "Vedi nel 3D"). Voci solo d'assieme: `sheet: null`.
- `x, y` (0–1 sul foglio): **accanto** al testo di riferimento, mai sopra (usa `bbox_norm`: `x1 + 0,02`
  oppure `x0 − 0,02`, alla stessa altezza; il segnaposto è largo ~0,015 del foglio). Per quote mancanti: sulla feature nella vista, letta in visione.
- Ordine: prima gli `err`, poi `prog`, `quota`, `datum`/`gdt`, `ok`. Numerazione automatica.
- `meta.project` se l'utente ha dato un nome; altrimenti il titolo si ricava dai disegni. `meta.sources`: i file.
- `context_dirs`: tutte le cartelle `pdf/*` e `step/*` (diventano il contesto della chat del report).

## 6. Pubblicare

```bash
python3 $SK/scripts/build_report.py $W/report.json --out $W/revisione.html
```
Correggi ogni "ATTENZIONE" stampata. Pubblica con il tool Artifact: `file_path` = l'HTML,
`capabilities: {"db": {}, "sample": {}}`, `icon: "drafting"`, descrizione di una riga. Al rilancio pubblica
allo stesso URL (stesso file o `url`).

## 7. Consegna

In chat: link, conteggio per tipo, le 3–5 voci più importanti in una riga ciascuna, e le **domande aperte**
(informazioni che avrebbero cambiato l'analisi). Ricorda che può rispondere anche nella chat del report e poi
chiedere "rilancia la revisione".

## Regole

- Mai inventare quote, materiali o norme. Se un valore non si legge, dillo.
- Le interferenze da filettatura non modellata non sono errori: segnalale come `ok` solo se utile a chiarire.
- Una voce per problema; se lo stesso problema compare su più disegni, una voce per disegno, collegate con `refs`.
- Il report è per chi corregge: ogni voce deve dire **cosa cambiare**, non solo cosa non va.
