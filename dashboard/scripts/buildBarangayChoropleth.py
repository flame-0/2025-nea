#!/usr/bin/env python3
"""
build a barangay-level choropleth GeoJSON with election vote data.

reads:
  - philippines-json-maps GeoJSON (barangay boundaries from municities/)
  - senate25-final_updated.csv
  - partylist25-final_updated.csv

outputs:
  - public/data/barangays.geojson (barangay polygons + vote properties)

strategy:
  1. build municipality PSGC -> CSV (province, municipality) mapping
  2. for each municipality, load barangay polygons from municities/hires
  3. match barangay names from CSV -> GeoJSON using normalized string comparison
  4. strip unnecessary properties + round coordinates to save space
"""

import json
import os
import csv
import re
import sys
import subprocess
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # 2025-national-electoral-analysis/
DASHBOARD_DIR = SCRIPT_DIR.parent
SOURCES_DIR = PROJECT_ROOT / "data" / "sources"
GEO_BASE = SOURCES_DIR / "philippines-json-maps" / "2023" / "geojson"
OUTPUT_DIR = DASHBOARD_DIR / "public" / "data"

# -- HDX OCHA geodatabase (PSA/NAMRIA barangay boundaries) --
HDX_GDB = SOURCES_DIR / "hdx_gdb" / "phl_adm_psa_namria_20231106_GDB.gdb"
HDX_LAYER = "phl_admbnda_adm4_psa_namria_20231106"

# -- HUC PSGC -> CSV name mapping (these are independent cities) --
HUC_MAPPING = {
    330100000: ("PAMPANGA", "CITY OF ANGELES"),
    331400000: ("ZAMBALES", "CITY OF OLONGAPO"),
    431200000: ("QUEZON", "CITY OF LUCENA"),
    630200000: ("NEGROS OCCIDENTAL", "CITY OF BACOLOD"),
    631000000: ("ILOILO", "CITY OF ILOILO"),
    730600000: ("CEBU", "CITY OF CEBU"),
    731100000: ("CEBU", "CITY OF LAPU-LAPU"),
    731300000: ("CEBU", "CITY OF MANDAUE"),
    831600000: ("LEYTE", "CITY OF TACLOBAN"),
    931700000: ("ZAMBOANGA DEL SUR", "CITY OF ZAMBOANGA"),
    1030500000: ("MISAMIS ORIENTAL", "CITY OF CAGAYAN DE ORO"),
    1030900000: ("LANAO DEL NORTE", "CITY OF ILIGAN"),
    1230800000: ("SOUTH COTABATO", "CITY OF GENERAL SANTOS"),
    1430300000: ("BENGUET", "CITY OF BAGUIO"),
    1630400000: ("AGUSAN DEL NORTE", "CITY OF BUTUAN"),
    1731500000: ("PALAWAN", "CITY OF PUERTO PRINCESA"),
}

# -- NCR district province name mapping: CSV -> GeoJSON --
NCR_PROV_FIXES = {
    "NATIONAL CAPITAL REGION - MANILA": "NCR, CITY OF MANILA, FIRST DISTRICT (NOT A PROVINCE)",
    "NATIONAL CAPITAL REGION - SECOND DISTRICT": "NCR, SECOND DISTRICT (NOT A PROVINCE)",
    "NATIONAL CAPITAL REGION - THIRD DISTRICT": "NCR, THIRD DISTRICT (NOT A PROVINCE)",
    "NATIONAL CAPITAL REGION - FOURTH DISTRICT": "NCR, FOURTH DISTRICT (NOT A PROVINCE)",
    "NATIONAL CAPITAL REGION - FIRST DISTRICT": "NCR, CITY OF MANILA, FIRST DISTRICT (NOT A PROVINCE)",
}

MUNI_NAME_FIXES = {
    "CITY OF OZAMIS": "CITY OF OZAMIZ",
    "GEN. S. K. PENDATUN": "GEN. S.K. PENDATUN",
}

# -- candidate column mappings (must match candidates.ts) --
SENATE_CANDIDATES = {
    "pangilinan": ["51. PANGILINAN, KIKO (LP)"],
    "aquino": ["5. AQUINO, BAM (KNP)"],
    "adonis": ["2. ADONIS, JEROME (MKBYN)"],
    "andamo": ["4. ANDAMO, NARS ALYN (MKBYN)"],
    "arambulo": ["6. ARAMBULO, RONNEL (MKBYN)"],
    "brosas": ["13. BROSAS, ARLENE (MKBYN)"],
    "casino": ["16. CASIÑO, TEDDY (MKBYN)"],
    "castro": ["17. CASTRO, TEACHER FRANCE (MKBYN)"],
    "doringo": ["23. DORINGO, NANAY MIMI (MKBYN)"],
    "floranda": ["26. FLORANDA, MODY PISTON (MKBYN)"],
    "espiritu": ["25. ESPIRITU, LUKE (PLM)"],
    "lidasan": ["37. LIDASAN, AMIRAH (MKBYN)"],
    "maza": ["44. MAZA, LIZA (MKBYN)"],
    "mendoza": ["45. MENDOZA, HEIDI (IND)"],
    "ramos": ["54. RAMOS, DANILO (MKBYN)"],
    "makabayan-senate": [
        "2. ADONIS, JEROME (MKBYN)",
        "4. ANDAMO, NARS ALYN (MKBYN)",
        "6. ARAMBULO, RONNEL (MKBYN)",
        "13. BROSAS, ARLENE (MKBYN)",
        "16. CASIÑO, TEDDY (MKBYN)",
        "17. CASTRO, TEACHER FRANCE (MKBYN)",
        "23. DORINGO, NANAY MIMI (MKBYN)",
        "26. FLORANDA, MODY PISTON (MKBYN)",
        "37. LIDASAN, AMIRAH (MKBYN)",
        "44. MAZA, LIZA (MKBYN)",
        "54. RAMOS, DANILO (MKBYN)",
    ],
}

