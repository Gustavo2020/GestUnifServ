import csv
import unicodedata
from difflib import get_close_matches
from pathlib import Path
from typing import Dict, List, Tuple

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CANON = DATA_DIR / "riesgos.csv"
ACTIVOS_CMP = DATA_DIR / "activos_riesgos_comparado.csv"


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


def load_canonical() -> Tuple[
    Dict[Tuple[str, str], Tuple[str, str, str]],
    Dict[str, str],
    Dict[str, List[str]],
    Dict[str, List[Tuple[str, str, str]]],
    List[Tuple[str, str, str]],
]:
    mapping: Dict[Tuple[str, str], Tuple[str, str, str]] = {}
    dept_slug_to_name: Dict[str, str] = {}
    muni_by_dept: Dict[str, List[str]] = {}
    global_muni: Dict[str, List[Tuple[str, str, str]]] = {}

    with CANON.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        cols = {k.lower(): k for k in (r.fieldnames or [])}
        c_dep = cols.get("departamento")
        c_mun = cols.get("municipio") or cols.get("ciudad")
        c_pais = cols.get("país") or cols.get("pais")
        if not (c_dep and c_mun):
            raise RuntimeError("riesgos.csv: faltan columnas Departamento/Municipio")
        for row in r:
            d = (row.get(c_dep) or "").strip()
            m = (row.get(c_mun) or "").strip()
            p = (row.get(c_pais) or "").strip() if c_pais else ""
            if not d or not m:
                continue
            key = (slug(d), slug(m))
            mapping[key] = (d, m, p)
            dslug = slug(d)
            dept_slug_to_name.setdefault(dslug, d)
            muni_by_dept.setdefault(dslug, []).append(m)
            global_muni.setdefault(slug(m), []).append((d, m, p))
    # flat list for global best-match search
    all_pairs: List[Tuple[str, str, str]] = [(d, m, p) for (d, m, p) in {v for v in mapping.values()}]
    return mapping, dept_slug_to_name, muni_by_dept, global_muni, all_pairs


def _letters(s: str) -> str:
    import unicodedata as U
    s = U.normalize('NFKD', s or '').encode('ascii', 'ignore').decode('ascii').lower()
    return ''.join(ch for ch in s if ch.isalpha())


def apply_alias(depto: str, muni: str) -> Tuple[str, str]:
    dslug = slug(depto)
    mslug = slug(muni)
    mlet = _letters(muni)
    # Cesar -> César
    if dslug == slug("Cesar"):
        depto = "César"
    # Togüí/Toguí -> Toguí
    if mslug in (slug("Togüí"), slug("Toguí")):
        muni = "Toguí"
    # Bolívar | Cartagena -> Cartagena de Indias
    if dslug == slug("Bolívar") and (mslug == slug("Cartagena") or mlet == _letters("Cartagena")):
        muni = "Cartagena de Indias"
    # Bolívar | Santa Rosa de Lima Norte -> Santa Rosa
    if dslug == slug("Bolívar") and mslug == slug("Santa Rosa de Lima Norte"):
        muni = "Santa Rosa"
    # Distrito Capital | Bogotá D.C. -> Cundinamarca | Bogotá
    if dslug == slug("Distrito Capital") and (mslug in (slug("Bogotá D.C."), slug("Bogotá")) or mlet in ("bogotadc","bogota","bogotad","bogotdc")):
        depto = "Cundinamarca"
        muni = "Bogotá"
    # Valle del Cauva (typo) | Santiago de Cali -> Valle del Cauca | Cali
    if dslug in (slug("Valle del Cauva"), slug("Valle del Cauca")) and (mslug in (slug("Santiago de Cali"), slug("Cali")) or mlet in ("santiagodecali","cali")):
        depto = "Valle del Cauca"
        muni = "Cali"
    return depto, muni


