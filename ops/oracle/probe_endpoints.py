#!/usr/bin/env python3
"""
Gate previo a montar cualquier cosa en la nube: ¿los supermercados le contestan
a una IP de datacenter igual que a una IP residencial argentina?

Se corre DOS veces —una desde tu máquina, para tener la línea de base, y otra
desde una EC2 recién lanzada— y se comparan las dos salidas. Si desde AWS vuelve
403, captcha, o HTML donde debería haber JSON, el plan de migración cambia entero
(proxy residencial = costo recurrente, o el pipeline se queda local), y conviene
enterarse antes de crear una RDS, no después.

    python3 ops/oracle/probe_endpoints.py                 # salida legible
    python3 ops/oracle/probe_endpoints.py --json > x.json # para diff entre corridas

Única dependencia: httpx. En una EC2 pelada alcanza con
`python3 -m pip install httpx` — a propósito NO importa nada de `src/`, así que
sirve sin clonar el repo ni armar el venv.

Códigos de salida (para poder encadenarlo en un script):
    0  las cuatro sondas OK
    1  alguna falló
"""
import argparse
import json
import sys
import time

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) "
      "Gecko/20100101 Firefox/152.0")

# El sha256Hash de la persisted query de VTEX. Está fijo y salió de una sesión de
# navegador: si la tienda lo rota, GraphQL contesta HTTP 200 con un array
# `errors` y sin `data`. Esa es una de las fallas que este probe distingue, y no
# tiene nada que ver con AWS — pero si aparece acá, aparece en producción.
VTEX_HASH = "b398fc0a2fd04ea5d4f7a94c732c10fb1bf64f8f9a2b31c92aee6a5e796457c9"


def _vtex_payload(category_query: str, product_origin_vtex: bool, skus_filter: str) -> dict:
    parts = [p for p in category_query.split("/") if p]
    return {
        "operationName": "productSearchV3",
        "variables": {
            "hideUnavailableItems": True,
            "skusFilter": skus_filter,
            "simulationBehavior": "default",
            "installmentCriteria": "MAX_WITHOUT_INTEREST",
            "productOriginVtex": product_origin_vtex,
            "map": ",".join(["c"] * len(parts)),
            "query": category_query,
            "orderBy": "OrderByScoreDESC",
            "from": 0,
            "to": 4,
            "selectedFacets": [{"key": "c", "value": p} for p in parts],
            "operator": "and",
            "fuzzy": "0",
            "searchState": None,
            "facetsBehavior": "Static",
            "categoryTreeBehavior": "default",
            "withFacets": False,
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": VTEX_HASH,
                "sender": "vtex.store-resources@0.x",
                "provider": "vtex.search-graphql@0.x",
            }
        },
    }


# ---------------------------------------------------------------------------
# Las cuatro sondas. Cada una devuelve (ok: bool, detalle: str).
# El criterio NO es "status 200": el sitio de Coto es un SPA que sirve su
# index.html con HTTP 200 para cualquier ruta desconocida, así que un cliente que
# sólo mire el código de estado parsea una página web creyendo que son datos.
# Por eso cada sonda exige content-type JSON y además una forma esperada.
# ---------------------------------------------------------------------------

def probe_coto_catalogo(client: httpx.Client) -> tuple[bool, str]:
    """El BFF de catálogo. `catv00001264` es una clave real del MVP (src/shelves.py)."""
    url = (
        "https://api.coto.com.ar/api/v1/ms-digital-sitio-bff-web/api/v1"
        "/products/categories/catv00001264"
        "?page=1&key=key_r6xzz4IAoTWcipni&num_results_per_page=4"
        "&pre_filter_expression=%7B%22name%22:%22store_availability%22,%22value%22:%22200%22%7D"
        "&c=cio-fe-web-coto-3.5.2&i=5792d439-2540-4787-a25c-b6cf441f61c9&s=1"
    )
    r = client.get(url, headers={
        "Accept": "application/json",
        "Origin": "https://www.cotodigital.com.ar",
        "Referer": "https://www.cotodigital.com.ar/",
    })
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    if "json" not in r.headers.get("content-type", "").lower():
        return False, f"content-type {r.headers.get('content-type')!r} (¿HTML del SPA o un captcha?)"
    results = r.json().get("response", {}).get("results", [])
    if not results:
        return False, "JSON válido pero sin `response.results`"
    return True, f"{len(results)} productos, p.ej. {results[0].get('value')!r}"


