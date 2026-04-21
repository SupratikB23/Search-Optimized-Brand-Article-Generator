import { useState, useEffect } from 'react';
import { Badge, Btn, Input, Spinner } from './components';
import { getClients, createClient, deleteClient } from './api';

// ── Client card ───────────────────────────────────────────────────────────────

function ClientCard({ client, onOpen, onDelete }) {
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting,   setDeleting]   = useState(false);
  const [hovered,    setHovered]    = useState(false);

  const initial     = (client.name || client.domain || "?")[0].toUpperCase();
  const lastUpdated = new Date(client.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

  async function handleDelete(e) {
    e.stopPropagation();
    if (!confirmDel) {
      setConfirmDel(true);
      setTimeout(() => setConfirmDel(false), 3000);
      return;
    }
    setDeleting(true);
    try { await onDelete(client.id); } catch { setDeleting(false); }
  }

  return (
    <div
      onClick={() => onOpen(client)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background:   "var(--surface)",
        border:       `1px solid ${hovered ? "var(--border-hover)" : "var(--border)"}`,
        borderRadius: 14,
        padding:      "18px 20px",
        cursor:       "pointer",
        transition:   "all 0.15s",
        boxShadow:    hovered ? "var(--shadow-hover)" : "var(--shadow)",
        transform:    hovered ? "translateY(-2px)" : "none",
        display:      "flex",
        flexDirection:"column",
        gap:          10,
        position:     "relative",
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div style={{
          width: 42, height: 42, borderRadius: 11,
          background: "var(--accent-subtle)",
          border: "1px solid var(--accent-border)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 20, fontWeight: 800, color: "var(--accent)", flexShrink: 0,
        }}>
          {initial}
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          style={{
            background: "none", border: "none", cursor: "pointer",
            fontSize: 11, fontWeight: 600,
            color: confirmDel ? "var(--red)" : "var(--text-4)",
            padding: "3px 6px", borderRadius: 5,
            transition: "color 0.15s",
          }}
        >
          {deleting ? "…" : confirmDel ? "Delete?" : "✕"}
        </button>
      </div>

      {/* Name + domain */}
      <div>
        <h3 style={{ margin: "0 0 2px", fontSize: 15, fontWeight: 700, color: "var(--text)", letterSpacing: "-0.01em", lineHeight: 1.3 }}>
          {client.name || client.domain}
        </h3>
        <p style={{ margin: 0, fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
          {client.domain}
        </p>
      </div>

      {/* Tagline */}
      {client.tagline && (
        <p style={{ margin: 0, fontSize: 12, color: "var(--text-3)", lineHeight: 1.55, fontStyle: "italic" }}>
          "{client.tagline.length > 90 ? client.tagline.slice(0, 87) + "…" : client.tagline}"
        </p>
      )}

      {/* Status badges */}
      <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
        {client.has_dna
          ? <Badge color="green"  size="xs">DNA ✓</Badge>
          : <Badge color="gray"   size="xs">No DNA</Badge>}
        {client.trend_count > 0   && <Badge color="blue"   size="xs">{client.trend_count} trend scans</Badge>}
        {client.brief_count > 0   && <Badge color="amber"  size="xs">{client.brief_count} briefs</Badge>}
        {client.article_count > 0 && <Badge color="purple" size="xs">{client.article_count} articles</Badge>}
      </div>

      {/* Footer */}
      <p style={{ margin: 0, fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
        Updated {lastUpdated}
      </p>
    </div>
  );
}


// ── New brand inline form ─────────────────────────────────────────────────────

function NewBrandForm({ onCreated, onCancel }) {
  const [url,     setUrl]     = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  async function submit() {
    const u = url.trim();
    if (!u) return;
    if (!u.startsWith("http")) {
      setError('URL must start with "https://"');
      return;
    }
    setLoading(true); setError(null);
    try {
      const client = await createClient(u);
      onCreated(client);
    } catch (e) {
      setError(e.message);
      setLoading(false);
    }
  }

  return (
    <div style={{
      marginBottom: 28,
      padding: "20px 22px",
      background: "var(--surface)",
      border: "1px solid var(--accent-border)",
      borderRadius: 14,
    }}>
      <p style={{ margin: "0 0 5px", fontSize: 14, fontWeight: 600, color: "var(--text)" }}>
        Add a new brand
      </p>
      <p style={{ margin: "0 0 14px", fontSize: 12, color: "var(--text-3)" }}>
        Enter the brand's website URL. DNA extraction runs on the next screen.
      </p>

      <div style={{ display: "flex", gap: 10, marginBottom: 8 }}>
        <Input
          value={url}
          onChange={setUrl}
          placeholder="https://yourclient.com"
          prefix="🌐"
          style={{ flex: 1 }}
          onKeyDown={e => e.key === "Enter" && submit()}
        />
        <Btn onClick={submit} disabled={!url.trim() || loading}>
          {loading ? <><Spinner size={13} /> Creating…</> : "Start →"}
        </Btn>
        <Btn onClick={onCancel} variant="ghost">Cancel</Btn>
      </div>

      {error && (
        <p style={{ margin: 0, fontSize: 12, color: "var(--red)" }}>{error}</p>
      )}
    </div>
  );
}


// ── Main ClientsPage ──────────────────────────────────────────────────────────

export default function ClientsPage({ onSelectClient, onNewClient, dark, setDark }) {
  const [clients,    setClients]    = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [showForm,   setShowForm]   = useState(false);
  const [error,      setError]      = useState(null);

  useEffect(() => { loadClients(); }, []);

  async function loadClients() {
    setLoading(true);
    try {
      setClients(await getClients());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleCreated(client) {
    // Don't add to list; navigate immediately so DNA extraction starts
    setShowForm(false);
    onNewClient(client);
  }

  async function handleDelete(clientId) {
    try {
      await deleteClient(clientId);
      setClients(prev => prev.filter(c => c.id !== clientId));
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", flexDirection: "column" }}>

      {/* ── Top bar ── */}
      <header style={{
        height: 52, flexShrink: 0,
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 28px",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 30, height: 30, borderRadius: 8,
            background: "var(--accent)", display: "flex",
            alignItems: "center", justifyContent: "center",
            fontSize: 14, fontWeight: 800, color: "#fff",
          }}>S</div>
          <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text)", letterSpacing: "-0.02em" }}>SearchOS</span>
          <span style={{ color: "var(--border-strong)", fontSize: 15, margin: "0 2px" }}>/</span>
          <span style={{ fontSize: 13, color: "var(--text-3)" }}>Brands</span>
        </div>
        <button
          onClick={() => setDark(d => !d)}
          title={dark ? "Switch to Light" : "Switch to Dark"}
          style={{
            width: 32, height: 32, borderRadius: 8,
            border: "1px solid var(--border)", background: "var(--surface-2)",
            cursor: "pointer", display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: 14, color: "var(--text-2)",
          }}
        >
          {dark ? "☀" : "☾"}
        </button>
      </header>

      {/* ── Main ── */}
      <main style={{ flex: 1, padding: "36px 28px", maxWidth: 1020, margin: "0 auto", width: "100%" }}>

        {/* Page header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 28 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", margin: "0 0 5px", letterSpacing: "-0.02em" }}>
              Your Brands
            </h1>
            <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
              Each brand stores its own DNA, trend scans, article briefs, and generated articles locally.
            </p>
          </div>
          {!showForm && (
            <Btn onClick={() => setShowForm(true)} size="md">+ New Brand</Btn>
          )}
        </div>

        {/* New brand form (inline) */}
        {showForm && (
          <NewBrandForm
            onCreated={handleCreated}
            onCancel={() => setShowForm(false)}
          />
        )}

        {/* Global error */}
        {error && (
          <div style={{ marginBottom: 18, padding: "11px 14px", background: "var(--red-subtle)", border: "1px solid var(--red-border)", borderRadius: 8 }}>
            <p style={{ margin: 0, fontSize: 13, color: "var(--red)" }}>{error}</p>
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", padding: 80 }}>
            <Spinner size={28} />
          </div>
        ) : clients.length === 0 && !showForm ? (
          /* Empty state */
          <div style={{ textAlign: "center", padding: "80px 0" }}>
            <div style={{ fontSize: 44, opacity: 0.18, marginBottom: 18 }}>◎</div>
            <p style={{ fontSize: 16, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>No brands yet</p>
            <p style={{ fontSize: 13, color: "var(--text-4)", marginBottom: 28, lineHeight: 1.65, maxWidth: 360, margin: "0 auto 28px" }}>
              Add your first brand to start extracting DNA and generating SEO-optimized content.
            </p>
            <Btn onClick={() => setShowForm(true)} size="lg">+ Add Your First Brand</Btn>
          </div>
        ) : (
          /* Client grid */
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(270px, 1fr))",
            gap: 14,
          }}>
            {clients.map(c => (
              <ClientCard
                key={c.id}
                client={c}
                onOpen={onSelectClient}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
