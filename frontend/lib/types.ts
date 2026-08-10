export type Sport = "football" | "basketball" | "tennis";
export type SportFilter = Sport | "all";

export interface Competitor {
  id: string;
  name: string;
  logo?: string | null;
}

export interface Fixture {
  id: string;
  sport: Sport;
  league: string;
  country?: string | null;
  start_time?: string | null;
  home: Competitor;
  away: Competitor;
  venue?: string | null;
  round?: string | null;
  surface?: string | null;
  best_of?: number | null;
}

export interface Market {
  name: string;
  outcomes: Record<string, number>;
  pick: string;
  pick_probability: number;
}

export interface Factor {
  label: string;
  detail: string;
  impact: "positive_home" | "positive_away" | "neutral";
}

export interface Injury {
  player: string;
  team_id: string;
  status: string;
  detail?: string | null;
  importance: number;
}

export interface NewsItem {
  team_id: string;
  headline: string;
  source?: string | null;
  published_at?: string | null;
  sentiment: number;
}

export interface Prediction {
  sport: Sport;
  date: string;
  fixture_id: string;
  fixture: Fixture;
  markets: Market[];
  predicted_score?: string | null;
  expected_home?: number | null;
  expected_away?: number | null;
  confidence: number;
  confidence_label: "low" | "medium" | "high";
  factors: Factor[];
  injuries: Injury[];
  news: NewsItem[];
  algorithm: string;
  data_source: "live" | "mock";
  generated_at: string;
}

export interface RefreshMeta {
  sport: Sport;
  date: string;
  refreshed_at: string;
  fixtures: number;
  data_source: "live" | "mock";
}

export interface PredictionsResponse {
  date: string;
  sport: string;
  predictions: Prediction[];
  meta: RefreshMeta[];
}