PARTYLIST_CANDIDATES = {
    "akbayan": ["51 AKBAYAN"],
    "duterte-youth": ["5 DUTERTE YOUTH"],
    "bayan-muna": ["59 BAYAN MUNA"],
    "gabriela": ["46 GABRIELA"],
    "act-teachers": ["21 ACT TEACHERS"],
    "kabataan": ["4 KABATAAN"],
    "ml": ["6 ML"],
    "makabayan-partylist": [
        "59 BAYAN MUNA",
        "46 GABRIELA",
        "21 ACT TEACHERS",
        "4 KABATAAN",
    ],
}


def normalize_brgy(name):
    """normalize a barangay name for fuzzy matching."""
    n = name.upper().strip()
    # normalize unicode
    n = n.replace("Ñ", "N").replace("ñ", "N")
    n = n.replace("Ñ", "N")
    # strip common prefixes/suffixes
    n = re.sub(r"\s+", " ", n)
    # normalize punctuation
    n = n.replace(".", "").replace(",", "").replace("'", "").replace("`", "")
    n = n.replace("(", "").replace(")", "").replace("*", "")
    # normalize common abbreviations
    n = re.sub(r"\bSTA\b", "SANTA", n)
    n = re.sub(r"\bSTO\b", "SANTO", n)
    n = re.sub(r"\bST\b", "SAINT", n)
    n = re.sub(r"\bPOB\b", "POBLACION", n)
    n = re.sub(r"\bBRGY\b", "BARANGAY", n)
    n = re.sub(r"\bBGY\b", "BARANGAY", n)
    n = re.sub(r"\bGEN\b", "GENERAL", n)
    n = re.sub(r"\bHEN\b", "GENERAL", n)  # HEN. = Gen. in Filipino
    n = re.sub(r"\bSGT\b", "SERGEANT", n)
    n = re.sub(r"\bCOL\b", "COLONEL", n)
    n = re.sub(r"\bDR\b", "DOCTOR", n)
    n = n.replace("-", " ")
    n = re.sub(r"\s+", " ", n).strip()
    return n


def strip_suffix(name):
    """strip letter/number suffix from barangay name for subdivision matching.
    e.g. 'BARANGAY 176-A' -> 'BARANGAY 176', 'ZONE 1-A' -> 'ZONE 1'
    """
    # strip trailing letter suffix like "-A", " A", "-B" etc.
    n = re.sub(r"[\s-]+[A-Z]$", "", name.upper().strip())
    return n


def build_psgc_to_csv_muni():
    """
    build mapping from municipality PSGC code -> CSV (province, municipality).
    uses the provdist GeoJSON + region GeoJSON to establish the link.
    """
    # step 1: build province name -> PSGC from region files
    prov_lookup = {}
    regions_dir = GEO_BASE / "regions" / "hires"
    for fname in os.listdir(regions_dir):
        fpath = regions_dir / fname
        with open(fpath) as f:
            data = json.load(f)
        for feat in data.get("features", []):
            props = feat["properties"]
            name = props.get("adm2_en")
            if name:
                prov_lookup[props["adm2_psgc"]] = name.upper().strip()

    # step 2: build muni PSGC -> (province_name, muni_name) from provdist
    psgc_to_muni = {}
    provdist_dir = GEO_BASE / "provdists" / "hires"
    for fname in os.listdir(provdist_dir):
        fpath = provdist_dir / fname
        with open(fpath) as f:
            data = json.load(f)
        for feat in data.get("features", []):
            props = feat["properties"]
            muni_name = props.get("adm3_en")
            if not muni_name:
                continue
            prov_psgc = props["adm2_psgc"]
            muni_psgc = props["adm3_psgc"]
            prov_name = prov_lookup.get(prov_psgc, "")
            psgc_to_muni[muni_psgc] = (prov_name, muni_name.upper().strip())

    # step 3: add HUC entries
    for psgc, (prov, muni) in HUC_MAPPING.items():
        psgc_to_muni[psgc] = (prov, muni)

    return psgc_to_muni, prov_lookup


def build_csv_to_psgc(psgc_to_muni):
    """
    build reverse mapping: CSV (province, municipality) -> municipality PSGC.
    handles NCR fixes and spelling fixes.
    """
    # build GeoJSON (prov, muni) -> psgc
    geo_to_psgc = {}
    for psgc, (prov, muni) in psgc_to_muni.items():
        geo_to_psgc[(prov, muni)] = psgc

    return geo_to_psgc


