"""Cálculo de la fecha límite de alegaciones.

Los anuncios expresan el plazo casi siempre en días hábiles contados desde el día siguiente
a la publicación. Los sábados no son hábiles en el procedimiento administrativo (Ley 39/2015).
Solo se descuentan los festivos nacionales: los autonómicos y locales varían, por eso la fecha
se presenta siempre como estimación.
"""

from __future__ import annotations

from datetime import date, timedelta

PLAZO_POR_DEFECTO = 30  # días hábiles, el plazo más habitual en información pública

FESTIVOS_NACIONALES: dict[int, list[str]] = {
    2026: ["01-01", "01-06", "04-03", "05-01", "08-15", "10-12", "11-01", "12-06", "12-08", "12-25"],
    2027: ["01-01", "01-06", "03-26", "05-01", "08-15", "10-12", "11-01", "12-06", "12-08", "12-25"],
    2028: ["01-01", "01-06", "04-14", "05-01", "08-15", "10-12", "11-01", "12-06", "12-08", "12-25"],
}


def _es_habil(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    return f"{d:%m-%d}" not in FESTIVOS_NACIONALES.get(d.year, [])


def fecha_limite(fecha_publicacion: date, plazo_dias: int | None) -> tuple[date, bool]:
    """Devuelve (fecha_limite, estimado). `estimado` es True si no se detectó el plazo en el anuncio."""
    estimado = plazo_dias is None
    n = plazo_dias or PLAZO_POR_DEFECTO
    d = fecha_publicacion
    restantes = n
    while restantes > 0:
        d += timedelta(days=1)
        if _es_habil(d):
            restantes -= 1
    return d, estimado


def dias_restantes(limite: date, hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    return (limite - hoy).days
