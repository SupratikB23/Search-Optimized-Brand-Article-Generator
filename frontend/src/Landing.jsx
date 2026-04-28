import { motion } from 'framer-motion';
import { Badge, TypewriterText } from './components';

// ── Background flowing paths ──────────────────────────────────────────────────
// Uses framer-motion pathLength + pathOffset so the stroke flows along the curve.
// Deterministic durations (no Math.random) to avoid hydration mismatches.
function FloatingPaths({ position }) {
  const paths = Array.from({ length: 36 }, (_, i) => ({
    id: i,
    d: `M-${380 - i * 5 * position} -${189 + i * 6}C-${380 - i * 5 * position} -${189 + i * 6} -${312 - i * 5 * position} ${216 - i * 6} ${152 - i * 5 * position} ${343 - i * 6}C${616 - i * 5 * position} ${470 - i * 6} ${684 - i * 5 * position} ${875 - i * 6} ${684 - i * 5 * position} ${875 - i * 6}`,
    strokeWidth: 0.5 + i * 0.03,
    strokeOpacity: 0.22 + i * 0.032,
    duration: 20 + (i * 1.3) % 10,
    delay: -(i * 0.6) % 8,
  }));

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      <svg
        style={{ width: "100%", height: "100%", color: "currentColor" }}
        viewBox="0 0 696 316"
        fill="none"
        preserveAspectRatio="xMidYMid slice"
      >
        {paths.map(p => (
          <motion.path
            key={p.id}
            d={p.d}
            stroke="currentColor"
            strokeWidth={p.strokeWidth}
            strokeOpacity={p.strokeOpacity}
            initial={{ pathLength: 0.3, opacity: 0.6 }}
            animate={{
              pathLength: 1,
              opacity: [0.5, 0.85, 0.5],
              pathOffset: [0, 1, 0],
            }}
            transition={{
              duration: p.duration,
              delay: p.delay,
              repeat: Infinity,
              ease: "linear",
            }}
          />
        ))}
      </svg>
    </div>
  );
}

