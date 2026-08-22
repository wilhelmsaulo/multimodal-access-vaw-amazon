from __future__ import annotations

import argparse
import json
import re
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

TOKENS = (
    "tempo", "dur", "min", "hora", "freq", "horar", "viagem", "percurso",
    "veloc", "speed", "dist", "extens", "frota", "embarc", "linha", "orig",
    "dest", "inicio", "final", "terminal", "atrac", "operac", "servico",
)


def norm(s: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())


def inspect_frame(df: pd.DataFrame, source: str, layer: str) -> dict[str, object]:
    cols = [str(c) for c in df.columns if str(c).lower() != "geometry"]
    evidence: dict[str, object] = {}
    for c in cols:
        nc = norm(c)
        if not any(tok in nc for tok in TOKENS):
            continue
        s = df[c]
        nonnull = int(s.notna().sum())
        if nonnull == 0:
            continue
        vals = s.dropna().astype(str).str.strip()
        vals = vals[vals.ne("")]
        evidence[c] = {
            "nonnull": int(len(vals)),
            "coverage_fraction": float(len(vals) / len(df)) if len(df) else 0.0,
            "unique_values": int(vals.nunique()),
            "sample_values": vals.drop_duplicates().head(20).tolist(),
        }
    return {
        "source": source,
        "layer": layer,
        "rows": int(len(df)),
        "columns": cols,
        "operational_candidate_columns": evidence,
    }


def inspect_zip(path: Path) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        try:
            with zipfile.ZipFile(path) as zf:
                zf.extractall(root)
        except Exception as exc:
            return [{"source": str(path), "error": f"zip_extract_failed: {exc}"}]

        shp_files = list(root.rglob("*.shp"))
        geojson_files = list(root.rglob("*.geojson")) + list(root.rglob("*.json"))
        csv_files = list(root.rglob("*.csv"))

        for f in shp_files + geojson_files:
            try:
                g = gpd.read_file(f)
                out.append(inspect_frame(g, str(path), f.relative_to(root).as_posix()))
            except Exception as exc:
                out.append({"source": str(path), "layer": f.relative_to(root).as_posix(), "error": str(exc)})
        for f in csv_files:
            try:
                df = pd.read_csv(f, low_memory=False)
                out.append(inspect_frame(df, str(path), f.relative_to(root).as_posix()))
            except Exception as exc:
                out.append({"source": str(path), "layer": f.relative_to(root).as_posix(), "error": str(exc)})
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw/transport"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/antaq_raw_operational_evidence"))
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    zips = sorted([p for p in args.raw_dir.rglob("*.zip") if any(k in p.name.lower() for k in ("travess", "tku", "ven", "port", "instala"))])
    records: list[dict[str, object]] = []
    for z in zips:
        records.extend(inspect_zip(z))

    candidate_layers = [r for r in records if r.get("operational_candidate_columns")]
    temporal_keys = ("tempo", "dur", "min", "hora", "freq", "viagem", "percurso", "veloc", "speed")
    layers_with_temporal = []
    for r in candidate_layers:
        cols = r.get("operational_candidate_columns", {})
        if any(any(t in norm(c) for t in temporal_keys) for c in cols):
            layers_with_temporal.append(r)

    summary = {
        "zip_files_scanned": len(zips),
        "datasets_or_layers_scanned": len(records),
        "layers_with_operational_candidate_fields": len(candidate_layers),
        "layers_with_temporal_candidate_fields": len(layers_with_temporal),
        "zip_files": [str(z) for z in zips],
        "scientific_policy": (
            "This audit inspects raw ANTAQ-distributed files for route-level operational evidence such as average travel time, "
            "frequency, schedules, fleet, distance, and vessel identifiers. It does not infer speed from geometry and does not "
            "assign hydro travel time when operational evidence is absent."
        ),
        "ready_for_hydro_temporal_evidence_decision": True,
        "hydro_time_assigned": False,
    }

    (args.output_dir / "antaq_raw_operational_evidence.json").write_text(
        json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for r in layers_with_temporal:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
