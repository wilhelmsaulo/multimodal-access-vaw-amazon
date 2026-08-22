from __future__ import annotations

import json
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

PORT_DIR = Path("data/raw/transport/antaq_ports")
WATER_DIR = Path("data/raw/transport/antaq_waterways")
OUT = Path("artifacts/antaq_port_hydro_associations")


def norm_text(v: object) -> str:
    if v is None or pd.isna(v):
        return ""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def pick_col(cols: list[str], tokens: tuple[str, ...]) -> str | None:
    scored: list[tuple[int, str]] = []
    for c in cols:
        n = norm_text(c)
        score = sum(1 for t in tokens if t in n)
        if score:
            scored.append((score, c))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    return scored[0][1]


def read_zip(path: Path) -> gpd.GeoDataFrame:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(root)
        shp = next(iter(root.rglob("*.shp")), None)
        if shp is None:
            raise RuntimeError(f"No shapefile in {path}")
        return gpd.read_file(shp)


def field_profile(df: pd.DataFrame) -> dict[str, object]:
    cols = [str(c) for c in df.columns if str(c).lower() != "geometry"]
    return {
        "columns": cols,
        "candidate_id_fields": [c for c in cols if any(t in norm_text(c) for t in ("id", "codigo", "cod", "seq"))],
        "candidate_name_fields": [c for c in cols if any(t in norm_text(c) for t in ("nome", "porto", "instal", "terminal"))],
        "candidate_municipality_fields": [c for c in cols if any(t in norm_text(c) for t in ("municip", "cidade", "mun"))],
        "candidate_state_fields": [c for c in cols if any(t in norm_text(c) for t in ("uf", "estado"))],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    port_zips = sorted(PORT_DIR.glob("*.zip"))
    water_zips = sorted(WATER_DIR.glob("*.zip"))

    port_records = []
    port_frames = []
    for z in port_zips:
        g = read_zip(z)
        prof = field_profile(g)
        cols = prof["columns"]
        mun = pick_col(cols, ("municip", "cidade", "mun"))
        uf = pick_col(cols, ("uf", "estado"))
        ident = pick_col(cols, ("idseq", "id", "codigo", "cod", "seq"))
        name = pick_col(cols, ("nome", "porto", "instal", "terminal"))
        port_records.append({"dataset": z.name, "rows": len(g), "profile": prof, "chosen": {"municipality": mun, "state": uf, "id": ident, "name": name}})
        tmp = pd.DataFrame(index=g.index)
        tmp["dataset"] = z.name
        tmp["municipality"] = g[mun].map(norm_text) if mun else ""
        tmp["state"] = g[uf].map(norm_text) if uf else ""
        tmp["port_id"] = g[ident].map(norm_text) if ident else ""
        tmp["port_name"] = g[name].astype(str) if name else ""
        port_frames.append(tmp)

    water_records = []
    endpoint_rows = []
    id_overlap_candidates = []
    for z in water_zips:
        g = read_zip(z)
        prof = field_profile(g)
        cols = prof["columns"]
        orig_mun = pick_col(cols, ("orig", "municip")) or pick_col(cols, ("orig", "cidade"))
        dest_mun = pick_col(cols, ("dest", "municip")) or pick_col(cols, ("dest", "cidade"))
        orig_uf = pick_col(cols, ("orig", "uf")) or pick_col(cols, ("orig", "estado"))
        dest_uf = pick_col(cols, ("dest", "uf")) or pick_col(cols, ("dest", "estado"))
        water_records.append({"dataset": z.name, "rows": len(g), "profile": prof, "chosen": {"origin_municipality": orig_mun, "origin_state": orig_uf, "destination_municipality": dest_mun, "destination_state": dest_uf}})

        for side, mc, uc in (("origin", orig_mun, orig_uf), ("destination", dest_mun, dest_uf)):
            if not mc:
                continue
            for i in g.index:
                endpoint_rows.append({
                    "dataset": z.name,
                    "row": int(i),
                    "side": side,
                    "municipality": norm_text(g.at[i, mc]),
                    "state": norm_text(g.at[i, uc]) if uc else "",
                })

        for c in prof["candidate_id_fields"]:
            vals = set(g[c].dropna().map(norm_text)) - {""}
            if not vals:
                continue
            for pr, pf in zip(port_records, port_frames):
                pvals = set(pf["port_id"]) - {""}
                overlap = vals & pvals
                if overlap:
                    id_overlap_candidates.append({
                        "water_dataset": z.name,
                        "water_field": c,
                        "port_dataset": pr["dataset"],
                        "port_field": pr["chosen"]["id"],
                        "overlap_count": len(overlap),
                        "sample_overlap": sorted(overlap)[:20],
                    })

    ports = pd.concat(port_frames, ignore_index=True) if port_frames else pd.DataFrame(columns=["municipality", "state"])
    endpoints = pd.DataFrame(endpoint_rows)
    if not endpoints.empty:
        endpoints = endpoints[endpoints["municipality"].ne("")].copy()
        port_keys = set(zip(ports["municipality"], ports["state"]))
        port_muns = set(ports["municipality"])
        endpoints["exact_municipality_state_port_present"] = [
            (m, u) in port_keys if u else m in port_muns for m, u in zip(endpoints["municipality"], endpoints["state"])
        ]
        endpoints["municipality_port_present"] = endpoints["municipality"].isin(port_muns)
    else:
        endpoints["exact_municipality_state_port_present"] = []
        endpoints["municipality_port_present"] = []

    exact_count = int(endpoints["exact_municipality_state_port_present"].sum()) if len(endpoints) else 0
    municipality_count = int(endpoints["municipality_port_present"].sum()) if len(endpoints) else 0

    audit = {
        "port_datasets": port_records,
        "waterway_datasets": water_records,
        "port_rows_total": int(len(ports)),
        "waterway_endpoint_rows_total": int(len(endpoints)),
        "endpoint_rows_with_port_in_same_municipality": municipality_count,
        "endpoint_rows_with_port_in_same_municipality_state": exact_count,
        "endpoint_same_municipality_fraction": float(municipality_count / len(endpoints)) if len(endpoints) else 0.0,
        "endpoint_same_municipality_state_fraction": float(exact_count / len(endpoints)) if len(endpoints) else 0.0,
        "explicit_identifier_overlap_candidates": id_overlap_candidates,
        "explicit_identifier_overlap_candidate_count": len(id_overlap_candidates),
        "scientific_policy": "This audit searches official ANTAQ port and waterway attributes for explicit identifier overlap and exact municipality/state endpoint associations. Municipality coincidence is evidence for candidate transfer validation but is not by itself promoted to a physical connector. No distance threshold or nearest-feature rule is applied here.",
        "connector_promoted": False,
        "ready_for_intermodal_connector_model_decision": True,
    }
    (OUT / "antaq_port_hydro_association_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    endpoints.to_csv(OUT / "waterway_endpoints_port_presence.csv", index=False)
    print(json.dumps({
        "port_rows_total": audit["port_rows_total"],
        "waterway_endpoint_rows_total": audit["waterway_endpoint_rows_total"],
        "endpoint_rows_with_port_in_same_municipality": municipality_count,
        "endpoint_rows_with_port_in_same_municipality_state": exact_count,
        "explicit_identifier_overlap_candidate_count": len(id_overlap_candidates),
        "connector_promoted": False,
        "ready_for_intermodal_connector_model_decision": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
