"""
Genera src/scrapers/bank_promos.json con las promociones bancarias de las tres
cadenas.

Vive acá y no en src/promotions/ por el mismo criterio que get_coto_categories.py
y get_carrefour_categories.py: los runners que vuelcan un artefacto JSON al repo
están todos juntos, al lado del archivo que producen.

Uso:
    python -m src.scrapers.get_bank_promos                 # las tres cadenas
    python -m src.scrapers.get_bank_promos --store coto
    python -m src.scrapers.get_bank_promos --dry-run       # muestra, no escribe
"""
import argparse
import json
import logging
import os
from datetime import datetime, timezone

from src.promotions import SCRAPERS, DiscountScrapeError

logger = logging.getLogger("get_bank_promos")

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "bank_promos.json")


def load_existing(path: str) -> dict:
    """
    Lee el archivo anterior, o devuelve un esqueleto vacío.

    Hace falta para poder conservar el bloque de una tienda que falló en esta
    corrida (ver run()); un archivo ausente o corrupto no es un error, es
    simplemente "no hay nada previo que conservar".
    """
    try:
        with open(path, encoding="utf-8") as archivo:
            data = json.load(archivo)
        if isinstance(data, dict) and isinstance(data.get("promos"), dict):
            return data
        logger.warning("%s no tiene la forma esperada; se ignora su contenido", path)
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("no se pudo leer %s (%s); se ignora su contenido", path, exc)

    return {"scraped_at": None, "promos": {}}


def run(stores: list[str], path: str = OUTPUT_PATH, dry_run: bool = False) -> dict:
    """
    Corre los scrapers pedidos y devuelve el documento resultante.

    Una tienda que falla no aborta a las demás, y su bloque anterior se conserva
    en vez de pisarse con []. El criterio es el mismo que el del pruning de
    run_scrapers.py: un dato viejo molesta, pero un bloque vaciado hace que el
    optimizador deje de aplicar descuentos que existen, y en silencio.
    """
    documento = load_existing(path)
    promos = dict(documento.get("promos") or {})
    fallidas = []

    for nombre in stores:
        scraper = SCRAPERS[nombre]()
        try:
            descuentos = scraper.scrape()
        except DiscountScrapeError as exc:
            fallidas.append(nombre)
            anteriores = len(promos.get(scraper.STORE_ID, []))
            logger.error("%s FALLÓ: %s", nombre, exc)
            logger.error("   se conservan los %d descuentos de la corrida anterior", anteriores)
            continue
        except Exception as exc:  # noqa: BLE001 - una tienda rota no voltea al resto
            fallidas.append(nombre)
            logger.exception("%s FALLÓ con un error inesperado: %s", nombre, exc)
            continue

        promos[scraper.STORE_ID] = [d.to_json_dict() for d in descuentos]
        logger.info(
            "%s OK: %d descuentos | descartes: %s",
            nombre, len(descuentos), dict(scraper.discards) or "ninguno",
        )

    documento = {"scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "promos": promos}

    if dry_run:
        logger.info("--dry-run: no se escribe nada")
    else:
        _write_atomic(path, documento)
        logger.info("escrito %s", path)

    total = sum(len(v) for v in promos.values())
    logger.info("total en el archivo: %d descuentos de %d tiendas", total, len(promos))
    if fallidas:
        logger.warning("tiendas con fallas: %s", ", ".join(fallidas))

    return documento


def _write_atomic(path: str, documento: dict) -> None:
    """
    Escribe vía archivo temporal + replace.

    Si el proceso muere a mitad de la escritura, el archivo viejo queda intacto:
    un bank_promos.json truncado haría que load_bank_promos() caiga al fallback y
    la app perdiera todos los descuentos scrapeados sin decir por qué.
    """
    temporal = f"{path}.tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(documento, archivo, ensure_ascii=False, indent=1)
    os.replace(temporal, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", choices=[*SCRAPERS, "all"], default="all")
    parser.add_argument("--out", default=OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="corre los scrapers y muestra el resultado sin escribir")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # playwright y httpx loguean cada request en INFO y tapan el resumen.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    stores = list(SCRAPERS) if args.store == "all" else [args.store]
    documento = run(stores, path=args.out, dry_run=args.dry_run)

    for store_id, descuentos in sorted(documento["promos"].items()):
        print(f"\n{store_id} ({len(descuentos)}):")
        for descuento in descuentos:
            dias = ",".join(d[:3] for d in descuento["dias_validos"])
            print(f"   {descuento['entidad']:<16}{descuento['porcentaje_descuento']:>5.0f}%  "
                  f"tope={str(descuento['tope_reintegro']):>8}  {dias}")


if __name__ == "__main__":
    main()
