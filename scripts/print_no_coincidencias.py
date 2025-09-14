import csv
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "activos_riesgos_comparado.csv"


def detect_delim(header: str) -> str:
    return ";" if header.count(";") > header.count(",") else ","


def main() -> int:
    with DATA.open("r", encoding="utf-8", errors="replace") as f:
        head = f.readline()
        delim = detect_delim(head)

    rows = []
    with DATA.open("r", encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f, delimiter=delim)
        cols = {k.lower(): k for k in (r.fieldnames or [])}
        c_dep = cols.get("departamento")
        c_mun = cols.get("municipio") or cols.get("ciudad")
        c_pais = cols.get("país") or cols.get("pais") or "País"
        c_cmp = cols.get("comparacion") or "comparacion"
        c_name = cols.get("name") or list(r.fieldnames or [""])[0]
        c_lbl = cols.get("label")

        for row in r:
            comp = (row.get(c_cmp) or "").strip().lower()
            if comp == "no coincidencia":
                name = (row.get(c_name) or "").strip()
                label = (row.get(c_lbl) or "").strip() if c_lbl else ""
                d = (row.get(c_dep) or "").strip()
                m = (row.get(c_mun) or "").strip()
                p = (row.get(c_pais) or "").strip()
                rows.append((name, label, d, m, p))

    for i, (name, label, d, m, p) in enumerate(rows, start=1):
        ident = name or label
        print(f"{i:02d}. {ident} | {d} | {m} | {p}")
    print(f"total: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