// ── Per-character drop animation ──────────────────────────────────────────────
// Gradient is applied to the h1 (spans the whole title correctly).
// Each letter is a motion.span that handles only its own y + opacity animation.
function AnimatedTitle({ title }) {
  const words = title.split(" ");
  return (
    <h1
      className="gradient-text"
      style={{
        margin: "0 0 10px",
        lineHeight: 1.05,
        letterSpacing: "-0.02em",
        fontFamily: "var(--font-display)",
        fontWeight: 300,
        fontSize: "clamp(48px, 7.5vw, 92px)",
      }}
    >
      {words.map((word, wi) => (
        <span key={wi} style={{ display: "inline-block", marginRight: "0.28em" }}>
          {word.split("").map((letter, li) => (
            <motion.span
              key={`${wi}-${li}`}
              style={{ display: "inline-block" }}
              initial={{ y: 100, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{
                delay: wi * 0.1 + li * 0.03,
                type: "spring",
                stiffness: 150,
                damping: 25,
              }}
            >
              {letter}
            </motion.span>
          ))}
        </span>
      ))}
    </h1>
  );
}

// ── Landing Page ──────────────────────────────────────────────────────────────
export default function LandingPage({ onEnter }) {
  const features = [
    { label: "Brand DNA",      desc: "Playwright + spaCy NLP — deep voice profiling",          step: "01", color: "#8B5CF6" },
    { label: "Trend Research", desc: "Google News · DuckDuckGo · Reddit — zero API cost",       step: "02", color: "#22D3EE" },
    { label: "Brief Builder",  desc: "Gap analysis + SEO / AEO / GEO signal scoring",           step: "03", color: "#FBBF24" },
    { label: "Article Writer", desc: "Gemini + Groq fallback — sounds exactly like your brand", step: "04", color: "#34D399" },
  ];

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      position: "relative",
      overflow: "hidden",
    }}>

      {/* ── Flowing SVG path background — two mirrored layers ── */}
      <div style={{ position: "absolute", inset: 0, color: "var(--text-4)", zIndex: 0 }}>
        <FloatingPaths position={1} />
        <FloatingPaths position={-1} />
      </div>

      {/* ── Atmospheric orbs — lightweight, GPU-hinted ── */}
      <div style={{
        position: "absolute", top: "8%", left: "5%",
        width: 340, height: 340, borderRadius: "50%",
        background: "radial-gradient(circle, var(--orb-1) 0%, transparent 70%)",
        filter: "blur(38px)",
        animation: "float-a 10s ease-in-out infinite",
        pointerEvents: "none", zIndex: 0, willChange: "transform",
      }} />
      <div style={{
        position: "absolute", bottom: "5%", right: "3%",
        width: 280, height: 280, borderRadius: "50%",
        background: "radial-gradient(circle, var(--orb-2) 0%, transparent 70%)",
        filter: "blur(32px)",
        animation: "float-b 13s ease-in-out infinite",
        pointerEvents: "none", zIndex: 0, willChange: "transform",
      }} />

      {/* ── Main content ── */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.2, ease: "easeOut" }}
        style={{
          position: "relative", zIndex: 1,
          textAlign: "center",
          maxWidth: 720, width: "100%",
          padding: "72px 32px",
        }}
      >

        {/* Logo row */}
        <motion.div
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.15 }}
          style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginBottom: 60 }}
        >
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: "var(--accent)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18, fontWeight: 700, color: "#fff",
            fontFamily: "var(--font-display)",
            boxShadow: "0 0 22px var(--accent-glow)",
          }}>S</div>
          <span style={{
            fontSize: 16, fontWeight: 600,
            color: "var(--text)",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            fontFamily: "var(--font-ui)",
          }}>SearchOS</span>
          <Badge color="green">v1.0 Free</Badge>
        </motion.div>

        {/* Animated editorial headline */}
        <AnimatedTitle title="Personal Brand Search Optimizer" />

        {/* Typewriter subtitle */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.9, delay: 1.3 }}
          style={{
            margin: "32px 0 0",
            fontSize: 16,
            color: "var(--text-3)",
            fontFamily: "var(--font-mono)",
            minHeight: 28,
            letterSpacing: "-0.01em",
            lineHeight: 1.6,
          }}
        >
          <TypewriterText phrases={[
            "Writes articles that rank on Google.",
            "Structures answers for AI Overviews.",
            "Gets cited by ChatGPT & Perplexity.",
            "Sounds exactly like your brand.",
            "Zero API cost. Runs on your laptop.",
          ]} />
        </motion.p>

        {/* CTA — glassmorphic wrapper */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 1.5 }}
          style={{ marginTop: 52 }}
        >
          <div style={{
            display: "inline-block",
            background: "linear-gradient(to bottom, rgba(255,255,255,0.12), rgba(255,255,255,0.04))",
            padding: "1px", borderRadius: 20,
            backdropFilter: "blur(12px)",
            boxShadow: "0 8px 32px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.07)",
          }}>
            <motion.button
              onClick={onEnter}
              whileHover={{ y: -3, boxShadow: "0 0 32px var(--accent-glow)" }}
              whileTap={{ scale: 0.98 }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
              style={{
                borderRadius: 18, padding: "15px 40px",
                fontSize: 14, fontWeight: 600,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                fontFamily: "var(--font-ui)",
                background: "var(--accent)",
                color: "#fff",
                border: "1px solid var(--accent-border)",
                cursor: "pointer",
                display: "inline-flex", alignItems: "center", gap: 12,
              }}
            >
              Open the Engine
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </motion.button>
          </div>
        </motion.div>

        {/* Feature cards — hover via CSS class, no JS style manipulation */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
          marginTop: 64,
          textAlign: "left",
        }}>
          {features.map((f, i) => (
            <motion.div
              key={f.step}
              className="feature-card"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 1.6 + i * 0.08, duration: 0.5 }}
              style={{
                padding: "20px 22px",
                borderRadius: 14,
                background: "var(--surface)",
                border: "1px solid var(--border)",
                backdropFilter: "var(--card-backdrop)",
                WebkitBackdropFilter: "var(--card-backdrop)",
                cursor: "default",
                position: "relative",
                overflow: "hidden",
              }}
            >
              {/* Accent line at top */}
              <div style={{
                position: "absolute", top: 0, left: 0, right: 0, height: 1,
                background: `linear-gradient(90deg, transparent, ${f.color}55, transparent)`,
              }} />
              <div style={{
                fontSize: 9, fontWeight: 700,
                color: f.color,
                fontFamily: "var(--font-mono)",
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                marginBottom: 10,
                opacity: 0.85,
              }}>
                Engine {f.step}
              </div>
              <div style={{
                fontSize: 14, fontWeight: 600,
                color: "var(--text)",
                marginBottom: 5,
                fontFamily: "var(--font-display)",
                letterSpacing: "-0.01em",
              }}>{f.label}</div>
              <div style={{
                fontSize: 12,
                color: "var(--text-3)",
                lineHeight: 1.6,
                fontFamily: "var(--font-ui)",
              }}>{f.desc}</div>
            </motion.div>
          ))}
        </div>

        {/* Footer note */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 2.1 }}
          style={{
            marginTop: 36,
            fontSize: 11,
            color: "var(--text-4)",
            fontFamily: "var(--font-mono)",
            letterSpacing: "0.04em",
          }}
        >
          100% free · Gemini + Groq API · runs on localhost
        </motion.p>

      </motion.div>
    </div>
  );
}
