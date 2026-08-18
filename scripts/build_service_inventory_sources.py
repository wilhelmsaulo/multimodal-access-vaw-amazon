from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import httpx
import pandas as pd

from src.data.service_inventory import fetch_cnes_establishments_pa, filter_cnes_vaw_relevant

CENSO_SUAS_INDEX = "https://aplicacoes.mds.gov.br/sagi/snas/vigilancia/index2.php"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def discover_creas_2024_links(html: str) -> list[str]:
    """Discover official CREAS 2024 file links from the Censo SUAS index page.

    The page groups resources by year. We isolate the 2024 block (before the 2023
    heading) and retain hrefs whose anchor/context mentions CREAS.
    """
    upper = html.upper()
    start = upper.find("CENSO SUAS 2024")
    end = upper.find("CENSO SUAS 2023", start + 1) if start >= 0 else -1
    block = html[start : end if end > start else None] if start >= 0 else html
    anchors = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, flags=re.I | re.S)
    links: list[str] = []
    for href, label in anchors:
        plain = re.sub(r"<[^>]+>", " ", label)
        if "CREAS" in plain.upper() or "CREAS" in href.upper():
            links.append(urljoin(CENSO_SUAS_INDEX, href))
    return list(dict.fromkeys(links))


def read_tabular_bytes(data: bytes, filename: str) -> dict[str, pd.DataFrame]:
    name = filename.lower()
    if name.endswith(".csv"):
        for encoding in ("utf-8", "latin1"):
            try:
                return {"csv": pd.read_csv(BytesIO(data), sep=None, engine="python", encoding=encoding)}
            except Exception:
                pass
        raise ValueError(f"Could not parse CSV {filename}")
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(data), sheet_name=None)
    return {}


def extract_zip_tables(data: bytes) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(BytesIO(data)) as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            payload = zf.read(member)
            for sheet, frame in read_tabular_bytes(payload, member).items():
                tables[f"{member}::{sheet}"] = frame
    return tables


def _norm_text(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def filter_para_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    candidates = []
    for col in frame.columns:
        n = _norm_text(col)
        if n in {"UF", "SGUF", "SIGLAUF", "ESTADO", "NOESTADO", "UFUNIDADE"} or n.endswith("UF"):
            candidates.append(col)
    for col in candidates:
        s = frame[col].astype(str).str.strip().str.upper()
        mask = s.isin({"PA", "PARA", "PARÁ", "15"})
        if mask.any():
            return frame.loc[mask].copy()
    # Some Censo SUAS sheets encode IBGE municipality codes. Pará codes start with 15.
    for col in frame.columns:
        n = _norm_text(col)
        if "IBGE" in n or n in {"CODMUNICIPIO", "CODMUNICIPIOIBGE", "CDMUNICIPIO"}:
            s = frame[col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
            mask = s.str.startswith("15")
            if mask.any():
                return frame.loc[mask].copy()
    return frame.iloc[0:0].copy()


def download_creas_2024(out_dir: Path, client: httpx.Client) -> dict:
    response = client.get(CENSO_SUAS_INDEX)
    response.raise_for_status()
    links = discover_creas_2024_links(response.text)
    if not links:
        raise RuntimeError("No Censo SUAS 2024 CREAS resource links discovered.")

    manifest = {"index_url": CENSO_SUAS_INDEX, "resources": []}
    normalized_frames: list[pd.DataFrame] = []
    raw_dir = out_dir / "creas_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for i, url in enumerate(links, start=1):
        r = client.get(url)
        r.raise_for_status()
        data = r.content
        cd = r.headers.get("content-disposition", "")
        match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)', cd, flags=re.I)
        filename = match.group(1) if match else Path(r.url.path).name or f"creas_resource_{i}"
        filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
        path = raw_dir / filename
        path.write_bytes(data)

        tables = extract_zip_tables(data) if zipfile.is_zipfile(BytesIO(data)) else read_tabular_bytes(data, filename)
        resource_entry = {
            "url": str(r.url),
            "filename": filename,
            "sha256": sha256_bytes(data),
            "content_type": r.headers.get("content-type"),
            "tables": [],
        }
        for table_name, frame in tables.items():
            pa = filter_para_rows(frame)
            resource_entry["tables"].append(
                {"name": table_name, "rows_total": int(len(frame)), "rows_para": int(len(pa))}
            )
            if len(pa):
                pa = pa.copy()
                pa["_source_file"] = filename
                pa["_source_table"] = table_name
                normalized_frames.append(pa)
        manifest["resources"].append(resource_entry)

    if normalized_frames:
        pd.concat(normalized_frames, ignore_index=True, sort=False).to_csv(
            out_dir / "creas_2024_para_extracted.csv", index=False
        )
    (out_dir / "creas_2024_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def build_cnes(out_dir: Path) -> dict:
    raw = fetch_cnes_establishments_pa(page_size=20)
    raw.to_csv(out_dir / "cnes_pa_active_raw.csv", index=False)
    candidates = filter_cnes_vaw_relevant(raw)
    candidates.to_csv(out_dir / "cnes_pa_vaw_health_candidates.csv", index=False)
    manifest = {
        "source": "DEMAS CNES API",
        "endpoint": "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos",
        "uf_code": 15,
        "status": 1,
        "rows_active_para": int(len(raw)),
        "rows_vaw_health_candidates": int(len(candidates)),
        "raw_columns": [str(c) for c in raw.columns],
    }
    (out_dir / "cnes_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/service_inventory"))
    parser.add_argument("--skip-cnes", action="store_true")
    parser.add_argument("--skip-creas", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {}
    if not args.skip_cnes:
        summary["cnes"] = build_cnes(args.output_dir)
    if not args.skip_creas:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            summary["creas"] = download_creas_2024(args.output_dir, client)
    (args.output_dir / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
