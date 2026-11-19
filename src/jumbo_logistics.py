# src/jumbo_logistics.py
"""
Consulta en línea de la logística de Jumbo: si entregan en una coordenada dada
y cuánto cobran por el envío. Es la plataforma de Vea (Cencosud), así que la
lectura es la de src/vea_logistics.py, con su dominio y su canal.

Relevado contra el sitio en vivo (nov 2026; públicos, sin cookie ni login):

- El canal de venta es el **32**: con `sc=1` `regions` contesta un error, y con
  `sc=34` devuelve las sucursales de Vea.
- `regions` **no filtra por coordenada** (19-20 sucursales en CABA, Córdoba y
  Ushuaia), como en Vea.
- El envío a domicilio es el SLA "Envío a Domicilio", con `price` 0 y la franja
  en 399900 centavos: **$3.999** en CABA, San Isidro, Quilmes y Morón. Córdoba
  y Ushuaia sólo tienen retiro.

El SKU 315800 (yerba Playadito 1 kg) es de stock general. Si una sucursal que
envía no lo tuviera, Jumbo quedaría excluida de más, y no de menos.
"""
from src.vea_logistics import cencosud_lookup

_lookup = cencosud_lookup("Jumbo", "www.jumbo.com.ar", 32, "315800")
check_coverage = _lookup.check_coverage
resolve_jumbo_logistics = _lookup.resolve
reset_cache = _lookup.reset_cache
