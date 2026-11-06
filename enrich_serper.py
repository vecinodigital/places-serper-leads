#!/usr/bin/env python3
"""Enriquecer los 141 leads de la tirada real con Serper (1 consulta/lead).

Lee los JSON de out-tirada-real/json/, lanza una búsqueda por negocio
("nombre zona Madrid") y clasifica los resultados orgánicos:

  tipo_web       web_directorio                 instagram
  ----------     ----------------------------   -------------------------
  propia         URL de la web propia           candidato si aparece
  directorio     URL de la ficha en directorio   candidato si aparece
  sin web        (vacío)                        candidato si aparece

Reglas (las mismas del CRM y de ARGUMENTARIOS.md):
- "sin web" en la tirada significa sin web enlazada en GBP, no que el
  negocio no exista en internet. Un resultado SERP vacío no prueba nada:
  la fila sale marcada para confirmar en la llamada.
- Instagram: la consulta SERP solo descubre un candidato. El handle se
  verifica después con el conector de Instagram por handle exacto antes
  de guardarlo en el CRM. Ausencia en SERP = "no encontrado", nunca
  "sin Instagram".
- Propia solo si el dominio contiene un token del nombre del negocio
  (≥4 letras): así no se marca como propia a agregadores ni a dominios
  que no tienen nada que ver.

Salida en OUT_DIR (por defecto out-enrich/ junto a out-tirada-real/):
  raw/<placeId>.json   respuesta cruda de Serper (caché: no se vuelve a
                       gastar crédito si ya existe, salvo --force)
  enrich.csv           una fila por lead con la clasificación y la
                       evidencia (dominios top) para revisión humana

Uso:
  python3 enrich_serper.py [--limit N] [--force] [--dry-query]
  python3 enrich_serper.py --whatsapp-only   # solo los 33 de WhatsApp
                                             # (decisión 27-oct: primero
                                             # este segmento; los 108 de
                                             # fijo se añaden después sin
                                             # regastar créditos, porque
                                             # las filas y la caché ya
                                             # existentes se reutilizan)
  python3 enrich_serper.py --test-classify   # prueba la clasificación
                                             # sin gastar créditos

Si la key de Serper no está disponible (en Muse: guardada en el
conector; fuera de Muse: variable SERPER_API_KEY), el helper falla
en la primera llamada y el script se detiene con un mensaje claro:
no se marca nada a medias.
"""
import csv
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(BASE, "out-tirada-real", "json")
OUT_DIR = os.path.join(BASE, "out-enrich")
# Resolución portable del helper (para Codex y otros entornos):
# 1) SERPER_HELPER explícito; 2) serper_api.py junto a este script;
# 3) ruta legacy del workspace de Muse (solo funciona allí).
_HELPER_SIBLING = os.path.join(BASE, "serper_api.py")
HELPER = os.environ.get("SERPER_HELPER") or (
    _HELPER_SIBLING if os.path.exists(_HELPER_SIBLING)
    else os.path.expanduser(
        "~/workspace/custom-connectors/custom.serper/bin/serper_api.py"))

DIRECTORIES = {
    "autojam.es", "fresha.com", "treatwell.es", "treatwell.com",
    "doctoralia.es", "doctoralia.com", "topdoctors.es",
    "paginasamarillas.es", "qdq.com", "yelp.es", "yelp.com",
    "tripadvisor.es", "tripadvisor.com", "11870.com",
    "salon.es", "booker.com", "booksy.com", "mytime.com",
    "autingo.es", "peluqueriamaster.com", "guiatalleres.com",
    "tallerbarato.com", "masquemedicos.com", "dentistaentuciudad.com",
    "lomejordelbarrio.com", "cronoshare.com",
}
# Palabras genéricas que NO distinguen un negocio de otro y por tanto
# nunca deben marcar una web como propia: el oficio ("taller",
# "peluqueria"), la ciudad y la zona (vienen en la consulta) y palabras
# de servicio ("imagen", "alisados"). Sin este filtro, "Taller Mora
# Motor" marcaba como propia sampermotor.es (otro negocio) y
# "Peluquería Marcia" marcaba peluqueriamaster.com (un directorio).
STOPWORDS = {
    "taller", "talleres", "peluqueria", "peluquerias", "clinica",
    "dental", "dentales", "motor", "motores", "automocion",
    "mecanica", "mecanico", "belleza", "estetica", "hair", "salon",
    "centro", "estudio", "imagen", "tratamientos", "alisados",
    "asesores", "services", "servicios", "studio", "beauty", "spa",
    "madrid", "chamberi", "salamanca", "retiro", "tetuan",
    "arganzuela", "vallecas", "usera", "carabanchel", "latina",
    "moncloa", "hortaleza",
}
PLATFORMS = {  # presencia, no web propia ni directorio
    "facebook.com", "instagram.com", "linkedin.com", "x.com",
    "twitter.com", "tiktok.com", "youtube.com",
}
IG_NON_PROFILE = {
    "p", "reel", "reels", "explore", "stories", "tv", "accounts",
    "direct", "about", "s", "tags", "locations",
}
HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{2,30}$")


def norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def name_tokens(name):
    return [t for t in norm(name).split()
            if len(t) >= 4 and t not in STOPWORDS]


def domain_of(link):
    try:
        host = urlparse(link).netloc.lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def classify(name, organic):
    """Clasifica una lista de resultados orgánicos de Serper."""
    tokens = name_tokens(name)
    name_slug = norm(name).replace(" ", "")
    directories, own, ig = [], [], None
    domains = []
    for r in organic or []:
        link = r.get("link", "")
        dom = domain_of(link)
        if not dom:
            continue
        domains.append(dom)
        if dom == "instagram.com":
            path = [s for s in urlparse(link).path.split("/") if s]
            if len(path) == 1 and path[0] not in IG_NON_PROFILE \
                    and HANDLE_RE.match(path[0]):
                if ig is None:
                    ig = {"handle": path[0], "url": link}
            continue
        if dom in DIRECTORIES:
            directories.append(link)
            continue
        if dom in PLATFORMS:
            continue
        dom_slug = re.sub(r"\.(es|com|net|org|eu|info)$", "", dom)
        dom_slug = re.sub(r"[^a-z0-9]", "", dom_slug)
        # La cláusula de slug completo solo vale si queda algún token
        # distintivo: un nombre compuesto solo de palabras genéricas
        # ("SM Motor") igualaría el slug de cualquier "SM Motor" del
        # país, y eso contradijo el registro verificado de SM Motor
        # (directorio autojam, revisado a mano).
        if tokens and (any(t in dom_slug or dom_slug in t for t in tokens)
                       or (dom_slug and dom_slug in name_slug)):
            own.append(link)
    if own:
        tipo, web = "propia", own[0]
    elif directories:
        tipo, web = "directorio", directories[0]
    else:
        tipo, web = "sin web", ""
    flags = []
    if len(directories) > 1:
        flags.append("varios directorios")
    if tipo == "directorio":
        path = urlparse(web).path
        if "/lp/" in path or "/clasificacion/" in path:
            flags.append("URL de directorio es página de categoría, "
                         "no ficha del negocio")
    if ig is not None and not any(t in ig["handle"].lower()
                                  for t in tokens):
        flags.append("handle IG sin coincidencia con el nombre")
    if tipo == "sin web":
        flags.append("confirmar en llamada")
    return {
        "tipo_web": tipo,
        "web_directorio": web,
        "instagram": ig["url"] if ig else "",
        "ig_handle": ig["handle"] if ig else "",
        "dominios_top": " | ".join(list(dict.fromkeys(domains))[:5]),
        "revision_manual": "; ".join(flags),
    }


