"""전체 코퍼스의 간지 불일치 항목을 출력한다 (Task 3 Step 5)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nanjung.dates import assign_dates  # noqa: E402
from nanjung.models import MonthRef  # noqa: E402
from nanjung.parse import parse_month_page  # noqa: E402

raw = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
refs = [MonthRef(**r) for r in json.loads((raw / "index.json").read_text(encoding="utf-8"))]
entries = []
for r in refs:
    entries += parse_month_page((raw / f"{r.data_id}.html").read_text(encoding="utf-8"), r)
dated = assign_dates(entries)
bad = [e for e in dated if e.ganji_mismatch]
print(f"entries={len(dated)} mismatch={len(bad)} no_ganji={sum(e.day_ganji is None for e in dated)}")
for e in bad:
    print(e.id, e.day_ganji, e.solar_date, e.original[:20])
dup = len(dated) - len({e.id for e in dated})
print(f"duplicate_ids={dup}")