def fuzzy_normalize() -> Tuple[int, int, int, int]:
    canon, dept_slug_to_name, muni_by_dept, global_muni, all_pairs = load_canonical()

    # Detect delimiter of comparado
    with ACTIVOS_CMP.open("r", encoding="utf-8", errors="replace") as f:
        first = f.readline()
        delim = detect_delim(first)

    total = 0
    sc = 0
    ch = 0
    nc = 0

    with ACTIVOS_CMP.open("r", encoding="utf-8", errors="replace", newline="") as f_in:
        r = csv.DictReader(f_in, delimiter=delim)
        fields = list(r.fieldnames or [])
        cols = {k.lower(): k for k in fields}
        c_dep = cols.get("departamento")
        c_mun = cols.get("municipio") or cols.get("ciudad")
        c_pais = cols.get("país") or cols.get("pais") or "País"
        c_cmp = cols.get("comparacion") or "comparacion"

        # Ensure País y comparacion en header
        if c_pais not in fields:
            fields.append(c_pais)
        if c_cmp not in fields:
            fields.append(c_cmp)

        rows_out = []
        for row in r:
            total += 1
            d = (row.get(c_dep) or "").strip()
            m = (row.get(c_mun) or "").strip()
            # Primero alias simples
            d, m = apply_alias(d, m)

            key = (slug(d), slug(m))
            if key in canon:
                d_can, m_can, p_can = canon[key]
                row[c_pais] = p_can
                if d == d_can and m == m_can:
                    row[c_cmp] = "sin cambio"
                    sc += 1
                else:
                    row[c_dep] = d_can
                    row[c_mun] = m_can
                    row[c_cmp] = "cambio"
                    ch += 1
                rows_out.append(row)
                continue

            # Intentar dentro del mismo departamento (por slug exacto)
            dslug = slug(d)
            candidates = muni_by_dept.get(dslug) or []
            found = False
            if candidates:
                # por nombre directo
                match = get_close_matches(m, candidates, n=1, cutoff=0.8)
                if not match:
                    match = get_close_matches(slug(m), [slug(x) for x in candidates], n=1, cutoff=0.7)
                    if match:
                        mslug = match[0]
                        # volver al original
                        for cand in candidates:
                            if slug(cand) == mslug:
                                match = [cand]
                                break
                if match:
                    m_can = match[0]
                    d_can = dept_slug_to_name.get(dslug, d)
                    p_can = canon[(slug(d_can), slug(m_can))][2]
                    row[c_dep] = d_can
                    row[c_mun] = m_can
                    row[c_pais] = p_can
                    row[c_cmp] = "cambio"
                    ch += 1
                    rows_out.append(row)
                    found = True
            if found:
                continue

            # Fuzzy del departamento completo
            depts = list(dept_slug_to_name.keys())
            dmatch = get_close_matches(dslug, depts, n=1, cutoff=0.8)
            if dmatch:
                dslug2 = dmatch[0]
                d_can = dept_slug_to_name[dslug2]
                candidates = muni_by_dept.get(dslug2) or []
                match = get_close_matches(m, candidates, n=1, cutoff=0.8)
                if not match:
                    match = get_close_matches(slug(m), [slug(x) for x in candidates], n=1, cutoff=0.7)
                    if match:
                        mslug = match[0]
                        for cand in candidates:
                            if slug(cand) == mslug:
                                match = [cand]
                                break
                if match:
                    m_can = match[0]
                    p_can = canon[(slug(d_can), slug(m_can))][2]
                    row[c_dep] = d_can
                    row[c_mun] = m_can
                    row[c_pais] = p_can
                    row[c_cmp] = "cambio"
                    ch += 1
                    rows_out.append(row)
                    continue

            # Global por municipio único
            gmatch = get_close_matches(slug(m), list(global_muni.keys()), n=1, cutoff=0.85)
            if gmatch:
                pairs = global_muni.get(gmatch[0]) or []
                if len(pairs) == 1:
                    d_can, m_can, p_can = pairs[0]
                    row[c_dep] = d_can
                    row[c_mun] = m_can
                    row[c_pais] = p_can
                    row[c_cmp] = "cambio"
                    ch += 1
                    rows_out.append(row)
                    continue

            # No encontrado -> buscar mejor sugerencia global por score combinado
            from difflib import SequenceMatcher
            ds = slug(d)
            ms = slug(m)
            best = None
            best_score = 0.0
            for d_can, m_can, p_can in all_pairs:
                score_m = SequenceMatcher(None, ms, slug(m_can)).ratio()
                score_d = SequenceMatcher(None, ds, slug(d_can)).ratio()
                score = 0.65 * score_m + 0.35 * score_d
                if score > best_score:
                    best_score = score
                    best = (d_can, m_can, p_can)
            # Umbral moderado para aplicar sugerencia automática
            if best and best_score >= 0.62:
                d_can, m_can, p_can = best
                row[c_dep] = d_can
                row[c_mun] = m_can
                row[c_pais] = p_can
                row[c_cmp] = "cambio"
                ch += 1
                rows_out.append(row)
                continue

            # No encontrado
            row[c_cmp] = "no coincidencia"
            # mantener país existente si lo tuviera
            rows_out.append(row)
            nc += 1

    # Escribir archivo actualizado
    with ACTIVOS_CMP.open("r", encoding="utf-8", errors="replace") as f:
        header_line = f.readline()
        delim = detect_delim(header_line)

    with ACTIVOS_CMP.open("w", encoding="utf-8", newline="") as f_out:
        if rows_out:
            fieldnames = list(rows_out[0].keys())
        else:
            # fallback: re-parse header
            with ACTIVOS_CMP.open("r", encoding="utf-8", errors="replace") as f:
                first = f.readline()
                delim = detect_delim(first)
                fieldnames = [h.strip() for h in first.strip().split(delim)]
        w = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=delim)
        w.writeheader()
        for row in rows_out:
            w.writerow(row)

    return total, sc, ch, nc


if __name__ == "__main__":
    t, sc, ch, nc = fuzzy_normalize()
    print(f"procesados: {t} | sin_cambio: {sc} | cambio: {ch} | no_coincidencia: {nc}")
