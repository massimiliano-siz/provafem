# Revisione CAD

Skill di Claude Code che rivede disegni (PDF) e modelli (STEP): trova errori sui disegni, differenze tra disegno e
modello, problemi di progetto e di lavorabilità, propone le correzioni e pubblica un report interattivo
(fogli navigabili, voci collegate, modello 3D con sezioni, chat).

## Come si usa

1. Esporta da Onshape gli STEP e i disegni in PDF con **Text = Selectable**.
2. Metti tutti i file in **un unico .zip** (nomi consigliati: il codice del disegno, es. `SIZ-PRT-0085.pdf`).
3. Apri una sessione Claude Code su questo repository (claude.ai/code), allega lo zip e scrivi `/revisione-cad`.
4. Ricevi il link del report. Rispondi alle domande nella chat del report o in conversazione.
5. Dopo le correzioni: allega i file nuovi e scrivi "rilancia la revisione". Il report si aggiorna allo stesso link.

La skill è in `.claude/skills/revisione-cad/` (procedura in `SKILL.md`, script in `scripts/`, grafica in
`assets/template.html`). `grafica-report/` contiene schermate di esempio del report.
