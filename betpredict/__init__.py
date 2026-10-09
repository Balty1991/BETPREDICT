"""BETPREDICT 3.0 — pachet unic (Etapa 0: fundație).

Module:
  ingest/   client BSD unic (rate-limit, retry, buget de cereri, cache pe disc)
  store/    SQLite (sursa de adevăr) + export Parquet opțional
  pipeline/ comenzi de colectare (daily-build)
  publish/  JSON-uri mici pentru site + asamblarea site-ului pentru gh-pages

Rulare: ``python -m betpredict --help``.
"""

__version__ = "3.0.0a0"
