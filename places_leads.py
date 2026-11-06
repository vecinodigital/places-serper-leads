#!/usr/bin/env python3
"""
places_leads.py — Sourcing de leads para la agencia de webs (VecinoDigital).

Flujo: Places API -> filtro "sin web" -> TRIAJE por teléfono -> CRM (CSV)
       -> JSON por web -> ganchos de outreach.

El teléfono es el combustible del outreach (call-first + WhatsApp).
Sin teléfono, el lead se aparca para enriquecimiento manual posterior.

Uso demo (sin API key, datos de ejemplo):
    python3 places_leads.py --demo --vertical Dental

Uso real (la clave vive en el conector custom.google_places, nunca en el
script ni en variables de entorno; solo como respaldo se acepta
GOOGLE_PLACES_API_KEY en el entorno):
    python3 places_leads.py --vertical Dental --queries "clinica dental Chamberi" "clinica dental Vallecas"

Salida:
    out/leads.csv      -> contactables, columnas = pestaña LEADS del CRM
    out/aparcados.csv  -> sin teléfono (enriquecer vía Facebook o revisitar)
    out/json/<slug>.json -> JSON listo para la fábrica de mockups
    out/ganchos.txt    -> línea personalizada por lead para el outreach
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import date

API_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.websiteUri,"
    "places.rating,places.userRatingCount,places.internationalPhoneNumber,"
    "places.googleMapsUri,places.businessStatus,places.regularOpeningHours"
)

# --- Datos de ejemplo (modo --demo). Estructura idéntica a la respuesta real ---
MOCK = [
    {
        "id": "ChIJDEMOSonrisa001",
        "displayName": {"text": "Clínica Dental Sonrisa"},
        "formattedAddress": "C/ de Fuencarral 12, 28004 Madrid, España",
        "rating": 4.6, "userRatingCount": 87,
        "internationalPhoneNumber": "+34 600 111 222",
        "googleMapsUri": "https://maps.google.com/?cid=111",
        "businessStatus": "OPERATIONAL",
        "regularOpeningHours": {"weekdayDescriptions": [
            "lunes: 9:00–14:00, 16:00–20:00"]},
    },
    {
        "id": "ChIJDEMOTaller002",
        "displayName": {"text": "Taller Hermanos Ruiz"},
        "formattedAddress": "Av. de la Aurora 45, 28031 Madrid, España",
        "rating": 4.3, "userRatingCount": 52,
        "internationalPhoneNumber": "+34 911 222 333",
        "googleMapsUri": "https://maps.google.com/?cid=222",
        "businessStatus": "OPERATIONAL",
    },
    {
        "id": "ChIJDEMORincon004",
        "displayName": {"text": "Bar El Rincón"},
        "formattedAddress": "C/ del Pez 5, 28004 Madrid, España",
        "rating": 4.1, "userRatingCount": 38,
        "googleMapsUri": "https://maps.google.com/?cid=444",
        "businessStatus": "OPERATIONAL",
    },
    {
        "id": "ChIJDEMOPelu003",
        "displayName": {"text": "Peluquería Luna"},
        "formattedAddress": "C/ de la Oca 8, 28025 Madrid, España",
        "rating": 4.8, "userRatingCount": 134,
        "websiteUri": "https://peluqueria-luna-ejemplo.es",
        "internationalPhoneNumber": "+34 622 333 444",
        "googleMapsUri": "https://maps.google.com/?cid=333",
        "businessStatus": "OPERATIONAL",
    },
]


def slugify(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def api_search(api_key, query):
    """Text Search con paginación (hasta 60 resultados).

    Sin api_key, la clave llega por el conector custom.google_places
    (intercambio surrogate): nunca se lee de un fichero ni del entorno.
    """
    results, page_token = [], None
    use_surrogate = not api_key
    headers = {"Content-Type": "application/json",
               "X-Goog-FieldMask": FIELD_MASK}
    if api_key:
        headers["X-Goog-Api-Key"] = api_key
    for _ in range(3):
        # Restricción a Madrid centro: Text Search NO acepta "circle" en
        # locationRestriction (la API lo rechazó con INVALID_ARGUMENT el
        # 27-oct-2026); rectángulo ~10 km alrededor de (40.4168, -3.7038).
        # Cubre Chamberí, Salamanca y Retiro y deja fuera Salamanca ciudad,
        # que coló en la tirada piloto del 27-oct con la query "Salamanca".
        body = {"textQuery": query, "languageCode": "es",
                "locationRestriction": {
                    "rectangle": {
                        "low": {"latitude": 40.327, "longitude": -3.822},
                        "high": {"latitude": 40.507, "longitude": -3.586}}}}
        if page_token:
            time.sleep(2)  # el pageToken necesita ~2s para activarse
            body["pageToken"] = page_token
        req = urllib.request.Request(API_URL, data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
        if use_surrogate:
            sys.path.insert(
                0, "/opt/muse/skills/custom-connector-setup/bin")
            from dynamic_credentials import add_surrogate_to_request
            add_surrogate_to_request(req, "custom.google_places",
                                     allowed_hosts=["places.googleapis.com"])
            opener = urllib.request.build_opener(NoRedirect())
        else:
            opener = urllib.request.build_opener()
        with opener.open(req, timeout=30) as r:
            data = json.load(r)
        results.extend(data.get("places", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return results


def to_lead(p, zona, vertical):
    digits = re.sub(r"\D", "", p.get("internationalPhoneNumber", ""))
    if not digits:
        tipo, canal = "sin-telefono", "aparcar"
    elif re.match(r"^34[67]", digits) or re.match(r"^[67]", digits):
        tipo, canal = "movil", "llamada+whatsapp"
    else:
        tipo, canal = "fijo", "llamada"
    return {
        "place_id": p.get("id", ""),
        "negocio": p.get("displayName", {}).get("text", ""),
        "vertical": vertical,
        "direccion": p.get("formattedAddress", ""),
        "zona": zona,
        "telefono": p.get("internationalPhoneNumber", ""),
        "whatsapp": digits,
        "tipo_tel": tipo,
        "canal": canal,
        "rating": p.get("rating", ""),
        "num_resenas": p.get("userRatingCount", ""),
        "maps_url": p.get("googleMapsUri", ""),
        "website": p.get("websiteUri", ""),
        "estado": p.get("businessStatus", ""),
        "horario": "; ".join(
            p.get("regularOpeningHours", {}).get("weekdayDescriptions", [])),
    }


def gancho(lead):
    base = (f"{lead['rating']} estrellas con {lead['num_resenas']} reseñas "
            f"en {lead['zona']} y sin web que las enseñe")
    if lead["tipo_tel"] == "movil":
        return base + " [WhatsApp disponible]"
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--vertical", default="")
    ap.add_argument("--queries", nargs="*", default=[])
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    vistos, contactables, aparcados = set(), [], []
    total = con_web = 0
    grupos = ([("Demo", MOCK)] if a.demo else
              [(q, api_search(os.environ.get("GOOGLE_PLACES_API_KEY", ""), q))
               for q in a.queries])

    for query, places in grupos:
        zona = "Chamberí" if a.demo else query.split()[-1]
        total += len(places)
        for p in places:
            lead = to_lead(p, zona, a.vertical)
            if lead["estado"] != "OPERATIONAL":
                continue
            if lead["website"]:
                con_web += 1
                continue
            if lead["place_id"] in vistos:
                continue
            vistos.add(lead["place_id"])
            (contactables if lead["canal"] != "aparcar"
             else aparcados).append(lead)

    os.makedirs(f"{a.out}/json", exist_ok=True)
    cols = ["ID", "Negocio", "Vertical", "Persona", "Email", "Tel/WhatsApp",
            "Dirección", "Rating", "Nº reseñas", "Link Maps",
            "Link mockup", "Etapa", "Último contacto", "Próx. acción", "Notas"]

    def fila(i, l):
        accion = {"llamada+whatsapp": "Llamar + WhatsApp día 1",
                  "llamada": "Llamar día 1"}.get(l["canal"], "Enriquecer")
        return [i, l["negocio"], l["vertical"], "", "", l["telefono"],
                l["direccion"], l["rating"], l["num_resenas"],
                l["maps_url"], "", "Lead", str(date.today()), accion,
                f"place_id {l['place_id']}"]

    with open(f"{a.out}/leads.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, l in enumerate(contactables, 1):
            w.writerow(fila(i, l))
    with open(f"{a.out}/aparcados.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, l in enumerate(aparcados, 1):
            w.writerow(fila(i, l))

    for l in contactables:
        with open(f"{a.out}/json/{slugify(l['negocio'])}.json",
                  "w", encoding="utf-8") as f:
            vertical_lower = (l["vertical"] or "").lower()
            if "dental" in vertical_lower or "clínica" in vertical_lower or "clinica" in vertical_lower:
                theme = "dental"
            elif "taller" in vertical_lower:
                theme = "taller"
            elif "peluquer" in vertical_lower or "estética" in vertical_lower or "estetica" in vertical_lower:
                theme = "belleza"
            else:
                theme = "local"
            json.dump({
                "business": {
                    "name": l["negocio"], "address": l["direccion"],
                    "zone": l["zona"], "phone": l["telefono"],
                    "whatsapp": l["whatsapp"], "mapsUrl": l["maps_url"]},
                "vertical": l["vertical"],
                "phoneType": l["tipo_tel"],
                "channel": l["canal"],
                "rating": l["rating"], "reviewCount": l["num_resenas"],
                "hours": l["horario"].split("; ") if l["horario"] else [],
                "theme": theme,
                "source": {"placeId": l["place_id"],
                           "sourcedAt": str(date.today())},
            }, f, ensure_ascii=False, indent=2)

    with open(f"{a.out}/ganchos.txt", "w", encoding="utf-8") as f:
        for l in contactables:
            f.write(f"{l['negocio']} [{l['canal']}] -> {gancho(l)}\n")

    moviles = sum(1 for l in contactables if l["tipo_tel"] == "movil")
    print(f"Resultados: {total} | con web (descartados): {con_web} | "
          f"contactables: {len(contactables)} (móvil: {moviles}) | "
          f"aparcados sin teléfono: {len(aparcados)}")


if __name__ == "__main__":
    main()
