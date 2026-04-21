import { useState, useRef } from 'react';
import { SectionHeader, Card, Badge, Btn, Input, Spinner, Divider } from './components';
import { writeArticle } from './api';

const MODELS = [
  { id: "gemini-2.0-flash",  label: "Gemini 2.0 Flash",   badge: "Recommended", color: "green",  note: "1,500 req/day free · Fastest" },
  { id: "gemini-1.5-flash",  label: "Gemini 1.5 Flash",   badge: "Free Tier",   color: "blue",   note: "Very similar quality" },
  { id: "gemini-1.5-pro",    label: "Gemini 1.5 Pro",     badge: "Best Quality",color: "purple", note: "Lower free quota" },
];

function renderMd(md) {
  if (!md) return "";
  let h = md
    .replace(/^# (.+)$/gm,  '<h1 class="art-h1">$1</h1>')
    .replace(/^## (.+)$/gm, '<h2 class="art-h2">$1</h2>')
    .replace(/^### (.+)$/gm,'<h3 class="art-h3">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="art-b">$1</strong>')
    .replace(/\*([^*\n]+)\*/g,  '<em class="art-i">$1</em>')
    .replace(/^> (.+)$/gm,  '<blockquote class="art-bq">$1</blockquote>')
    .replace(/^[-–] (.+)$/gm,'<li class="art-li">$1</li>');
  h = h.replace(/(<li[^>]*>[\s\S]*?<\/li>\n?)+/g, m => `<ul class="art-ul">${m}</ul>`);
  const lines = h.split('\n');
  const out = [];
  for (const line of lines) {
    const t = line.trim();
    if (!t) continue;
    if (/^<(h[1-6]|ul|ol|blockquote)/.test(t)) out.push(t);
    else out.push(`<p class="art-p">${t}</p>`);
  }
  return out.join('\n');
}

export default function ArticleWriterPage({ dna, brief, trend, onArticleReady }) {
  const [model, setModel]       = useState("gemini-2.0-flash");
  const [apiKey, setApiKey]     = useState("");
  const [generating, setGen]    = useState(false);
  const [article, setArticle]   = useState(null);
  const [stream, setStream]     = useState("");
  const [done, setDone]         = useState(false);
  const [copied, setCopied]     = useState(null);
  const [viewMode, setViewMode] = useState("preview");
  const [error, setError]       = useState(null);
  const [checks, setChecks]     = useState([]);
  const timerRef = useRef(null);
  const outRef   = useRef(null);

  const activeBrief = brief || {};
  const activeDNA   = dna   || {};

  function startStream(text, fullArticle) {
    setStream(""); setDone(false);
    let i = 0;
    timerRef.current = setInterval(() => {
      i += 8;
      if (i >= text.length) {
        clearInterval(timerRef.current);
        setStream(text); setDone(true); setGen(false);
        const wc = text.split(/\s+/).length;
        const articleObj = fullArticle || {
          content: text,
          word_count: wc,
          seo_title: activeBrief.title?.slice(0, 60) || "",
          meta_description: (text.split('\n\n')[1] || "").replace(/[#*>]/g, "").slice(0, 157) + "…",
        };
        setArticle(articleObj);
        onArticleReady && onArticleReady(articleObj);
      } else {
        setStream(text.slice(0, i));
        if (outRef.current) outRef.current.scrollTop = outRef.current.scrollHeight;
      }
    }, 16);
  }

  async function generate() {
    if (!brief || !dna) return;
    setGen(true); setStream(""); setDone(false); setArticle(null); setError(null); setChecks([]);

    // Build the trend object for the API
    const trendData = trend || { title: brief.trend_hook || "", summary: "", source: "", url: "" };

    try {
      const result = await writeArticle({
        brief: activeBrief,
        dna: activeDNA,
        trend: trendData,
        model,
        api_key: apiKey || undefined,
      });

      if (result.quality_checks) setChecks(result.quality_checks);
      if (result.seo_title) {
        setArticle({
          content: result.content,
          word_count: result.word_count,
          seo_title: result.seo_title,
          meta_description: result.meta_description,
          quality_passed: result.quality_passed,
        });
      }
      startStream(result.content, result);
    } catch (e) {
      setError(e.message);
      setGen(false);
    }
  }

  function copyContent(type) {
    const text = type === "md"
      ? (article?.content || stream || "")
      : `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>${article?.seo_title || ""}</title></head><body>${renderMd(article?.content || stream)}</body></html>`;
    navigator.clipboard.writeText(text).then(() => { setCopied(type); setTimeout(() => setCopied(null), 2000); });
  }

  const wc = stream.split(/\s+/).filter(Boolean).length;
  const wcColor = wc < 1100 ? "var(--text-3)" : wc <= 1600 ? "var(--green)" : "var(--red)";

  const hasBrief = brief && brief.title;

  return (
    <div>
      <SectionHeader step="04" title="Article Generator"
        subtitle="Company voice + trend hook + brief → full SEO/AEO/GEO article. Powered by Gemini free tier. No paid API required." />

      {!hasBrief && (
        <Card style={{ marginBottom: 18 }}>
          <p style={{ margin: 0, fontSize: 14, color: "var(--text-3)", textAlign: "center" }}>
            Complete Engines 01–03 first to generate an article.
          </p>
        </Card>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 16, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Card style={{ padding: 16 }}>
            <p style={{ margin: "0 0 9px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Active Brief</p>
            <p style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 600, color: "var(--text)", lineHeight: 1.4 }}>{activeBrief.title || "No brief selected"}</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 7 }}>
              {activeBrief.primary_keyword && <Badge color="blue">{activeBrief.primary_keyword}</Badge>}
              {activeBrief.article_type && <Badge color="gray">{activeBrief.article_type}</Badge>}
              {activeBrief.word_count && <Badge color="amber">{activeBrief.word_count}w</Badge>}
            </div>
            <p style={{ margin: 0, fontSize: 11, color: "var(--text-4)" }}>
              {activeDNA.name || "—"} · {activeDNA.tone_adjectives?.join(", ") || "—"}
            </p>
          </Card>

          <Card style={{ padding: 16 }}>
            <p style={{ margin: "0 0 9px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Model</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {MODELS.map(m => (
                <div key={m.id} onClick={() => setModel(m.id)} style={{
                  padding: "8px 10px", borderRadius: 7, cursor: "pointer",
                  background: model === m.id ? "var(--accent-subtle)" : "transparent",
                  border: `1px solid ${model === m.id ? "var(--accent-border)" : "transparent"}`,
                  transition: "all 0.13s",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: model === m.id ? "var(--text)" : "var(--text-2)" }}>{m.label}</span>
                    <Badge color={m.color} size="xs">{m.badge}</Badge>
                  </div>
                  <span style={{ fontSize: 10, color: "var(--text-4)" }}>{m.note}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card style={{ padding: 16 }}>
            <p style={{ margin: "0 0 8px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Gemini API Key</p>
            <Input value={apiKey} onChange={setApiKey} placeholder="Blank = use server .env key" type="password" style={{ marginBottom: 7 }} />
            <p style={{ margin: 0, fontSize: 11, color: "var(--text-4)" }}>
              Free at <span style={{ color: "var(--accent)" }}>aistudio.google.com</span> — 1,500 req/day
            </p>
          </Card>

          {error && (
            <Card style={{ padding: 16, borderColor: "var(--red-border)" }}>
              <p style={{ margin: 0, fontSize: 12, color: "var(--red)" }}>{error}</p>
            </Card>
          )}

          <button onClick={generate} disabled={generating || !hasBrief} style={{
            background: generating || !hasBrief ? "var(--surface-2)" : "var(--accent)",
            color: generating || !hasBrief ? "var(--text-3)" : "#fff",
            border: generating || !hasBrief ? "1px solid var(--border)" : "none",
            borderRadius: 9, padding: "12px 0", fontSize: 14, fontWeight: 700,
            cursor: generating || !hasBrief ? "not-allowed" : "pointer",
            transition: "all 0.18s", display: "flex", alignItems: "center",
            justifyContent: "center", gap: 9, fontFamily: "var(--font-ui)",
            boxShadow: generating || !hasBrief ? "none" : "0 4px 16px var(--accent-glow)",
          }}>
            {generating ? <><Spinner size={14} /> Generating…</> : "Generate Article"}
          </button>

          {done && checks.length > 0 && (
            <Card style={{ padding: 16 }}>
              <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>Quality Checks</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {checks.map((c, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 12, color: c.pass ? "var(--green)" : "var(--red)", flexShrink: 0 }}>{c.pass ? "✓" : "✗"}</span>
                    <span style={{ fontSize: 11, color: c.pass ? "var(--text-2)" : "var(--red)" }}>{c.label}</span>
                  </div>
                ))}
              </div>
              <Divider style={{ margin: "10px 0" }} />
              <Badge color={article?.quality_passed ? "green" : "amber"}>
                {checks.filter(c => c.pass).length} / {checks.length} checks passed
              </Badge>
            </Card>
          )}
        </div>

        <Card style={{ padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <div style={{
            padding: "11px 16px", borderBottom: "1px solid var(--border)",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ display: "flex", background: "var(--surface-2)", borderRadius: 7, padding: 3, gap: 2 }}>
                {[["preview","Preview"],["raw","Markdown"]].map(([id,lbl]) => (
                  <button key={id} onClick={() => setViewMode(id)} style={{
                    background: viewMode === id ? "var(--surface)" : "transparent",
                    border: viewMode === id ? "1px solid var(--border)" : "1px solid transparent",
                    borderRadius: 5, padding: "3px 10px", fontSize: 11, fontWeight: 600,
                    cursor: "pointer", color: viewMode === id ? "var(--text)" : "var(--text-3)",
                    transition: "all 0.12s", fontFamily: "var(--font-ui)",
                  }}>{lbl}</button>
                ))}
              </div>
              {wc > 0 && <span style={{ fontSize: 11, color: wcColor, fontFamily: "var(--font-mono)" }}>{wc.toLocaleString()} words</span>}
              {generating && !done && <Spinner size={12} />}
              {done && <Badge color="green" size="xs">Complete</Badge>}
            </div>
            {done && (
              <div style={{ display: "flex", gap: 7 }}>
                <Btn onClick={() => copyContent("md")}   variant="ghost" size="sm">{copied === "md"   ? "✓ Copied" : "Copy .md"}</Btn>
                <Btn onClick={() => copyContent("html")} variant="ghost" size="sm">{copied === "html" ? "✓ Copied" : "Copy HTML"}</Btn>
              </div>
            )}
          </div>

          <div ref={outRef} style={{ flex: 1, overflowY: "auto", minHeight: 520, maxHeight: "68vh", padding: "22px 26px" }}>
            {!stream && !generating && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 400, gap: 10 }}>
                <div style={{ fontSize: 36, opacity: 0.2 }}>✍</div>
                <p style={{ color: "var(--text-3)", fontSize: 14, margin: 0, textAlign: "center", lineHeight: 1.7 }}>
                  Select your brief, choose a model,<br />then click Generate Article.
                </p>
                <p style={{ color: "var(--text-4)", fontSize: 11, margin: 0, fontFamily: "var(--font-mono)" }}>
                  ~1,300 words · SEO + AEO + GEO signals baked in
                </p>
              </div>
            )}
            {stream && viewMode === "preview" && (
              <div className="art-body" dangerouslySetInnerHTML={{ __html: renderMd(stream) }} />
            )}
            {stream && viewMode === "raw" && (
              <pre style={{
                fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-2)",
                whiteSpace: "pre-wrap", lineHeight: 1.7, margin: 0,
              }}>{stream}</pre>
            )}
          </div>

          {done && article && (
            <div style={{ padding: "11px 18px", borderTop: "1px solid var(--border)", display: "flex", gap: 20, flexWrap: "wrap" }}>
              <div style={{ flex: "0 0 auto" }}>
                <p style={{ margin: "0 0 3px", fontSize: 9, color: "var(--text-4)", textTransform: "uppercase", letterSpacing: "0.09em", fontFamily: "var(--font-mono)" }}>SEO Title</p>
                <p style={{ margin: 0, fontSize: 12, color: "var(--text-2)" }}>{article.seo_title}</p>
              </div>
              <div style={{ flex: 1 }}>
                <p style={{ margin: "0 0 3px", fontSize: 9, color: "var(--text-4)", textTransform: "uppercase", letterSpacing: "0.09em", fontFamily: "var(--font-mono)" }}>Meta Description</p>
                <p style={{ margin: 0, fontSize: 12, color: "var(--text-2)" }}>{article.meta_description}</p>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
