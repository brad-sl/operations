#!/usr/bin/env python3
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
j = json.loads((ROOT / "reports/FEE_DRAG_AUDIT_LATEST.json").read_text())
print("30d order_types", j["fee_drag"]["30d"]["order_types"])
print("90d order_types", j["fee_drag"]["90d"]["order_types"])
print("30d reasons", j["fee_drag"]["30d"]["top_reasons"])
print("90d by_month", j["fee_drag"]["90d"]["by_month"])
print(
    "fee median 30",
    j["fee_drag"]["30d"]["fee_pct_median"],
    "p75",
    j["fee_drag"]["30d"]["fee_pct_p75"],
)
print("nav", j.get("nav_usd_snapshot"))
labs = json.loads((ROOT / "reports/ENTRY_PROCESS_VS_HEAT_LABELS_90D.json").read_text())
print("heat", [x for x in labs if x["label"] == "heat_reaction"][:5])
print(
    "elevated",
    [x for x in labs if x["label"] == "process_in_elevated_tape"][:5],
)
rs = [x["r24_pct"] for x in labs if x.get("r24_pct") is not None]
print(
    "n_r24",
    len(rs),
    "median",
    sorted(rs)[len(rs) // 2] if rs else None,
    "max",
    max(rs) if rs else None,
    "min",
    min(rs) if rs else None,
)
print("sources", Counter((x.get("signal_source") or "")[:50] for x in labs).most_common(15))
con = sqlite3.connect(str(ROOT / "data/phase6.db"))
print("trade_sides", con.execute("select side, count(*) from trades group by side").fetchall())
print(
    "sample",
    con.execute(
        "select ts, pair, side, pnl, status from trades order by ts desc limit 8"
    ).fetchall(),
)
# try match outcomes with case variants
n_sell = con.execute(
    "select count(*) from trades where side in ('SELL','sell','Sell') and pnl is not null"
).fetchone()[0]
print("sells_with_pnl", n_sell)
con.close()
fees30 = j["fee_drag"]["30d"]["total_fees_usd"]
nav = j.get("nav_usd_snapshot") or 2500
print("30d_fees_pct_nav", round(fees30 / float(nav) * 100, 3) if nav else None)
