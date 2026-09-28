"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { Ic } from "../../../icons";
import {
  Candidate,
  LEVEL_LABEL,
  SearchRun,
  SOURCE_TYPE_LABEL,
  fetchSearch,
  formatDate,
  formatDateShort,
  langCode,
  predictorChips,
  scoreLevel,
  scorePercent,
  splitItems,
} from "../../../lib";

export default function InsightPage({
  params,
}: {
  params: Promise<{ runId: string; candidateId: string }>;
}) {
  const { runId, candidateId } = use(params);
  const [run, setRun] = useState<SearchRun | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchSearch(runId).then(setRun).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть отчёт.");
    });
  }, [runId]);

  const item = run?.candidates.find((candidate) => String(candidate.id) === candidateId) ?? null;
  if (error || (run && !item)) {
    return (
      <main className="page">
        <section className="empty-state" role="status">
          <Ic id="i-empty" size={42} />
          <p className="empty-state__title">{error || "Сигнал не найден"}</p>
          <p className="empty-state__text">Вернитесь к результатам и выберите другой сигнал</p>
          <Link className="btn" href="/">Назад к результатам</Link>
        </section>
      </main>
    );
  }
  if (!run || !item) {
    return (
      <main className="page">
        <section className="loading" role="status">
          <svg className="ic spinner" width="46" height="46" aria-hidden="true"><use href="#i-spinner" /></svg>
          <p>Открываем отчёт…</p>
        </section>
      </main>
    );
  }

  return <InsightReport run={run} item={item} />;
}

