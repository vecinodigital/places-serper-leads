# Leads de Google Maps: Places API + enriquecimiento Serper

Código tal como lo usamos en VecinoDigital / Localia para sacar
negocios de Google Maps a CSV. Sin claves dentro: cada uno pone la suya
en variables de entorno. Nunca subas las claves a git ni las pegues en
un fichero.

## Archivos

- `places_leads.py` — el principal. Consulta Places API (New) Text Search,
  filtra negocios `OPERATIONAL` **sin web**, deduplica por `place_id`,
  clasifica el teléfono (móvil / fijo / sin teléfono) y genera:
  - `out/leads.csv` — contactables, columnas de la pestaña LEADS del CRM
  - `out/aparcados.csv` — sin teléfono, para enriquecer después
  - `out/json/<negocio>.json` — un JSON por negocio
  - `out/ganchos.txt` — línea personalizada por lead para el outreach
- `enrich_serper.py` — enriquecimiento con Serper. Lee los JSON de la
  tirada, hace 1 búsqueda por negocio (`nombre + zona + Madrid`) y
  clasifica cada resultado: web `propia`, `directorio` o `sin web`,
  más candidato de Instagram. Genera `out-enrich/enrich.csv` y guarda
  la respuesta cruda en `out-enrich/raw/<placeId>.json` como caché
  (no vuelve a gastar crédito si ya existe, salvo `--force`).
- `places_api_standalone.py` — búsqueda suelta en Places (1 página,
  hasta 20 resultados). Versión portable del helper de Muse.
- `serper_api_standalone.py` — búsqueda suelta en Serper (hasta 10
  resultados). Versión portable del helper de Muse.

En Muse los helpers originales usan el conector (la clave llega por
surrogate y nunca está en fichero). Fuera de Muse, usa los
`*_standalone.py` de este paquete.

## Claves que necesita tu amigo

1. **Google Places API (New)**: proyecto en Google Cloud Console con
   facturación habilitada y la API "Places API (New)" activada.
   Ojo: pedir el teléfono activa el SKU Enterprise de Text Search,
   revisa el precio vigente antes de escalar.
2. **Serper** (serper.dev): API key del dashboard, plan gratuito
   (2.500 créditos; 1 crédito = 1 consulta, hasta 10 resultados).

```bash
export GOOGLE_PLACES_API_KEY="..."
export SERPER_API_KEY="..."
```

## Uso

```bash
# 1) Prueba sin gastar nada (datos de ejemplo)
python3 places_leads.py --demo --vertical Dental

# 2) Tirada real: negocios sin web en Madrid centro (~10 km)
#    Text Search NO acepta "circle" en locationRestriction
#    (la API lo rechazó con INVALID_ARGUMENT el 27-oct-2026);
#    por eso el script usa un rectángulo.
python3 places_leads.py --vertical Dental \
  --queries "clinica dental Chamberi" "clinica dental Retiro" \
  --out out-tirada-real

# 3) Enriquecimiento Serper (primero solo los de WhatsApp)
#    El script busca el helper como serper_api.py junto a él,
#    o por la variable SERPER_HELPER:
export SERPER_HELPER="./serper_api_standalone.py"
#    o bien: cp serper_api_standalone.py serper_api.py
python3 enrich_serper.py --whatsapp-only

#    Todos los leads, o solo reclasificar desde la caché sin gastar:
python3 enrich_serper.py
python3 enrich_serper.py --reclassify
python3 enrich_serper.py --test-classify   # prueba la clasificación sin gastar
```

## Resultado real de referencia (27-oct-2026, Madrid)

5 tiradas en 12 distritos (dental, talleres, peluquerías):
565 resultados brutos → 413 descartados por tener web →
**141 contactables (33 con WhatsApp)** + 9 aparcados sin teléfono.
En dental céntrico ~90% ya tiene web; talleres (79) y peluquerías (34)
dieron más leads sin web. Serper: 33 consultas / 33 créditos sobre
los 33 leads de WhatsApp.

## Límites y avisos

- Places API **no devuelve email**. El email se consigue en la llamada.
- "Sin web" en la tirada = sin web enlazada en Google Business Profile,
  no que el negocio no exista en internet. Un SERP vacío no prueba nada:
  la fila sale marcada para confirmar en la llamada.
- Instagram: Serper solo descubre un **candidato** a handle. Hay que
  verificarlo por handle exacto antes de guardarlo en el CRM.
  Ausencia en SERP = "no encontrado", nunca "sin Instagram".
- Términos de Google: prohíben scrapear/exportar en masa contenido de
  Google Maps; solo caché limitado (place ID sin límite temporal;
  lat/lng hasta 30 días). Revisar antes de guardar nombres/direcciones/
  teléfonos/ratings indefinidamente en un CRM.
