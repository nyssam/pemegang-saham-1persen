// Vercel Serverless Function -- called every 15 min during trading hours by
// the GitHub Action in .github/workflows/update-prices.yml (same pattern as
// pp-sahamdarinol's api/update-prices.js).
//
// Fetches last price for every ticker in tickers.json from Yahoo Finance's
// batch quote endpoint (free, ~15-20min delayed, fine for this educational
// use), then upserts into the `stock_prices` table in Supabase.
//
// Uses the SERVICE ROLE KEY (write access, bypasses RLS) -- must only ever
// live in Vercel Environment Variables, never in frontend code.

const tickers = require('./tickers.json');

const CHUNK_SIZE = 50;
const CONCURRENCY = 5;

module.exports = async function handler(req, res) {
  const authHeader = req.headers.authorization;
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return res.status(401).json({ error: 'unauthorized' });
  }

  const chunks = [];
  for (let i = 0; i < tickers.length; i += CHUNK_SIZE) {
    chunks.push(tickers.slice(i, i + CHUNK_SIZE));
  }

  const prices = {};
  const errors = [];

  for (let i = 0; i < chunks.length; i += CONCURRENCY) {
    const batch = chunks.slice(i, i + CONCURRENCY);
    const results = await Promise.all(batch.map(fetchChunkPrices));
    for (const r of results) {
      if (r.error) errors.push(r.error);
      Object.assign(prices, r.prices);
    }
  }

  const now = new Date().toISOString();
  const rows = Object.entries(prices).map(([ticker, price]) => ({
    ticker,
    price,
    updated_at: now,
  }));

  if (rows.length === 0) {
    return res.status(200).json({ updated: 0, errors });
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
    fetchErrors: errors,
    upsertErrors,
  });
};

async function fetchChunkPrices(chunk) {
  const symbols = chunk.map((t) => `${t}.JK`).join(',');
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbols}`;
  try {
    const resp = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; pemegang-saham-1persen/1.0)' },
    });
    if (!resp.ok) return { prices: {}, error: `HTTP ${resp.status} for chunk starting ${chunk[0]}` };
    const json = await resp.json();
    const results = json?.quoteResponse?.result || [];
    const prices = {};
    for (const r of results) {
      const ticker = (r.symbol || '').replace(/\.JK$/, '');
      if (ticker && typeof r.regularMarketPrice === 'number') {
        prices[ticker] = r.regularMarketPrice;
      }
    }
    return { prices };
  } catch (e) {
    return { prices: {}, error: e.message };
  }
}