def aggregate_csv_barangay(csv_path, candidate_mapping):
    """
    read CSV and aggregate votes to barangay level.
    returns: dict of (province, municipality, barangay) -> {rv, av, votes: {cid: count}}
    """
    brgy_data = defaultdict(lambda: {
        "rv": 0,
        "av": 0,
        "votes": defaultdict(int),
    })

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames

        col_map = {}
        for cand_id, col_names in candidate_mapping.items():
            col_map[cand_id] = [c for c in col_names if c in headers]

        row_count = 0
        for row in reader:
            region = row.get("region", "").strip()
            province = row.get("province", "").strip()
            municipality = row.get("municipality", "").strip()
            barangay = row.get("barangay", "").strip()

            if region in ("OAV", "LAV"):
                continue

            key = (province, municipality, barangay)
            entry = brgy_data[key]
            entry["rv"] += int(row.get("registeredVoters", 0) or 0)
            entry["av"] += int(row.get("actualVoters", 0) or 0)

            for cand_id, cols in col_map.items():
                for col in cols:
                    entry["votes"][cand_id] += int(row.get(col, 0) or 0)

            row_count += 1

    print(f"    processed {row_count} rows -> {len(brgy_data)} barangays")
    return dict(brgy_data)


def round_coords(coords, precision=4):
    """recursively round coordinate arrays to save space."""
    if isinstance(coords, (int, float)):
        return round(coords, precision)
    return [round_coords(c, precision) for c in coords]


def match_and_build(psgc_to_muni, csv_brgy_data):
    """
    match CSV barangays to GeoJSON barangay polygons.
    returns: (list of GeoJSON features, set of matched CSV keys)
    """
    hires_dir = GEO_BASE / "municities" / "hires"

    # group CSV data by (province, municipality) for efficient lookup
    csv_by_muni = defaultdict(dict)  # (prov, muni) -> {norm_brgy: [(brgy_key, data), ...]}
    csv_by_muni_exact = defaultdict(dict)
    for (prov, muni, brgy), data in csv_brgy_data.items():
        norm = normalize_brgy(brgy)
        # store as lists to handle multiple CSV brgys mapping to same normalized name
        if norm not in csv_by_muni[(prov, muni)]:
            csv_by_muni[(prov, muni)][norm] = []
        csv_by_muni[(prov, muni)][norm].append(((prov, muni, brgy), data))
        csv_by_muni_exact[(prov, muni)][brgy.upper().strip()] = ((prov, muni, brgy), data)

    # also build subdivision index: "BARANGAY 176" -> [176-A data, 176-B data, ...]
    csv_by_muni_stripped = defaultdict(lambda: defaultdict(list))
    for (prov, muni, brgy), data in csv_brgy_data.items():
        stripped = normalize_brgy(strip_suffix(brgy))
        csv_by_muni_stripped[(prov, muni)][stripped].append(((prov, muni, brgy), data))

    # also build index stripping parenthetical suffixes
    csv_by_muni_noparen = defaultdict(dict)
    for (prov, muni, brgy), data in csv_brgy_data.items():
        if "(" in brgy:
            bare = re.sub(r"\s*\(.*?\)\s*", "", brgy).strip()
            norm = normalize_brgy(bare)
            csv_by_muni_noparen[(prov, muni)][norm] = ((prov, muni, brgy), data)

    matched_features = []
    matched_brgys = 0
    unmatched_brgys = 0
    total_csv_brgys = len(csv_brgy_data)
    matched_csv_keys = set()

    # reverse NCR fixes for lookup
    ncr_reverse = {}
    for csv_name, geo_name in NCR_PROV_FIXES.items():
        ncr_reverse[geo_name] = csv_name

    for fname in sorted(os.listdir(hires_dir)):
        fpath = hires_dir / fname
        with open(fpath) as f:
            data = json.load(f)

        feats = data.get("features", [])
        if not feats:
            continue

        # figure out which CSV municipality this file corresponds to
        first_props = feats[0]["properties"]
        muni_psgc = first_props.get("adm3_psgc")

        if muni_psgc not in psgc_to_muni:
            # try adm2_psgc for HUCs where adm2==adm3
            adm2 = first_props.get("adm2_psgc")
            if adm2 in psgc_to_muni:
                muni_psgc = adm2
            else:
                continue

        geo_prov, geo_muni = psgc_to_muni[muni_psgc]

        # find the CSV (prov, muni) key - try direct match, then NCR fix, then name fixes
        csv_muni_key = None
        if (geo_prov, geo_muni) in csv_by_muni:
            csv_muni_key = (geo_prov, geo_muni)
        else:
            # try NCR reverse
            csv_prov = ncr_reverse.get(geo_prov)
            if csv_prov and (csv_prov, geo_muni) in csv_by_muni:
                csv_muni_key = (csv_prov, geo_muni)

        if not csv_muni_key:
            # try reverse name fixes
            for csv_name, geo_name in MUNI_NAME_FIXES.items():
                if geo_muni == geo_name:
                    if (geo_prov, csv_name) in csv_by_muni:
                        csv_muni_key = (geo_prov, csv_name)
                        break
                    csv_prov = ncr_reverse.get(geo_prov)
                    if csv_prov and (csv_prov, csv_name) in csv_by_muni:
                        csv_muni_key = (csv_prov, csv_name)
                        break

        if not csv_muni_key:
            # try "City of X" variations
            for prov_candidate in [geo_prov] + [ncr_reverse.get(geo_prov, "")]:
                if not prov_candidate:
                    continue
                if (prov_candidate, f"CITY OF {geo_muni}") in csv_by_muni:
                    csv_muni_key = (prov_candidate, f"CITY OF {geo_muni}")
                    break
                bare = geo_muni.replace("CITY OF ", "")
                if (prov_candidate, bare) in csv_by_muni:
                    csv_muni_key = (prov_candidate, bare)
                    break

        if not csv_muni_key:
            continue

        csv_brgys = csv_by_muni[csv_muni_key]
        csv_brgys_exact = csv_by_muni_exact[csv_muni_key]
        csv_brgys_stripped = csv_by_muni_stripped[csv_muni_key]
        csv_brgys_noparen = csv_by_muni_noparen[csv_muni_key]

        for feat in feats:
            props = feat["properties"]
            geom = feat.get("geometry")
            if not geom:
                continue

            geo_brgy = (props.get("adm4_en") or "").upper().strip()
            norm_geo = normalize_brgy(geo_brgy)

            # try matching: exact first, then normalized, then without parens, then subdivision merge
            matches = []
            if geo_brgy in csv_brgys_exact:
                matches = [csv_brgys_exact[geo_brgy]]
            elif norm_geo in csv_brgys:
                matches = csv_brgys[norm_geo]
            elif norm_geo in csv_brgys_noparen:
                matches = [csv_brgys_noparen[norm_geo]]

            # subdivision merge: if GeoJSON has "Barangay 176" but CSV has 176-A, 176-B, etc.
            if not matches and norm_geo in csv_brgys_stripped:
                sub_matches = csv_brgys_stripped[norm_geo]
                # only use if there are multiple subdivisions (otherwise it'd be a normal match)
                if len(sub_matches) > 1 or (len(sub_matches) == 1 and normalize_brgy(sub_matches[0][0][2]) != norm_geo):
                    matches = sub_matches

            # comma-prefix match: GeoJSON "Dagsian, Upper" or "BGY. NO. 42, APAYA"
            # -> try matching just the part before the comma when CSV has no suffix
            if not matches and "," in geo_brgy:
                prefix = geo_brgy.split(",")[0].strip()
                norm_prefix = normalize_brgy(prefix)
                if norm_prefix in csv_brgys:
                    matches = csv_brgys[norm_prefix]

            if matches:
                # merge all matched CSV entries into one feature
                total_rv = 0
                total_av = 0
                total_votes = defaultdict(int)
                brgy_names = []
                for csv_key, vote_data in matches:
                    matched_csv_keys.add(csv_key)
                    total_rv += vote_data["rv"]
                    total_av += vote_data["av"]
                    brgy_names.append(csv_key[2])
                    for cand_id, count in vote_data["votes"].items():
                        total_votes[cand_id] += count

                matched_brgys += 1
                # use first matched name as the display name
                display_name = brgy_names[0] if len(brgy_names) == 1 else brgy_names[0]

                # build minimal feature
                out_props = {
                    "p": matches[0][0][0],  # province
                    "m": matches[0][0][1],  # municipality
                    "b": display_name,      # barangay
                    "rv": total_rv,
                    "av": total_av,
                }
                for cand_id, count in total_votes.items():
                    out_props[f"v_{cand_id}"] = count

                matched_features.append({
                    "type": "Feature",
                    "properties": out_props,
                    "geometry": {
                        "type": geom["type"],
                        "coordinates": round_coords(geom["coordinates"], 3),
                    },
                })
            else:
                unmatched_brgys += 1

    unmatched_csv = total_csv_brgys - len(matched_csv_keys)
    print(f"\n    GeoJSON barangays matched: {matched_brgys}")
    print(f"    GeoJSON barangays unmatched: {unmatched_brgys}")
    print(f"    CSV barangays matched: {len(matched_csv_keys)}/{total_csv_brgys}")
    print(f"    CSV barangays without polygon: {unmatched_csv}")

    return matched_features, matched_csv_keys


