import { useState } from 'react';
import { SectionHeader, Card, Input, Btn, Spinner, Badge, Divider, Tag } from './components';
import { extractDNA } from './api';

const SCRAPE_STEPS = [
  { label: "Checking robots.txt compliance", duration: 500 },
  { label: "Scraping homepage", duration: 850 },
  { label: "Discovering section pages — about, services, portfolio", duration: 1000 },
  { label: "Reading blog articles for tone analysis", duration: 1200 },
  { label: "Running spaCy NLP keyword extraction", duration: 900 },
  { label: "Analysing tone and writing style", duration: 650 },
  { label: "Extracting USPs and portfolio items", duration: 550 },
  { label: "Building CompanyDNA profile", duration: 450 },
];

export default function BrandDNAPage({ dna, onDNAReady, initialUrl }) {
  const [url, setUrl]         = useState(initialUrl || "");
  const [phase, setPhase]     = useState("idle");
  const [stepIdx, setStepIdx] = useState(0);
  const [stepsDone, setStepsDone] = useState([]);
  const [result, setResult]   = useState(dna || null);
  const [error, setError]     = useState(null);

  function animateSteps(idx, done) {
    if (idx >= SCRAPE_STEPS.length) return;
    setStepIdx(idx);
    setTimeout(() => {
      const next = [...done, idx];
      setStepsDone(next);
      animateSteps(idx + 1, next);
    }, SCRAPE_STEPS[idx].duration);
  }

  async function start() {
    const u = url.trim();
    if (!u) return;
    setPhase("scraping"); setStepIdx(0); setStepsDone([]); setResult(null); setError(null);
    animateSteps(0, []);
    try {
      const r = await extractDNA(u);
      setResult(r); setPhase("done");
      onDNAReady && onDNAReady(r);
    } catch (e) {
      setError(e.message); setPhase("error");
    }
  }

  const d = result;

  return (
    <div>
      <SectionHeader step="01" title="Brand DNA Extraction"
        subtitle="Paste a website URL. The engine scrapes homepage, about, services, portfolio and blog pages — then builds a full company voice profile using NLP." />

      <Card style={{ marginBottom: 18 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Input value={url} onChange={setUrl} placeholder="https://yourclient.com"
            prefix="🌐" style={{ flex: 1 }}
            onKeyDown={e => e.key === "Enter" && start()} />
          <Btn onClick={start} disabled={!url.trim() || phase === "scraping"}>
            {phase === "scraping" ? <><Spinner size={13} /> Scraping…</> : "Extract DNA"}
          </Btn>
        </div>
        <p style={{ margin: "9px 0 0", fontSize: 12, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
          Respects robots.txt · 1.2 s delay between requests · Playwright headless Chromium
        </p>
      </Card>

      {error && (
        <Card style={{ marginBottom: 18, borderColor: "var(--red-border)" }}>
          <p style={{ margin: 0, fontSize: 13, color: "var(--red)" }}>Error: {error}</p>
        </Card>
      )}

      {phase === "scraping" && (
        <Card style={{ marginBottom: 18 }}>
          <p style={{ margin: "0 0 14px", fontSize: 12, fontWeight: 600, color: "var(--text-2)", fontFamily: "var(--font-mono)", letterSpacing: "0.05em" }}>EXTRACTING COMPANY DNA</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
            {SCRAPE_STEPS.map((s, i) => {
              const done = stepsDone.includes(i);
              const active = stepIdx === i && !done;
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, opacity: i > stepIdx ? 0.25 : 1, transition: "opacity 0.3s" }}>
                  <div style={{
                    width: 20, height: 20, borderRadius: "50%", flexShrink: 0,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    background: done ? "var(--badge-green-bg)" : active ? "var(--badge-blue-bg)" : "var(--surface-2)",
                    border: `1px solid ${done ? "var(--badge-green-border)" : active ? "var(--badge-blue-border)" : "var(--border)"}`,
                    transition: "all 0.25s",
                  }}>
                    {done ? <span style={{ fontSize: 10, color: "var(--green)" }}>✓</span>
                          : active ? <Spinner size={9} /> : null}
                  </div>
                  <span style={{ fontSize: 13, color: done ? "var(--text)" : active ? "var(--accent)" : "var(--text-3)", transition: "color 0.25s" }}>{s.label}</span>
                </div>
              );
            })}
            {stepsDone.length === SCRAPE_STEPS.length && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                <Spinner size={12} />
                <span style={{ fontSize: 12, color: "var(--text-2)" }}>Waiting for server response…</span>
              </div>
            )}
          </div>
        </Card>
      )}

      {d && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 5 }}>
                  <h2 style={{ margin: 0, fontSize: 19, fontWeight: 700, color: "var(--text)", letterSpacing: "-0.02em" }}>{d.name}</h2>
                  <Badge color="green">DNA Saved</Badge>
                </div>
                <p style={{ margin: "0 0 6px", fontSize: 13, color: "var(--accent)", fontStyle: "italic" }}>{d.tagline}</p>
                <p style={{ margin: 0, fontSize: 12, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>{d.domain}</p>
              </div>
            </div>
            <Divider style={{ margin: "16px 0" }} />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 0 }}>
              {[
                { label: "Services", value: d.services?.length || 0 },
                { label: "Keywords", value: d.top_keywords?.length || 0 },
                { label: "Articles found", value: d.existing_article_titles?.length || 0 },
                { label: "Portfolio items", value: d.portfolio_items?.length || 0 },
              ].map((stat, i) => (
                <div key={i} style={{ textAlign: "center", padding: "8px 0", borderRight: i < 3 ? "1px solid var(--border)" : "none" }}>
                  <div style={{ fontSize: 26, fontWeight: 800, color: "var(--accent)", fontFamily: "var(--font-mono)", lineHeight: 1 }}>{stat.value}</div>
                  <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }}>{stat.label}</div>
                </div>
              ))}
            </div>
          </Card>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <Card>
              <p style={{ margin: "0 0 12px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Services</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {d.services?.slice(0, 6).map((s, i) => (
                  <div key={i} style={{ display: "flex", gap: 9 }}>
                    <span style={{ color: "var(--accent)", fontSize: 12, marginTop: 1, flexShrink: 0 }}>—</span>
                    <span style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.45 }}>{s}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <p style={{ margin: "0 0 12px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Tone of Voice</p>
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 12 }}>
                {d.tone_adjectives?.map(t => <Badge key={t} color="purple">{t}</Badge>)}
                <Badge color="blue">{d.uses_first_person ? "first person" : "third person"}</Badge>
                <Badge color="gray">~{d.avg_sentence_length}w/sentence</Badge>
              </div>
              {d.tone_sample && (
                <div style={{ background: "var(--surface-2)", borderRadius: 8, padding: "11px 13px", borderLeft: "3px solid var(--accent)" }}>
                  <p style={{ margin: 0, fontSize: 12, color: "var(--text-2)", fontStyle: "italic", lineHeight: 1.65 }}>"{d.tone_sample}"</p>
                  <p style={{ margin: "6px 0 0", fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>tone sample from site</p>
                </div>
              )}
            </Card>

            <Card>
              <p style={{ margin: "0 0 12px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Keywords — spaCy NLP</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                {d.top_keywords?.map((k, i) => <Tag key={k} active={i < 4}>{k}</Tag>)}
              </div>
            </Card>

            <Card>
              <p style={{ margin: "0 0 12px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>USPs Detected</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                {d.usps?.length ? d.usps.map((u, i) => (
                  <div key={i} style={{ display: "flex", gap: 9, alignItems: "flex-start" }}>
                    <span style={{ color: "var(--amber)", fontSize: 13, flexShrink: 0 }}>★</span>
                    <span style={{ fontSize: 12, color: "var(--text-2)", lineHeight: 1.55 }}>{u}</span>
                  </div>
                )) : (
                  <span style={{ fontSize: 12, color: "var(--text-4)" }}>No USPs detected from website content</span>
                )}
              </div>
            </Card>
          </div>

          {d.existing_article_titles?.length > 0 && (
            <Card>
              <p style={{ margin: "0 0 12px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
                Existing Articles — Topics Already Covered
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 7 }}>
                {d.existing_article_titles.map((t, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 11px", background: "var(--surface-2)", borderRadius: 7 }}>
                    <span style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>#{i+1}</span>
                    <span style={{ fontSize: 12, color: "var(--text-2)" }}>{t}</span>
                  </div>
                ))}
              </div>
              <p style={{ margin: "11px 0 0", fontSize: 11, color: "var(--text-4)" }}>
                Brief Builder will avoid these angles when generating new article ideas.
              </p>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
