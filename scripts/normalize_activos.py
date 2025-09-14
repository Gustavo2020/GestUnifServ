import csv
import sys
import unicodedata
from pathlib import Path
from difflib import get_close_matches
from typing import Dict, Tuple, List, Optional

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RIESGOS_CSV = DATA_DIR / "riesgos.csv"
ACTIVOS_CSV = DATA_DIR / "activos_riesgos.csv"
OUTPUT_CSV = DATA_DIR / "activos_riesgos_revisado.csv"


def slug(s: str) -> str:
    if s is None:
        return ""
    s = s.strip()
    s = (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    out = []
    for ch in s:
        out.append(ch if ("a" <= ch <= "z" or ch == " ") else " ")
    s2 = "".join(out)
    return " ".join(s2.split())


def load_canonical() -> Tuple[
    Dict[Tuple[str, str], Tuple[str, str]],
    Dict[str, List[str]],
    Dict[str, str],
    Dict[str, List[Tuple[str, str]]],
]:
    """Load canonical (Departamento, Municipio) from riesgos.csv.
    Returns:
      - mapping from (slug(depto), slug(muni)) -> (Departamento, Municipio)
      - index of depto_slug -> list of muni canonical names (for fuzzy)
    """
    mapping: Dict[Tuple[str, str], Tuple[str, str]] = {}
    muni_by_depto: Dict[str, List[str]] = {}
    depto_slug_to_name: Dict[str, str] = {}
    muni_global_index: Dict[str, List[Tuple[str, str]]] = {}
    with RIESGOS_CSV.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        # tolerant header: accept both Municipio/municipio
        cols = {k.lower(): k for k in (r.fieldnames or [])}
        c_depto = cols.get("departamento")
        c_muni = cols.get("municipio") or cols.get("ciudad")
        if not c_depto or not c_muni:
            raise RuntimeError("riesgos.csv missing Departamento/Municipio columns")
        for row in r:
            depto = (row.get(c_depto) or "").strip()
            muni = (row.get(c_muni) or "").strip()
            if not depto or not muni:
                continue
            key = (slug(depto), slug(muni))
            mapping[key] = (depto, muni)
            dslug = slug(depto)
            depto_slug_to_name[dslug] = depto
            muni_by_depto.setdefault(dslug, []).append(muni)
            muni_global_index.setdefault(slug(muni), []).append((depto, muni))
    return mapping, muni_by_depto, depto_slug_to_name, muni_global_index


def detect_delimiter(header_line: str) -> str:
    return ";" if header_line.count(";") > header_line.count(",") else ","


def find_columns(fieldnames: List[str]) -> Tuple[str, str]:
    cols = {k.lower(): k for k in (fieldnames or [])}
    c_depto = cols.get("departamento")
    c_muni = cols.get("municipio") or cols.get("ciudad")
    if not c_depto or not c_muni:
        raise RuntimeError("activos_riesgos.csv missing Departamento/Municipio columns")
    return c_depto, c_muni


def _baseline_input_path() -> Path:
    """Preferir el CSV revisado si existe para mantener cambios previos."""
    return OUTPUT_CSV if OUTPUT_CSV.exists() else ACTIVOS_CSV


def plan_replacements(batch_size: int = 50, offset: int = 0):
    canon, muni_by_depto, depto_slug_to_name, muni_global_index = load_canonical()

    # Peek header to detect delimiter
    with ACTIVOS_CSV.open("r", encoding="utf-8", errors="replace") as f:
        first = f.readline()
        delim = detect_delimiter(first)

    replacements: List[Tuple[int, Tuple[str, str], Tuple[str, str], str]] = []
    missing: List[Tuple[int, str, str]] = []

    with ACTIVOS_CSV.open("r", encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f, delimiter=delim)
        c_depto, c_muni = find_columns(r.fieldnames or [])
        for idx, row in enumerate(r, start=2):  # start=2 to account header line
            depto = (row.get(c_depto) or "").strip()
            muni = (row.get(c_muni) or "").strip()
            if not depto and not muni:
                continue
            key = (slug(depto), slug(muni))
            reason = ""
            if key in canon:
                cdep, cmun = canon[key]
                if cdep != depto or cmun != muni:
                    reason = "normalize"
                    replacements.append((idx, (depto, muni), (cdep, cmun), reason))
                continue
            # Try fuzzy by depto -> muni
            dslug = slug(depto)
            candidates = muni_by_depto.get(dslug) or []
            # If depart. not found, fuzzy-map the department name
            if not candidates and depto_slug_to_name:
                depts = list(depto_slug_to_name.keys())
                dmatch = get_close_matches(dslug, depts, n=1, cutoff=0.8)
                if dmatch:
                    dslug = dmatch[0]
                    candidates = muni_by_depto.get(dslug) or []
            best: Optional[str] = None
            if candidates:
                matches = get_close_matches(muni, candidates, n=1, cutoff=0.8)
                if not matches:
                    # try slugged comparison space-joined
                    matches = get_close_matches(slug(muni), [slug(x) for x in candidates], n=1, cutoff=0.85)
                    if matches:
                        # map slug back to original candidate with same slug
                        mslug = matches[0]
                        for c in candidates:
                            if slug(c) == mslug:
                                best = c
                                break
                else:
                    best = matches[0]
            if best:
                key2 = (dslug, slug(best))
                cdep, cmun = canon.get(key2, (depto, muni))
                if (cdep, cmun) != (depto, muni):
                    reason = "fuzzy"
                    replacements.append((idx, (depto, muni), (cdep, cmun), reason))
            if not best:
                # As a last resort: try global municipality index ignoring depto
                all_munis = list(muni_global_index.keys())
                gm = get_close_matches(slug(muni), all_munis, n=1, cutoff=0.9)
                if gm:
                    pairs = muni_global_index.get(gm[0]) or []
                    if len(pairs) == 1:
                        cdep, cmun = pairs[0]
                        if (cdep, cmun) != (depto, muni):
                            reason = "global"
                            replacements.append((idx, (depto, muni), (cdep, cmun), reason))
                        else:
                            # no change needed
                            pass
                        continue
            # If still no candidate, mark as missing
            if not best and (idx, depto, muni) not in missing:
                missing.append((idx, depto, muni))

    total = len(replacements)
    print(f"Total reemplazos propuestos: {total}")
    if missing:
        print(f"No mapeados (muestreo hasta 10): {len(missing)}")
        for i, (idx, d, m) in enumerate(missing[:10], start=1):
            print(f"  ln {idx}: {d} | {m}")
    start = max(0, offset)
    end = min(total, start + batch_size)
    print(f"\nReemplazos propuestos del {start+1} al {end}:")
    for i, (ln, (od, om), (nd, nm), reason) in enumerate(replacements[start:end], start=start+1):
        print(f"{i:>3}. ln {ln}: ({od} | {om}) -> ({nd} | {nm}) [{reason}]")

    return replacements, delim


def apply_replacements(replacements: List[Tuple[int, Tuple[str, str], Tuple[str, str], str]], delim: str, up_to: int):
    """Apply first `up_to` replacements into OUTPUT_CSV, preserving other columns."""
    idx_set = set(x[0] for x in replacements[:up_to])
    repl_map = {x[0]: (x[2][0], x[2][1]) for x in replacements[:up_to]}

    src_path = _baseline_input_path()
    # Detect delimiter from first non-empty line in baseline
    with src_path.open("r", encoding="utf-8", errors="replace") as _f:
        first_nonempty = ""
        for line in _f:
            if line.strip():
                first_nonempty = line
                break
    delim2 = detect_delimiter(first_nonempty) if first_nonempty else delim

    with src_path.open("r", encoding="utf-8", errors="replace", newline="") as f_in:
        all_lines = f_in.readlines()
    start = 0
    while start < len(all_lines) and not all_lines[start].strip():
        start += 1
    it = all_lines[start:]
    r = csv.DictReader(it, delimiter=delim2)
    fieldnames = r.fieldnames or []
    if not fieldnames:
        raise RuntimeError(f"Cabecera no válida en {src_path}; no se puede aplicar reemplazos")
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f_out:
        w = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=delim)
        w.writeheader()
        c_depto, c_muni = find_columns(fieldnames)
        line_no = 2
        for row in r:
            if line_no in idx_set:
                nd, nm = repl_map[line_no]
                row[c_depto] = nd
                row[c_muni] = nm
            w.writerow(row)
            line_no += 1
    print(f"Escrito {OUTPUT_CSV} con {len(idx_set)} reemplazos aplicados (hasta índice {up_to}).")


