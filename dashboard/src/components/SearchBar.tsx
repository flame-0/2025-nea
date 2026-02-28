import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import type { BarangayCollection } from "../types";

export interface SearchResult {
    label: string;
    type: "barangay" | "municipality";
    province: string;
    municipality: string;
    barangay?: string;
}

interface SearchBarProps {
    data: BarangayCollection;
    onSelect: (result: SearchResult | null) => void;
}

export function SearchBar({ data, onSelect }: SearchBarProps) {
    const [query, setQuery] = useState("");
    const [open, setOpen] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const wrapperRef = useRef<HTMLDivElement>(null);

    // close dropdown on click outside
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, []);

    // build search index from geojson features
    const searchIndex = useMemo(() => {
        if (!data.features.length) return [];

        const muniSet = new Map<string, SearchResult>();
        const brgyList: SearchResult[] = [];

        for (const feat of data.features) {
            const props = feat.properties;
            if (!props) continue;

            const p = props.p;
            const m = props.m;
            const b = props.b;

            // add municipality (deduplicated)
            const muniKey = `${p}|${m}`;
            if (!muniSet.has(muniKey)) {
                muniSet.set(muniKey, {
                    label: `${m}, ${p}`.toLowerCase(),
                    type: "municipality",
                    province: p,
                    municipality: m,
                });
            }

            // add barangay
            brgyList.push({
                label: `${b}, ${m}, ${p}`.toLowerCase(),
                type: "barangay",
                province: p,
                municipality: m,
                barangay: b,
            });
        }

        // municipalities first, then barangays (sorted)
        const munis = Array.from(muniSet.values()).sort((a, b) =>
            a.label.localeCompare(b.label)
        );
        return [...munis, ...brgyList.sort((a, b) => a.label.localeCompare(b.label))];
    }, [data]);

    // filter results based on query
    const results = useMemo(() => {
        if (!query.trim()) return [];
        const q = query.toLowerCase().trim();
        const tokens = q.split(/\s+/);

        const matches = searchIndex.filter((item) => {
            const label = item.label.toLowerCase();
            return tokens.every((t) => label.includes(t));
        });

        // limit to 50 results for performance
        return matches.slice(0, 50);
    }, [query, searchIndex]);

    // reset selected index when results change
    useEffect(() => {
        setSelectedIndex(0);
    }, [results]);

    // scroll active item into view
    useEffect(() => {
        if (!listRef.current) return;
        const active = listRef.current.querySelector("[data-active='true']");
        active?.scrollIntoView({ block: "nearest" });
    }, [selectedIndex]);

    const handleSelect = useCallback(
        (result: SearchResult) => {
            setQuery(result.label);
            setOpen(false);
            onSelect(result);
        },
        [onSelect]
    );

    const handleClear = useCallback(() => {
        setQuery("");
        setOpen(false);
        onSelect(null);
        inputRef.current?.focus();
    }, [onSelect]);

    const handleKeyDown = useCallback(
        (e: React.KeyboardEvent) => {
            if (!open || !results.length) return;

            if (e.key === "ArrowDown") {
                e.preventDefault();
                setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setSelectedIndex((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter") {
                e.preventDefault();
                handleSelect(results[selectedIndex]);
            } else if (e.key === "Escape") {
                setOpen(false);
            }
        },
        [open, results, selectedIndex, handleSelect]
    );

    return (
        <div ref={wrapperRef} className="relative w-full">
            <div className="relative">
                <svg
                    className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-neutral-500"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                >
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                    />
                </svg>
                <input
                    ref={inputRef}
                    type="text"
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setOpen(true);
                    }}
                    onFocus={() => query.trim() && setOpen(true)}
                    onKeyDown={handleKeyDown}
                    placeholder="search barangay or city..."
                    className="w-full rounded-lg border border-neutral-800 bg-neutral-900 py-2 pl-8 pr-8 text-xs text-neutral-200 placeholder-neutral-600 outline-none transition-colors focus:border-neutral-600"
                />
                {query && (
                    <button
                        onClick={handleClear}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-500 hover:text-neutral-300"
                    >
                        <svg
                            className="h-3.5 w-3.5"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M6 18L18 6M6 6l12 12"
                            />
                        </svg>
                    </button>
                )}
            </div>

            {/* dropdown results */}
            {open && results.length > 0 && (
                <div
                    ref={listRef}
                    className="absolute z-50 mt-1 max-h-60 w-full overflow-y-auto rounded-lg border border-neutral-800 bg-neutral-900 py-1 shadow-xl"
                >
                    {results.map((result, i) => (
                        <button
                            key={`${result.type}-${result.label}`}
                            data-active={i === selectedIndex}
                            onClick={() => handleSelect(result)}
                            onMouseEnter={() => setSelectedIndex(i)}
                            className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors ${
                                i === selectedIndex
                                    ? "bg-neutral-800 text-neutral-200"
                                    : "text-neutral-400 hover:bg-neutral-800/50"
                            }`}
                        >
                            <span
                                className={`shrink-0 rounded px-1 py-0.5 text-[10px] font-medium ${
                                    result.type === "municipality"
                                        ? "bg-orange-400/15 text-orange-400"
                                        : "bg-neutral-700/50 text-neutral-500"
                                }`}
                            >
                                {result.type === "municipality" ? "city" : "brgy"}
                            </span>
                            <span className="truncate lowercase">
                                {result.label}
                            </span>
                        </button>
                    ))}
                </div>
            )}

            {open && query.trim() && results.length === 0 && (
                <div className="absolute z-50 mt-1 w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-xs text-neutral-500 shadow-xl">
                    no results found
                </div>
            )}
        </div>
    );
}
