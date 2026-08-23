from __future__ import annotations

import json
import math
import re
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

RAW = Path("data/raw/transport/antaq_waterways")
OUT = Path("artifacts/antaq_reference_time_semantics")
TARGET_CRS = "EPSG:4674"
PA_BBOX = box(-58.95, -9.95, -46.0, 2.8)
ARCHIVES = [
    "SHPTKU2023cabotagem.zip",
    "SHPTKUinterior2023.zip",
    "SHP_VEN2022completo.zip",
]


def find_col(cols: list[str], name: str) -> str | None:
    lut = {str(c).lower(): str(c) for c in cols}
    return lut.get(name.lower())


def parse_time_minutes(v: object) -> float | None:
    if v is None or pd.isna(v):
        return None
    m = re.fullmatch(r"\s*(\d+)d\s*(\d+)h\s*(\d+)min\s*", str(v))
    if not m:
        return None
    d, h, minute = map(int, m.groups())
    return float(d * 1440 + h * 60 + minute)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for archive_name in ARCHIVES:
            archive = RAW / archive_name
            if not archive.exists():
                raise RuntimeError(f"Missing ANTAQ archive: {archive}")
            target = tmp / archive.stem
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(target)
            shps = sorted(target.rglob("*.shp"))
            if not shps:
                raise RuntimeError(f"No shapefile in {archive_name}")
            for shp in shps:
                g = gpd.read_file(shp)
                if g.crs is None:
                    continue
                g = g.to_crs(TARGET_CRS)
                g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
                g = g[g.geometry.intersects(PA_BBOX)].copy()
                if g.empty:
                    continue
                cols = [str(c) for c in g.columns]
                hid = find_col(cols, "idhidrovia") or find_col(cols, "idantaq")
                ext = find_col(cols, "extensao")
                tempo = find_col(cols, "tempo")
                vel = find_col(cols, "vel_cional")
                orig = find_col(cols, "mun_origem")
                dest = find_col(cols, "mun_estino") or find_col(cols, "mun_destino")
                ost = find_col(cols, "est_origem")
                dst = find_col(cols, "est_estino") or find_col(cols, "est_destino")
                if not all([hid, ext, tempo, vel]):
                    continue
                for _, r in g.iterrows():
                    length_km = pd.to_numeric(pd.Series([r[ext]]), errors="coerce").iloc[0]
                    speed_kmh = pd.to_numeric(pd.Series([r[vel]]), errors="coerce").iloc[0]
                    time_min = parse_time_minutes(r[tempo])
                    implied = None
                    rel_error = None
                    if pd.notna(length_km) and pd.notna(speed_kmh) and float(speed_kmh) > 0 and time_min and time_min > 0:
                        implied = float(length_km) / (float(time_min) / 60.0)
                        rel_error = abs(implied - float(speed_kmh)) / float(speed_kmh)
                    rows.append({
                        "archive": archive_name,
                        "hydro_id": r[hid],
                        "origin_municipality": r[orig] if orig else None,
                        "origin_state": r[ost] if ost else None,
                        "destination_municipality": r[dest] if dest else None,
                        "destination_state": r[dst] if dst else None,
                        "reported_length_km": float(length_km) if pd.notna(length_km) else None,
                        "reported_time": r[tempo],
                        "reported_time_min": time_min,
                        "vel_cional_kmh": float(speed_kmh) if pd.notna(speed_kmh) else None,
                        "implied_speed_kmh": implied,
                        "relative_speed_error": rel_error,
                    })

    table = pd.DataFrame(rows)
    if table.empty:
        raise RuntimeError("No PA-intersecting ANTAQ records audited")
    valid = table.dropna(subset=["reported_length_km", "reported_time_min", "vel_cional_kmh", "relative_speed_error"]).copy()
    if valid.empty:
        raise RuntimeError("No records have length, time and VEL_CIONAL")

    unique_hydro = int(table["hydro_id"].nunique(dropna=True))
    hydro_counts = table.groupby("hydro_id", dropna=True).size()
    duplicate_hydro_ids = int((hydro_counts > 1).sum())
    duplicate_rows = int(hydro_counts[hydro_counts > 1].sum())

    def share(tol: float) -> float:
        return float((valid["relative_speed_error"] <= tol).mean())

    by_archive = (
        valid.groupby("archive")
        .agg(
            rows=("hydro_id", "size"),
            unique_hydro_ids=("hydro_id", "nunique"),
            median_relative_speed_error=("relative_speed_error", "median"),
            p95_relative_speed_error=("relative_speed_error", lambda s: float(s.quantile(0.95))),
        )
        .reset_index()
    )
    by_archive["within_1pct"] = by_archive["archive"].map(
        lambda a: float((valid.loc[valid["archive"] == a, "relative_speed_error"] <= 0.01).mean())
    )
    by_archive["within_5pct"] = by_archive["archive"].map(
        lambda a: float((valid.loc[valid["archive"] == a, "relative_speed_error"] <= 0.05).mean())
    )

    # Same hydro_id appearing in multiple official archive products is treated as
    # provenance overlap evidence, not automatically as a distinct independent route.
    archive_sets = table.groupby("hydro_id", dropna=True)["archive"].agg(lambda x: "|".join(sorted(set(x))))
    multi_archive_ids = int(archive_sets.str.contains("\\|").sum())

    anchor_ids = {"Muaná": "200002819", "Soure": "200002926", "Moju": "200300074"}
    anchor_rows = []
    for name, hid in anchor_ids.items():
        mask = table["hydro_id"].astype(str).str.replace(".0", "", regex=False).eq(hid)
        sub = table.loc[mask].copy()
        for _, r in sub.iterrows():
            anchor_rows.append({"anchor": name, **r.to_dict()})
    anchor_table = pd.DataFrame(anchor_rows)

    audit = {
        "pa_intersecting_raw_records": int(len(table)),
        "records_with_length_time_and_vel_cional": int(len(valid)),
        "unique_hydro_ids": unique_hydro,
        "duplicate_hydro_ids": duplicate_hydro_ids,
        "rows_in_duplicate_hydro_groups": duplicate_rows,
        "hydro_ids_present_in_multiple_archives": multi_archive_ids,
        "median_relative_speed_error": float(valid["relative_speed_error"].median()),
        "p95_relative_speed_error": float(valid["relative_speed_error"].quantile(0.95)),
        "time_matches_length_over_vel_cional_within_1pct_fraction": share(0.01),
        "time_matches_length_over_vel_cional_within_5pct_fraction": share(0.05),
        "time_matches_length_over_vel_cional_within_10pct_fraction": share(0.10),
        "vel_cional_is_observed_passenger_speed_claimed": False,
        "reported_time_is_observed_passenger_time_claimed": False,
        "directional_asymmetry_inferred_from_municipality_labels": False,
        "archive_provenance_overlap_requires_canonicalization": bool(multi_archive_ids > 0),
        "scientific_interpretation": (
            "ANTAQ raw hydro products expose EXTENSAO, TEMPO and VEL_CIONAL together. This audit tests whether TEMPO behaves as a corridor reference impedance generated from route length and the published conventional/reference speed field. Strong agreement supports treating TEMPO as a modeled network reference impedance rather than observed directional passenger travel time. Archive overlaps sharing the same official hydro_id are provenance/version overlaps and must be canonicalized before graph construction rather than counted as independent routes."
        ),
        "next_required_step": (
            "If the length/time/VEL_CIONAL relationship is strong in the Pará-intersecting records, revise hydro graph semantics away from municipality-label-derived directionality and canonicalize overlapping archive records by official hydro_id with explicit source provenance before final graph assembly."
        ),
    }

    table.to_csv(OUT / "antaq_pa_reference_time_semantics_rows.csv", index=False)
    by_archive.to_csv(OUT / "antaq_pa_reference_time_semantics_by_archive.csv", index=False)
    archive_sets.rename("archive_set").reset_index().to_csv(OUT / "antaq_hydro_id_archive_overlap.csv", index=False)
    anchor_table.to_csv(OUT / "validated_anchor_reference_time_semantics.csv", index=False)
    (OUT / "antaq_reference_time_semantics_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(by_archive.to_string(index=False))
    if not anchor_table.empty:
        print(anchor_table.to_string(index=False))


if __name__ == "__main__":
    main()