def report_missing(ignore_lines: Optional[List[int]] = None, out_path: Optional[Path] = None):
    canon, muni_by_depto, depto_slug_to_name, muni_global_index = load_canonical()
    src_path = _baseline_input_path()
    with src_path.open("r", encoding="utf-8", errors="replace") as f:
        first = f.readline()
        delim = detect_delimiter(first)
    missing: List[Tuple[int, str, str]] = []
    with src_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f, delimiter=delim)
        c_depto, c_muni = find_columns(r.fieldnames or [])
        for idx, row in enumerate(r, start=2):
            depto = (row.get(c_depto) or "").strip()
            muni = (row.get(c_muni) or "").strip()
            if not depto and not muni:
                continue
            key = (slug(depto), slug(muni))
            if key in canon:
                continue
            if ignore_lines and idx in ignore_lines:
                continue
            missing.append((idx, depto, muni))

    lines = [f"No mapeados: {len(missing)}"] + [f"  ln {ln}: {d} | {m}" for ln, d, m in missing]
    text = "\n".join(lines)
    if out_path:
        out_path.write_text(text, encoding="utf-8")
        print(f"Escrito reporte de no mapeados en {out_path}")
    else:
        print(text)


def load_extra_canonical_csv(path: Path) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    if not path.exists():
        return pairs
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f)
        cols = {k.lower(): k for k in (r.fieldnames or [])}
        c_depto = cols.get("departamento")
        c_muni = cols.get("municipio") or cols.get("ciudad")
        if not c_depto or not c_muni:
            return pairs
        for row in r:
            d = (row.get(c_depto) or "").strip()
            m = (row.get(c_muni) or "").strip()
            if d and m:
                pairs.append((d, m))
    return pairs


