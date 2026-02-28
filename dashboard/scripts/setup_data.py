#!/usr/bin/env python3
"""
automated data pipeline for the barangay election dashboard.

downloads all required source data and builds the final barangays.geojson.
all intermediate/source files are stored under data/sources/ (gitignored).

usage:
    python scripts/setup_data.py          # download everything + build
    python scripts/setup_data.py --skip-download   # rebuild from cached sources
    python scripts/setup_data.py --download-only    # download only, don't build

sources:
    1. election CSVs - figshare (2025 philippine midterm elections data)
    2. barangay boundaries - faeldon/philippines-json-maps (psgc 2023, hires)
    3. osm gap-fill - overpass api (ncr + basilan admin_level=10)
    4. hdx gap-fill - psa/namria administrative boundaries geodatabase
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DASHBOARD_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = DASHBOARD_DIR.parent
SOURCES_DIR = PROJECT_ROOT / "data" / "sources"

# -- download URLs --
FIGSHARE_SENATE = "https://api.figshare.com/v2/file/download/54696185"
FIGSHARE_PARTYLIST = "https://api.figshare.com/v2/file/download/54696545"
PHILIPPINES_JSON_MAPS_REPO = "https://github.com/faeldon/philippines-json-maps.git"
HDX_GDB_URL = "https://data.humdata.org/dataset/caf116df-f984-4deb-85ca-41b349d3f313/resource/314cbaea-c7a0-4ce9-a4ea-e5af2a788ac1/download/phl_adm_psa_namria_20231106_gdb.gdb.zip"

# -- output paths inside sources/ --
SENATE_CSV = SOURCES_DIR / "senate25-final_updated.csv"
PARTYLIST_CSV = SOURCES_DIR / "partylist25-final_updated.csv"
GEOJSON_MAPS_DIR = SOURCES_DIR / "philippines-json-maps"
OSM_GEOJSON = SOURCES_DIR / "osm_barangays.geojson"
HDX_GDB_ZIP = SOURCES_DIR / "hdx_gdb.zip"
HDX_GDB_DIR = SOURCES_DIR / "hdx_gdb"
HDX_GDB = HDX_GDB_DIR / "phl_adm_psa_namria_20231106_GDB.gdb"

# -- overpass config (same as fetchOsmBarangays.py) --
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_QUERIES = [
    {"name": "NCR (Manila + Metro Manila)", "bbox": "14.35,120.90,14.80,121.15"},
    {"name": "Basilan", "bbox": "6.35,121.85,6.80,122.25"},
]


def download_file(url, dest, label):
    """download a file with progress indication and retry for HTTP 202."""
    if dest.exists() and dest.stat().st_size > 0:
        size_mb = dest.stat().st_size / 1024 / 1024
        print(f"    {label}: already exists ({size_mb:.1f} MB) - skipping")
        return

    print(f"    {label}: downloading...")
    dest.parent.mkdir(parents=True, exist_ok=True)

    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "election-dashboard-builder/1.0")
            resp = urllib.request.urlopen(req, timeout=300)

            # figshare returns HTTP 202 with empty body on first request
            # (deferred download) - retry after a short wait
            if resp.status == 202:
                resp.close()
                if attempt < max_retries:
                    wait = 3 * attempt
                    print(f"    {label}: server preparing download, retrying in {wait}s... (attempt {attempt}/{max_retries})")
                    time.sleep(wait)
                    continue
                else:
                    print(f"    {label}: ERROR - server returned 202 after {max_retries} attempts")
                    sys.exit(1)

            total = int(resp.headers.get("Content-Length", 0))
            chunk_size = 1024 * 256
            downloaded = 0

            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded * 100 // total
                        mb = downloaded / 1024 / 1024
                        print(f"\r    {label}: {mb:.1f} MB ({pct}%)", end="", flush=True)

            resp.close()

            if dest.stat().st_size == 0:
                dest.unlink()
                if attempt < max_retries:
                    wait = 3 * attempt
                    print(f"    {label}: empty response, retrying in {wait}s... (attempt {attempt}/{max_retries})")
                    time.sleep(wait)
                    continue
                else:
                    print(f"    {label}: ERROR - empty file after {max_retries} attempts")
                    sys.exit(1)

            size_mb = dest.stat().st_size / 1024 / 1024
            print(f"\r    {label}: {size_mb:.1f} MB - done")
            return

        except Exception as e:
            if dest.exists():
                dest.unlink()
            if attempt < max_retries:
                wait = 3 * attempt
                print(f"    {label}: error ({e}), retrying in {wait}s... (attempt {attempt}/{max_retries})")
                time.sleep(wait)
            else:
                print(f"\n    ERROR: {e}")
                sys.exit(1)


def download_csvs():
    """download senate + partylist csvs from figshare."""
    print("\n[1/4] downloading election CSVs from figshare...")
    download_file(FIGSHARE_SENATE, SENATE_CSV, "senate csv")
    download_file(FIGSHARE_PARTYLIST, PARTYLIST_CSV, "partylist csv")


def download_geojson_maps():
    """clone philippines-json-maps with sparse checkout (hires only)."""
    print("\n[2/4] downloading barangay boundaries (faeldon/philippines-json-maps)...")

    if (GEOJSON_MAPS_DIR / "2023" / "geojson" / "municities" / "hires").exists():
        count = len(os.listdir(GEOJSON_MAPS_DIR / "2023" / "geojson" / "municities" / "hires"))
        print(f"    already exists ({count} municipality files) - skipping")
        return

    if GEOJSON_MAPS_DIR.exists():
        shutil.rmtree(GEOJSON_MAPS_DIR)

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"    cloning with sparse checkout (hires only)...")
    subprocess.run(
        ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
         PHILIPPINES_JSON_MAPS_REPO, str(GEOJSON_MAPS_DIR)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "sparse-checkout", "set",
         "2023/geojson/municities/hires",
         "2023/geojson/regions/hires",
         "2023/geojson/provdists/hires"],
        cwd=str(GEOJSON_MAPS_DIR),
        check=True, capture_output=True, text=True,
    )

    count = len(os.listdir(GEOJSON_MAPS_DIR / "2023" / "geojson" / "municities" / "hires"))
    print(f"    cloned - {count} municipality files")


def fetch_osm_barangays():
    """fetch barangay boundaries from osm overpass api."""
    print("\n[3/4] fetching OSM barangay boundaries (NCR + Basilan)...")

    if OSM_GEOJSON.exists():
        with open(OSM_GEOJSON) as f:
            data = json.load(f)
        count = len(data.get("features", []))
        print(f"    already exists ({count} features) - skipping")
        return

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    all_features = []

    for q in OSM_QUERIES:
        query = f"""
        [out:json][timeout:120];
        relation["admin_level"="10"]["boundary"="administrative"]({q["bbox"]});
        out body;
        >;
        out skel qt;
        """
        print(f"    fetching {q['name']}...")
        data = urllib.parse.urlencode({"data": query}).encode()
        req = urllib.request.Request(OVERPASS_URL, data=data)
        req.add_header("User-Agent", "election-dashboard-builder/1.0")

        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = json.loads(resp.read())

        nodes, ways, relations = {}, {}, []
        for el in raw.get("elements", []):
            if el["type"] == "node":
                nodes[el["id"]] = (el["lon"], el["lat"])
            elif el["type"] == "way":
                ways[el["id"]] = el.get("nodes", [])
            elif el["type"] == "relation":
                relations.append(el)

        print(f"        {len(relations)} relations, {len(ways)} ways, {len(nodes)} nodes")

        for rel in relations:
            tags = rel.get("tags", {})
            name = tags.get("name", "")
            psgc = str(tags.get("ref", ""))

            outer_ways = [
                m["ref"] for m in rel.get("members", [])
                if m["type"] == "way" and m.get("role", "outer") in ("outer", "")
            ]
            if not outer_ways:
                continue

            rings = _build_rings(outer_ways, ways, nodes)
            if not rings:
                continue

            if len(rings) == 1:
                geometry = {"type": "Polygon", "coordinates": rings}
            else:
                geometry = {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}

            all_features.append({
                "type": "Feature",
                "properties": {"name": name, "psgc": psgc, "osm_id": rel["id"]},
                "geometry": geometry,
            })

        print(f"        {len(all_features)} features total")

        if q != OSM_QUERIES[-1]:
            print(f"    waiting 10s before next query...")
            time.sleep(10)

    geojson = {"type": "FeatureCollection", "features": all_features}
    with open(OSM_GEOJSON, "w") as f:
        json.dump(geojson, f, separators=(",", ":"))

    print(f"    {len(all_features)} features saved")


def _build_rings(way_ids, ways, nodes):
    """assemble way segments into closed rings."""
    segments = []
    for wid in way_ids:
        if wid not in ways:
            continue
        coords = [nodes[nid] for nid in ways[wid] if nid in nodes]
        if coords:
            segments.append(coords)

    if not segments:
        return []

    rings = []
    while segments:
        ring = list(segments.pop(0))
        changed = True
        while changed:
            changed = False
            for i, seg in enumerate(segments):
                if not seg:
                    continue
                if ring[-1] == seg[0]:
                    ring.extend(seg[1:])
                    segments.pop(i)
                    changed = True
                    break
                elif ring[-1] == seg[-1]:
                    ring.extend(reversed(seg[:-1]))
                    segments.pop(i)
                    changed = True
                    break
                elif ring[0] == seg[-1]:
                    ring = seg[:-1] + ring
                    segments.pop(i)
                    changed = True
                    break
                elif ring[0] == seg[0]:
                    ring = list(reversed(seg[1:])) + ring
                    segments.pop(i)
                    changed = True
                    break

        if ring[0] != ring[-1]:
            ring.append(ring[0])
        ring = [[round(c[0], 6), round(c[1], 6)] for c in ring]
        if len(ring) >= 4:
            rings.append(ring)

    return rings


def download_hdx_gdb():
    """download and extract the HDX/OCHA PSA/NAMRIA geodatabase."""
    print("\n[4/4] downloading HDX/OCHA geodatabase (PSA/NAMRIA boundaries)...")

    if HDX_GDB.exists():
        print(f"    already exists - skipping")
        return

    # check ogr2ogr availability
    if not shutil.which("ogr2ogr"):
        print(f"    WARNING: ogr2ogr not found - skipping HDX download")
        print(f"    install GDAL to enable HDX gap-filling (e.g. sudo apt install gdal-bin)")
        return

    download_file(HDX_GDB_URL, HDX_GDB_ZIP, "hdx geodatabase")

    print(f"    extracting...")
    HDX_GDB_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(HDX_GDB_ZIP, "r") as zf:
        zf.extractall(HDX_GDB_DIR)

    if HDX_GDB.exists():
        print(f"    extracted to {HDX_GDB.relative_to(PROJECT_ROOT)}")
    else:
        # check what was extracted
        extracted = list(HDX_GDB_DIR.glob("*.gdb"))
        if extracted:
            print(f"    extracted: {extracted[0].name}")
        else:
            print(f"    WARNING: extraction succeeded but .gdb not found")


def run_build():
    """run the choropleth build script."""
    print("\n" + "=" * 50)
    print("building barangay choropleth...")
    print("=" * 50 + "\n")

    build_script = SCRIPT_DIR / "buildBarangayChoropleth.py"
    result = subprocess.run(
        [sys.executable, str(build_script)],
        cwd=str(SCRIPT_DIR),
    )
    return result.returncode


def main():
    skip_download = "--skip-download" in sys.argv
    download_only = "--download-only" in sys.argv

    print("=" * 50)
    print("2025 philippine election dashboard - data pipeline")
    print("=" * 50)
    print(f"\nsource data directory: {SOURCES_DIR.relative_to(PROJECT_ROOT)}/")

    if not skip_download:
        download_csvs()
        download_geojson_maps()
        fetch_osm_barangays()
        download_hdx_gdb()
        print("\n[ok] all source data downloaded")

    if download_only:
        print("\n--download-only: skipping build")
        return

    rc = run_build()
    if rc != 0:
        print(f"\nERROR: build failed with exit code {rc}")
        sys.exit(rc)

    print("\n[ok] pipeline complete")


if __name__ == "__main__":
    main()