# -- OSM PSGC -> municipality PSGC mapping --
# the first 7 digits of a 10-digit barangay PSGC give the municipality
# e.g. 1381100025 -> 1381100000 (City of Manila)
OSM_MUNI_PSGC_TO_CSV = {
    # NCR First District (Manila)
    1381100000: ("NATIONAL CAPITAL REGION - MANILA", "CITY OF MANILA"),
    # NCR Second District
    1380200000: ("NATIONAL CAPITAL REGION - SECOND DISTRICT", "CITY OF MANDALUYONG"),
    1380300000: ("NATIONAL CAPITAL REGION - SECOND DISTRICT", "CITY OF MAKATI"),
    1380400000: ("NATIONAL CAPITAL REGION - SECOND DISTRICT", "CITY OF MARIKINA"),
    1380500000: ("NATIONAL CAPITAL REGION - SECOND DISTRICT", "CITY OF PASIG"),
    1381300000: ("NATIONAL CAPITAL REGION - SECOND DISTRICT", "CITY OF SAN JUAN"),
    1380700000: ("NATIONAL CAPITAL REGION - SECOND DISTRICT", "PATEROS"),
    1381600000: ("NATIONAL CAPITAL REGION - SECOND DISTRICT", "CITY OF TAGUIG"),
    # NCR Third District
    1380800000: ("NATIONAL CAPITAL REGION - THIRD DISTRICT", "CITY OF CALOOCAN"),
    1381000000: ("NATIONAL CAPITAL REGION - THIRD DISTRICT", "CITY OF MALABON"),
    1381400000: ("NATIONAL CAPITAL REGION - THIRD DISTRICT", "CITY OF NAVOTAS"),
    1381500000: ("NATIONAL CAPITAL REGION - THIRD DISTRICT", "CITY OF VALENZUELA"),
    # NCR Fourth District
    1380600000: ("NATIONAL CAPITAL REGION - FOURTH DISTRICT", "CITY OF PARANAQUE"),
    1380900000: ("NATIONAL CAPITAL REGION - FOURTH DISTRICT", "CITY OF LAS PINAS"),
    1381200000: ("NATIONAL CAPITAL REGION - FOURTH DISTRICT", "CITY OF MUNTINLUPA"),
    1381701000: ("NATIONAL CAPITAL REGION - FOURTH DISTRICT", "CITY OF PASAY"),
    # Quezon City spans two sub-provinces in the CSV
    402109000: ("NATIONAL CAPITAL REGION - SECOND DISTRICT", "CITY OF QUEZON"),
    # Bulacan suburbs in NCR area
    301405000: ("BULACAN", "CITY OF MEYCAUAYAN"),
    301412000: ("BULACAN", "OBANDO"),
    301414000: ("BULACAN", "CITY OF SAN JOSE DEL MONTE"),
    # Cavite
    402103000: ("CAVITE", "CITY OF BACOOR"),
    402106000: ("CAVITE", "CITY OF DASMARINAS"),
    402108000: ("CAVITE", "CITY OF GENERAL TRIAS"),
    402111000: ("CAVITE", "CITY OF IMUS"),
    # Laguna
    405801000: ("LAGUNA", "CITY OF BINAN"),
    405802000: ("LAGUNA", "CITY OF CABUYAO"),
    405813000: ("LAGUNA", "CITY OF SANTA ROSA"),
    # Pasay sub-municipalities
    1380608000: ("NATIONAL CAPITAL REGION - FOURTH DISTRICT", "CITY OF PASAY"),
    1380609000: ("NATIONAL CAPITAL REGION - FOURTH DISTRICT", "CITY OF PASAY"),
    1380611000: ("NATIONAL CAPITAL REGION - FOURTH DISTRICT", "CITY OF PASAY"),
}


