import { useState, useEffect, Component } from 'react';
import { Badge } from './components';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "40px 32px" }}>
          <p style={{ fontSize: 11, fontWeight: 700, color: "var(--red)", fontFamily: "var(--font-mono)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>
            Render Error
          </p>
          <p style={{ fontSize: 14, color: "var(--text)", marginBottom: 16 }}>
            {this.state.error?.message || "An unexpected error occurred."}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{ fontSize: 13, padding: "7px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)", cursor: "pointer" }}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
import LandingPage from './Landing';
import BrandDNAPage from './BrandDNA';
import TrendResearchPage from './TrendResearch';
import BriefBuilderPage from './BriefBuilder';
import ArticleWriterPage from './ArticleWriter';

const NAV = [
  { id: "dna",    engine: "01", label: "Brand DNA",      desc: "Extract company profile",    icon: "◎" },
  { id: "trends", engine: "02", label: "Trend Research", desc: "Live industry signals",       icon: "⟡" },
  { id: "brief",  engine: "03", label: "Brief Builder",  desc: "Article architecture",        icon: "⬡" },
  { id: "writer", engine: "04", label: "Article Writer", desc: "Generate full article",       icon: "✦" },
];

function ThemeToggle({ dark, setDark }) {
  return (
    <button onClick={() => setDark(d => !d)} title={dark ? "Switch to Light" : "Switch to Dark"} style={{
      width: 32, height: 32, borderRadius: 8, border: "1px solid var(--border)",
      background: "var(--surface-2)", cursor: "pointer", display: "flex",
      alignItems: "center", justifyContent: "center", fontSize: 14,
      transition: "all 0.15s", color: "var(--text-2)",
    }}>
      {dark ? "☀" : "☾"}
    </button>
  );
}

function Sidebar({ active, setActive, completed, dark, setDark }) {
  return (
    <aside style={{
      width: 216, flexShrink: 0, background: "var(--surface)",
      borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column", height: "100vh",
      position: "sticky", top: 0,
    }}>
      <div style={{ padding: "16px 16px 14px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 7,
            background: "var(--accent)", display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: 13, fontWeight: 800, color: "#fff",
          }}>S</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", letterSpacing: "-0.02em", lineHeight: 1.1 }}>SearchOS</div>
            <div style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>v1.0 · Free</div>
          </div>
        </div>
        <ThemeToggle dark={dark} setDark={setDark} />
      </div>

      <nav style={{ flex: 1, padding: "10px 10px", display: "flex", flexDirection: "column", gap: 2 }}>
        {NAV.map(item => {
          const isActive = active === item.id;
          const isDone   = completed.includes(item.id);
          return (
            <button key={item.id} onClick={() => setActive(item.id)} style={{
              width: "100%", background: isActive ? "var(--accent-subtle)" : "transparent",
              border: `1px solid ${isActive ? "var(--accent-border)" : "transparent"}`,
              borderRadius: 8, padding: "9px 11px", cursor: "pointer",
              display: "flex", alignItems: "center", gap: 10, textAlign: "left",
              transition: "all 0.15s",
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: 7, flexShrink: 0,
                background: isActive ? "var(--accent-subtle)" : isDone ? "var(--badge-green-bg)" : "var(--surface-2)",
                border: `1px solid ${isActive ? "var(--accent-border)" : isDone ? "var(--badge-green-border)" : "var(--border)"}`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 13, transition: "all 0.15s",
                color: isActive ? "var(--accent)" : isDone ? "var(--green)" : "var(--text-3)",
              }}>
                {isDone && !isActive ? <span style={{ fontSize: 11 }}>✓</span> : item.icon}
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: isActive ? "var(--accent)" : "var(--text-4)", letterSpacing: "0.1em", fontFamily: "var(--font-mono)" }}>
                  ENGINE {item.engine}
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, color: isActive ? "var(--text)" : "var(--text-2)", marginTop: 1 }}>{item.label}</div>
              </div>
            </button>
          );
        })}
      </nav>

      <div style={{ padding: "14px 16px", borderTop: "1px solid var(--border)" }}>
        <div style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)", letterSpacing: "0.08em", marginBottom: 7 }}>PIPELINE</div>
        <div style={{ display: "flex", gap: 4, marginBottom: 5 }}>
          {NAV.map(item => (
            <div key={item.id} style={{
              flex: 1, height: 3, borderRadius: 99,
              background: completed.includes(item.id) ? "var(--green)" : active === item.id ? "var(--accent)" : "var(--surface-3)",
              transition: "background 0.4s",
            }} />
          ))}
        </div>
        <div style={{ fontSize: 10, color: "var(--text-4)" }}>{completed.length} / 4 complete</div>
      </div>
    </aside>
  );
}

