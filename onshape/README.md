# Bilancino di sollevamento 6 t — 6 punti

FeatureScript per Onshape che genera il bilancino (telaio saldato) per il sollevamento
dell'assieme da 6 t con imbracatura a 6 tiri verticali sui `LiftingDisc` / golfari DIN 580 M36.

- Sorgente: `BilancinoSollevamento.fs`
- Documento Onshape: <https://cad.onshape.com/documents/9425081ca37e3833a42ccd9d/w/d96ec2823c2214c0dc3d728d>
- Feature Studio: **Bilancino 6t** (`dafb145402692ac0c580eb78`)
- Feature: **Bilancino 6 t - 6 punti**

## 1. Geometria dei punti di aggancio (estratta da `Test_assy (1).step`)

Ricostruito l'albero d'assieme STEP (2901 occorrenze) e calcolate le trasformazioni globali
dei 6 `LiftingDisc`. Unità del file: metri. Y è la verticale nel modello d'assieme.

| # | Frame assy | X [mm] | Z [mm] | Y [mm] |
|---|------------|-------:|-------:|-------:|
| 1 | Semi_assy 2 | 1457.2 |  312.1 | 1530 |
| 2 | Semi_assy 2 | 1457.2 | -813.7 | 1530 |
| 3 | Semi_assy 2 | 2432.2 | -250.8 | 1530 |
| 4 | Semi_assy 1 |  507.2 | -813.7 | 1530 |
| 5 | Semi_assy 1 |  507.2 |  312.1 | 1530 |
| 6 | Semi_assy 1 | -467.8 | -250.8 | 1530 |

Struttura del pattern:

- ogni frame assy porta 3 punti a 120° su una circonferenza **R = 650 mm**
  (lato del triangolo 650·√3 = **1125.8 mm**); i `Frame bracket` hanno assi a ±30°/90°,
  quindi il passo complessivo è di **60°**;
- i due triangoli sono controrotati di 180°, interasse tra i centri **1600 mm**;
- in pianta il risultato è **un rettangolo 950 × 1125.8 mm + 2 punti sulla mezzeria
  longitudinale a ±1450 mm** (campata totale 2900 mm);
- baricentro geometrico dei 6 punti: X = 982.2, Z = -250.8;
- `LiftingDisc`: Ø300 × 60 mm, faccia superiore a Y = 1590; i golfari DIN 580 M36 sono
  piantati sopra, asse verticale, ingombro +65 mm sopra la faccia.

> **Nota**: gli interassi indicati a memoria (1000 mm nello stesso frame assy, 850 mm tra
> frame assy) non coincidono con il CAD. I valori misurati sono 1125.8 mm (lato triangolo)
> e 950 mm (punti affacciati dei due frame). Quelli del CAD sono numeri tondi di progetto
> (R650 / 950 / 2900) e sono stati usati come default della feature.

## 2. Architettura del bilancino

Telaio a doppio T, tutto tubolare + piastre passanti (through-plate, buona trasmissione
del carico e booleane robuste):

| Elemento | Sezione | Lunghezza |
|---|---|---|
| Trave principale (X) | CHS Ø219.1 × 10 | 3200 mm (perni a ±1450) |
| 2 traverse (Y), a X = ±475 | CHS Ø168.3 × 8 | 1425.8 mm (perni a ±562.9) |
| 6 orecchioni inferiori | piastra 25 mm, R120, foro Ø40 | tutti alla stessa quota Z = -400 |
| Pad-eye centrale | piastra 35 mm, foro Ø50 a Z = +400 | — |

Le traverse sono **sellate** sulla trave principale (incastro 15 mm), il che riproduce la
cianfrinatura/cope di un nodo saldato reale e rende l'unione booleana pulita: il risultato
è **un corpo unico**.

Tutti e 6 i perni sono alla stessa quota, così le **6 funi da 2 m sono verticali**: è la
condizione corretta perché i golfari DIN 580 vanno caricati **in asse** (nessuna componente
orizzontale). Ingombro telaio 3200 × 1425.8 × 1130 mm, massa ≈ 500 kg (S355, 7850 kg/m³).

### Quote di montaggio

```
asse trave principale       Z =     0
asse traverse               Z =  -178.7
perni inferiori (6)         Z =  -400
piano golfari               Z = -2400     (= -400 - 2000 di fune)
foro pad-eye                Z =  +400
```

## 3. Dimensionamento (di massima)

Carico 6 t, 6 punti → 1 t/punto in ipotesi di distribuzione uniforme.
Momento in mezzeria della trave principale: 9.81 kN × 1.45 m + 19.62 kN × 0.475 m ≈ 23.5 kNm.
Con fattore di carico 2.0 (dinamico + sicurezza) → 47 kNm; σ_amm = 355/1.5 = 237 MPa →
W richiesto ≈ 198 cm³. Il CHS Ø219.1 × 10 ha W ≈ 328 cm³ → verificato con margine.
Traverse: M ≈ 5.5 kNm × 2 = 11 kNm → W richiesto ≈ 47 cm³; il CHS Ø168.3 × 8 ha W ≈ 120 cm³.

**Limiti dichiarati**:

- con 6 tiri e telaio rigido il sistema è **iperstatico**: la ripartizione reale non è
  uniforme. Per un bilancino da noleggio certificato questo lo copre il costruttore; se si
  costruisse su misura serve una verifica EN 13155 con distribuzione sfavorevole
  (es. carico su 3 o 4 punti);
- la massa di 500 kg è conservativa: gli orecchioni sono piastre piene non rastremate;
- nessun dettaglio di saldatura, cianfrini, rinforzi (cheek plate), marcatura.

## 4. Uso della feature

1. Aprire il Part Studio, aggiungere la feature **Bilancino 6 t - 6 punti**.
2. I default riproducono la geometria sopra. Nessun mate viene creato dalla feature.
3. Con `mateConnectors` attivo (default) vengono creati:
   - 6 mate connector sui perni inferiori, **Z rivolto verso il basso** = asse della fune;
   - 1 mate connector sul foro del pad-eye;
   - 1 mate connector `ref` a Z = -2400, da far coincidere col baricentro dei 6 golfari:
     è il modo più rapido per posizionare il bilancino sull'assieme.
4. Flag `topSlings`: genera in più 4 tiranti Ø26 + maglia master (parti separate), con
   prolunga degli orecchioni delle traverse e secondo foro superiore.
5. `hookOffsetX` / `hookOffsetY`: spostano il punto di tiro sul baricentro reale del carico.
   Default 0 = baricentro geometrico dei 6 punti.

> **Da definire**: la posizione del CdG reale dei 6 t. Con offset trasversale oltre ~80 mm
> il pad-eye esce dalla sagoma della trave principale e serve una traversa di testa
> dedicata — in quel caso il modello va esteso.
