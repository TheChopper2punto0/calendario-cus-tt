#!/usr/bin/env python3
"""
Calendario unico delle squadre di una società nel Portale Risultati FITeT.

Cosa fa, ogni volta che parte:
  1. elenca i campionati nazionali e quelli delle regioni indicate in config.json;
  2. per ogni girone legge la classifica e, solo per le squadre mai viste, la scheda
     squadra (che riporta il codice di affiliazione della società);
  3. tiene i gironi dove gioca almeno una squadra della società e ne legge il calendario;
  4. scrive in docs/ la pagina (index.html), i calendari .ics e i dati in JSON.

Le schede squadra vengono salvate in cache/squadre.json, così le esecuzioni successive
fanno poche richieste al portale. Tra una richiesta e l'altra c'è una pausa.

Uso:  python aggiorna.py            (aggiornamento completo)
      python aggiorna.py --solo-pagina   (rigenera pagina e .ics dai dati già salvati)
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
CACHE = ROOT / "cache" / "squadre.json"
TZ = ZoneInfo("Europe/Rome")
BASE = "https://portale.fitet.org/"
CAMP = BASE + "risultati/campionati/"
UA = "Calendario squadre tennistavolo (GitHub Actions; aggiornamento notturno)"


# ----------------------------------------------------------------------------- utilità
def zuppa(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html5lib")


def testo(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el is not None else ""


def chiave(s):
    return re.sub(r"\s+", " ", s or "").strip().upper()


def param(href, nome):
    m = re.search(rf"[?&]{nome}=(-?\d+)", href or "")
    return m.group(1) if m else None


class Portale:
    def __init__(self, pausa):
        import requests
        self.req = requests
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.pausa = pausa
        self.richieste = 0

    def get(self, url):
        errore = None
        for tentativo in range(4):
            time.sleep(self.pausa)
            try:
                r = self.s.get(url, timeout=40)
                self.richieste += 1
                r.raise_for_status()
                b = r.content
                try:
                    return b.decode("utf-8")
                except UnicodeDecodeError:
                    return b.decode("cp1252")
            except self.req.RequestException as e:
                errore = e
                time.sleep(5 * (tentativo + 1))
        raise RuntimeError(f"Impossibile leggere {url}: {errore}")


# ----------------------------------------------------------------------------- lettura pagine
def categorie_nazionali(html):
    """menu.php -> [(CID, nome)]"""
    out = []
    for a in zuppa(html).find_all("a", href=True):
        if "visualizza_campionati.php" in a["href"]:
            cid = param(a["href"], "CID")
            if cid:
                out.append((cid, testo(a)))
    return out


def categoria(nome_cid):
    n = nome_cid.lower()
    if "paralimp" in n:
        return "para"
    if "master" in n:
        return "master"
    if "coppa italia" in n:
        return "coppa"
    return "serie"


def gironi_nazionali(html, cat):
    """elenco_campionati.php -> gironi con sesso (riga Maschile/Femminile)."""
    out = []
    for tr in zuppa(html).find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
        sesso = testo(tds[0])
        for a in tr.find_all("a", href=True):
            cam = param(a["href"], "CAM")
            if cam:
                out.append({"cam": cam, "nome": testo(a), "sesso": sesso, "cat": cat,
                            "conc": param(a["href"], "CONC") == "1", "ambito": "naz"})
    return out


def gironi_regionali(html, reg):
    out = []
    for a in zuppa(html).find_all("a", href=True):
        cam = param(a["href"], "CAM")
        if cam:
            nome = testo(a)
            cat = "coppa" if re.match(r"\s*C\.\s*I\.", nome) else "serie"
            out.append({"cam": cam, "nome": nome, "sesso": "", "cat": cat,
                        "conc": param(a["href"], "CONC") == "1", "ambito": f"reg{reg}"})
    return out


def trova_anno(html):
    for a in zuppa(html).find_all("a", href=True):
        if "Calendario.asp" in a["href"]:
            return param(a["href"], "ANNO")
    return None


def squadre_girone(html):
    """classifica_squadre.php -> {id_squadra: nome}"""
    nomi, ids = {}, []
    for a in zuppa(html).find_all("a", href=True):
        sid = param(a["href"], "SQUADRA")
        if not sid:
            continue
        if "percentuali.php" in a["href"]:
            nomi[sid] = testo(a)
        if sid not in ids:
            ids.append(sid)
    return {sid: nomi.get(sid, "") for sid in ids}


def scheda_squadra(html):
    s = zuppa(html)
    r = {"nome": "", "societa": "", "albo": "", "campo1": None, "campo2": None, "formazione": []}
    p = s.find(lambda t: t.name == "p" and testo(t) == "Scheda della squadra")
    if p:
        r["nome"] = testo(p.find_next("p"))

    def riga_dopo(intestazione):
        th = s.find(lambda t: t.name == "th" and testo(t).lower().startswith(intestazione.lower()))
        if not th:
            return None
        tr = th.find_parent("tr")
        nxt = tr.find_next_sibling("tr") if tr else None
        return [testo(td) for td in nxt.find_all("td")] if nxt else None

    soc = riga_dopo("Nome Societa")
    if soc and len(soc) >= 2:
        r["societa"], r["albo"] = soc[0], soc[1]
    if not r["albo"]:
        img = s.find("img", src=re.compile(r"societa/(\d+)"))
        if img:
            r["albo"] = re.search(r"societa/(\d+)", img["src"]).group(1)
    for k, h in (("campo1", "Campo gara principale"), ("campo2", "Campo gara riserva")):
        c = riga_dopo(h)
        if c and len(c) >= 2 and c[0]:
            r[k] = {"nome": c[0], "indirizzo": c[1]}
    th = s.find(lambda t: t.name == "th" and testo(t) == "Formazione")
    if th:
        tab = th.find_parent("table").find_next_sibling("table")
        if tab:
            r["formazione"] = [re.sub(r"\s*\([A-Z]{3}\)\s*$", "", testo(td)) for td in tab.find_all("td") if testo(td)]
    return r


DATA_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def calendario(html):
    """Calendario.asp -> lista di incontri.
    Righe da 8 colonne: andata + ritorno (data, ora, ris, casa, ospite, ris, ora, data).
    Righe da 5 colonne: incontro singolo (concentramenti)."""
    out = []
    gio = None
    for tr in zuppa(html).find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        t = testo(tr)
        m = re.search(r"(\d+)\^\s*Giornata", t)
        if m and len(tds) < 3:
            gio = int(m.group(1))
            continue
        if len(tds) < 5 or not DATA_RE.search(testo(tds[0])):
            continue
        c = [testo(td) for td in tds]
        casa, ospite = c[3], c[4]

        def incontro(td_data, td_ora, td_ris, h, a, fase):
            d = DATA_RE.search(testo(td_data))
            if not d:
                return None
            ora = re.search(r"(\d{1,2})[.:](\d{2})", testo(td_ora))
            a_link = td_ris.find("a", href=True)
            ris = re.search(r"(\d+)\s*-\s*(\d+)", testo(td_ris))
            return {
                "giornata": gio, "fase": fase,
                "data": f"{d.group(3)}-{d.group(2)}-{d.group(1)}",
                "ora": f"{int(ora.group(1)):02d}:{ora.group(2)}" if ora else "",
                "casa": h, "ospite": a,
                "risultato": f"{ris.group(1)}-{ris.group(2)}" if ris else "",
                "riserva": "*" in testo(td_data),
                "incontro": param(a_link["href"], "INCONTRO") if a_link else None,
            }

        if len(tds) >= 8:
            for x in (incontro(tds[0], tds[1], tds[2], casa, ospite, "A"),
                      incontro(tds[7], tds[6], tds[5], ospite, casa, "R")):
                if x:
                    out.append(x)
        else:
            x = incontro(tds[0], tds[1], tds[2], casa, ospite, "U")
            if x:
                out.append(x)
    return out


# ----------------------------------------------------------------------------- etichette
def etichetta_serie(g):
    n = g["nome"]
    if g["cat"] == "coppa":
        return "C.I."
    m = re.match(r"\s*([A-D])\s*/?\s*(\d)?", n)
    base = (m.group(1) + (m.group(2) or "")) if m else n.split(" Gir")[0].strip()
    if g["cat"] == "para":
        return base + (" ♿" if re.search(r"gruppo\s*1\s*-\s*5", n) else " Para")
    if g["cat"] == "master":
        return "M. " + base
    if g["sesso"].lower().startswith("f") or re.search(r"femm", n, re.I):
        return base + " ♀"
    return base


def etichetta_girone(g):
    n = re.sub(r"^\s*(C\.\s*I\.|[A-D]\s*/?\s*\d?)\s*", "", g["nome"])
    n = re.sub(r"\bgir\.\s*", "Gir. ", n, flags=re.I)
    return n.strip()


def etichetta_squadra(nome, cfg):
    tok = nome.strip().split()
    if len(tok) >= 2 and re.fullmatch(r"[A-Za-z]", tok[-1]):
        return f"{cfg['societa']['nome_breve']} {tok[-1].upper()}"
    return cfg["societa"]["nome"]


def maiuscole(s):
    """Rende leggibili i testi scritti tutti in maiuscolo (nomi, campi gara)."""
    s = re.sub(r"\s+", " ", s or "").strip()
    if not (s.isupper() and len(s) > 4):
        return s
    sigle = {"CRDC", "SIAL", "ASD", "APD", "APS", "TT", "XXV", "CUS", "IC3", "E/23", "SNC"}
    parole = []
    for w in s.split(" "):
        if re.search(r"\d", w) or w in sigle or re.fullmatch(r"([A-Z]\.)+[A-Z]?\.?", w) or len(w) <= 1:
            parole.append(w)
        else:
            w = w.lower()
            parole.append(re.sub(r"[a-zà-ÿ]", lambda m: m.group(0).upper(), w, count=1))
    return " ".join(parole)


def correggi(s, cfg):
    for a, b in cfg.get("correzioni_testi", {}).items():
        s = s.replace(a, b)
    return s


def campo(c, cfg):
    if not c:
        return None
    ind = re.sub(r"\s+", " ", c["indirizzo"]).strip()
    ind = re.sub(r"\s\d{5}\s+[A-Z ]+-", "-", ind)  # "CORSO SICILIA, 12 10133 TORINO-Torino"
    via, _, citta = ind.partition("-")
    via = via.strip().rstrip(",").strip()
    nome = correggi(maiuscole(c["nome"]), cfg)
    via = correggi(maiuscole(correggi(via, cfg)), cfg)
    return {"n": nome, "s": via, "city": citta.strip()}


def nome_avversario(s):
    s = re.sub(r"\s+", " ", s).strip()
    if s == s.lower():
        s = " ".join(w.upper() if len(w) == 1 else w.capitalize() for w in s.split())
    return s


# ----------------------------------------------------------------------------- uscite
def scrivi_uscite(dati, cfg):
    DOCS.mkdir(exist_ok=True)
    (DOCS / "squadre").mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("")
    shutil.copy(ROOT / "assets" / "logo.png", DOCS / "logo.png")
    (DOCS / "dati.json").write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
    tpl = (ROOT / "template.html").read_text(encoding="utf-8")
    pagina = (tpl.replace("__TITOLO__", cfg["titolo_pagina"])
                 .replace("__SOTTOTITOLO__", cfg["sottotitolo_pagina"])
                 .replace("__DATA__", json.dumps(dati, ensure_ascii=False, separators=(",", ":"))))
    (DOCS / "index.html").write_text(pagina, encoding="utf-8")
    scrivi_ics(DOCS / "calendario.ics", dati["matches"], dati, cfg, cfg["titolo_pagina"])
    vecchi = {p.name for p in (DOCS / "squadre").glob("*.ics")}
    for t in dati["teams"]:
        ms = [m for m in dati["matches"] if t["id"] in m["teams"]]
        nome = f"{t['lab']} {t['ser']} ({t['gir']})"
        scrivi_ics(DOCS / "squadre" / f"{t['id']}.ics", ms, dati, cfg, nome)
        vecchi.discard(f"{t['id']}.ics")
    for v in vecchi:
        (DOCS / "squadre" / v).unlink()


def _esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _piega(riga):
    out, cur = [], b""
    for ch in riga:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += cb
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def testo_serie(s):
    """Nei calendari del telefono i simboli diventerebbero emoji: meglio le parole."""
    return s.replace(" ♿", " paralimpica").replace(" ♀", " femminile")


def scrivi_ics(path, matches, dati, cfg, nome_cal):
    nome_cal = testo_serie(nome_cal)
    T = {t["id"]: t for t in dati["teams"]}
    V = dati["venues"]
    stamp = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Calendario squadre FITeT//IT", "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH", _piega("X-WR-CALNAME:" + _esc(nome_cal)), "X-WR-TIMEZONE:Europe/Rome",
         "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H",
         "BEGIN:VTIMEZONE", "TZID:Europe/Rome",
         "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST", "DTSTART:19700329T020000",
         "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
         "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET", "DTSTART:19701025T030000",
         "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD", "END:VTIMEZONE"]
    for m in matches:
        nm = lambda x, c: T[x]["lab"] if c else x
        h, a = nm(m["h"], m["hc"]), nm(m["a"], m["ac"])
        if m["hc"] and m["ac"]:
            tipo = "derby"
        elif m["conc"]:
            tipo = "concentramento"
        else:
            tipo = "casa" if m["hc"] else "trasferta"
        fase = {"A": "andata", "R": "ritorno", "U": ""}[m["f"]]
        ser = testo_serie(m["ser"])
        desc = f"Serie {ser} {m['gir']} · {m['g']}ª giornata {fase} ({tipo})".replace("  ", " ")
        if m["r"]:
            desc += f"\nRisultato: {m['r']}"
        for x in m["teams"]:
            if T[x]["form"]:
                desc += f"\nFormazione {T[x]['lab']}: " + ", ".join(T[x]["form"])
        desc += "\nFonte: Portale Risultati FITeT (salvo variazioni)"
        uid = hashlib.md5(f"{m['id']}".encode()).hexdigest() + f"@fitet-{cfg['societa']['codice_albo']}"
        L += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}"]
        if m["dt"][11:]:
            start = datetime.fromisoformat(m["dt"])
            end = start + timedelta(hours=cfg.get("durata_incontro_ore", 3))
            L += [f"DTSTART;TZID=Europe/Rome:{start:%Y%m%dT%H%M%S}", f"DTEND;TZID=Europe/Rome:{end:%Y%m%dT%H%M%S}"]
        else:
            d = date.fromisoformat(m["dt"][:10])
            L += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}"]
        L.append(_piega("SUMMARY:" + _esc(f"{ser} · {h} – {a}")))
        if m["v"] is not None:
            v = V[m["v"]]
            L.append(_piega("LOCATION:" + _esc(f"{v['n']}, {v['s']}, {v['city']}")))
        L += [_piega("DESCRIPTION:" + _esc(desc)), "END:VEVENT"]
    L.append("END:VCALENDAR")
    path.write_text("\r\n".join(L) + "\r\n", encoding="utf-8", newline="")


# ----------------------------------------------------------------------------- flusso principale
def leggi_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def aggiorna(cfg):
    P = Portale(cfg.get("pausa_tra_richieste_secondi", 1.0))
    albo = str(cfg["societa"]["codice_albo"])
    oggi = date.today()

    # 1. elenco dei gironi
    gironi = []
    if cfg.get("campionati_nazionali", True):
        for cid, nome in categorie_nazionali(P.get(BASE + "menu.php")):
            if nome in cfg.get("categorie_nazionali_escluse", []):
                continue
            gironi += gironi_nazionali(P.get(CAMP + f"elenco_campionati.php?ID_CAMP={cid}"), categoria(nome))
    for reg in cfg.get("regioni", []):
        gironi += gironi_regionali(P.get(BASE + f"risultati/regioni/menu_reg.php?REG={reg}"), reg)
    visti, unici = set(), []
    for g in gironi:
        if g["cam"] not in visti:
            visti.add(g["cam"])
            unici.append(g)
    gironi = unici
    if not gironi:
        raise RuntimeError("Nessun girone trovato: il portale potrebbe aver cambiato struttura.")
    anno = trova_anno(P.get(CAMP + f"testa_campionati.php?CAM={gironi[0]['cam']}&CONC=0"))
    if not anno:
        raise RuntimeError("Stagione (ANNO) non trovata nel portale.")
    print(f"Stagione {anno}: {len(gironi)} gironi da controllare")

    cache = leggi_json(CACHE, {})
    if cache.get("anno") != anno:
        cache = {"anno": anno, "squadre": {}}
    SQ = cache["squadre"]

    def leggi_scheda(sid, cam):
        sc = scheda_squadra(P.get(CAMP + f"DatiSquadra.asp?SQUADRA={sid}&CAM={cam}&ANNO={anno}"))
        sc["letta"] = oggi.isoformat()
        sc["cam"] = cam
        SQ[sid] = sc
        return sc

    # 2. squadre di ogni girone (schede lette solo la prima volta)
    nuove = 0
    for g in gironi:
        g["squadre"] = squadre_girone(P.get(CAMP + f"classifica_squadre.php?CAM={g['cam']}"))
        for sid in g["squadre"]:
            if sid not in SQ:
                leggi_scheda(sid, g["cam"])
                nuove += 1
                if nuove % 50 == 0:
                    CACHE.parent.mkdir(exist_ok=True)
                    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"Schede squadra nuove lette: {nuove}")

    nostri = [g for g in gironi if any(SQ[s]["albo"] == albo for s in g["squadre"])]
    print(f"Gironi con squadre della società {albo}: {len(nostri)}")

    # 3. schede aggiornate per i gironi che ci interessano (campi gara e formazioni)
    limite = (oggi - timedelta(days=cfg.get("rileggi_schede_squadre_ogni_giorni", 7))).isoformat()
    for g in nostri:
        for sid in g["squadre"]:
            if SQ[sid].get("letta", "") < limite:
                leggi_scheda(sid, g["cam"])

    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    # 4. calendari
    cal = {}
    for g in nostri:
        cal[g["cam"]] = calendario(P.get(CAMP + f"Calendario.asp?CAM={g['cam']}&ANNO={anno}"))
        if not cal[g["cam"]]:
            print(f"ATTENZIONE: calendario vuoto o in formato non riconosciuto per {g['nome']} (CAM {g['cam']})")
    print(f"Richieste al portale: {P.richieste}")
    return {"anno": anno, "gironi": nostri, "squadre": SQ, "calendari": cal}


def componi(raw, cfg):
    albo = str(cfg["societa"]["codice_albo"])
    SQ = raw["squadre"]
    ordine = cfg.get("ordine_serie", [])
    teams, venues, vidx, matches = [], [], {}, {}

    def venue(c):
        v = campo(c, cfg)
        if not v:
            return None
        k = (v["n"].lower(), v["s"].lower(), v["city"].lower())
        if k not in vidx:
            vidx[k] = len(venues)
            venues.append(v)
        return vidx[k]

    for g in raw["gironi"]:
        ser, gir = etichetta_serie(g), etichetta_girone(g)
        nomi = {}
        for sid, nome in g["squadre"].items():
            sc = SQ[sid]
            nomi[chiave(nome or sc["nome"])] = sid
            if sc.get("nome"):
                nomi.setdefault(chiave(sc["nome"]), sid)
        nostre = {sid for sid in g["squadre"] if SQ[sid]["albo"] == albo}
        for sid in nostre:
            teams.append({"id": sid, "ser": ser, "gir": gir, "lab": etichetta_squadra(g["squadre"][sid] or SQ[sid]["nome"], cfg),
                          "form": [maiuscole(p) for p in SQ[sid]["formazione"]]})
        conc = g["conc"]  # concentramenti (es. paralimpici): sede decisa dalla FITeT, non dalla squadra di casa
        for m in raw["calendari"].get(g["cam"], []):
            hid, aid = nomi.get(chiave(m["casa"])), nomi.get(chiave(m["ospite"]))
            hc, ac = hid in nostre, aid in nostre
            if not (hc or ac):
                continue
            v = None
            if not conc and hid:
                v = venue(SQ[hid]["campo2"] if m["riserva"] and SQ[hid]["campo2"] else SQ[hid]["campo1"])
            mid = m["incontro"] or f"{g['cam']}-{m['giornata']}-{m['fase']}-{chiave(m['casa'])}-{chiave(m['ospite'])}"
            matches[mid] = {
                "id": mid, "dt": m["data"] + ("T" + m["ora"] if m["ora"] else ""), "ser": ser, "gir": gir,
                "g": m["giornata"], "f": m["fase"],
                "h": hid if hc else nome_avversario(m["casa"]), "a": aid if ac else nome_avversario(m["ospite"]),
                "hc": int(hc), "ac": int(ac), "r": m["risultato"], "v": v, "conc": conc,
                "teams": [x for x in (hid if hc else None, aid if ac else None) if x],
            }

    rank = lambda s: ordine.index(s) if s in ordine else len(ordine)
    teams.sort(key=lambda t: (rank(t["ser"]), t["ser"], t["gir"], t["lab"]))
    ml = sorted(matches.values(), key=lambda m: (m["dt"], rank(m["ser"])))
    serie = sorted({t["ser"] for t in teams}, key=lambda s: (rank(s), s))
    ora = datetime.now(TZ)
    return {"club": cfg["societa"]["nome"], "series": serie, "teams": teams, "venues": venues, "matches": ml,
            "updated": ora.strftime("%d/%m/%Y alle %H:%M"), "updated_iso": ora.isoformat(timespec="seconds"),
            "season": raw["anno"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-pagina", action="store_true", help="rigenera le uscite da docs/grezzi.json senza leggere il portale")
    args = ap.parse_args()
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    grezzi = ROOT / "cache" / "grezzi.json"

    if args.solo_pagina:
        raw = leggi_json(grezzi, None)
        if not raw:
            sys.exit("Nessun dato salvato: esegui prima un aggiornamento completo.")
    else:
        raw = aggiorna(cfg)

    dati = componi(raw, cfg)
    precedenti = leggi_json(DOCS / "dati.json", {}).get("matches", [])
    if not dati["matches"]:
        sys.exit("ERRORE: nessun incontro trovato. Non sovrascrivo il calendario esistente.")
    if len(precedenti) > 20 and len(dati["matches"]) < len(precedenti) / 2:
        sys.exit(f"ERRORE: trovati {len(dati['matches'])} incontri contro {len(precedenti)} della volta scorsa. "
                 "Probabile problema del portale: non sovrascrivo il calendario.")
    if not args.solo_pagina:
        utili = {sid for g in raw["gironi"] for sid in g["squadre"]}
        grezzi.write_text(json.dumps({**raw, "squadre": {k: v for k, v in raw["squadre"].items() if k in utili}},
                                     ensure_ascii=False), encoding="utf-8")
    scrivi_uscite(dati, cfg)
    print(f"Fatto: {len(dati['teams'])} squadre, {len(dati['matches'])} incontri, aggiornato il {dati['updated']}")


if __name__ == "__main__":
    main()
