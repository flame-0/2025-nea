import { useEffect, useRef, useCallback } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import type { BarangayCollection, BarangayProperties } from "../types";
import type { SearchResult } from "./SearchBar";

interface ChoroplethLayerProps {
    data: BarangayCollection;
    candidateId: string;
    color: string;
    onFeatureHover: (props: BarangayProperties | null, latlng?: L.LatLng) => void;
    searchSelection: SearchResult | null;
    highContrast: boolean;
}

// convert hex to rgb components
function hexToRgb(hex: string): [number, number, number] {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result
        ? [parseInt(result[1], 16), parseInt(result[2], 16), parseInt(result[3], 16)]
        : [251, 146, 60];
}

// single-hue fill: dark -> candidate color
function getFillColor(share: number, color: string): string {
    const [r, g, b] = hexToRgb(color);
    const t = Math.sqrt(Math.min(share, 1));
    const minBrightness = 0.08;
    const factor = minBrightness + t * (1 - minBrightness);
    return `rgb(${Math.round(r * factor)}, ${Math.round(g * factor)}, ${Math.round(b * factor)})`;
}

// multi-hue gradient stops: dark navy -> teal -> yellow -> hot white
// designed to maximize perceptual contrast across the full range
const MULTI_HUE_STOPS: [number, number, number, number][] = [
    [0.0, 10, 10, 30],      // near-black navy
    [0.15, 15, 60, 90],     // deep blue
    [0.3, 20, 120, 120],    // teal
    [0.45, 40, 170, 100],   // green
    [0.6, 160, 200, 40],    // lime-yellow
    [0.75, 240, 180, 30],   // amber
    [0.9, 250, 100, 40],    // orange-red
    [1.0, 255, 240, 220],   // hot white
];

function getMultiHueFillColor(share: number): string {
    const t = Math.sqrt(Math.min(share, 1));
    // find the two stops to interpolate between
    let lo = MULTI_HUE_STOPS[0];
    let hi = MULTI_HUE_STOPS[MULTI_HUE_STOPS.length - 1];
    for (let i = 0; i < MULTI_HUE_STOPS.length - 1; i++) {
        if (t >= MULTI_HUE_STOPS[i][0] && t <= MULTI_HUE_STOPS[i + 1][0]) {
            lo = MULTI_HUE_STOPS[i];
            hi = MULTI_HUE_STOPS[i + 1];
            break;
        }
    }
    const range = hi[0] - lo[0] || 1;
    const f = (t - lo[0]) / range;
    const r = Math.round(lo[1] + (hi[1] - lo[1]) * f);
    const g = Math.round(lo[2] + (hi[2] - lo[2]) * f);
    const b = Math.round(lo[3] + (hi[3] - lo[3]) * f);
    return `rgb(${r}, ${g}, ${b})`;
}

export function ChoroplethLayer({
    data,
    candidateId,
    color,
    onFeatureHover,
    searchSelection,
    highContrast,
}: ChoroplethLayerProps) {
    const map = useMap();
    const layerRef = useRef<L.GeoJSON | null>(null);
    const candidateIdRef = useRef(candidateId);
    const colorRef = useRef(color);
    const searchRef = useRef<SearchResult | null>(null);
    const highContrastRef = useRef(highContrast);

    // compute max share across all features for normalization
    const maxShareRef = useRef(0);

    const computeMaxShare = useCallback(
        (cId: string) => {
            let max = 0;
            for (const feat of data.features) {
                const props = feat.properties;
                if (!props) continue;
                const votes = (props[`v_${cId}`] as number) ?? 0;
                const av = props.av ?? 0;
                if (av > 0) {
                    const share = votes / av;
                    if (share > max) max = share;
                }
            }
            return max || 1;
        },
        [data]
    );

    const getStyle = useCallback(
        (feature: GeoJSON.Feature | undefined): L.PathOptions => {
            if (!feature?.properties) {
                return { fillColor: "#000", fillOpacity: 0.8, weight: 0.3, color: "#222", opacity: 0.4 };
            }
            const props = feature.properties as BarangayProperties;
            const votes = (props[`v_${candidateIdRef.current}`] as number) ?? 0;
            const av = props.av ?? 0;
            const share = av > 0 ? votes / av : 0;
            const normalized = maxShareRef.current > 0 ? share / maxShareRef.current : 0;

            // check if this feature matches the search selection
            const sel = searchRef.current;
            let isMatch = true;
            if (sel) {
                if (sel.type === "municipality") {
                    isMatch = props.m === sel.municipality && props.p === sel.province;
                } else {
                    isMatch = props.b === sel.barangay && props.m === sel.municipality && props.p === sel.province;
                }
            }

            return {
                fillColor: highContrastRef.current
                    ? getMultiHueFillColor(normalized)
                    : getFillColor(normalized, colorRef.current),
                fillOpacity: sel ? (isMatch ? 0.9 : 0.15) : 0.85,
                weight: sel && isMatch ? 1.5 : 0.3,
                color: sel && isMatch ? "#fff" : "#222",
                opacity: sel && isMatch ? 0.8 : 0.4,
            };
        },
        []
    );

    // initial layer creation
    useEffect(() => {
        if (!data.features.length) return;

        maxShareRef.current = computeMaxShare(candidateId);
        candidateIdRef.current = candidateId;
        colorRef.current = color;

        const canvasRenderer = L.canvas({ padding: 0.5 });

        const geoJsonOptions = {
            renderer: canvasRenderer,
            style: getStyle,
            onEachFeature: (_feature: GeoJSON.Feature, layer: L.Layer) => {
                layer.on({
                    mouseover: (e: L.LeafletMouseEvent) => {
                        const l = e.target as L.Path;
                        l.setStyle({ weight: 2, color: "#fff", opacity: 0.8 });
                        l.bringToFront();
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        const props = (e.target as any).feature?.properties as BarangayProperties;
                        onFeatureHover(props, e.latlng);
                    },
                    mouseout: (e: L.LeafletMouseEvent) => {
                        layerRef.current?.resetStyle(e.target as L.Path);
                        onFeatureHover(null);
                    },
                    mousemove: (e: L.LeafletMouseEvent) => {
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        const props = (e.target as any).feature?.properties as BarangayProperties;
                        onFeatureHover(props, e.latlng);
                    },
                });
            },
        };

        const layer = L.geoJSON(data as GeoJSON.GeoJsonObject, geoJsonOptions as L.GeoJSONOptions);

        layer.addTo(map);
        layerRef.current = layer;

        return () => {
            if (layerRef.current) {
                map.removeLayer(layerRef.current);
                layerRef.current = null;
            }
        };
    }, [data, map]); // eslint-disable-line react-hooks/exhaustive-deps

    // update styles when candidate, color, or contrast mode changes
    useEffect(() => {
        if (!layerRef.current) return;

        candidateIdRef.current = candidateId;
        colorRef.current = color;
        highContrastRef.current = highContrast;
        maxShareRef.current = computeMaxShare(candidateId);

        layerRef.current.setStyle(getStyle);
    }, [candidateId, color, highContrast, computeMaxShare, getStyle]);

    // update styles when search selection changes (highlight/dim)
    useEffect(() => {
        searchRef.current = searchSelection;
        if (!layerRef.current) return;
        layerRef.current.setStyle(getStyle);
    }, [searchSelection, getStyle]);

    return null;
}
