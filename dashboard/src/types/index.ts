import type { FeatureCollection, Feature, Geometry } from "geojson";

export interface BarangayProperties {
    p: string;  // province
    m: string;  // municipality
    b: string;  // barangay
    rv: number; // registered voters
    av: number; // actual voters
    [key: string]: string | number; // v_{candidateId} vote counts
}

export type BarangayFeature = Feature<Geometry, BarangayProperties>;
export type BarangayCollection = FeatureCollection<Geometry, BarangayProperties>;

export interface CandidateConfig {
    id: string;
    name: string;
    type: "senate" | "partylist";
    color: string;
    columns: string[];
}

export type DatasetType = "senate" | "partylist";