def probe_coto_cobertura(client: httpx.Client) -> tuple[bool, str]:
    """El actor ATG de cobertura (src/coto_logistics.py). Coordenadas: Obelisco."""
    r = client.get(
        "https://www.coto.com.ar/rest/model/atg/actors/cProfileActor/getCobertura",
        params={"lat": "-34.6037", "lng": "-58.3816"},
        headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.coto.com.ar/",
            "Origin": "https://www.coto.com.ar",
        },
    )
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    if "json" not in r.headers.get("content-type", "").lower():
        return False, f"content-type {r.headers.get('content-type')!r} (el SPA devuelve 200 + HTML)"
    suc = r.json().get("sucursal", {})
    if "mensajeError" not in suc:
        return False, f"JSON sin `sucursal.mensajeError`: {list(suc)[:5]}"
    return True, f"sucursal={suc.get('sucursal')!r} mensajeError={suc.get('mensajeError')!r}"


def _probe_vtex(client: httpx.Client, url: str, payload: dict) -> tuple[bool, str]:
    r = client.post(url, json=payload, headers={
        "Accept": "*/*",
        "Content-Type": "application/json",
    })
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    if "json" not in r.headers.get("content-type", "").lower():
        return False, f"content-type {r.headers.get('content-type')!r} (¿WAF o captcha?)"
    body = r.json()
    # HTTP 200 con `errors` y sin `data` es la firma del sha256Hash rotado.
    if body.get("errors"):
        msgs = "; ".join(str(e.get("message"))[:80] for e in body["errors"][:2])
        return False, f"200 con errors (¿persisted query rotada?): {msgs}"
    products = (body.get("data") or {}).get("productSearch", {}).get("products", [])
    if not products:
        return False, "200, sin errors, pero cero productos"
    return True, f"{len(products)} productos, p.ej. {products[0].get('productName')!r}"


def probe_dia(client: httpx.Client) -> tuple[bool, str]:
    return _probe_vtex(
        client,
        "https://diaonline.supermercadosdia.com.ar/_v/segment/graphql/v1"
        "?workspace=master&maxAge=short&appsEtag=remove&domain=store&locale=es-AR",
        _vtex_payload("almacen/aceites-y-aderezos", product_origin_vtex=True,
                      skus_filter="FIRST_AVAILABLE"),
    )


def probe_carrefour(client: httpx.Client) -> tuple[bool, str]:
    return _probe_vtex(
        client,
        "https://www.carrefour.com.ar/_v/segment/graphql/v1?workspace=master",
        _vtex_payload("almacen/aceites-y-vinagres", product_origin_vtex=False,
                      skus_filter="ALL_AVAILABLE"),
    )


PROBES = [
    ("coto-catalogo", "BFF de catálogo (el que barre el scraper)", probe_coto_catalogo),
    ("coto-cobertura", "actor ATG getCobertura (src/coto_logistics.py)", probe_coto_cobertura),
    ("dia-graphql", "VTEX productSearchV3", probe_dia),
    ("carrefour-graphql", "VTEX productSearchV3", probe_carrefour),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true",
                        help="salida JSON, para diffear la corrida local contra la de AWS")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    resultados = []
    # http2=True igual que los scrapers: si un WAF discrimina por ALPN, que
    # discrimine acá también y no recién en producción.
    with httpx.Client(headers={"User-Agent": UA, "Accept-Language": "es-AR,es;q=0.9"},
                      http2=True, timeout=args.timeout, follow_redirects=True) as client:
        for nombre, que_es, fn in PROBES:
            t0 = time.perf_counter()
            try:
                ok, detalle = fn(client)
            except Exception as exc:
                ok, detalle = False, f"{type(exc).__name__}: {exc}"
            ms = round((time.perf_counter() - t0) * 1000)
            resultados.append({"probe": nombre, "que_es": que_es,
                               "ok": ok, "ms": ms, "detalle": detalle})

    if args.json:
        print(json.dumps(resultados, ensure_ascii=False, indent=2))
    else:
        ancho = max(len(r["probe"]) for r in resultados)
        for r in resultados:
            print(f"{'OK  ' if r['ok'] else 'FALLA'} {r['probe']:<{ancho}}  "
                  f"{r['ms']:>6} ms  {r['detalle']}")
        print()
        fallaron = [r["probe"] for r in resultados if not r["ok"]]
        if fallaron:
            print(f"VEREDICTO: falla {', '.join(fallaron)}.")
            print("Si esto pasa en AWS pero NO en tu máquina, el bloqueo es por IP de")
            print("datacenter y hay que replantear antes de crear nada más.")
        else:
            print("VEREDICTO: las cuatro contestan. Comparar los ms contra la corrida")
            print("local: el barrido son miles de requests secuenciales, así que +200 ms")
            print("por request se nota en la ventana del job (timeout-minutes).")

    return 0 if all(r["ok"] for r in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