def match_osm_fallback(psgc_to_muni, csv_brgy_data, already_matched, osm_path):
    """
    match remaining unmatched CSV barangays against OSM boundary data.
    returns: list of additional GeoJSON features.
    """
    with open(osm_path) as f:
        osm_data = json.load(f)

    # build set of unmatched CSV entries
    unmatched = {}
    for key, data in csv_brgy_data.items():
        if key not in already_matched:
            unmatched[key] = data

    # group unmatched by (province, municipality) with normalized names
    unmatched_by_muni = defaultdict(dict)
    for (prov, muni, brgy), data in unmatched.items():
        norm = normalize_brgy(brgy)
        if norm not in unmatched_by_muni[(prov, muni)]:
            unmatched_by_muni[(prov, muni)][norm] = []
        unmatched_by_muni[(prov, muni)][norm].append(((prov, muni, brgy), data))

    # also stripped index for subdivision merging
    unmatched_by_muni_stripped = defaultdict(lambda: defaultdict(list))
    for (prov, muni, brgy), data in unmatched.items():
        stripped = normalize_brgy(strip_suffix(brgy))
        unmatched_by_muni_stripped[(prov, muni)][stripped].append(((prov, muni, brgy), data))

    # process OSM features
    new_features = []
    matched_count = 0
    newly_matched_keys = set()

    for feat in osm_data["features"]:
        props = feat["properties"]
        osm_name = props.get("name", "")
        psgc = props.get("psgc", "")
        geom = feat.get("geometry")

        if not geom or not osm_name:
            continue

        # determine which CSV municipality this OSM feature belongs to
        csv_muni_key = None
        if psgc and len(psgc) == 10:
            muni_psgc = int(psgc[:7] + "000")
            if muni_psgc in OSM_MUNI_PSGC_TO_CSV:
                csv_muni_key = OSM_MUNI_PSGC_TO_CSV[muni_psgc]

        if not csv_muni_key:
            # fallback for features without PSGC:
            # numbered barangays ("Barangay NNN") within Manila bbox -> assume Manila
            # named barangays -> try all unmatched municipalities
            import re as _re
            if _re.match(r"Barangay \d+", osm_name):
                # only assume Manila if centroid is within Manila City bbox
                try:
                    coords = (geom["coordinates"][0] if geom["type"] == "Polygon"
                              else geom["coordinates"][0][0])
                    clat = sum(c[1] for c in coords) / len(coords)
                    clon = sum(c[0] for c in coords) / len(coords)
                    if 14.55 <= clat <= 14.63 and 120.96 <= clon <= 121.02:
                        csv_muni_key = ("NATIONAL CAPITAL REGION - MANILA", "CITY OF MANILA")
                    else:
                        # numbered brgy outside Manila - try all munis
                        norm_osm_tmp = normalize_brgy(osm_name)
                        found_keys = []
                        for muni_key, brgys in unmatched_by_muni.items():
                            if norm_osm_tmp in brgys:
                                found_keys.append(muni_key)
                        if len(found_keys) == 1:
                            csv_muni_key = found_keys[0]
                        else:
                            continue
                except (KeyError, IndexError, ZeroDivisionError):
                    continue
            else:
                # try matching this name against all unmatched municipalities
                norm_osm_tmp = normalize_brgy(osm_name)
                found_keys = []
                for muni_key, brgys in unmatched_by_muni.items():
                    if norm_osm_tmp in brgys:
                        found_keys.append(muni_key)
                if len(found_keys) == 1:
                    csv_muni_key = found_keys[0]
                else:
                    continue

        if csv_muni_key not in unmatched_by_muni:
            # try without "CITY OF" prefix
            prov, muni = csv_muni_key
            alt_key = (prov, muni.replace("CITY OF ", ""))
            if alt_key in unmatched_by_muni:
                csv_muni_key = alt_key
            else:
                continue

        norm_osm = normalize_brgy(osm_name)

        # try matching
        muni_brgys = unmatched_by_muni[csv_muni_key]
        matches = muni_brgys.get(norm_osm, [])

        # try stripped match (subdivision merge)
        if not matches:
            stripped = normalize_brgy(strip_suffix(osm_name))
            stripped_brgys = unmatched_by_muni_stripped.get(csv_muni_key, {})
            sub_matches = stripped_brgys.get(stripped, [])
            if len(sub_matches) > 1 or (len(sub_matches) == 1 and normalize_brgy(sub_matches[0][0][2]) != norm_osm):
                matches = sub_matches

        # skip if already matched by main pass
        matches = [m for m in matches if m[0] not in newly_matched_keys]

        if matches:
            total_rv = 0
            total_av = 0
            total_votes = defaultdict(int)
            for csv_key, vote_data in matches:
                newly_matched_keys.add(csv_key)
                total_rv += vote_data["rv"]
                total_av += vote_data["av"]
                for cand_id, count in vote_data["votes"].items():
                    total_votes[cand_id] += count

            matched_count += 1
            out_props = {
                "p": matches[0][0][0],
                "m": matches[0][0][1],
                "b": matches[0][0][2],
                "rv": total_rv,
                "av": total_av,
            }
            for cand_id, count in total_votes.items():
                out_props[f"v_{cand_id}"] = count

            new_features.append({
                "type": "Feature",
                "properties": out_props,
                "geometry": {
                    "type": geom["type"],
                    "coordinates": round_coords(geom["coordinates"], 3),
                },
            })

    print(f"    OSM features checked: {len(osm_data['features'])}")
    print(f"    OSM barangays matched: {matched_count}")
    print(f"    CSV barangays newly matched: {len(newly_matched_keys)}")
    remaining = len(unmatched) - len(newly_matched_keys)
    print(f"    still unmatched: {remaining}")

    return new_features, newly_matched_keys


