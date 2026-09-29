"use client";

import Link from "next/link";
import { FormEvent, Fragment, useEffect, useMemo, useState } from "react";

import { Ic } from "./icons";
import {
  API_BASE,
  LEVEL_LABEL,
  SearchRun,
  TERMINAL,
  fetchSearch,
  predictorChips,
  scoreLevel,
  scorePercent,
} from "./lib";

const VISIBLE_WHEN_COLLAPSED = 15;

function emptyStateCopy(run: SearchRun): { title: string; text: string } {
  const joined = run.errors.join(" ");
  if (joined.includes("query_not_translated")) {
    return {
      title: "Запрос не удалось сопоставить с англоязычными источниками",
      text: "Сформулируйте тему конкретнее или добавьте английский термин. Сырой кириллический запрос в arXiv и OpenAlex не отправляется.",
    };
  }
  if (joined.includes("no_projects_after_filters")) {
    return {
      title: "Источники нашлись, но проектов не осталось",
      text: `Обработано ${run.processed_sources} документов. Обзоры, использование прибора как инструмента и слишком широкие темы отсекаются — это не зарождающиеся проекты.`,
    };
  }
  return {
    title: "По этому направлению пока не нашли зарождающихся трендов",
    text: "Попробуйте изменить формулировку запроса или выбрать другое направление",
  };
}

function SearchForm({
  query,
  setQuery,
  onSubmit,
  disabled,
}: {
  query: string;
  setQuery: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  disabled: boolean;
}) {
  return (
    <form className="search" onSubmit={onSubmit} role="search">
      <div className="search__field">
        <Ic id="i-search" size={18} />
        <input
          className="search__input"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Введите технологию, область науки или ключевое слово"
          aria-label="Запрос"
        />
        {query && (
          <button className="search__clear" type="button" aria-label="Очистить" onClick={() => setQuery("")}>
            ×
          </button>
        )}
      </div>
      <button className="search__submit" type="submit" disabled={disabled}>
        <Ic id="i-search-white" size={16} />
        Найти сигналы
      </button>
    </form>
  );
}