def propose_and_apply_missing(extra_canonical: Optional[Path] = None) -> int:
    """
    Intenta corregir filas no mapeadas comparando con la base canónica (riesgos.csv)
    y opcionalmente con una base adicional (por ejemplo, Guatemala) en CSV con
    columnas Departamento,Municipio.
    Devuelve el número de reemplazos aplicados.
    """
    canon, muni_by_depto, depto_slug_to_name, muni_global_index = load_canonical()
    if extra_canonical:
        extras = load_extra_canonical_csv(extra_canonical)
        for d, m in extras:
            key = (slug(d), slug(m))
            canon[key] = (d, m)
            dslug = slug(d)
            muni_by_depto.setdefault(dslug, []).append(m)
            depto_slug_to_name[dslug] = d
            muni_global_index.setdefault(slug(m), []).append((d, m))

    # Detect delimiter and headers from baseline
    src_path = _baseline_input_path()
    with src_path.open("r", encoding="utf-8", errors="replace") as f:
        first = f.readline()
        delim = detect_delimiter(first)

    # Some known aliases to normalize common variants
    alias_pairs: Dict[Tuple[str, str], Tuple[str, str]] = {
        (slug("Bolívar"), slug("Cartagena")): ("Bolívar", "Cartagena de Indias"),
        (slug("Distrito Capital"), slug("Bogotá D.C.")): ("Distrito Capital", "Bogotá"),
        (slug("Distrito Capital"), slug("Bogotá  D.C.")): ("Distrito Capital", "Bogotá"),
        (slug("Bolívar"), slug("Santa Rosa de Lima Norte")): ("Bolívar", "Santa Rosa"),
    }

    # Collect replacements only for missing rows
    replacements: List[Tuple[int, Tuple[str, str], Tuple[str, str], str]] = []
    with src_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f, delimiter=delim)
        c_depto, c_muni = find_columns(r.fieldnames or [])
        for idx, row in enumerate(r, start=2):
            depto = (row.get(c_depto) or "").strip()
            muni = (row.get(c_muni) or "").strip()
            if not depto and not muni:
                continue
            key = (slug(depto), slug(muni))
            if key in canon:
                continue

            # Try direct alias first
            alias_key = (slug(depto), slug(muni))
            if alias_key in alias_pairs:
                nd, nm = alias_pairs[alias_key]
                replacements.append((idx, (row.get(c_depto,""), row.get(c_muni,"")), (nd, nm), "alias"))
                continue

            # Try depto-local candidates
            dslug = slug(depto)
            candidates = muni_by_depto.get(dslug) or []
            best: Optional[str] = None
            if candidates:
                m = get_close_matches(muni, candidates, n=1, cutoff=0.8)
                if m:
                    best = m[0]
                else:
                    m2 = get_close_matches(slug(muni), [slug(x) for x in candidates], n=1, cutoff=0.85)
                    if m2:
                        mslug = m2[0]
                        for c in candidates:
                            if slug(c) == mslug:
                                best = c
                                break
            # Fuzzy depto name if no candidates
            if not best and depto_slug_to_name:
                depts = list(depto_slug_to_name.keys())
                dmatch = get_close_matches(dslug, depts, n=1, cutoff=0.8)
                if dmatch:
                    dslug2 = dmatch[0]
                    candidates = muni_by_depto.get(dslug2) or []
                    if candidates:
                        m = get_close_matches(muni, candidates, n=1, cutoff=0.8)
                        if m:
                            best = m[0]
                        else:
                            m2 = get_close_matches(slug(muni), [slug(x) for x in candidates], n=1, cutoff=0.85)
                            if m2:
                                mslug = m2[0]
                                for c in candidates:
                                    if slug(c) == mslug:
                                        best = c
                                        break
                    if best:
                        # align depto name to canonical for that slug
                        depto = depto_slug_to_name[dslug2]

            if not best:
                # last resort: global match by municipio slug
                gm = get_close_matches(slug(muni), list(muni_global_index.keys()), n=1, cutoff=0.9)
                if gm:
                    pairs = muni_global_index.get(gm[0]) or []
                    if len(pairs) == 1:
                        depto, best = pairs[0]

            if best:
                replacements.append((idx, (row.get(c_depto,""), row.get(c_muni,"")), (depto, best), "missing"))

    # Apply replacements to OUTPUT_CSV
    if not replacements:
        return 0

    idx_set = set(x[0] for x in replacements)
    repl_map = {x[0]: (x[2][0], x[2][1]) for x in replacements}

    with src_path.open("r", encoding="utf-8", errors="replace", newline="") as f_in:
        r = csv.DictReader(f_in, delimiter=delim)
        fieldnames = r.fieldnames or []
        c_depto, c_muni = find_columns(fieldnames)
        with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f_out:
            w = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=delim)
            w.writeheader()
            for idx, row in enumerate(r, start=2):
                if idx in idx_set:
                    nd, nm = repl_map[idx]
                    row[c_depto] = nd
                    row[c_muni] = nm
                w.writerow(row)

    return len(replacements)


