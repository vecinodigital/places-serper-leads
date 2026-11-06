#!/usr/bin/env python3
"""Places API (New) helper STANDALONE (fuera de Muse).

Uso:
  export GOOGLE_PLACES_API_KEY="tu-clave-de-google-cloud"
  python3 places_api_standalone.py search "clinica dental Chamberi"

Equivalente portable de places_api.py: en Muse la clave llega por el
conector (surrogate), aquí se lee de la variable de entorno.
POST a https://places.googleapis.com/v1/places:searchText, una página
(hasta 20 resultados), rectángulo ~10 km alrededor del centro de Madrid.
Imprime el JSON crudo.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://places.googleapis.com"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.websiteUri,"
    "places.rating,places.userRatingCount,places.internationalPhoneNumber,"
    "places.googleMapsUri,places.businessStatus,places.regularOpeningHours"
)


def search(query):
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        print("Falta GOOGLE_PLACES_API_KEY en el entorno", file=sys.stderr)
        raise SystemExit(1)
    body = {"textQuery": query, "languageCode": "es",
            "locationRestriction": {
                "rectangle": {
                    "low": {"latitude": 40.327, "longitude": -3.822},
                    "high": {"latitude": 40.507, "longitude": -3.586}}}}
    request = urllib.request.Request(
        BASE + "/v1/places:searchText", data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json",
                 "X-Goog-FieldMask": FIELD_MASK,
                 "X-Goog-Api-Key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:1000]}",
              file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "search":
        print(json.dumps(search(sys.argv[2]), indent=2, ensure_ascii=False))
    else:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
