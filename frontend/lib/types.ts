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

export interface MatchFact {
  category: "market" | "venue" | "weather" | "referee" | "absence" | "h2h" | "form";
  label: string;
  value: string;
}

export interface MarketOdds {
  match_winner: Record<string, number>;
  over_under_25?: Record<string, number> | null;
  btts?: Record<string, number> | null;
  bookmakers: number;
}

export interface AIPrediction {
  picks: Record<string, string>;
  confidence: number;
  analysis: string;
  model: string;
}

export interface FixtureResult {
  home_score: number;
  away_score: number;
  status: string;
  outcome: "home" | "draw" | "away";
  ht_home?: number | null;
  ht_away?: number | null;
  fetched_at: string;
}

export interface MarketGrade {
  market: string;
  pick: string;
  actual: string;
  correct: boolean;
}

export interface ConfidenceBucket {
  graded: number;
  accuracy: number;
}

export interface AccuracySummary {
  date: string;
  graded: number;
  total: number;
  pick_accuracy?: number | null;
  market_accuracy: Record<string, number>;
  exact_score_accuracy?: number | null;
  ai_overall?: number | null;
  ai_accuracy: Record<string, number>;
  confidence_accuracy?: Record<string, ConfidenceBucket>;
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
  insight?: string | null;
  ai?: AIPrediction | null;
  match_facts?: MatchFact[];
  odds?: MarketOdds | null;
  algorithm: string;
  data_source: "live" | "mock";
  data_quality?: number;
  generated_at: string;
  result?: FixtureResult | null;
  grades: MarketGrade[];
  ai_grades?: MarketGrade[];
  pick_correct?: boolean | null;
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
  accuracy?: AccuracySummary | null;
  errors?: string[];
}