function LoadingTimer({ active }: { active: boolean }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!active) {
      setElapsed(0);
      return;
    }
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 250);
    return () => window.clearInterval(timer);
  }, [active]);
  const pad = (value: number) => String(value).padStart(2, "0");
  return <p className="loading__timer">{`${pad(Math.floor(elapsed / 60))}:${pad(elapsed % 60)}`}</p>;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [run, setRun] = useState<SearchRun | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());
  const [listExpanded, setListExpanded] = useState(true);

  const inProgress = Boolean(run && !TERMINAL.has(run.status));
  const done = Boolean(run && TERMINAL.has(run.status));

  useEffect(() => {
    const lastId = sessionStorage.getItem("trendme:lastRun");
    if (!lastId) return;
    fetchSearch(lastId).then((saved) => {
      setRun(saved);
      setQuery(saved.query);
    }).catch(() => sessionStorage.removeItem("trendme:lastRun"));
  }, []);

  useEffect(() => {
    if (run?.id) sessionStorage.setItem("trendme:lastRun", run.id);
  }, [run?.id]);

  useEffect(() => {
    if (!run || TERMINAL.has(run.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/api/searches/${run.id}/`);
        if (!response.ok) throw new Error("Не удалось обновить статус поиска.");
        setRun(await response.json());
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Ошибка соединения с сервисом.");
      }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [run]);

  useEffect(() => {
    if (!run || !TERMINAL.has(run.status)) return;
    setOpenIds(new Set(run.candidates.slice(0, 3).map((item) => item.id)));
    setListExpanded(true);
  }, [run?.id, run?.status]);

  const visible = useMemo(() => {
    if (!run) return [];
    return listExpanded ? run.candidates : run.candidates.slice(0, VISIBLE_WHEN_COLLAPSED);
  }, [run, listExpanded]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) {
      setError("Введите технологическое направление — минимум 2 символа.");
      return;
    }
    setError("");
    setIsSubmitting(true);
    setRun(null);
    try {
      const response = await fetch(`${API_BASE}/api/searches/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim() }),
      });
      if (!response.ok) throw new Error("Не удалось запустить поиск. Проверьте доступность сервиса.");
      setRun(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ошибка соединения с сервисом.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function reset() {
    setQuery("");
    setRun(null);
    setError("");
    setOpenIds(new Set());
    sessionStorage.removeItem("trendme:lastRun");
  }

  function toggle(id: number) {
    setOpenIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <main className="page">
      <section>
        <h1 className="hero__title">TrendME</h1>
        <p className="hero__subtitle">Поиск зарождающихся научно-технологических трендов на основе ИИ</p>
        <SearchForm query={query} setQuery={setQuery} onSubmit={submit} disabled={isSubmitting || inProgress} />
        {run && (
          <div className="query">
            <span className="query__label">Запрос:</span>
            <span className="query__chip">«{run.query}»</span>
            <button className="query__reset" type="button" onClick={reset}>Сбросить</button>
          </div>
        )}
        {error && <p className="error-message">{error}</p>}
      </section>

      {inProgress && (
        <section className="loading" role="status" aria-live="polite">
          <svg className="ic spinner" width="46" height="46" aria-hidden="true"><use href="#i-spinner" /></svg>
          <p>{run?.status === "analyzing" ? "Анализируем кандидатов…" : "Анализируем источники…"}</p>
          <LoadingTimer active={inProgress} />
        </section>
      )}

      {done && run && run.candidates.length === 0 && (
        <section className="empty-state" role="status">
          <Ic id="i-empty" size={42} />
          <p className="empty-state__title">{emptyStateCopy(run).title}</p>
          <p className="empty-state__text">{emptyStateCopy(run).text}</p>
          {run.processed_sources > 0 && (
            <p className="empty-state__text">Источников: {run.processed_sources}</p>
          )}
        </section>
      )}

      {done && run && run.candidates.length > 0 && (
        <>
          <section className="stats" aria-label="Сводка">
            <div className="stat">
              <div className="stat__label"><Ic id="i-database" size={14} />Обработано источников</div>
              <div className="stat__value">{run.processed_sources}</div>
              <div className="stat__note">наука и препринты; патент — фактор</div>
            </div>
            <div className="stat">
              <div className="stat__label"><Ic id="i-zap" size={14} />Технологий-кандидатов на слабый сигнал</div>
              <div className="stat__value stat__value--amber">{run.weak_signals_count}</div>
              <a className="stat__note stat__note--link" href="#list">Перейти к полному списку <Ic id="i-arrow-right" size={12} /></a>
            </div>
            <div className="stat">
              <div className="stat__label"><Ic id="i-check-circle" size={14} />Подтверждённых сигналов (топ 25%, не больше 4)</div>
              <div className="stat__value stat__value--green">{run.high_confidence_count}</div>
              <div className="stat__note">Относительно этого прогона, не абсолютный порог ML</div>
            </div>
          </section>

          {run.errors.length > 0 && <div className="notice">Часть источников недоступна: {run.errors.join("; ")}</div>}

          <section className="card" id="list">
            <div className="card__header">
              <div>
                <h2 className="card__title">Топ найденных «слабых сигналов»<span className="muted"> по теме </span><span className="accent">«{run.query}»</span></h2>
                <p className="card__note">В выдаче только слабые сигналы зарождающихся научно-технологических проектов</p>
              </div>
              <span className="card__count">{run.high_confidence_count} из {run.candidates.length}</span>
            </div>
            <div className="table-scroll">
              <table>
                <colgroup>
                  <col className="c-num" /><col className="c-name" /><col className="c-score" /><col className="c-pred" /><col className="c-act" />
                </colgroup>
                <thead>
                  <tr>
                    <th className="num">№</th>
                    <th>Технология / Тема</th>
                    <th>Скоринг (уверенность ИИ)</th>
                    <th>Ключевые предикторы</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((item, index) => {
                    const open = openIds.has(item.id);
                    const level = scoreLevel(item.confidence);
                    const chips = predictorChips(item);
                    return (
                      <Fragment key={item.id}>
                        <tr className={`signal${open ? " is-open" : ""}`}>
                          <td className="num">{index + 1}</td>
                          <td>
                            <p className="name">{item.title}</p>
                            {level === "low" && <span className="lowconf"><Ic id="i-warn" size={10} />Низкий уровень уверенности ИИ</span>}
                          </td>
                          <td><span className={`badge badge--${level}`}>{LEVEL_LABEL[level]} · {scorePercent(item.confidence)}%</span></td>
                          <td><div className="chips">{chips.map((chip) => <span className="chip" key={chip}>{chip}</span>)}</div></td>
                          <td className="act">
                            <div className="actions">
                              <button className="btn" type="button" onClick={() => toggle(item.id)} aria-expanded={open}>
                                <Ic id={open ? "i-chevron-up-13" : "i-chevron-down-13"} size={13} />
                                <span>{open ? "Скрыть" : "Обоснование"}</span>
                              </button>
                              <Link className="btn btn--primary" href={`/insight/${run.id}/${item.id}`}>
                                Инсайт <Ic id="i-external" size={12} />
                              </Link>
                            </div>
                          </td>
                        </tr>
                        {open && (
                          <tr className="rationale">
                            <td></td>
                            <td colSpan={4}>
                              <div className="rationale__box">
                                <div className="rationale__icon"><Ic id="i-zap-amber" size={15} /></div>
                                <div>
                                  <p className="rationale__title">Обоснование классификации</p>
                                  <p className="rationale__text">{item.explanation || "Модель отнесла кандидата к слабому сигналу по совокупности научных источников."}</p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {run.candidates.length > VISIBLE_WHEN_COLLAPSED && (
              <div className="card__footer">
                <button className="collapse" type="button" aria-expanded={listExpanded} onClick={() => setListExpanded((value) => !value)}>
                  <Ic id="i-chevron-up-15" size={15} />
                  <span>{listExpanded ? "Свернуть список" : "Показать весь список"}</span>
                </button>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}
