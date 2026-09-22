"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type Source = { source_name: string; url: string; published_date: string | null; source_type: string; language: string; trust: number; trust_level: string };
type Factor = { name: string; value: number; direction: number; description: string; contribution: number };
type Candidate = { id: number; title: string; description: string; potential_benefit: string; case_example: string; confidence: number; is_weak_signal: boolean; is_high_confidence: boolean; explanation: string; factors: Factor[]; sources: Source[] };
type Status = "queued" | "fetching" | "analyzing" | "completed" | "partial" | "failed";
type SearchRun = { id: string; query: string; status: Status; processed_sources: number; candidates_count: number; weak_signals_count: number; high_confidence_count: number; errors: string[]; candidates: Candidate[] };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const examples = ["Квантовые сенсоры", "Перспективные решения в финтехе", "Слабые сигналы в кибербезопасности"];
const terminalStates = new Set<Status>(["completed", "partial", "failed"]);
const labels: Record<Status, string> = { queued: "В очереди", fetching: "Собираем источники", analyzing: "Анализируем кандидатов", completed: "Анализ завершён", partial: "Завершён частично", failed: "Не удалось завершить" };
const score = (value: number) => `${Math.round(value * 100)}%`;

function CandidateCard({ item, rank }: { item: Candidate; rank: number }) {
  const [expanded, setExpanded] = useState(false);
  const factors = item.factors.filter((factor) => Math.abs(factor.contribution) > 0.01).slice(0, 4);
  return <article className="candidate-card">
    <div className="candidate-topline"><span className="rank">{String(rank).padStart(2, "0")}</span><span className="signal-tag">Слабый сигнал</span><span className="confidence">{score(item.confidence)}</span></div>
    <h3>{item.title}</h3>
    <p className="candidate-description">{item.description || "Описание пока отсутствует в открытом источнике."}</p>
    <div className="why-box"><span>Почему в выдаче</span><p>{item.explanation}</p></div>
    <div className="factor-list">{factors.map((factor) => <span key={factor.name} className={`factor ${factor.contribution >= 0 ? "positive" : "negative"}`}>{factor.description}</span>)}</div>
    <button className="detail-button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>{expanded ? "Скрыть аналитический отчёт" : "Открыть аналитический отчёт"}<span>{expanded ? "−" : "+"}</span></button>
    {expanded && <div className="detail-panel">
      <div className="detail-grid"><div><span className="eyebrow">Потенциальное преимущество</span><p>{item.potential_benefit}</p></div><div><span className="eyebrow">Кейс-пример</span><p>{item.case_example}</p></div></div>
      <div className="sources-section"><span className="eyebrow">Подтверждающие источники</span>{item.sources.map((source) => <a className="source-row" key={source.url} href={source.url} target="_blank" rel="noreferrer"><span className="source-icon">↗</span><span className="source-main"><b>{source.source_name}</b><small>{source.source_type} · {source.published_date ?? "Дата не указана"} · {source.language || "Язык не указан"}</small></span><span className={`trust ${source.trust_level}`}>{source.trust_level} доверенность</span></a>)}</div>
    </div>}
  </article>;
}

export default function Home() {
  const [query, setQuery] = useState(""); const [run, setRun] = useState<SearchRun | null>(null); const [isSubmitting, setIsSubmitting] = useState(false); const [error, setError] = useState("");
  useEffect(() => { if (!run || terminalStates.has(run.status)) return; const timer = window.setInterval(async () => { try { const response = await fetch(`${API_BASE}/api/searches/${run.id}/`); if (!response.ok) throw new Error("Не удалось обновить статус поиска."); setRun(await response.json()); } catch (reason) { setError(reason instanceof Error ? reason.message : "Ошибка соединения с сервисом."); } }, 1800); return () => window.clearInterval(timer); }, [run]);
  const progress = useMemo(() => run?.status === "queued" ? 12 : run?.status === "fetching" ? 46 : run?.status === "analyzing" ? 78 : run && terminalStates.has(run.status) ? 100 : 0, [run]);
  async function submit(event: FormEvent) { event.preventDefault(); if (query.trim().length < 2) { setError("Введите технологическое направление — минимум 2 символа."); return; } setError(""); setIsSubmitting(true); setRun(null); try { const response = await fetch(`${API_BASE}/api/searches/`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: query.trim() }) }); if (!response.ok) throw new Error("Не удалось запустить поиск. Проверьте доступность сервиса."); setRun(await response.json()); } catch (reason) { setError(reason instanceof Error ? reason.message : "Ошибка соединения с сервисом."); } finally { setIsSubmitting(false); } }
  return <main>
    <nav className="nav"><a className="brand" href="#top"><i>◒</i>Trend<span>Me</span></a><div className="nav-note"><span className="status-dot" />Аналитика ранних технологических сигналов</div></nav>
    <section className="hero" id="top"><div className="hero-orb orb-one" /><div className="hero-orb orb-two" /><p className="kicker">СИСТЕМА ТЕХНОЛОГИЧЕСКОЙ РАЗВЕДКИ</p><h1>Находите тренды<br /><em>до того, как они станут очевидными.</em></h1><p className="hero-copy">TrendMe анализирует научные публикации, препринты и патенты, чтобы найти подтверждённые ранние сигналы в нужной области.</p>
      <form className="search-box" onSubmit={submit}><span className="search-symbol">⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Например, квантовые сенсоры" aria-label="Технологическое направление" /><button disabled={isSubmitting}>{isSubmitting ? "Запускаем…" : "Найти сигналы"}<span>→</span></button></form>
      <div className="examples"><span>Попробуйте:</span>{examples.map((example) => <button key={example} onClick={() => setQuery(example)}>{example}</button>)}</div>{error && <p className="error-message">{error}</p>}
    </section>
    {run && <section className="workspace"><div className="run-header"><div><p className="kicker">ПОИСКОВЫЙ ЗАПРОС</p><h2>«{run.query}»</h2></div><span className={`run-status ${run.status}`}><i />{labels[run.status]}</span></div>
      {!terminalStates.has(run.status) && <div className="progress-wrap"><div className="progress-copy"><span>{labels[run.status]}</span><span>{progress}%</span></div><div className="progress-track"><i style={{ width: `${progress}%` }} /></div><p>Собираем и проверяем открытые источники. Это обычно занимает до минуты.</p></div>}
      {terminalStates.has(run.status) && <><div className="metrics"><div><span>Обработано источников</span><b>{run.processed_sources}</b><small>научные публикации, препринты и патенты</small></div><div><span>Кандидаты в слабые сигналы</span><b>{run.weak_signals_count}</b><small>прошли тематическую и доказательную проверку</small></div><div><span>Уверенность выше 75%</span><b>{run.high_confidence_count}</b><small>сигналы высокой уверенности</small></div></div>
      {run.errors.length > 0 && <div className="notice">Часть источников недоступна: {run.errors.join("; ")}</div>}<div className="results-head"><div><p className="kicker">РЕЗУЛЬТАТЫ АНАЛИЗА</p><h2>{run.candidates.length ? `ТОП-${run.candidates.length} зарождающихся технологий` : "Подтверждённые сигналы не найдены"}</h2></div><p>{run.candidates.length ? "Карточки отсортированы по уверенности модели." : "Попробуйте уточнить запрос или выбрать более узкое технологическое направление."}</p></div><div className="results">{run.candidates.map((item, index) => <CandidateCard item={item} rank={index + 1} key={item.id} />)}</div></>}
    </section>}
    <footer><span>TrendMe · 2026</span><span>Проверяемые источники · Объяснимая модель · Human-in-the-loop</span></footer>
  </main>;
}
