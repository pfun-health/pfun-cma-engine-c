#!/usr/bin/env python3
"""Download CGM sample data and convert it to the `time,value` CSV accepted by
`pfun_cgm_read_csv` (ISO8601 local time with UTC offset, glucose value).

Sources:
  pfun-sample  valid_data.csv from pfun-health/pfun-data (used by pfun-cma-model);
               columns ts_utc, ts_local, sg, user_id. Select one user with --user-id.
  ohio-t1dm    OhioT1DM XML (<glucose_level><event ts="DD-MM-YYYY HH:MM:SS" value=.../>).
               The dataset is distributed under a data use agreement, so there is no
               public URL: pass --url (a mirror you are licensed to use) or --path.
  url          Any CSV at --url having a time column (time/ts_local/ts_utc) and a
               value column (value/sg/glucose); copied through with the same conversion.
"""
import argparse
import csv
import hashlib
import io
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

PFUN_SAMPLE_URL = (
    "https://github.com/pfun-health/pfun-data/releases/download/0.1.4/valid_data.csv"
)
MAX_BYTES = 512 * 1024 * 1024


def fetch(url):
    if not url.startswith("https://"):
        sys.exit("error: only https:// URLs are allowed")
    req = urllib.request.Request(url, headers={"User-Agent": "pfun-cma-engine-c"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        sys.exit("error: download too large")
    return data


def fmt_offset(td):
    s = int(td.total_seconds())
    sign = "-" if s < 0 else "+"
    s = abs(s)
    return f"{sign}{s // 3600:02d}:{s % 3600 // 60:02d}"


def parse_dt(s):
    return datetime.fromisoformat(s.strip().replace("Z", "+00:00"))


def rows_from_csv(text, user_id=None):
    rd = csv.DictReader(io.StringIO(text))
    cols = rd.fieldnames or []
    vcol = next((c for c in ("value", "sg", "glucose") if c in cols), None)
    if vcol is None:
        sys.exit(f"error: no value column (value/sg/glucose) in {cols}")
    for row in rd:
        if user_id is not None and row.get("user_id") != str(user_id):
            continue
        if row.get("is_sg") not in (None, "", "1", "1.0", "True"):
            continue
        try:
            v = float(row[vcol])
        except (TypeError, ValueError):
            continue
        if "ts_local" in row and "ts_utc" in row and row["ts_local"] and row["ts_utc"]:
            loc, utc = parse_dt(row["ts_local"]), parse_dt(row["ts_utc"])
            off = loc.replace(tzinfo=None) - utc.replace(tzinfo=None)
            ts = loc.replace(tzinfo=None).isoformat() + fmt_offset(off)
        else:
            tcol = next((c for c in ("time", "ts_local", "ts_utc") if row.get(c)), None)
            if tcol is None:
                continue
            ts = row[tcol]
        yield ts, v


def rows_from_ohio(data):
    root = ET.fromstring(data)  # data is trusted-format XML from the licensed set
    gl = root.find("glucose_level")
    if gl is None:
        sys.exit("error: no <glucose_level> element in XML")
    for ev in gl.findall("event"):
        try:
            t = datetime.strptime(ev.get("ts"), "%d-%m-%Y %H:%M:%S")
            v = float(ev.get("value"))
        except (TypeError, ValueError):
            continue
        yield t.isoformat(), v


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="pfun-sample", choices=["pfun-sample", "ohio-t1dm", "url"])
    ap.add_argument("--url", help="https URL (required for 'url'; optional override otherwise)")
    ap.add_argument("--path", help="local file instead of downloading (ohio-t1dm/url)")
    ap.add_argument("--user-id", help="select a single user_id (pfun-sample)")
    ap.add_argument("--out", default="data/cgm/cgm.csv")
    ap.add_argument("--sha256", help="verify the raw download against this checksum")
    a = ap.parse_args()

    if a.path:
        data = Path(a.path).read_bytes()
    else:
        url = a.url or (PFUN_SAMPLE_URL if a.source == "pfun-sample" else None)
        if not url:
            sys.exit(f"error: source '{a.source}' needs --url or --path")
        data = fetch(url)
    digest = hashlib.sha256(data).hexdigest()
    if a.sha256 and a.sha256.lower() != digest:
        sys.exit(f"error: sha256 mismatch (got {digest})")

    if a.source == "ohio-t1dm":
        rows = list(rows_from_ohio(data))
    else:
        text = data.decode("utf-8-sig")
        user = a.user_id
        if a.source == "pfun-sample" and user is None:
            first = next(csv.DictReader(io.StringIO(text)), {})
            user = first.get("user_id")
        rows = list(rows_from_csv(text, user))
    if len(rows) < 2:
        sys.exit("error: no usable glucose rows found")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "value"])
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out} (raw sha256 {digest})")


if __name__ == "__main__":
    main()
