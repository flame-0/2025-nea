import type { CandidateConfig, DatasetType, BarangayCollection } from "../types";
import { SearchBar } from "./SearchBar";
import type { SearchResult } from "./SearchBar";

interface CandidatePanelProps {
    datasetType: DatasetType;
    onDatasetChange: (type: DatasetType) => void;
    candidates: CandidateConfig[];
    selectedCandidate: CandidateConfig;
    onCandidateSelect: (candidate: CandidateConfig) => void;
    stats: {
        totalVotes: number;
        avgShare: number;
        topProvinces: Array<{ name: string; votes: number; share: number }>;
    };
    isOpen: boolean;
    onToggle: () => void;
    data: BarangayCollection;
    onSearchSelect: (result: SearchResult | null) => void;
    highContrast: boolean;
    onHighContrastToggle: () => void;
}

export function CandidatePanel({
    datasetType,
    onDatasetChange,
    candidates,
    selectedCandidate,
    onCandidateSelect,
    stats,
    isOpen,
    onToggle,
    data,
    onSearchSelect,
    highContrast,
    onHighContrastToggle,
}: CandidatePanelProps) {
    return (
        <>
            {/* mobile toggle button */}
            <button
                onClick={onToggle}
                className="fixed bottom-4 left-1/2 z-1001 flex -translate-x-1/2 items-center gap-2 rounded-full bg-neutral-800 px-4 py-2 text-xs text-neutral-300 shadow-lg md:hidden"
            >
                <svg
                    className="h-4 w-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                >
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d={
                            isOpen
                                ? "M19 9l-7 7-7-7"
                                : "M5 15l7-7 7 7"
                        }
                    />
                </svg>
                <span>{isOpen ? "hide panel" : "show panel"}</span>
            </button>

            {/* mobile overlay */}
            {isOpen && (
                <div
                    className="fixed inset-0 z-999 bg-black/50 md:hidden"
                    onClick={onToggle}
                />
            )}

            {/* panel */}
            <div
                className={`
                    panel-scroll fixed bottom-0 left-0 right-0 z-1000 max-h-[70vh] overflow-y-auto
                    rounded-t-2xl border-t border-neutral-800 bg-neutral-950 p-4
                    transition-transform duration-300 ease-in-out
                    md:static md:z-auto md:h-full md:max-h-none md:w-80 md:shrink-0
                    md:translate-y-0 md:rounded-none md:border-r md:border-t-0
                    ${isOpen ? "translate-y-0" : "translate-y-full"}
                    md:block
                `}
            >
                {/* header */}
                <div className="mb-4">
                    <h1 className="text-sm font-semibold text-neutral-200">
                        2025 national electoral analysis
                    </h1>
                    <p className="mt-1 text-xs text-neutral-500">
                        barangay-level choropleth
                    </p>
                </div>

                {/* search */}
                <div className="mb-4">
                    <SearchBar data={data} onSelect={onSearchSelect} />
                </div>

                {/* dataset tabs */}
                <div className="mb-4 flex gap-2">
                    <button
                        onClick={() => onDatasetChange("senate")}
                        className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                            datasetType === "senate"
                                ? "bg-orange-400/15 text-orange-400"
                                : "bg-neutral-900 text-neutral-500 hover:text-neutral-300"
                        }`}
                    >
                        senate
                    </button>
                    <button
                        onClick={() => onDatasetChange("partylist")}
                        className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                            datasetType === "partylist"
                                ? "bg-orange-400/15 text-orange-400"
                                : "bg-neutral-900 text-neutral-500 hover:text-neutral-300"
                        }`}
                    >
                        partylist
                    </button>
                </div>

                {/* candidate list */}
                <div className="mb-4">
                    <p className="mb-2 text-xs text-neutral-500">
                        select candidate
                    </p>
                    <div className="flex flex-col gap-1.5">
                        {candidates.map((candidate) => (
                            <button
                                key={candidate.id}
                                onClick={() => onCandidateSelect(candidate)}
                                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs transition-colors ${
                                    selectedCandidate.id === candidate.id
                                        ? "bg-neutral-800 text-neutral-200"
                                        : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-300"
                                }`}
                            >
                                <span
                                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                                    style={{
                                        backgroundColor: candidate.color,
                                        opacity:
                                            selectedCandidate.id ===
                                            candidate.id
                                                ? 1
                                                : 0.4,
                                    }}
                                />
                                <span className="lowercase">
                                    {candidate.name}
                                </span>
                            </button>
                        ))}
                    </div>
                </div>

                {/* stats */}
                <div className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-3">
                    <p className="mb-3 text-xs font-medium text-neutral-400">
                        statistics
                    </p>

                    <div className="mb-3 grid grid-cols-2 gap-2">
                        <div className="rounded-lg bg-neutral-800/50 p-2.5">
                            <p className="text-xs text-neutral-500">
                                total votes
                            </p>
                            <p
                                className="mt-0.5 text-sm font-semibold"
                                style={{ color: selectedCandidate.color }}
                            >
                                {stats.totalVotes.toLocaleString()}
                            </p>
                        </div>
                        <div className="rounded-lg bg-neutral-800/50 p-2.5">
                            <p className="text-xs text-neutral-500">
                                avg share
                            </p>
                            <p
                                className="mt-0.5 text-sm font-semibold"
                                style={{ color: selectedCandidate.color }}
                            >
                                {stats.avgShare.toFixed(2)}%
                            </p>
                        </div>
                    </div>

                    {/* top provinces */}
                    <p className="mb-2 text-xs text-neutral-500">
                        top provinces
                    </p>
                    <div className="flex flex-col gap-1">
                        {stats.topProvinces.map((prov, i) => (
                            <div
                                key={prov.name}
                                className="flex items-center justify-between rounded px-2 py-1.5 text-xs"
                            >
                                <span className="text-neutral-400">
                                    <span className="mr-2 text-neutral-600">
                                        {i + 1}
                                    </span>
                                    <span className="lowercase">
                                        {prov.name}
                                    </span>
                                </span>
                                <span className="text-neutral-500">
                                    {prov.votes.toLocaleString()}
                                    <span className="ml-1 text-neutral-600">
                                        ({prov.share.toFixed(1)}%)
                                    </span>
                                </span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* legend */}
                <div className="mt-4 rounded-xl border border-neutral-800 bg-neutral-900/50 p-3">
                    <div className="mb-2 flex items-center justify-between">
                        <p className="text-xs font-medium text-neutral-400">
                            intensity legend
                        </p>
                        <button
                            onClick={onHighContrastToggle}
                            className={`rounded-md px-2 py-1 text-[10px] font-medium transition-colors ${
                                highContrast
                                    ? "bg-orange-400/15 text-orange-400"
                                    : "bg-neutral-800 text-neutral-500 hover:text-neutral-300"
                            }`}
                        >
                            {highContrast ? "multi-hue" : "single-hue"}
                        </button>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-neutral-600">low</span>
                        <div
                            className="h-2 flex-1 rounded-full"
                            style={{
                                background: highContrast
                                    ? "linear-gradient(to right, rgb(10,10,30), rgb(20,120,120), rgb(160,200,40), rgb(250,100,40), rgb(255,240,220))"
                                    : `linear-gradient(to right, transparent, ${selectedCandidate.color})`,
                            }}
                        />
                        <span className="text-xs text-neutral-600">high</span>
                    </div>
                </div>

                {/* footer */}
                <div className="mt-4 border-t border-neutral-800 pt-3 text-center">
                    <p className="mt-1 text-xs text-neutral-600">
                        &copy; {new Date().getFullYear()} comelec 2025 election data
                    </p>
                    <p className="mt-1 text-xs text-neutral-700">
                        made with ❤️ by cpu
                    </p>
                </div>
            </div>
        </>
    );
}