function TopBar({ page, onHome, dark, setDark }) {
  const meta = NAV.find(n => n.id === page);
  return (
    <header style={{
      height: 50, borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0 24px", background: "var(--surface)", flexShrink: 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button onClick={onHome} style={{
          background: "none", border: "none", color: "var(--text-3)", cursor: "pointer",
          fontSize: 12, fontFamily: "var(--font-ui)", padding: "4px 8px",
          borderRadius: 6, transition: "color 0.12s",
        }} onMouseEnter={e => e.target.style.color = "var(--text)"}
           onMouseLeave={e => e.target.style.color = "var(--text-3)"}>
          ← Home
        </button>
        {meta && <>
          <span style={{ color: "var(--border-strong)", fontSize: 14 }}>/</span>
          <span style={{ fontSize: 13, color: "var(--text)", fontWeight: 600 }}>{meta.label}</span>
          <span style={{ fontSize: 12, color: "var(--text-4)" }}>— {meta.desc}</span>
        </>}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Badge color="green" size="xs">● Live</Badge>
        <Badge color="gray"  size="xs">Gemini Free</Badge>
        <Badge color="gray"  size="xs">spaCy NLP</Badge>
        <ThemeToggle dark={dark} setDark={setDark} />
      </div>
    </header>
  );
}

export default function App() {
  const [screen, setScreen]   = useState(() => localStorage.getItem("so_screen") || "landing");
  const [page, setPage]       = useState(() => localStorage.getItem("so_page")   || "dna");
  const [dark, setDark]       = useState(() => localStorage.getItem("so_theme") !== "light");
  const [dna, setDNA]         = useState(null);
  const [trends, setTrends]   = useState(null);
  const [brief, setBrief]     = useState(null);
  const [selectedTrend, setSelectedTrend] = useState(null);
  const [article, setArticle] = useState(null);

  useEffect(() => {
    const r = document.documentElement;
    r.setAttribute("data-theme", dark ? "dark" : "light");
    localStorage.setItem("so_theme", dark ? "dark" : "light");
  }, [dark]);

  function gotoPage(id) { setPage(id); localStorage.setItem("so_page", id); }
  function gotoScreen(s) { setScreen(s); localStorage.setItem("so_screen", s); }

  const completed = [dna && "dna", trends && "trends", brief && "brief", article && "writer"].filter(Boolean);

  if (screen === "landing") return <LandingPage onEnter={() => gotoScreen("app")} />;

  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--bg)", overflow: "hidden" }}>
      <Sidebar active={page} setActive={gotoPage} completed={completed} dark={dark} setDark={setDark} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <TopBar page={page} onHome={() => gotoScreen("landing")} dark={dark} setDark={setDark} />
        <main style={{ flex: 1, overflowY: "auto", padding: "28px 32px" }}>
          <ErrorBoundary key={page}>
            {page === "dna"    && <BrandDNAPage      dna={dna}   onDNAReady={d => { setDNA(d); setTimeout(() => gotoPage("trends"), 700); }} />}
            {page === "trends" && <TrendResearchPage dna={dna}   trends={trends} onTrendsReady={t => { setTrends(t); gotoPage("brief"); }} />}
            {page === "brief"  && <BriefBuilderPage  dna={dna}   trends={trends} brief={brief}  onBriefReady={(b, t) => { setBrief(b); setSelectedTrend(t); setTimeout(() => gotoPage("writer"), 400); }} />}
            {page === "writer" && <ArticleWriterPage dna={dna}   brief={brief}   trend={selectedTrend} onArticleReady={a => setArticle(a)} />}
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
