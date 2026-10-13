"""Controlli sulla lettura delle pagine del portale (pagine reali salvate in fixtures/).
Esegui con:  python -m pytest tests   oppure   python tests/test_lettura.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aggiorna as A  # noqa: E402

P = json.loads((Path(__file__).parent / "fixtures" / "pagine.json").read_text(encoding="utf-8"))


def test_calendario_andata_ritorno():
    c = A.calendario(P["cal213"])
    assert len(c) == 12  # 2 giornate x 3 righe x (andata + ritorno)
    m = c[0]
    assert m == {"giornata": 1, "fase": "A", "data": "2026-10-08", "ora": "20:30", "casa": "cus c",
                 "ospite": "PONGISTISERI Giaveno", "risultato": "5-2", "riserva": True, "incontro": "376815"}
    r = c[1]
    assert (r["fase"], r["data"], r["ora"], r["casa"], r["ospite"], r["risultato"], r["riserva"]) == \
           ("R", "2027-01-15", "20:00", "PONGISTISERI Giaveno", "cus c", "", False)
    assert c[6]["giornata"] == 2 and c[6]["risultato"] == ""


def test_calendario_concentramento():
    c = A.calendario(P["cal54"])
    assert len(c) == 4 and all(m["fase"] == "U" for m in c)
    assert c[2]["casa"] == "ASD CUS TORINO" and c[2]["ospite"] == "A4 VERZUOLO TONOLI-SCOTTA"
    assert c[2]["data"] == "2026-10-25" and c[2]["ora"] == "09:30"


def test_classifica():
    s = A.squadre_girone(P["class213"])
    assert s == {"38866": "cus c", "38869": "ASD TT GASP Moncalieri A"}


def test_scheda():
    s = A.scheda_squadra(P["dati"])
    assert s["albo"] == "437" and s["societa"] == "A.S. Dilettantistica Cus Torino"
    assert s["nome"] == "cus c"
    assert s["campo1"]["nome"] == "Istituto Vittorini"
    assert s["campo2"]["indirizzo"] == "vial CLN 53-Grugliasco"
    assert s["formazione"] == ["SCHIAVONE VALERIO", "FORMICHETTI LEONARDO", "AMEDURI FABRIZIO"]


def test_elenchi():
    assert A.categorie_nazionali(P["menu"])[:2] == [("2", "Serie A"), ("3", "Serie B")]
    g = A.gironi_nazionali(P["elenco2"], "serie")
    assert [(x["cam"], x["sesso"]) for x in g] == [("1", "Maschile"), ("3", "Maschile"), ("2", "Femminile"), ("18", "Femminile")]
    p = A.gironi_nazionali(P["elenco7"], "para")
    assert [x["cam"] for x in p] == ["51", "49", "54", "57"] and all(x["conc"] for x in p)
    r = A.gironi_regionali(P["menureg"], 2)
    assert [(x["cam"], x["cat"]) for x in r] == [("233", "coppa"), ("201", "serie"), ("213", "serie")]
    assert A.trova_anno(P["testa"]) == "41"


def test_etichette():
    E = lambda nome, sesso="Maschile", cat="serie": A.etichetta_serie({"nome": nome, "sesso": sesso, "cat": cat})
    assert E("B/1 Gir.B") == "B1"
    assert E("D/3 Gir.N") == "D3"
    assert E("C Gir.A", "Femminile") == "C ♀"
    assert E("A/2 gruppo 1-5 Gir.B", cat="para") == "A2 ♿"
    assert E("A/2 Gir.A", cat="master") == "M. A2"
    assert E("C Gir.A", cat="master") == "M. C"
    assert E("C.I. C2D1 gir. A", "", "coppa") == "C.I."
    G = lambda nome: A.etichetta_girone({"nome": nome})
    assert G("D/2 Gir.B") == "Gir. B"
    assert G("A/2 gruppo 1-5 Gir.B") == "gruppo 1-5 Gir. B"
    assert G("C.I. C2D1 gir. A") == "C2D1 Gir. A"
    cfg = {"societa": {"nome": "CUS Torino", "nome_breve": "CUS"}}
    assert A.etichetta_squadra("TT.Cus C", cfg) == "CUS C"
    assert A.etichetta_squadra("cus a", cfg) == "CUS A"
    assert A.etichetta_squadra("ASD CUS TORINO", cfg) == "CUS Torino"


def test_testi():
    assert A.maiuscole("SCHIAVONE VALERIO") == "Schiavone Valerio"
    assert A.maiuscole("PALESTRA SCUOLE MEDIE “V. ALFIERI”") == "Palestra Scuole Medie “V. Alfieri”"
    cfg = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
    v = A.campo({"nome": "PALESTRA CRDC TORINO", "indirizzo": "CORSO SICILIA, 12  10133 TORINO-Torino"}, cfg)
    assert v == {"n": "Palestra CRDC Torino", "s": "Corso Sicilia, 12", "city": "Torino"}
    v = A.campo({"nome": "Istituto Vittorinio", "indirizzo": "Corso Allamano 130, ingresso strada del Barocchio 27-Grugliasco"}, cfg)
    assert v == {"n": "Istituto Vittorini", "s": "Corso Allamano 130 (ingresso Strada del Barocchio 27)", "city": "Grugliasco"}


def test_componi_e_uscite(tmp_path, monkeypatch=None):
    cfg = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
    nostra = A.scheda_squadra(P["dati"])
    altra = {"nome": "ASD TT GASP Moncalieri A", "albo": "999", "campo1": {"nome": "Imp. Sportivo Palablu",
             "indirizzo": "Piazza Brennero 3-Moncalieri"}, "campo2": None, "formazione": []}
    raw = {"anno": "41", "calendari": {"213": A.calendario(P["cal213"])}, "squadre": {"38866": nostra, "38869": altra},
           "gironi": [{"cam": "213", "nome": "D/2 Gir.B", "sesso": "", "cat": "serie", "conc": False,
                       "squadre": {"38866": "cus c", "38869": "ASD TT GASP Moncalieri A"}}]}
    d = A.componi(raw, cfg)
    assert [t["lab"] for t in d["teams"]] == ["CUS C"] and d["series"] == ["D2"]
    assert len(d["matches"]) == 4
    primo = d["matches"][0]
    assert primo["dt"] == "2026-10-08T20:30" and primo["r"] == "5-2" and primo["hc"] == 1
    assert d["venues"][primo["v"]]["n"] == "Palazzetto dello Sport"  # asterisco = campo di riserva
    A.DOCS = Path(tmp_path)
    A.scrivi_uscite(d, cfg)
    assert (Path(tmp_path) / "index.html").read_text(encoding="utf-8").count("CUS C") >= 1
    assert "BEGIN:VEVENT" in (Path(tmp_path) / "squadre" / "38866.ics").read_text(encoding="utf-8")


if __name__ == "__main__":
    import tempfile
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(tempfile.mkdtemp()) if k == "test_componi_e_uscite" else f()
            print("ok", k)
