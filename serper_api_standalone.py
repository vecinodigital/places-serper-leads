#!/usr/bin/env python3
"""Serper helper STANDALONE (fuera de Muse).

Uso:
  export SERPER_API_KEY="tu-clave-de-serper.dev"
  python3 serper_api_standalone.py search "SM Motor Madrid"

Es el equivalente portable de serper_api.py: en Muse la clave llega
por el conector (surrogate), aquí se lee de la variable de entorno.
POST a https://google.serper.dev/search con gl=es, hl=es, num=10,
location Madrid, Spain. Imprime el JSON crudo.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://google.serper.dev"


def search(query):
    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        print("Falta SERPER_API_KEY en el entorno", file=sys.stderr)
        raise SystemExit(1)
    body = {"q": query, "gl": "es", "hl": "es", "num": 10,
            "location": "Madrid, Spain"}
    request = urllib.request.Request(
        BASE + "/search", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-API-KEY": api_key},
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