# -- CSV province -> HDX ADM2_EN mapping for provinces with different naming --
CSV_PROV_TO_HDX_ADM2 = {
    "NATIONAL CAPITAL REGION - MANILA": "Metropolitan Manila First District",
    "NATIONAL CAPITAL REGION - SECOND DISTRICT": "Metropolitan Manila Second District",
    "NATIONAL CAPITAL REGION - THIRD DISTRICT": "Metropolitan Manila Third District",
    "NATIONAL CAPITAL REGION - FOURTH DISTRICT": "Metropolitan Manila Fourth District",
    "BASILAN": "City of Isabela (not a province)",
    "SPECIAL GEOGRAPHIC AREA": None,  # no HDX equivalent
    "DAVAO DEL NORTE": "Davao del Norte",
    "COMPOSTELA VALLEY": "Davao de Oro",
}


def normalize_muni_name(name):
    """normalize a municipality name for fuzzy matching against HDX ADM3_EN."""
    n = name.upper().strip()
    n = n.replace("Ñ", "N").replace("ñ", "N").replace("Ñ", "N")
    n = n.replace(".", "").replace(",", "").replace("'", "").replace("`", "")
    # strip parenthetical qualifiers like (Capital), (Bugho) BEFORE general cleanup
    n = re.sub(r"\s*\([^)]*\)", "", n)
    n = re.sub(r"^CITY OF\s+", "", n)
    n = re.sub(r"\s+CITY$", "", n)
    n = re.sub(r"\bSTA\b", "SANTA", n)
    n = re.sub(r"\bSTO\b", "SANTO", n)
    n = re.sub(r"\bGEN\b", "GENERAL", n)
    n = n.replace("-", " ")
    n = re.sub(r"\s+", " ", n).strip()
    return n


