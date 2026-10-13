# Calendario CUS Torino · Tennistavolo

Calendario unico di tutte le partite delle squadre del CUS Torino nei campionati a squadre FITeT
(serie nazionali, paralimpici, Master, Coppa Italia e campionati regionali del Piemonte).

Ogni notte GitHub legge il Portale Risultati FITeT, trova le squadre della società e ripubblica il sito
con calendario, risultati, campi gara e formazioni. Il computer non serve.

## Cosa c'è nel sito

- **Pagina web**: tutte le partite giorno per giorno, filtri per serie e per squadra, prossimo turno.
- **Calendario per il telefono** (`calendario.ics`): il pulsante «Aggiungi al calendario» lo collega
  all'app Calendario (iPhone, Mac, Outlook; per Android c'è il pulsante «Google Calendar»), e rinvii e
  nuovi orari compaiono da soli. C'è anche un calendario per ogni squadra (`squadre/<numero>.ics`):
  il pulsante dà quello della squadra scelta nel filtro. In fondo alla pagina c'è anche il link
  «Scarica una copia delle partite», per chi vuole il file una volta sola.

## Come trova le squadre

Non guarda il nome della squadra ma il **codice di affiliazione della società** (CUS Torino = 437),
che il portale riporta nella scheda di ogni squadra. Per questo una nuova squadra iscritta a qualsiasi
campionato (anche a metà stagione) compare da sola, qualunque nome abbia.

La prima volta legge la scheda di tutte le squadre dei campionati controllati (circa 800 pagine,
20-25 minuti). Le schede vengono salvate in `cache/squadre.json`, così le notti successive bastano
poco più di 100 pagine. Tra una richiesta e l'altra c'è un secondo di pausa per non pesare sul portale.
A inizio stagione (cambia l'anno nel portale) la cache si azzera da sola.

## Cosa si può cambiare in `config.json`

| Voce | A cosa serve |
|---|---|
| `societa.codice_albo` | Codice FITeT della società (437 = CUS Torino) |
| `societa.nome`, `nome_breve` | Come vengono chiamate le squadre: «CUS Torino», «CUS A», «CUS B»… |
| `titolo_pagina`, `sottotitolo_pagina` | Testi in cima alla pagina |
| `campionati_nazionali` | `true` per controllare anche i campionati nazionali |
| `categorie_nazionali_escluse` | Categorie del portale da saltare |
| `regioni` | Codici delle regioni da controllare (2 = Piemonte) |
| `ordine_serie` | Ordine dei pulsanti dei filtri |
| `pausa_tra_richieste_secondi` | Pausa tra le pagine lette dal portale |
| `rileggi_schede_squadre_ogni_giorni` | Ogni quanti giorni rileggere campi gara e formazioni |
| `durata_incontro_ore` | Durata degli eventi nel calendario del telefono |
| `correzioni_testi` | Correzioni di refusi nei nomi dei campi gara (testo sbagliato → giusto) |

Le serie hanno queste etichette: B1, C1, C2, D1, D2, D3, «C ♀» per le serie femminili, «A2 ♿» per la
A2 paralimpica classi 1-5, «M. A2» e «M. C» per il Master, «C.I.» per la Coppa Italia. Sulla pagina i simboli
sono disegnati come icone; nei calendari del telefono diventano «femminile» e «paralimpica».

## Struttura del progetto

```
aggiorna.py                  legge il portale e genera il sito
template.html                aspetto della pagina
config.json                  impostazioni
assets/logo.png              logo (uso autorizzato dal CUS Torino)
tests/                       controlli automatici con pagine reali del portale
.github/workflows/aggiorna.yml   esecuzione notturna su GitHub
docs/                        sito generato (non modificarlo a mano)
cache/                       schede squadre salvate
```

## Avviare un aggiornamento a mano

Scheda **Actions** → **Aggiorna calendario** → **Run workflow**. In pochi minuti il sito è aggiornato.

## Se qualcosa va storto

- Se un aggiornamento fallisce, GitHub manda una mail al proprietario del progetto e il sito resta
  com'era: lo script non sovrascrive mai il calendario con dati vuoti o dimezzati.
- Il motivo si legge in **Actions** → l'esecuzione segnata in rosso → il passaggio fallito.
- Se il portale cambia struttura, il primo passaggio a fallire sarà quasi sempre
  «Controlla che la lettura delle pagine funzioni»: va aggiornato `aggiorna.py`.
- Per i concentramenti (paralimpici) la sede non si ricava dal calendario: la pagina indica di
  consultare i comunicati FITeT.

## Esecuzione sul proprio computer

```
pip install -r requirements.txt
python aggiorna.py                 # aggiornamento completo
python aggiorna.py --solo-pagina   # rigenera pagina e calendari dagli ultimi dati, senza leggere il portale
python -m pytest tests             # controlli
```

Dati: Portale Risultati FITeT (portale.fitet.org). Orari salvo variazioni concordate tra le società.
