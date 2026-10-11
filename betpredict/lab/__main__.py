"""python -m betpredict.lab <fd.db> [out.json] — rulează laboratorul și scrie data/lab/results.json."""
import json
import sqlite3
import sys

from betpredict.lab.engine import run_lab
from betpredict.lab.superbilete import RESULTS

db = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else str(RESULTS)
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
res = run_lab([dict(r) for r in c.execute("SELECT * FROM fd_match ORDER BY day")])
with open(out, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print({k: res[k] for k in ("matches", "configs_tested", "test_positive", "both_positive", "both_positive_expected_by_chance")})