def serper_search(query):
    proc = subprocess.run(
        [sys.executable, HELPER, "search", query],
        capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Serper falló para {query!r}: {proc.stderr.strip()[:300]}")
    return json.loads(proc.stdout)


def load_leads(json_dir):
    leads = []
    for fname in sorted(os.listdir(json_dir)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(json_dir, fname), encoding="utf-8") as fh:
            leads.append(json.load(fh))
    return leads


def run(limit=None, force=False, dry_query=False, whatsapp_only=False):
    leads = load_leads(JSON_DIR)
    if whatsapp_only:
        leads = [l for l in leads
                 if l.get("channel") == "llamada+whatsapp"]
    raw_dir = os.path.join(OUT_DIR, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "enrich.csv")
    existing = {}
    if os.path.exists(out_path) and not force:
        with open(out_path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                existing[row["place_id"]] = row
    rows, spent = [], 0
    for i, lead in enumerate(leads, 1):
        biz = lead["business"]
        place_id = lead["source"]["placeId"]
        if place_id in existing:
            rows.append(existing[place_id])
            continue
        if limit and spent >= limit:
            break
        query = f"{biz['name']} {biz.get('zone', '')} Madrid".strip()
        if dry_query:
            print(f"[dry] {query}")
            continue
        raw_path = os.path.join(raw_dir, f"{place_id}.json")
        if os.path.exists(raw_path) and not force:
            with open(raw_path, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = serper_search(query)  # aborta si la key no está
            with open(raw_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            spent += 1
        cls = classify(biz["name"], data.get("organic"))
        rows.append({
            "place_id": place_id, "negocio": biz["name"],
            "vertical": lead.get("vertical", ""), "query": query, **cls})
        if i % 10 == 0:
            print(f"{i}/{len(leads)} leads, {spent} consultas nuevas")
        time.sleep(0.3)
    if not dry_query:
        fields = ["place_id", "negocio", "vertical", "query", "tipo_web",
                  "web_directorio", "instagram", "ig_handle",
                  "dominios_top", "revision_manual"]
        with open(out_path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        from collections import Counter
        print(f"Filas: {len(rows)} | consultas nuevas: {spent}")
        print(Counter(r["tipo_web"] for r in rows))
        print(f"Salida: {out_path}")


def reclassify():
    """Reclasifica desde la caché raw sin gastar créditos.

    Para corregir la clasificación sin volver a llamar a Serper: lee
    raw/<placeId>.json de cada lead de WhatsApp y reescribe enrich.csv.
    """
    leads = [l for l in load_leads(JSON_DIR)
             if l.get("channel") == "llamada+whatsapp"]
    raw_dir = os.path.join(OUT_DIR, "raw")
    rows, missing = [], []
    for lead in leads:
        biz = lead["business"]
        place_id = lead["source"]["placeId"]
        raw_path = os.path.join(raw_dir, f"{place_id}.json")
        if not os.path.exists(raw_path):
            missing.append(biz["name"])
            continue
        with open(raw_path, encoding="utf-8") as fh:
            data = json.load(fh)
        cls = classify(biz["name"], data.get("organic"))
        rows.append({
            "place_id": place_id, "negocio": biz["name"],
            "vertical": lead.get("vertical", ""),
            "query": f"{biz['name']} {biz.get('zone', '')} Madrid".strip(),
            **cls})
    fields = ["place_id", "negocio", "vertical", "query", "tipo_web",
              "web_directorio", "instagram", "ig_handle",
              "dominios_top", "revision_manual"]
    with open(os.path.join(OUT_DIR, "enrich.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(f"Filas: {len(rows)} | consultas nuevas: 0 (caché)")
    print(Counter(r["tipo_web"] for r in rows))
    if missing:
        print(f"Sin caché (no clasificados): {missing}")


def test_classify():
    cases = [
        ("SM Motor", [
            {"link": "https://autojam.es/directorio/ficha/sm-motor-madrid-21988/"},
            {"link": "https://www.instagram.com/smmotor.madrid/"},
            {"link": "https://www.google.com/maps/place/SM+Motor"},
        ], "directorio"),
        ("Salon Elegance", [
            {"link": "https://www.fresha.com/es/lvp/salon-elegance-madrid"},
            {"link": "https://www.treatwell.es/establecimiento/studio-elegance/"},
            {"link": "https://www.instagram.com/peluqueria_nailsmadridelegance/"},
        ], "directorio"),
        ("Taller Hermanos Ruiz", [
            {"link": "https://tallerhermanosruiz.es/"},
            {"link": "https://www.paginasamarillas.es/f/taller-hermanos-ruiz"},
        ], "propia"),
        ("Clínica Dental Sonrisa", [
            {"link": "https://www.facebook.com/clinicadentalsonrisa"},
            {"link": "https://www.google.com/maps/place/Cl%C3%ADnica+Dental+Sonrisa"},
        ], "sin web"),
        ("Auto López", [
            {"link": "https://apiempresas.es/auto-lopez-madrid"},
            {"link": "https://www.instagram.com/autolopez_taller/"},
        ], "sin web"),
    ]
    ok = True
    for name, organic, expected in cases:
        got = classify(name, organic)
        status = "OK " if got["tipo_web"] == expected else "FAIL"
        ok = ok and got["tipo_web"] == expected
        print(f"{status} {name}: {got['tipo_web']} "
              f"(esperado {expected}) web={got['web_directorio'] or '-'} "
              f"ig={got['ig_handle'] or '-'} "
              f"flags={got['revision_manual'] or '-'}")
    print("TODAS OK" if ok else "HAY FALLOS")
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--test-classify" in args:
        raise SystemExit(test_classify())
    if "--reclassify" in args:
        reclassify()
        raise SystemExit(0)
    limit = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    run(limit=limit, force="--force" in args, dry_query="--dry-query" in args,
        whatsapp_only="--whatsapp-only" in args)
