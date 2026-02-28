import { useState, useEffect, useMemo, useCallback } from "react";
import { MapView } from "./components/MapView";
import { CandidatePanel } from "./components/CandidatePanel";
import type { SearchResult } from "./components/SearchBar";
import { senateCandidates, partylistCandidates } from "./data/candidates";
import type { BarangayCollection, CandidateConfig, DatasetType } from "./types";

function App() {
    const [data, setData] = useState<BarangayCollection>({
        type: "FeatureCollection",
        features: [],
    });
    const [loading, setLoading] = useState(true);
    const [datasetType, setDatasetType] = useState<DatasetType>("senate");
    const [selectedCandidate, setSelectedCandidate] =
        useState<CandidateConfig>(senateCandidates[0]);
    const [panelOpen, setPanelOpen] = useState(false);
    const [searchSelection, setSearchSelection] = useState<SearchResult | null>(null);
    const [highContrast, setHighContrast] = useState(true);

    // load geojson data on mount
    useEffect(() => {
        fetch("/data/barangays.geojson")
            .then((res) => res.json())
            .then((geojson: BarangayCollection) => {
                setData(geojson);
                setLoading(false);
            })
            .catch((err) => {
                console.error("failed to load election data:", err);
                setLoading(false);
            });
    }, []);

    // get current candidate list based on dataset type
    const candidates = useMemo(
        () =>
            datasetType === "senate"
                ? senateCandidates
                : partylistCandidates,
        [datasetType]
    );

    // switch dataset type and auto-select first candidate
    const handleDatasetChange = useCallback(
        (type: DatasetType) => {
            setDatasetType(type);
            const newCandidates =
                type === "senate" ? senateCandidates : partylistCandidates;
            setSelectedCandidate(newCandidates[0]);
        },
        []
    );

    // compute stats for the selected candidate from geojson properties
    const stats = useMemo(() => {
        if (!data.features.length || !selectedCandidate) {
            return {
                totalVotes: 0,
                avgShare: 0,
                topProvinces: [],
            };
        }

        const voteKey = `v_${selectedCandidate.id}`;
        let totalVotes = 0;
        let totalActual = 0;
        const provinceMap = new Map<
            string,
            { votes: number; actual: number }
        >();

        for (const feat of data.features) {
            const props = feat.properties;
            if (!props) continue;

            const votes = (props[voteKey] as number) ?? 0;
            const av = props.av ?? 0;
            totalVotes += votes;
            totalActual += av;

            const province = props.p;
            const existing = provinceMap.get(province);
            if (existing) {
                existing.votes += votes;
                existing.actual += av;
            } else {
                provinceMap.set(province, { votes, actual: av });
            }
        }

        const avgShare =
            totalActual > 0 ? (totalVotes / totalActual) * 100 : 0;

        // sort provinces by total votes
        const topProvinces = Array.from(provinceMap.entries())
            .map(([name, { votes, actual }]) => ({
                name,
                votes,
                share: actual > 0 ? (votes / actual) * 100 : 0,
            }))
            .sort((a, b) => b.votes - a.votes)
            .slice(0, 5);

        return { totalVotes, avgShare, topProvinces };
    }, [data, selectedCandidate]);

    return (
        <div className="flex h-screen w-screen flex-col bg-neutral-950 text-neutral-200">
            <main className="flex flex-1 overflow-hidden">
                {/* sidebar panel - hidden on mobile unless toggled */}
                <CandidatePanel
                    datasetType={datasetType}
                    onDatasetChange={handleDatasetChange}
                    candidates={candidates}
                    selectedCandidate={selectedCandidate}
                    onCandidateSelect={setSelectedCandidate}
                    stats={stats}
                    isOpen={panelOpen}
                    onToggle={() => setPanelOpen(!panelOpen)}
                    data={data}
                    onSearchSelect={setSearchSelection}
                    highContrast={highContrast}
                    onHighContrastToggle={() => setHighContrast(!highContrast)}
                />

                {/* map */}
                <div className="relative flex-1">
                    <MapView
                        data={data}
                        candidateId={selectedCandidate.id}
                        candidateColor={selectedCandidate.color}
                        loading={loading}
                        searchSelection={searchSelection}
                        highContrast={highContrast}
                    />
                </div>
            </main>
        </div>
    );
}

export default App;
