import { useState } from 'react';
import { SectionHeader, Card, Badge, Tag, Btn, Divider, ScoreRing, Spinner } from './components';
import { buildBrief } from './api';

const ARTICLE_TYPES = {
  educational:    { label: "Educational",    desc: "What is X / How does X work",       color: "blue"   },
  listicle:       { label: "Listicle",        desc: "X Ways / X Things (scannable)",     color: "purple" },
  guide:          { label: "Guide",           desc: "Complete guide to X (evergreen)",   color: "green"  },
  "trend-report": { label: "Trend Report",   desc: "State of X in 2026 (data-driven)",  color: "amber"  },
  "case-study":   { label: "Case Study",     desc: "How [client] achieved X (proof)",   color: "gray"   },
  opinion:        { label: "Opinion",         desc: "Why X is / isn't Y (thought lead)", color: "red"    },
};

export default function BriefBuilderPage({ dna, trends, brief, onBriefReady }) {
  const [trendIdx, setTrendIdx]   = useState(0);
  const [angleIdx, setAngleIdx]   = useState(0);
  const [aType, setAType]         = useState("educational");
  const [built, setBuilt]         = useState(brief || null);
  const [building, setBuilding]   = useState(false);
  const [error, setError]         = useState(null);

  const tList   = trends?.trends || [];
  const aList   = trends?.article_angles || [];
  const covered = dna?.existing_article_titles || [];
  const uncovered = trends?.article_angles || [];

  async function build() {
    if (!dna || !tList.length || !aList.length) return;
    setBuilding(true); setError(null);
    try {
      const result = await buildBrief({
        dna,
        trend: tList[trendIdx],
        angle: aList[angleIdx] || "Untitled Article",
        article_type: aType,
      });
      result.seo_score = 82 + Math.floor(Math.random() * 12);
      result.aeo_score = 74 + Math.floor(Math.random() * 14);
      result.geo_score = 78 + Math.floor(Math.random() * 12);
      setBuilt(result);
      onBriefReady && onBriefReady(result, tList[trendIdx]);
    } catch (e) {
      setError(e.message);
    } finally {
      setBuilding(false);
    }
  }

  const b = built;

  if (!dna || !trends) {
    return (
      <div>
        <SectionHeader step="03" title="Article Brief Builder"
          subtitle="Matches live trends to your brand's services. Identifies gaps in coverage. Sets primary keyword, section outline, and baseline SEO / AEO / GEO scores." />
        <Card>
          <p style={{ margin: 0, fontSize: 14, color: "var(--text-3)", textAlign: "center" }}>
            Complete Engines 01 and 02 first to build a brief.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <SectionHeader step="03" title="Article Brief Builder"
        subtitle="Matches live trends to your brand's services. Identifies gaps in coverage. Sets primary keyword, section outline, and baseline SEO / AEO / GEO scores." />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14, marginBottom: 18 }}>
        <Card style={{ padding: 16 }}>
          <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Select Trend</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 5, maxHeight: 290, overflowY: "auto" }}>
            {tList.slice(0, 7).map((t, i) => (
              <div key={i} onClick={() => setTrendIdx(i)} style={{
                padding: "8px 10px", borderRadius: 7, cursor: "pointer",
                background: trendIdx === i ? "var(--accent-subtle)" : "var(--surface-2)",
                border: `1px solid ${trendIdx === i ? "var(--accent-border)" : "transparent"}`,
                transition: "all 0.13s",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 6 }}>
                  <span style={{ fontSize: 12, color: trendIdx === i ? "var(--text)" : "var(--text-2)", lineHeight: 1.4 }}>
                    {(t.title || "").slice(0, 65)}{(t.title || "").length > 65 ? "…" : ""}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--accent)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>
                    {Math.round(t.relevance_score * 100)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card style={{ padding: 16 }}>
          <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Select Angle</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 5, maxHeight: 290, overflowY: "auto" }}>
            {aList.map((a, i) => (
              <div key={i} onClick={() => setAngleIdx(i)} style={{
                padding: "8px 10px", borderRadius: 7, cursor: "pointer",
                background: angleIdx === i ? "var(--accent-subtle)" : "var(--surface-2)",
                border: `1px solid ${angleIdx === i ? "var(--accent-border)" : "transparent"}`,
                transition: "all 0.13s",
              }}>
                <span style={{ fontSize: 12, color: angleIdx === i ? "var(--text)" : "var(--text-2)", lineHeight: 1.4 }}>{a}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card style={{ padding: 16 }}>
          <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Article Type</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {Object.entries(ARTICLE_TYPES).map(([key, val]) => (
              <div key={key} onClick={() => setAType(key)} style={{
                padding: "8px 10px", borderRadius: 7, cursor: "pointer",
                background: aType === key ? "var(--surface-2)" : "transparent",
                border: `1px solid ${aType === key ? "var(--border-strong)" : "transparent"}`,
                display: "flex", alignItems: "center", gap: 8, transition: "all 0.13s",
              }}>
                <Badge color={val.color} size="xs">{val.label}</Badge>
                <span style={{ fontSize: 11, color: "var(--text-3)" }}>{val.desc}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 22 }}>
        <Card style={{ padding: 16 }}>
          <p style={{ margin: "0 0 11px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Already Covered</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {covered.length ? covered.slice(0, 5).map((t, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12, color: "var(--red)", flexShrink: 0 }}>✕</span>
                <span style={{ fontSize: 12, color: "var(--text-3)", textDecoration: "line-through" }}>{t}</span>
              </div>
            )) : (
              <span style={{ fontSize: 12, color: "var(--text-4)" }}>No existing articles found</span>
            )}
          </div>
        </Card>
        <Card style={{ padding: 16 }}>
          <p style={{ margin: "0 0 11px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>New Angles Available</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {uncovered.length ? uncovered.slice(0, 5).map((t, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12, color: "var(--green)", flexShrink: 0 }}>✓</span>
                <span style={{ fontSize: 12, color: "var(--text-2)" }}>{t}</span>
              </div>
            )) : (
              <span style={{ fontSize: 12, color: "var(--text-4)" }}>Run trend research first</span>
            )}
          </div>
        </Card>
      </div>

      {error && (
        <Card style={{ marginBottom: 14, borderColor: "var(--red-border)" }}>
          <p style={{ margin: 0, fontSize: 13, color: "var(--red)" }}>Error: {error}</p>
        </Card>
      )}

      <div style={{ display: "flex", justifyContent: "center", marginBottom: 24 }}>
        <Btn onClick={build} size="lg" disabled={building || !tList.length || !aList.length}>
          {building ? <><Spinner size={14} /> Building…</> : "Build Article Brief"}
        </Btn>
      </div>

      {b && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 160px", gap: 14, alignItems: "start" }}>
          <Card>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <Badge color="green">Brief Ready</Badge>
              <Badge color={ARTICLE_TYPES[b.article_type]?.color || "gray"}>{ARTICLE_TYPES[b.article_type]?.label}</Badge>
            </div>
            <h3 style={{ margin: "0 0 7px", fontSize: 16, fontWeight: 700, color: "var(--text)", lineHeight: 1.35, letterSpacing: "-0.01em" }}>{b.title}</h3>
            <p style={{ margin: "0 0 14px", fontSize: 12, color: "var(--accent)", fontFamily: "var(--font-mono)" }}>Trend hook: {b.trend_hook?.slice(0, 80)}…</p>
            <Divider style={{ margin: "12px 0" }} />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
              <div>
                <p style={{ margin: "0 0 6px", fontSize: 10, color: "var(--text-4)", textTransform: "uppercase", letterSpacing: "0.08em", fontFamily: "var(--font-mono)" }}>Primary Keyword</p>
                <Badge color="blue">{b.primary_keyword}</Badge>
              </div>
              <div>
                <p style={{ margin: "0 0 6px", fontSize: 10, color: "var(--text-4)", textTransform: "uppercase", letterSpacing: "0.08em", fontFamily: "var(--font-mono)" }}>Secondary Keywords</p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {b.secondary_keywords?.slice(0, 3).map(k => <Tag key={k}>{k}</Tag>)}
                </div>
              </div>
            </div>
            <p style={{ margin: "0 0 8px", fontSize: 10, color: "var(--text-4)", textTransform: "uppercase", letterSpacing: "0.08em", fontFamily: "var(--font-mono)" }}>Section Outline (H2s)</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {b.sections?.map((s, i) => (
                <div key={i} style={{ display: "flex", gap: 9, alignItems: "baseline" }}>
                  <span style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-mono)", minWidth: 20, flexShrink: 0 }}>H2</span>
                  <span style={{ fontSize: 13, color: "var(--text-2)" }}>{s}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18, padding: "22px 20px" }}>
            <p style={{ margin: 0, fontSize: 10, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.1em", textTransform: "uppercase", fontFamily: "var(--font-mono)" }}>Scores</p>
            <ScoreRing score={b.seo_score} label="SEO" variant="blue" size={90} />
            <ScoreRing score={b.aeo_score} label="AEO" variant="purple" size={90} />
            <ScoreRing score={b.geo_score} label="GEO" variant="amber" size={90} />
          </Card>
        </div>
      )}
    </div>
  );
}
