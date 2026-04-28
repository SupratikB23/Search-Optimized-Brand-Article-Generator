// ── HTTP helpers ──────────────────────────────────────────────────────────────

async function post(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `POST ${path} failed`);
  }
  return res.json();
}

async function get(path) {
  const res = await fetch(path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `GET ${path} failed`);
  }
  return res.json();
}

async function del(path) {
  const res = await fetch(path, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `DELETE ${path} failed`);
  }
  return res.json();
}


// ── Engine APIs ───────────────────────────────────────────────────────────────

export const extractDNA = (url) =>
  post('/api/extract-dna', { url });

export const researchTrends = ({ services, top_keywords, existing_titles, brand_name, domain }) =>
  post('/api/research-trends', {
    services,
    top_keywords,
    existing_titles: existing_titles || [],
    brand_name: brand_name || '',
    domain: domain || '',
  });

export const buildBrief = ({ dna, trend, angle, article_type }) =>
  post('/api/build-brief', { dna, trend, angle, article_type });

export const writeArticle = ({ brief, dna, trend, model, api_key }) =>
  post('/api/write-article', { brief, dna, trend, model, api_key: api_key || undefined });


// ── Client management APIs ────────────────────────────────────────────────────

export const getClients    = ()         => get('/api/clients');
export const createClient  = (url)      => post('/api/clients', { url });
export const getClient     = (id)       => get(`/api/clients/${id}`);
export const deleteClient  = (id)       => del(`/api/clients/${id}`);


// ── Save APIs (called silently after each engine completes) ───────────────────

export const saveClientDNA = (clientId, dna) =>
  post(`/api/clients/${clientId}/save-dna`, { dna });

export const saveClientTrends = (clientId, report) =>
  post(`/api/clients/${clientId}/save-trends`, { report });

export const saveClientBrief = (clientId, brief) =>
  post(`/api/clients/${clientId}/save-brief`, { brief });

export const saveClientArticle = (clientId, article, briefId = null) =>
  post(`/api/clients/${clientId}/save-article`, { article, brief_id: briefId });

export const getClientArticle = (clientId, articleId) =>
  get(`/api/clients/${clientId}/articles/${articleId}`);
