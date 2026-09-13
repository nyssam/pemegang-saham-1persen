// Vercel Serverless Function -- called every 15 min during trading hours by
// pg_cron in Supabase (migration lives in the pp-sahamdarinol repo:
// supabase/migrations/011_pg_cron_update_prices.sql). It used to be a GitHub
// Actions schedule, but GitHub kept dropping runs (~2 per day).
//
// Fetches last price for every ticker in tickers.json from Yahoo Finance's
// per-ticker chart endpoint (same one pp-sahamdarinol uses -- the batch
// /v7/finance/quote endpoint now requires a crumb/cookie and 401s without
// it, but /v8/finance/chart still works unauthenticated). With ~955
// tickers we fan requests out with bounded concurrency to stay well under
// the function timeout -- see CONCURRENCY below.
//
// Uses the SERVICE ROLE KEY (write access, bypasses RLS) -- must only ever
// live in Vercel Environment Variables, never in frontend code.

const tickers = require('./tickers.json');

const CONCURRENCY = 20;
const FETCH_TIMEOUT_MS = 6000;

// Two accepted callers: Bearer CRON_SECRET (Vercel env), or Bearer <secret
// generated inside the database> sent by pg_cron and checked through the
// verify_cron_secret() RPC, so that secret never has to be copied anywhere.
async function isCronRequest(req) {
  const auth = req.headers.authorization || '';
  const envSecret = process.env.CRON_SECRET;
  if (envSecret && auth === `Bearer ${envSecret}`) return true;

  const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
  if (!token) return false;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  const resp = await fetch(`${process.env.SUPABASE_URL}/rest/v1/rpc/verify_cron_secret`, {
    method: 'POST',
    headers: { apikey: key, Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  return resp.ok && (await resp.json()) === true;
}

module.exports = async function handler(req, res) {
  if (!(await isCronRequest(req))) {
    return res.status(401).json({ error: 'unauthorized' });
  }

  const prices = {};
  const errors = [];

  for (let i = 0; i < tickers.length; i += CONCURRENCY) {
    const batch = tickers.slice(i, i + CONCURRENCY);
    const results = await Promise.all(batch.map(fetchOnePrice));
    for (const r of results) {
      if (r.error) errors.push(r.error);
      else if (r.price != null) prices[r.ticker] = r.price;
    }
  }

  const now = new Date().toISOString();
  const rows = Object.entries(prices).map(([ticker, price]) => ({
    ticker,
    price,
    updated_at: now,
  }));

  if (rows.length === 0) {
    return res.status(200).json({ updated: 0, errors: errors.slice(0, 20) });
  }

  const upsertErrors = [];
  const UPSERT_CHUNK = 500;
  for (let i = 0; i < rows.length; i += UPSERT_CHUNK) {
    const slice = rows.slice(i, i + UPSERT_CHUNK);
    const resp = await fetch(`${process.env.SUPABASE_URL}/rest/v1/stock_prices`, {
      method: 'POST',
      headers: {
        apikey: process.env.SUPABASE_SERVICE_ROLE_KEY,
        Authorization: `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
        'Content-Type': 'application/json',
        Prefer: 'resolution=merge-duplicates,return=minimal',
      },
      body: JSON.stringify(slice),
    });
    if (!resp.ok) {
      upsertErrors.push(await resp.text());
    }
  }

  return res.status(200).json({
    updated: rows.length,
    skipped: tickers.length - rows.length,
    fetchErrorCount: errors.length,
    fetchErrorsSample: errors.slice(0, 20),
    upsertErrors,
  });
};

async function fetchOnePrice(ticker) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}.JK?interval=1d&range=1d`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const resp = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; pemegang-saham-1persen/1.0)' },
      signal: controller.signal,
    });
    if (!resp.ok) return { ticker, price: null, error: `HTTP ${resp.status} for ${ticker}` };
    const json = await resp.json();
    const price = json?.chart?.result?.[0]?.meta?.regularMarketPrice;
    return { ticker, price: typeof price === 'number' ? price : null };
  } catch (e) {
    return { ticker, price: null, error: `${ticker}: ${e.message}` };
  } finally {
    clearTimeout(timer);
  }
}
