# 2025 philippine national electoral analysis

a barangay-level choropleth dashboard for the 2025 philippine midterm elections, covering all 66 senate candidates and 166+ partylist groups across ~41,300 barangays. built with vite, react, typescript, tailwind css, and leaflet

## features

- **barangay-level choropleth map** - renders ~41,300 high-resolution barangay polygons (99.8% of all barangays) on a dark-themed leaflet map. uses canvas rendering instead of svg for smooth pan/zoom even with tens of thousands of features
- **senate and partylist datasets** - switch between senate and partylist vote distributions using dataset tabs. each dataset has its own set of candidates with independent vote counts and share calculations
- **candidate selection** - pick any candidate to colorize the map by their vote share per barangay. color intensity is sqrt-scaled so low-vote areas are still visible instead of being washed out
- **multi-hue / single-hue color modes** - toggle between a multi-hue gradient (navy -> teal -> green -> amber -> red -> white) for maximizing perceptual contrast, and a single-hue gradient that scales from black to the candidate's assigned color
- **searchable locations** - typeahead search across all barangays and municipalities. selecting a result auto-zooms and highlights the matching feature on the map
- **hover tooltips** - hovering a barangay shows its name, municipality, province, vote count, vote share percentage, and voter turnout
- **responsive sidebar** - collapsible candidate panel with stats summary, color legend, and dataset tabs. collapses to a floating toggle button on smaller screens
- **dark theme** - neutral-950 background with orange-400 accents throughout all ui elements, including map tiles (carto dark matter)

## tech stack

| layer           | tool                                        |
|-----------------|---------------------------------------------|
| framework       | react 19 + typescript 5.7                   |
| bundler         | vite 6                                      |
| styling         | tailwind css 4                              |
| mapping         | leaflet + react-leaflet 5 (canvas renderer) |
| tiles           | carto dark matter (raster)                  |
| data processing | python 3 (stdlib only, no pip dependencies) |
| hosting         | vercel (static)                             |

## data sources

