import { useState, useCallback, useEffect, useRef } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import { ChoroplethLayer } from "./ChoroplethLayer";
import type { SearchResult } from "./SearchBar";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { BarangayCollection, BarangayProperties } from "../types";

interface MapViewProps {
    data: BarangayCollection;
    candidateId: string;
    candidateColor: string;
    loading: boolean;
    searchSelection: SearchResult | null;
    highContrast: boolean;
}

// philippines center coordinates
const PH_CENTER: [number, number] = [12.5, 122.0];
const PH_ZOOM = 6;

// tooltip component rendered via state
function Tooltip({
    props,
    candidateId,
    color,
    position,
}: {
    props: BarangayProperties;
    candidateId: string;
    color: string;
    position: { x: number; y: number };
}) {
    const votes = (props[`v_${candidateId}`] as number) ?? 0;
    const av = props.av ?? 0;
    const share = av > 0 ? ((votes / av) * 100).toFixed(1) : "0.0";

    return (
        <div
            className="pointer-events-none fixed z-1000 rounded-lg border border-neutral-700 bg-neutral-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm"
            style={{ left: position.x + 12, top: position.y - 10 }}
        >
            <p className="mb-0.5 font-medium lowercase text-neutral-200">
                {props.b}
            </p>
            <p className="lowercase text-neutral-500">
                {props.m}, {props.p}
            </p>
            <div className="mt-1.5 border-t border-neutral-800 pt-1.5">
                <div className="flex items-center justify-between gap-4">
                    <span className="text-neutral-400">votes</span>
                    <span style={{ color }} className="font-medium">
                        {votes.toLocaleString()}
                    </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                    <span className="text-neutral-400">share</span>
                    <span style={{ color }} className="font-medium">
                        {share}%
                    </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                    <span className="text-neutral-400">turnout</span>
                    <span className="text-neutral-300">
                        {av.toLocaleString()} / {props.rv.toLocaleString()}
                    </span>
                </div>
            </div>
        </div>
    );
}

// zoom map to matching features when search selection changes
function MapZoomController({
    data,
    searchSelection,
}: {
    data: BarangayCollection;
    searchSelection: SearchResult | null;
}) {
    const map = useMap();

    useEffect(() => {
        if (!searchSelection) return;

        // find matching features and compute bounds
        const bounds = L.latLngBounds([]);
        for (const feat of data.features) {
            const props = feat.properties;
            if (!props) continue;

            let match = false;
            if (searchSelection.type === "municipality") {
                match =
                    props.m === searchSelection.municipality &&
                    props.p === searchSelection.province;
            } else {
                match =
                    props.b === searchSelection.barangay &&
                    props.m === searchSelection.municipality &&
                    props.p === searchSelection.province;
            }

            if (match && feat.geometry) {
                // extract bounds from the geometry
                const geoLayer = L.geoJSON(feat as GeoJSON.Feature);
                bounds.extend(geoLayer.getBounds());
            }
        }

        if (bounds.isValid()) {
            map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
        }
    }, [searchSelection, data, map]);

    return null;
}

export function MapView({
    data,
    candidateId,
    candidateColor,
    loading,
    searchSelection,
    highContrast,
}: MapViewProps) {
    const [hoveredProps, setHoveredProps] =
        useState<BarangayProperties | null>(null);
    const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
    const containerRef = useRef<HTMLDivElement>(null);

    // track mouse position on the container for tooltip placement
    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        const handler = (e: MouseEvent) => {
            setTooltipPos({ x: e.clientX, y: e.clientY });
        };
        el.addEventListener("mousemove", handler);
        return () => el.removeEventListener("mousemove", handler);
    }, []);

    const handleFeatureHover = useCallback(
        (props: BarangayProperties | null, _latlng?: L.LatLng) => {
            setHoveredProps(props);
        },
        []
    );

    return (
        <div ref={containerRef} className="relative h-full w-full">
            {loading && (
                <div className="absolute inset-0 z-50 flex items-center justify-center bg-neutral-950/80">
                    <div className="flex flex-col items-center gap-3">
                        <div className="h-8 w-8 animate-spin rounded-full border-2 border-neutral-700 border-t-orange-400" />
                        <span className="text-xs text-neutral-500">
                            loading barangay data...
                        </span>
                    </div>
                </div>
            )}
            <MapContainer
                center={PH_CENTER}
                zoom={PH_ZOOM}
                minZoom={5}
                maxZoom={18}
                preferCanvas={true}
                style={{ height: "100%", width: "100%" }}
                zoomControl={true}
                attributionControl={true}
            >
                <TileLayer
                    url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                    subdomains="abcd"
                    maxZoom={20}
                />
                {data.features.length > 0 && (
                    <ChoroplethLayer
                        data={data}
                        candidateId={candidateId}
                        color={candidateColor}
                        onFeatureHover={handleFeatureHover}
                        searchSelection={searchSelection}
                        highContrast={highContrast}
                    />
                )}
                <MapZoomController data={data} searchSelection={searchSelection} />
            </MapContainer>
            {hoveredProps && (
                <Tooltip
                    props={hoveredProps}
                    candidateId={candidateId}
                    color={candidateColor}
                    position={tooltipPos}
                />
            )}
        </div>
    );
}
