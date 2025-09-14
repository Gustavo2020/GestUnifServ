import csv
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ACTIVOS = DATA_DIR / "activos_riesgos.csv"
RIESGOS = DATA_DIR / "riesgos.csv"
# Salida corregida: nombre requerido "activos_riesgos_comparado.csv"
SALIDA = DATA_DIR / "activos_riesgos_comparado.csv"


def slug(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()
    # conservar solo alfanumérico y espacios simples
    out = []
    for ch in s:
        if ch.isalnum() or ch == " ":
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def detectar_delimitador(header_line: str) -> str:
    return ";" if header_line.count(";") > header_line.count(",") else ","


def cargar_canon() -> dict[tuple[str, str], tuple[str, str, str]]:
    mapping: dict[tuple[str, str], tuple[str, str, str]] = {}
    with RIESGOS.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        cols = {k.lower(): k for k in (r.fieldnames or [])}
        c_dep = cols.get("departamento")
        c_mun = cols.get("municipio") or cols.get("ciudad")
        c_pais = cols.get("país") or cols.get("pais")
        if not c_dep or not c_mun:
            raise RuntimeError("riesgos.csv sin columnas Departamento/Municipio")
        for row in r:
            d = (row.get(c_dep) or "").strip()
            m = (row.get(c_mun) or "").strip()
            if not d or not m:
                continue
            pais = (row.get(c_pais) or "").strip() if c_pais else ""
            mapping[(slug(d), slug(m))] = (d, m, pais)
    return mapping


def generar_comparado():
    canon = cargar_canon()

    # detectar delimitador de activos
    with ACTIVOS.open("r", encoding="utf-8", errors="replace") as f:
        head = f.readline()
        delim = detectar_delimitador(head)

    total = 0
    sin_cambio = 0
    cambio = 0
    no_coinc = 0
    pais_col = "País"

    with ACTIVOS.open("r", encoding="utf-8", errors="replace", newline="") as f_in, \
         SALIDA.open("w", encoding="utf-8", newline="") as f_out:
        r = csv.DictReader(f_in, delimiter=delim)
        fields = list(r.fieldnames or [])
        campo_estado = "comparacion"
        # Añadir columna País al final
        if pais_col not in fields:
            fields.append(pais_col)
        if campo_estado not in fields:
            fields.append(campo_estado)
        w = csv.DictWriter(f_out, fieldnames=fields, delimiter=delim)
        w.writeheader()

        # localizar columnas
        cols = {k.lower(): k for k in (r.fieldnames or [])}
        c_dep = cols.get("departamento")
        c_mun = cols.get("municipio") or cols.get("ciudad")
        if not c_dep or not c_mun:
            raise RuntimeError("activos_riesgos.csv sin columnas Departamento/Municipio")

        for row in r:
            total += 1
            d = (row.get(c_dep) or "").strip()
            m = (row.get(c_mun) or "").strip()
            key = (slug(d), slug(m))
            if key not in canon:
                row[campo_estado] = "no coincidencia"
                # País vacío si no hay match canónico
                row[pais_col] = row.get(pais_col, "")
                no_coinc += 1
            else:
                d_can, m_can, pais = canon[key]
                row[pais_col] = pais
                if d != d_can or m != m_can:
                    row[campo_estado] = "cambio"
                    cambio += 1
                else:
                    row[campo_estado] = "sin cambio"
                    sin_cambio += 1

            w.writerow(row)

    return total, sin_cambio, cambio, no_coinc


if __name__ == "__main__":
    t, sc, c, nc = generar_comparado()
    print(f"generado: {SALIDA}")
    print(f"registros: {t} | sin_cambio: {sc} | cambio: {c} | no_coincidencia: {nc}")