def normalize_aliases_and_country(extra_canonical: Optional[Path] = None, country_col: str = "País") -> Tuple[int, int, int]:
    """
    Recorre todo el CSV base (revisado si existe) y:
      - Aplica alias solicitados sobre Departamento/Municipio en todas las filas.
      - Añade/actualiza la columna País con valores {Colombia, Guatemala} según match exacto
        contra las bases canónicas (riesgos.csv y extra_canonical si se provee).

    Devuelve: (alias_aplicados, marcados_colombia, marcados_guatemala)
    """
    canon_co, muni_by_depto_co, depto_slug_to_name_co, muni_global_index_co = load_canonical()
    canon_gt: Dict[Tuple[str, str], Tuple[str, str]] = {}
    if extra_canonical:
        for d, m in load_extra_canonical_csv(extra_canonical):
            canon_gt[(slug(d), slug(m))] = (d, m)

    src_path = _baseline_input_path()
    # Detect delimiter
    with src_path.open("r", encoding="utf-8", errors="replace") as f:
        first = f.readline()
        delim = detect_delimiter(first)

    alias_count = 0
    marked_co = 0
    marked_gt = 0

    with src_path.open("r", encoding="utf-8", errors="replace", newline="") as f_in:
        r = csv.DictReader(f_in, delimiter=delim)
        fieldnames = r.fieldnames or []
        c_depto, c_muni = find_columns(fieldnames)
        # Ensure País in header
        out_fields = list(fieldnames)
        if country_col not in out_fields:
            out_fields.append(country_col)

        with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f_out:
            w = csv.DictWriter(f_out, fieldnames=out_fields, delimiter=delim)
            w.writeheader()

            for row in r:
                depto = (row.get(c_depto) or "").strip()
                muni = (row.get(c_muni) or "").strip()
                dslug = slug(depto)
                mslug = slug(muni)

                # Alias de normalización solicitados
                changed = False
                # Departamento 'Cesar' -> 'César'
                if dslug == slug("Cesar"):
                    if depto != "César":
                        depto = "César"; row[c_depto] = depto; changed = True
                # Municipio 'Togüí' -> 'Toguí'
                if mslug == slug("Togüí") or mslug == slug("Toguí"):
                    if muni != "Toguí":
                        muni = "Toguí"; row[c_muni] = muni; changed = True
                # Bolívar | Cartagena -> Cartagena de Indias
                if dslug == slug("Bolívar") and mslug == slug("Cartagena"):
                    if muni != "Cartagena de Indias":
                        muni = "Cartagena de Indias"; row[c_muni] = muni; changed = True
                # Bolívar | Santa Rosa de Lima Norte -> Santa Rosa
                if dslug == slug("Bolívar") and mslug == slug("Santa Rosa de Lima Norte"):
                    if muni != "Santa Rosa":
                        muni = "Santa Rosa"; row[c_muni] = muni; changed = True

                if changed:
                    alias_count += 1

                # País según match exacto en canónicos
                key = (slug(depto), slug(muni))
                if key in canon_co:
                    row[country_col] = "Colombia"; marked_co += 1
                elif key in canon_gt:
                    row[country_col] = "Guatemala"; marked_gt += 1
                else:
                    # Si no matchea ninguno, dejamos vacío (o "").
                    row[country_col] = row.get(country_col, "")

                w.writerow(row)

    return alias_count, marked_co, marked_gt


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Normaliza Departamento/Municipio en activos_riesgos.csv según riesgos.csv")
    p.add_argument("--apply", type=int, default=0, help="Aplicar N reemplazos (0 = solo mostrar)")
    p.add_argument("--batch", type=int, default=50, help="Tamaño de lote para mostrar")
    p.add_argument("--offset", type=int, default=0, help="Desplazamiento para paginar (muestra/applica desde este índice)")
    p.add_argument("--report-missing", action="store_true", help="Solo generar reporte de filas no mapeadas")
    p.add_argument("--ignore-lines", type=str, default="", help="Lista de números de línea (1-based) separados por coma a ignorar en el reporte de no mapeados")
    p.add_argument("--apply-missing", action="store_true", help="Aplicar correcciones automáticas a filas no mapeadas")
    p.add_argument("--extra-canonical", type=str, default="", help="Ruta a CSV adicional con columnas Departamento,Municipio (p.ej., Guatemala)")
    p.add_argument("--normalize-country", action="store_true", help="Aplicar alias en todo el archivo y añadir columna País (Colombia/Guatemala)")
    args = p.parse_args()

    if args.report_missing:
        ignore = [int(x) for x in args.ignore_lines.split(',') if x.strip().isdigit()]
        out = DATA_DIR / "activos_no_mapeados.txt"
        report_missing(ignore_lines=ignore, out_path=out)
    else:
        repl, delim = plan_replacements(batch_size=args.batch, offset=args.offset)
        if args.apply > 0:
            total_to_apply = min(args.offset + args.apply, len(repl))
            apply_replacements(repl, delim, total_to_apply)
            print(f"Sugerencia: volver a ejecutar con --offset {total_to_apply} para el siguiente lote.")
        else:
            print("Ejecuta con --apply 50 para aplicar el primer lote")

    if args.apply_missing:
        extra = Path(args.extra_canonical) if args.extra_canonical else None
        applied = propose_and_apply_missing(extra_canonical=extra)
        print(f"Correcciones automáticas aplicadas a no mapeados: {applied}")

    if args.normalize_country:
        extra = Path(args.extra_canonical) if args.extra_canonical else None
        a, co, gt = normalize_aliases_and_country(extra_canonical=extra)
        print(f"Alias aplicados: {a} | País=Colombia: {co} | País=Guatemala: {gt}")
