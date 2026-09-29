export type Source = {
  title: string;
  provider: string;
  external_id: string;
  source_name: string;
  url: string;
  published_date: string | null;
  source_type: string;
  role: string;
  language: string;
  trust: number;
  trust_level: string;
};

export type Factor = {
  name: string;
  value: number;
  direction: number;
  description: string;
  contribution: number;
};

export type Candidate = {
  id: number;
  title: string;
  description: string;
  potential_benefit: string;
  case_example: string;
  confidence: number;
  is_weak_signal: boolean;
  is_high_confidence: boolean;
  explanation: string;
  factors: Factor[];
  industry: string;
  industry_label: string;
  sources: Source[];
};

export type Status = "queued" | "fetching" | "analyzing" | "completed" | "partial" | "failed";

export type SearchRun = {
  id: string;
  query: string;
  status: Status;
  processed_sources: number;
  candidates_count: number;
  weak_signals_count: number;
  high_confidence_count: number;
  errors: string[];
  created_at?: string;
  candidates: Candidate[];
};

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
export const TERMINAL = new Set<Status>(["completed", "partial", "failed"]);

export const SOURCE_TYPE_LABEL: Record<string, string> = {
  academic: "Научная публикация",
  preprint: "Препринт",
  patent: "Патент",
  encyclopedia: "Энциклопедия",
};

export function scorePercent(value: number) {
  return Math.round(value * 100);
}

export function scoreLevel(value: number, isHighConfidence?: boolean): "high" | "mid" | "low" {
  if (isHighConfidence === true) return "high";
  if (isHighConfidence === false) {
    return value >= 0.5 ? "mid" : "low";
  }
  if (value >= 0.75) return "high";
  if (value >= 0.5) return "mid";
  return "low";
}

export const LEVEL_LABEL = { high: "Высокий", mid: "Средний", low: "Низкий" } as const;

export function predictorChips(item: Candidate) {
  return item.factors
    .filter((factor) => Math.abs(factor.contribution) > 0.01)
    .slice(0, 4)
    .map((factor) => factor.description);
}

export function splitItems(text: string) {
  return text
    .split(/\n+|(?<=[.!?])\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "Дата не указана";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateShort(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("ru-RU");
}

export function langCode(value: string) {
  const lang = (value || "").toLowerCase();
  if (lang.startsWith("ru")) return "RU";
  if (lang.startsWith("en")) return "EN";
  return (value || "—").slice(0, 3).toUpperCase();
}

export async function fetchSearch(id: string): Promise<SearchRun> {
  const response = await fetch(`${API_BASE}/api/searches/${id}/`);
  if (!response.ok) throw new Error("Не удалось загрузить поиск.");
  return response.json();
}