def build_hdx_muni_index():
    """
    build index of HDX municipalities from the GDB using ogr2ogr CSV export.
    returns: dict of (norm_muni_name, adm2_en_upper) -> ADM3_PCODE
             dict of ADM3_PCODE -> (ADM3_EN, ADM2_EN)
    """
    result = subprocess.run(
        ["ogr2ogr", "-f", "CSV", "/dev/stdout", str(HDX_GDB), HDX_LAYER,
         "-select", "ADM4_EN,ADM3_EN,ADM3_PCODE,ADM2_EN"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        print(f"    ERROR: ogr2ogr failed: {result.stderr}")
        return {}, {}

    muni_index = {}  # (norm_name, adm2_upper) -> pcode
    pcode_info = {}  # pcode -> (adm3_en, adm2_en)

    reader = csv.DictReader(result.stdout.splitlines())
    for row in reader:
        pcode = row["ADM3_PCODE"]
        adm3 = row["ADM3_EN"]
        adm2 = row["ADM2_EN"]
        if pcode not in pcode_info:
            pcode_info[pcode] = (adm3, adm2)
            norm = normalize_muni_name(adm3)
            muni_index[(norm, adm2.upper())] = pcode
            # also index without province for unique names
            if (norm, "") not in muni_index:
                muni_index[(norm, "")] = pcode
            else:
                # mark as ambiguous
                muni_index[(norm, "")] = None

    return muni_index, pcode_info


def extract_hdx_features(adm3_pcode):
    """
    extract barangay features for a single municipality from the HDX GDB.
    uses ogr2ogr to query the GDB and returns parsed GeoJSON features.
    """
    result = subprocess.run(
        ["ogr2ogr", "-f", "GeoJSON", "/dev/stdout", str(HDX_GDB), HDX_LAYER,
         "-select", "ADM4_EN,ADM4_PCODE,ADM3_EN",
         "-where", f"ADM3_PCODE = '{adm3_pcode}'",
         "-lco", "COORDINATE_PRECISION=4"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return []

    try:
        data = json.loads(result.stdout)
        return data.get("features", [])
    except json.JSONDecodeError:
        return []


def match_hdx_fallback(csv_brgy_data, already_matched):
    """
    match remaining unmatched CSV barangays against HDX/OCHA geodatabase.
    uses ogr2ogr to extract per-municipality features from the GDB.
    returns: (list of GeoJSON features, set of matched CSV keys)
    """
    # build set of unmatched CSV entries
    unmatched = {}
    for key, data in csv_brgy_data.items():
        if key not in already_matched:
            unmatched[key] = data

    if not unmatched:
        print("    no unmatched barangays - nothing to do")
        return [], set()

    # group unmatched by (province, municipality)
    unmatched_by_muni = defaultdict(dict)
    for (prov, muni, brgy), data in unmatched.items():
        norm = normalize_brgy(brgy)
        if norm not in unmatched_by_muni[(prov, muni)]:
            unmatched_by_muni[(prov, muni)][norm] = []
        unmatched_by_muni[(prov, muni)][norm].append(((prov, muni, brgy), data))

    # stripped index for subdivision merging
    unmatched_by_muni_stripped = defaultdict(lambda: defaultdict(list))
    for (prov, muni, brgy), data in unmatched.items():
        stripped = normalize_brgy(strip_suffix(brgy))
        unmatched_by_muni_stripped[(prov, muni)][stripped].append(((prov, muni, brgy), data))

    # parenthetical-stripped index
    unmatched_by_muni_noparen = defaultdict(dict)
    for (prov, muni, brgy), data in unmatched.items():
        if "(" in brgy:
            bare = re.sub(r"\s*\(.*?\)\s*", "", brgy).strip()
            norm = normalize_brgy(bare)
            unmatched_by_muni_noparen[(prov, muni)][norm] = ((prov, muni, brgy), data)

    # build HDX municipality index
    print("    building HDX municipality index...")
    muni_index, pcode_info = build_hdx_muni_index()
    print(f"    {len(pcode_info)} HDX municipalities indexed")

    # map each unmatched CSV municipality to an HDX ADM3_PCODE
    csv_muni_to_pcode = {}
    unmatched_municipalities = set(unmatched_by_muni.keys())

    for (prov, muni) in unmatched_municipalities:
        norm = normalize_muni_name(muni)

        # try province-aware match first
        hdx_adm2 = CSV_PROV_TO_HDX_ADM2.get(prov)
        if hdx_adm2 is None and prov in CSV_PROV_TO_HDX_ADM2:
            # explicitly mapped to None (e.g. SGA) - skip
            continue
        if hdx_adm2 is None:
            # use province name directly (works for most provinces)
            hdx_adm2 = prov.title()

        pcode = muni_index.get((norm, hdx_adm2.upper()))
        if not pcode:
            # try without province (unique match only)
            pcode = muni_index.get((norm, ""))
        if pcode:
            csv_muni_to_pcode[(prov, muni)] = pcode

    print(f"    mapped {len(csv_muni_to_pcode)}/{len(unmatched_municipalities)} unmatched municipalities to HDX")

    # extract features and match barangays
    new_features = []
    newly_matched_keys = set()
    munis_with_matches = 0

    for (prov, muni), pcode in sorted(csv_muni_to_pcode.items()):
        hdx_features = extract_hdx_features(pcode)
        if not hdx_features:
            continue

        csv_brgys = unmatched_by_muni[(prov, muni)]
        csv_brgys_stripped = unmatched_by_muni_stripped[(prov, muni)]
        csv_brgys_noparen = unmatched_by_muni_noparen.get((prov, muni), {})
        muni_matched = 0

        for feat in hdx_features:
            props = feat["properties"]
            hdx_brgy = (props.get("ADM4_EN") or "").strip()
            geom = feat.get("geometry")

            if not geom or not hdx_brgy:
                continue

            norm_hdx = normalize_brgy(hdx_brgy)

            # try matching
            matches = csv_brgys.get(norm_hdx, [])
            if not matches and norm_hdx in csv_brgys_noparen:
                matches = [csv_brgys_noparen[norm_hdx]]

            # try with parenthetical stripped from HDX name (e.g. "La Piedad (Pob.)" -> "La Piedad")
            if not matches and "(" in hdx_brgy:
                bare_hdx = re.sub(r"\s*\(.*?\)\s*", "", hdx_brgy).strip()
                norm_bare = normalize_brgy(bare_hdx)
                matches = csv_brgys.get(norm_bare, [])

            # subdivision merge
            if not matches:
                stripped = normalize_brgy(strip_suffix(hdx_brgy))
                sub_matches = csv_brgys_stripped.get(stripped, [])
                if len(sub_matches) > 1 or (len(sub_matches) == 1 and normalize_brgy(sub_matches[0][0][2]) != norm_hdx):
                    matches = sub_matches

            # comma-prefix match
            if not matches and "," in hdx_brgy:
                prefix = hdx_brgy.split(",")[0].strip()
                norm_prefix = normalize_brgy(prefix)
                matches = csv_brgys.get(norm_prefix, [])

            # skip already matched
            matches = [m for m in matches if m[0] not in newly_matched_keys]

            if matches:
                total_rv = 0
                total_av = 0
                total_votes = defaultdict(int)
                for csv_key, vote_data in matches:
                    newly_matched_keys.add(csv_key)
                    total_rv += vote_data["rv"]
                    total_av += vote_data["av"]
                    for cand_id, count in vote_data["votes"].items():
                        total_votes[cand_id] += count

                muni_matched += 1
                out_props = {
                    "p": matches[0][0][0],
                    "m": matches[0][0][1],
                    "b": matches[0][0][2],
                    "rv": total_rv,
                    "av": total_av,
                }
                for cand_id, count in total_votes.items():
                    out_props[f"v_{cand_id}"] = count

                new_features.append({
                    "type": "Feature",
                    "properties": out_props,
                    "geometry": {
                        "type": geom["type"],
                        "coordinates": round_coords(geom["coordinates"], 3),
                    },
                })

        if muni_matched:
            munis_with_matches += 1

    print(f"    HDX municipalities with matches: {munis_with_matches}")
    print(f"    HDX barangays matched: {len(new_features)}")
    print(f"    CSV barangays newly matched: {len(newly_matched_keys)}")
    remaining = len(unmatched) - len(newly_matched_keys)
    print(f"    still unmatched: {remaining}")

    return new_features, newly_matched_keys


def main():
    print("building barangay choropleth data...\n")

    # step 1: build PSGC mapping
    print("step 1: building municipality PSGC mapping...")
    psgc_to_muni, prov_lookup = build_psgc_to_csv_muni()
    print(f"    {len(psgc_to_muni)} municipality PSGC entries")

    # step 2: aggregate senate CSV to barangay level
    print("\nstep 2: aggregating senate CSV data...")
    senate_csv = SOURCES_DIR / "senate25-final_updated.csv"
    senate_data = aggregate_csv_barangay(senate_csv, SENATE_CANDIDATES)

    # step 3: aggregate partylist CSV to barangay level
    print("\nstep 3: aggregating partylist CSV data...")
    partylist_csv = SOURCES_DIR / "partylist25-final_updated.csv"
    partylist_data = aggregate_csv_barangay(partylist_csv, PARTYLIST_CANDIDATES)

    # step 4: merge senate + partylist data
    print("\nstep 4: merging senate + partylist data...")
    merged = {}
    all_keys = set(senate_data.keys()) | set(partylist_data.keys())
    for key in all_keys:
        s = senate_data.get(key)
        p = partylist_data.get(key)
        if s and p:
            merged[key] = {
                "rv": s["rv"],
                "av": s["av"],
                "votes": {**s["votes"], **p["votes"]},
            }
        elif s:
            merged[key] = s
        else:
            merged[key] = p
    print(f"    merged: {len(merged)} barangays")

    # step 5: match barangays and build features
    print("\nstep 5: matching barangays to GeoJSON polygons...")
    features, matched_csv_keys = match_and_build(psgc_to_muni, merged)

    # step 5b: fill gaps with OSM barangay boundaries
    osm_path = SOURCES_DIR / "osm_barangays.geojson"
    if osm_path.exists():
        print("\nstep 5b: filling gaps with OSM barangay boundaries...")
        osm_features, osm_matched_keys = match_osm_fallback(psgc_to_muni, merged, matched_csv_keys, osm_path)
        features.extend(osm_features)
        matched_csv_keys = matched_csv_keys | osm_matched_keys
    else:
        print("\n    (skipping OSM fallback - osm_barangays.geojson not found)")
        print("    run: python scripts/fetchOsmBarangays.py")

    # step 5c: fill remaining gaps with HDX/OCHA geodatabase
    if HDX_GDB.exists():
        print("\nstep 5c: filling gaps with HDX/OCHA barangay boundaries...")
        hdx_features, hdx_matched_keys = match_hdx_fallback(merged, matched_csv_keys)
        features.extend(hdx_features)
        matched_csv_keys = matched_csv_keys | hdx_matched_keys
    else:
        print("\n    (skipping HDX fallback - geodatabase not found)")
        print(f"    download from: https://data.humdata.org/dataset/cod-ab-phl")
        print(f"    extract to: {HDX_GDB}")

    # step 6: write output
    print("\nstep 6: writing output...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "barangays.geojson"

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    # write compact JSON (no whitespace)
    raw = json.dumps(geojson, separators=(",", ":"))
    with open(output_path, "w") as f:
        f.write(raw)

    raw_mb = len(raw) / 1024 / 1024
    print(f"\noutput: {output_path}")
    print(f"    {len(features)} barangays, {raw_mb:.2f} MB")

    # check gzip size
    import gzip
    gz = gzip.compress(raw.encode())
    gz_mb = len(gz) / 1024 / 1024
    print(f"    gzipped: {gz_mb:.2f} MB")

    print("\ndone!")


if __name__ == "__main__":
    main()
