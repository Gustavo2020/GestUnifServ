import csv
import unicodedata
from pathlib import Path
from typing import Dict, Tuple

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CMP_PATH = DATA_DIR / "activos_riesgos_comparado.csv"
MANUAL_PATH = DATA_DIR / "activos_no_coincidencia.csv"
RIESGOS_PATH = DATA_DIR / "riesgos.csv"


def slug(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch == " ":
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def detect_delim(line: str) -> str:
    return ";" if line.count(";") > line.count(",") else ","


def load_canon() -> Dict[Tuple[str, str], Tuple[str, str, str]]:
    mapping: Dict[Tuple[str, str], Tuple[str, str, str]] = {}
    with RIESGOS_PATH.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        cols = {k.lower(): k for k in (r.fieldnames or [])}
        c_dep = cols.get("departamento")
        c_mun = cols.get("municipio") or cols.get("ciudad")
        c_pais = cols.get("país") or cols.get("pais")
        if not (c_dep and c_mun):
            raise RuntimeError("riesgos.csv sin columnas Departamento/Municipio")
        for row in r:
            d = (row.get(c_dep) or "").strip()
            m = (row.get(c_mun) or "").strip()
            p = (row.get(c_pais) or "").strip() if c_pais else ""
            if not d or not m:
                continue
            mapping[(slug(d), slug(m))] = (d, m, p)
    return mapping


KEY_COLS = [
    "name",
    "label",
    "filial",
    "regional_distrito",
    "tipo_activo",
    "condicion_activo",
    "propiedad",
    "activos_proyectos_sigeb",
]


def build_row_key(row: dict, cols_map: dict) -> Tuple[str, ...]:
    key = []
    for k in KEY_COLS:
        col = cols_map.get(k)
        key.append((row.get(col) or "").strip())
    return tuple(key)


def apply_manual_and_recompare() -> Tuple[int, int, int, int]:
    canon = load_canon()

    # Load comparado
    with CMP_PATH.open("r", encoding="utf-8", errors="replace") as f:
        head = f.readline()
        delim = detect_delim(head)
    with CMP_PATH.open("r", encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f, delimiter=delim)
        cmp_fields = r.fieldnames or []
        cmp_rows = list(r)
    cmp_cols = {k.lower(): k for k in cmp_fields}
    c_dep_cmp = cmp_cols.get("departamento")
    c_mun_cmp = cmp_cols.get("municipio") or cmp_cols.get("ciudad")
    c_pais_cmp = cmp_cols.get("país") or cmp_cols.get("pais") or "País"
    c_cmp_cmp = cmp_cols.get("comparacion") or "comparacion"

    # Build index for comparado
    cmp_key_map: Dict[Tuple[str, ...], int] = {}
    for idx, row in enumerate(cmp_rows):
        cmp_key_map[build_row_key(row, cmp_cols)] = idx

    # Load manual corrections
    with MANUAL_PATH.open("r", encoding="utf-8", errors="replace") as f:
        m_head = f.readline()
        m_delim = detect_delim(m_head)
    with MANUAL_PATH.open("r", encoding="utf-8", errors="replace", newline="") as f:
        mr = csv.DictReader(f, delimiter=m_delim)
        m_cols = {k.lower(): k for k in (mr.fieldnames or [])}
        m_dep = m_cols.get("departamento")
        m_mun = m_cols.get("municipio") or m_cols.get("ciudad")
        # Iterate manual rows, update comparado
        updates = 0
        for mrow in mr:
            key = build_row_key(mrow, m_cols)
            if key in cmp_key_map:
                i = cmp_key_map[key]
                if m_dep:
                    cmp_rows[i][c_dep_cmp] = (mrow.get(m_dep) or "").strip()
                if m_mun:
                    cmp_rows[i][c_mun_cmp] = (mrow.get(m_mun) or "").strip()
                updates += 1

    # Recompare exact against canon and set País/comparacion
    total = 0
    sc = 0
    ch = 0
    nc = 0
    for row in cmp_rows:
        total += 1
        d = (row.get(c_dep_cmp) or "").strip()
        m = (row.get(c_mun_cmp) or "").strip()
        key = (slug(d), slug(m))
        if key in canon:
            d_can, m_can, p_can = canon[key]
            row[c_pais_cmp] = p_can
            if d == d_can and m == m_can:
                row[c_cmp_cmp] = "sin cambio"
                sc += 1
            else:
                row[c_dep_cmp] = d_can
                row[c_mun_cmp] = m_can
                row[c_cmp_cmp] = "cambio"
                ch += 1
        else:
            row[c_cmp_cmp] = "no coincidencia"
            # keep País as-is
            nc += 1

    # Write back comparado
    with CMP_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cmp_fields, delimiter=delim)
        w.writeheader()
        for row in cmp_rows:
            w.writerow(row)

    return total, sc, ch, nc


if __name__ == "__main__":
    t, sc, ch, nc = apply_manual_and_recompare()
    print(f"procesados: {t} | sin_cambio: {sc} | cambio: {ch} | no_coincidencia: {nc}")