| source                                                                                                                          | description                                                                                                      |                      size |
|---------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|---------------------------|
| [2025 philippine midterm elections data](https://figshare.com/articles/dataset/2025_Philippine_Midterm_Elections_Data/29086472) | precinct-level comelec results for all 66 senate candidates and 166+ partylist groups, ~92k rows per csv         | ~60 mb                    |
| [faeldon/philippines-json-maps](https://github.com/faeldon/philippines-json-maps)                                               | barangay boundary polygons based on psgc 2023 (high-resolution geojson)                                          | ~1,600 municipality files |
| [openstreetmap overpass api](https://overpass-api.de/)                                                                          | admin_level=10 boundaries for ncr and basilan, used to fill gaps where the primary source has empty geometries   | ~1,100 features           |
| [hdx/ocha administrative boundaries](https://data.humdata.org/dataset/cod-ab-phl)                                               | psa/namria geodatabase with 42k barangay features, used as a tertiary fallback for remaining unmatched barangays | ~346 mb                   |

## running locally

### prerequisites

- node.js 18+
- npm
- python 3.10+ (only needed for rebuilding the geojson data)
- gdal/ogr2ogr (only needed for the hdx gap-fill step during data rebuild)

### setup

```sh
git clone https://github.com/flame-0/2025-nea.git
cd 2025-nea/dashboard
npm install
npm run dev
```

the dev server starts at `http://localhost:5173`. the pre-built `barangays.geojson` is included in the repo, so the dashboard works immediately without running any python scripts

### build for production

```sh
npm run build
npm run preview
```

outputs to `dashboard/dist/`

### rebuilding the geojson data

a single script downloads all source data and runs the build:

```sh
python scripts/setup_data.py
```

what it does:

1. downloads the senate and partylist csvs from figshare (~60 mb total)
2. clones [faeldon/philippines-json-maps](https://github.com/faeldon/philippines-json-maps) using git sparse checkout (only the hires directories)
3. fetches ncr and basilan barangay boundaries from openstreetmap via overpass api
4. downloads the hdx/ocha administrative boundaries geodatabase (~346 mb), extracts it with ogr2ogr
5. runs `buildBarangayChoropleth.py` to match election data to polygons and produce `public/data/barangays.geojson`

all source data goes into `data/sources/` (gitignored). the only system dependency beyond python 3 is gdal/ogr2ogr for step 4

**flags:**

- `--skip-download` - skip all downloads, only run the build step (useful when sources are already downloaded)
- `--download-only` - download all sources without running the build

**output:** `dashboard/public/data/barangays.geojson` (~54 mb raw, ~6 mb gzipped)

## project structure

```
2025-nea/
    data/
        sources/                        # all downloaded source data (gitignored)
    dashboard/
        public/
            data/
                barangays.geojson       # pre-built choropleth geojson
        src/
            components/
                CandidatePanel.tsx      # sidebar: search, candidate list, stats, legend
                ChoroplethLayer.tsx     # leaflet geojson layer with color modes
                MapView.tsx             # map container with tooltip overlay
                SearchBar.tsx           # typeahead location search
            data/
                candidates.ts           # candidate id/name/color configs
            types/
                index.ts                # shared typescript interfaces
            App.tsx                     # root component, data loading + state
            main.tsx                    # entry point
        scripts/
            setup_data.py               # downloads all sources + runs build
            buildBarangayChoropleth.py  # matches election data to polygons
        package.json
        vite.config.ts
        tsconfig.json
    vercel.json
    .gitignore
```

## data pipeline

`buildBarangayChoropleth.py` processes data in six steps:

1. **psgc mapping** - reads the geojson source directory structure to build a lookup table from municipality psgc codes to their csv-side (province, municipality) names. handles highly urbanized cities (huc) and ncr district naming differences between comelec and psgc conventions

2. **csv aggregation** - reads each precinct-level csv (~92k rows) and aggregates vote counts up to the barangay level, producing ~41,400 unique barangay records keyed by (province, municipality, barangay)

3. **primary polygon matching** - for each municipality geojson file, normalizes barangay names (lowercasing, stripping sto./sta./san prefixes, removing suffixes like "poblacion", handling roman numerals) and matches them against the csv records. also merges subdivided barangays (e.g. "barangay 176-a" + "barangay 176-b" into "barangay 176") when the geojson has a single polygon for the parent name. result: **~40,360 matches**

4. **osm gap-fill** - for the ~1,000 barangays still unmatched (mostly in ncr where the primary source has empty geometries), fetches admin_level=10 boundaries from openstreetmap. matches by psgc code where available, and by name + bounding box heuristics for manila's numbered barangays. result: **~285 matches**

5. **hdx gap-fill** - for the remaining ~770 unmatched barangays, extracts per-municipality features from the hdx/ocha geodatabase using ogr2ogr. matches by normalized name with province-aware disambiguation, stripping parenthetical suffixes like "(pob.)" from hdx names. result: **~685 matches**

6. **output** - writes a single geojson file with coordinates rounded to 5 decimal places and only the essential properties: province, municipality, barangay name, registered voters, actual voters, and per-candidate vote counts (keyed by short candidate ids like "s01", "p01")

**final result:** 41,333 barangays out of 41,401 in the election data (99.8% coverage)

## known limitations

- **~56 barmm barangays unmatched** - these are special geographic area (sga) barangays created or redistricted after the 2019 bangsamoro transition. the boundary sources still use pre-transition boundaries, so there are no matching polygons for these
- **~35 barangays with name mismatches** - scattered across leyte, pangasinan, palawan, and other provinces where the comelec csv uses a different spelling or alternate name than the boundary sources (e.g. "bagong silang" vs "new silang")
- **~6 mb initial load** - the gzipped geojson is fetched on first page load, which may take a few seconds on slower connections. there is no progressive loading or tiling
