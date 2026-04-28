import { useState } from 'react';
import { SectionHeader, Card, Btn, Spinner, Badge, Tag, ProgressBar } from './components';
import { researchTrends } from './api';

const SRC_COLOR = { "Google News": "blue", "DuckDuckGo": "purple" };

// Segment display config
const SEG_CONFIG = {
  brand_news:     { label: "Brand News",     color: "green",  dot: "#22c55e" },
  brand_future:   { label: "Brand Future",   color: "amber",  dot: "#f59e0b" },
  industry_trend: { label: "Industry Trend", color: "blue",   dot: "#3b82f6" },
  competitive:    { label: "Competitive",    color: "purple", dot: "#a855f7" },
};

export default function TrendResearchPage({ dna, trends, onTrendsReady }) {
  const [tab, setTab]           = useState("live");
  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [log, setLog]           = useState([]);
  const [result, setResult]     = useState(trends || null);
  const [expanded, setExpanded] = useState(null);
  const [filter, setFilter]     = useState("all");
  const [error, setError]       = useState(null);

  async function scan() {
    if (!dna) return;
    setScanning(true); setProgress(0); setLog([]); setResult(null); setError(null);

    const logSteps = [
      { t: "info", msg: `[trends] Starting research for: ${dna.name}` },
      { t: "req",  msg: `[trends] Searching brand activity — what ${dna.name} has done & plans…` },
      { t: "req",  msg: "[trends] Google News RSS — fetching real-time industry headlines…" },
      { t: "req",  msg: "[trends] DuckDuckGo — querying broader web context…" },
      { t: "info", msg: "[trends] Deduplicating and scoring relevance…" },
      { t: "info", msg: "[trends] Gemini AI — classifying segments & generating brand-aware angles…" },
    ];
    let i = 0;
    const iv = setInterval(() => {
      if (i < logSteps.length) {
        const step = logSteps[i];
        const pct  = Math.round(((i + 1) / logSteps.length) * 80);
        i++;
        setLog(prev => [...prev, step]);
        setProgress(pct);
      } else {
        clearInterval(iv);
      }
    }, 500);

    try {
      const report = await researchTrends({
        services:        dna.services,
        top_keywords:    dna.top_keywords,
        existing_titles: dna.existing_article_titles || [],
        brand_name:      dna.name  || '',
        domain:          dna.domain || '',
      });
      clearInterval(iv);
      const segCounts = report.segments || {};
      setLog(prev => [
        ...prev,
        { t: "ok", msg: `[trends] ${report.trends.length} trends found` },
        { t: "ok", msg: `[trends] Segments — brand:${(segCounts.brand_news||0)+(segCounts.brand_future||0)} industry:${segCounts.industry_trend||0} competitive:${segCounts.competitive||0}` },
        { t: "ok", msg: `[trends] ${report.article_angles.length} article angles generated` },
      ]);
      setProgress(100);
      setTimeout(() => { setResult(report); setScanning(false); }, 400);
    } catch (e) {
      clearInterval(iv);
      setError(e.message);
      setScanning(false);
    }
  }

  const logColor = { req: "var(--accent)", info: "var(--text-2)", ok: "var(--green)" };

  const FILTER_TABS = [
    { id: "all",            label: "All" },
    { id: "brand_news",     label: "Brand News" },
    { id: "brand_future",   label: "Brand Future" },
    { id: "industry_trend", label: "Industry" },
    { id: "competitive",    label: "Competitive" },
  ];
  const filtered = result?.trends?.filter(t =>
    filter === "all" || t.segment === filter
  ) || [];

  return (
    <div>
      <SectionHeader step="02" title="Live Trend Research"
        subtitle="Pulls real-time signals from Google News RSS and DuckDuckGo web search. No API keys. Scores each trend by relevance to your Brand DNA." />

      <div style={{ display: "flex", gap: 0, marginBottom: 22, borderBottom: "1px solid var(--border)" }}>
        {[["live", "Live Trends"], ["scraper", "Article Scraper"]].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            background: "none", border: "none", borderBottom: `2px solid ${tab === id ? "var(--accent)" : "transparent"}`,
            padding: "9px 18px", cursor: "pointer", fontSize: 13, fontWeight: 600,
            color: tab === id ? "var(--text)" : "var(--text-3)",
            transition: "all 0.15s", fontFamily: "var(--font-ui)", marginBottom: -1,
          }}>{label}</button>
        ))}
      </div>

      {tab === "live" && (
        <div>
          {!result && !scanning && (
            <Card style={{ marginBottom: 18, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
              <div>
                <p style={{ margin: "0 0 3px", fontSize: 14, fontWeight: 600, color: "var(--text)" }}>Ready to scan industry trends</p>
                <p style={{ margin: 0, fontSize: 12, color: "var(--text-3)" }}>
                  {dna ? `Detected company: ${dna.name} · Sources: Google News, DuckDuckGo` : "Complete Brand DNA extraction first"}
                </p>
              </div>
              <Btn onClick={scan} disabled={!dna}>Scan Now</Btn>
            </Card>
          )}

          {error && (
            <Card style={{ marginBottom: 18, borderColor: "var(--red-border)" }}>
              <p style={{ margin: 0, fontSize: 13, color: "var(--red)" }}>Error: {error}</p>
            </Card>
          )}

          {scanning && (
            <Card style={{ marginBottom: 18 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                <Spinner size={13} />
                <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", fontFamily: "var(--font-mono)" }}>SCANNING — {progress}%</span>
              </div>
              <ProgressBar value={progress} />
              <div style={{
                marginTop: 13,
                background: "rgba(0,0,0,0.5)",
                borderRadius: 8,
                border: "1px solid var(--border)",
                padding: "12px 16px",
                maxHeight: 170, overflow: "hidden",
                fontFamily: "var(--font-mono)", fontSize: 11, lineHeight: 1.85,
              }}>
                {log.map((l, i) => (
                  <div key={i} style={{ color: logColor[l.t] || "var(--text-2)", animation: "fadeIn 0.3s ease both" }}>{l.msg}</div>
                ))}
              </div>
            </Card>
          )}

          {result && (
            <div>
              {/* Header row */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
                <Badge color="green">{result.trends.length} trends</Badge>
                <Badge color="blue">{result.industry}</Badge>
                {result.segments?.brand_news > 0 && <Badge color="green">{result.segments.brand_news} brand news</Badge>}
                {result.segments?.brand_future > 0 && <Badge color="amber">{result.segments.brand_future} brand future</Badge>}
                {result.segments?.competitive > 0 && <Badge color="purple">{result.segments.competitive} competitive</Badge>}
                <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
                  {new Date(result.generated_at).toLocaleTimeString()}
                </span>
                <Btn onClick={scan} variant="ghost" size="sm">↻ Rescan</Btn>
                <Btn onClick={() => onTrendsReady && onTrendsReady(result)} size="sm">
                  Continue to Brief →
                </Btn>
              </div>

              {/* Brand summary box */}
              {result.brand_summary && (
                <Card style={{ marginBottom: 16, borderColor: "var(--badge-green-border)", background: "var(--badge-green-bg)" }}>
                  <p style={{ margin: "0 0 4px", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--green)", fontFamily: "var(--font-mono)" }}>
                    Brand Trajectory
                  </p>
                  <p style={{ margin: 0, fontSize: 13, color: "var(--text)", lineHeight: 1.6 }}>{result.brand_summary}</p>
                </Card>
              )}

              {/* Key themes */}
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 14 }}>
                {result.key_themes?.map(t => <Tag key={t}>{t}</Tag>)}
              </div>

              {/* Segment filter tabs */}
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 14 }}>
                {FILTER_TABS.map(f => {
                  const seg = SEG_CONFIG[f.id];
                  const isActive = filter === f.id;
                  return (
                    <button key={f.id} onClick={() => setFilter(f.id)} style={{
                      padding: "4px 11px", borderRadius: 20, fontSize: 11, fontWeight: 600, cursor: "pointer",
                      border: `1px solid ${isActive && seg ? seg.dot : "var(--border)"}`,
                      background: isActive ? (seg ? seg.dot + "22" : "var(--surface-2)") : "transparent",
                      color: isActive && seg ? seg.dot : "var(--text-3)",
                      transition: "all 0.15s",
                    }}>
                      {seg && <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: seg.dot, marginRight: 5, verticalAlign: "middle" }} />}
                      {f.label}
                    </button>
                  );
                })}
              </div>

              {/* Trends list */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {filtered.map((t, i) => {
                  const segCfg = SEG_CONFIG[t.segment] || SEG_CONFIG.industry_trend;
                  return (
                  <div key={i} onClick={() => setExpanded(expanded === i ? null : i)} style={{
                    background: expanded === i ? "var(--surface-2)" : "var(--surface)",
                    border: `1px solid ${expanded === i ? segCfg.dot + "66" : "var(--border)"}`,
                    borderLeft: `3px solid ${segCfg.dot}`,
                    borderRadius: 10, padding: "13px 16px", cursor: "pointer", transition: "all 0.15s",
                  }}>
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                      <div style={{
                        width: 40, height: 40, borderRadius: 8, flexShrink: 0,
                        background: "var(--surface-2)", border: "1px solid var(--border)",
                        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                      }}>
                        <span style={{
                          fontSize: 15, fontWeight: 800, fontFamily: "var(--font-display)",
                          color: t.relevance_score > 0.8 ? "var(--green)" : t.relevance_score > 0.7 ? "var(--accent)" : "var(--amber)",
                          lineHeight: 1,
                        }}>{Math.round(t.relevance_score * 100)}</span>
                        <span style={{ fontSize: 8, color: "var(--text-4)", letterSpacing: "0.05em" }}>REL</span>
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5, flexWrap: "wrap" }}>
                          <Badge color={segCfg.color} size="xs">{segCfg.label}</Badge>
                          <Badge color={SRC_COLOR[t.source] || "gray"} size="xs">{t.source}</Badge>
                          {t.published && <span style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>{t.published}</span>}
                        </div>
                        <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: "var(--text)", lineHeight: 1.4 }}>{t.title}</p>
                        {expanded === i && (
                          <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--text-2)", lineHeight: 1.65 }}>{t.summary}</p>
                        )}
                      </div>
                      <span style={{ fontSize: 11, color: "var(--text-4)", flexShrink: 0, marginTop: 2 }}>{expanded === i ? "▲" : "▼"}</span>
                    </div>
                  </div>
                  );
                })}
              </div>

              {result.article_angles?.length > 0 && (
                <Card style={{ marginTop: 18 }}>
                  <p style={{ margin: "0 0 12px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
                    Generated Article Angles
                  </p>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {result.article_angles.map((a, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 10, padding: "8px 11px", background: "var(--surface-2)", borderRadius: 7 }}>
                        <span style={{ fontSize: 10, color: "var(--accent)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>#{i+1}</span>
                        <span style={{ fontSize: 13, color: "var(--text-2)" }}>{a}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

            </div>
          )}
        </div>
      )}

      {tab === "scraper" && (
        <div>
          {dna ? (
            <div>
              <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
                <Badge color="green">{dna.existing_article_titles?.length || 0} articles found</Badge>
                <Badge color="gray">{dna.domain}</Badge>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {dna.existing_article_titles?.map((title, i) => (
                  <Card key={i} style={{ padding: "11px 15px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
                      <span style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)", minWidth: 22 }}>#{i+1}</span>
                      <span style={{ flex: 1, fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{title}</span>
                      <Badge color="amber" size="xs">covered</Badge>
                    </div>
                  </Card>
                ))}
              </div>
              {dna.existing_article_titles?.length > 0 && (
                <div style={{ marginTop: 14, padding: "11px 14px", background: "var(--badge-green-bg)", border: "1px solid var(--badge-green-border)", borderRadius: 8 }}>
                  <p style={{ margin: 0, fontSize: 13, color: "var(--green)" }}>
                    Brief Builder will detect these {dna.existing_article_titles.length} covered topics and generate only fresh angles.
                  </p>
                </div>
              )}
            </div>
          ) : (
            <Card>
              <p style={{ color: "var(--text-3)", fontSize: 14, textAlign: "center", margin: 0 }}>
                Complete Brand DNA extraction first to see scraped articles.
              </p>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