function InsightReport({ run, item }: { run: SearchRun; item: Candidate }) {
  const level = scoreLevel(item.confidence);
  const percent = scorePercent(item.confidence);
  const predictors = predictorChips(item);
  const benefits = splitItems(item.potential_benefit);
  const cases = splitItems(item.case_example);
  const similar = run.candidates.filter((candidate) => candidate.id !== item.id).slice(0, 3);

  return (
    <>
      <header className="topbar">
        <div className="topbar__inner">
          <Link className="back" href="/">
            <Ic id="i-back" size={15} />
            Назад к результатам
          </Link>
          <nav className="crumbs" aria-label="Навигация">
            <Link href="/">Слабые сигналы</Link>
            <Ic id="i-chevron-r" size={12} />
            <span className="crumbs__current" aria-current="page">Аналитический отчёт</span>
          </nav>
          <button className="export" type="button" onClick={() => window.print()}>
            <Ic id="i-download" size={13} />
            Экспортировать отчёт
          </button>
        </div>
      </header>

      <main className="insight">
        <section className="report" aria-labelledby="title">
          <div className="meta">
            <span className="tag">Аналитический отчёт</span>
            <span className="dot">·</span>
            <span className="meta__area">{item.industry_label || "Научно-технологический проект"}</span>
            <span className="dot">·</span>
            <span className="meta__date">
              <Ic id="i-calendar12" size={12} />
              {formatDate(run.created_at)}
            </span>
          </div>
          <h1 className="report__title" id="title">{item.title}</h1>
          <div className="metrics">
            <div className="confidence">
              <div className="confidence__label">Уверенность модели</div>
              <div className="confidence__bar">
                <div className="track" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label="Уверенность модели">
                  <div className={`track__fill ${level}`} style={{ width: `${percent}%` }} />
                </div>
                <span className={`confidence__value ${level}`}>{percent}%</span>
              </div>
              <div className="level"><span className="pill-green">{LEVEL_LABEL[level]} уровень уверенности</span></div>
            </div>
            <div className="report-stat">
              <div className="report-stat__label"><Ic id="i-db13" size={13} />Источников</div>
              <div className="report-stat__value">{item.sources.length}</div>
            </div>
            <div className="report-stat">
              <div className="report-stat__label"><Ic id="i-trend13" size={13} />Предикторов</div>
              <div className="report-stat__value">{predictors.length}</div>
            </div>
            <div className="report-stat">
              <div className="report-stat__label"><Ic id="i-star13" size={13} />Отрасль</div>
              <div className="report-stat__value" style={{ fontSize: 12, lineHeight: "17.5px" }}>{item.industry_label}</div>
            </div>
            <div className="report-stat">
              <div className="report-stat__label"><Ic id="i-book13" size={13} />Кейс-примеров</div>
              <div className="report-stat__value">{cases.length || 1}</div>
            </div>
          </div>
        </section>

        <div className="layout">
          <article className="insight-card">
            <section className="section">
              <div className="section__head">
                <div className="section__icon"><Ic id="i-sec-book" size={16} /></div>
                <h2 className="section__title">Описание технологии</h2>
              </div>
              <div className="section__body">
                <p className="prose">{item.description || "Подробное описание пока отсутствует в открытых источниках. Ниже — подтверждающие публикации и факторы модели."}</p>
              </div>
            </section>

            <section className="section">
              <div className="section__head">
                <div className="section__icon"><Ic id="i-sec-check" size={16} /></div>
                <h2 className="section__title">Преимущества и потенциал</h2>
              </div>
              <div className="section__body">
                <ul className="checks">
                  {(benefits.length ? benefits : ["Не извлечено из абстракта источника."]).map((benefit) => (
                    <li key={benefit}><span className="check" aria-hidden="true">✓</span><span>{benefit}</span></li>
                  ))}
                </ul>
              </div>
            </section>

            <section className="section">
              <div className="section__head">
                <div className="section__icon"><Ic id="i-sec-trend" size={16} /></div>
                <h2 className="section__title">Кейс-примеры</h2>
              </div>
              <div className="section__body cases">
                {(cases.length ? cases : ["Исходная научная публикация или препринт из списка источников."]).map((text, index) => (
                  <div className="case" key={text}>
                    <div className="case__title">{item.sources[index]?.title || item.sources[index]?.source_name || "Научный источник"}</div>
                    <p className="case__text">{text}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="section">
              <div className="section__head">
                <div className="section__icon"><Ic id="i-sec-info" size={16} /></div>
                <h2 className="section__title">Объяснение статуса слабого сигнала</h2>
              </div>
              <div className="section__body">
                <div className="status">
                  <div className="status__icon"><Ic id="i-zap-green" size={16} /></div>
                  <div className="status__body">
                    <div className="status__title">Уверенность ИИ-модели: {percent}% — {LEVEL_LABEL[level]}</div>
                    <p className="status__text">{item.explanation || "Модель отнесла проект к слабому сигналу: научное ядро есть, массового внедрения нет."}</p>
                    {predictors.length > 0 && (
                      <div className="predictors">
                        <div className="status__title">Ключевые предикторы классификации</div>
                        <div className="predictors__chips">
                          {predictors.map((predictor, index) => (
                            <span className="pred" key={predictor}><b>{index + 1}.</b>{predictor}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </section>

            <section className="section">
              <div className="section__head">
                <div className="section__icon"><Ic id="i-sec-link" size={16} /></div>
                <div className="grow">
                  <h2 className="section__title">Источники и ссылки</h2>
                  <p className="section__sub">{item.sources.length} источников · наименование, ссылка, дата, тип, язык, уровень доверенности</p>
                </div>
                <span className="badge-count"><Ic id="i-shield11" size={11} />{item.sources.length}</span>
              </div>
              <div className="sources">
                {item.sources.map((source, index) => (
                  <div className="source" key={`${source.url}-${index}`}>
                    <span className="source__n mono">{String(index + 1).padStart(2, "0")}</span>
                    <div className="source__main">
                      <a className="source__title" href={source.url} target="_blank" rel="noreferrer">{source.title || source.source_name}</a>
                      <div className="source__tags">
                        <span className="tagpill tagpill--type">{SOURCE_TYPE_LABEL[source.source_type] || source.source_type}</span>
                        <span className="tagpill tagpill--lang mono">{langCode(source.language)}</span>
                        <span className="tagpill tagpill--date"><Ic id="i-calendar10" size={10} />{formatDateShort(source.published_date)}</span>
                        <span className="tagpill tagpill--trust"><Ic id="i-shield10" size={10} />Доверенность: {source.trust_level}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </article>

          <aside className="side" aria-label="Справка по сигналу">
            <div className="side__card">
              <div className="side__title">Карточка сигнала</div>
              <dl className="facts">
                <div><dt>Статус</dt><dd>Слабый сигнал</dd></div>
                <div><dt>Область</dt><dd>{item.industry_label}</dd></div>
                <div><dt>Дата обнаружения</dt><dd>{formatDate(run.created_at)}</dd></div>
                <div><dt>Проанализировано источников</dt><dd>{run.processed_sources}</dd></div>
                <div><dt>Уверенность модели</dt><dd>{percent}% ({LEVEL_LABEL[level]})</dd></div>
              </dl>
            </div>
            {similar.length > 0 && (
              <div className="side__card">
                <div className="side__title">Похожие сигналы</div>
                <div className="similar">
                  {similar.map((candidate) => (
                    <Link className="similar__item" href={`/insight/${run.id}/${candidate.id}`} key={candidate.id}>
                      <span>{candidate.title}</span>
                      <span className="similar__score">{scorePercent(candidate.confidence)}%</span>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </aside>
        </div>
      </main>
    </>
  );
}
