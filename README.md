# Pemegang Saham ≥1%

Situs pencarian pemegang saham ≥1% per emiten (IDX/KSEI), sisanya dihitung
otomatis sebagai kepemilikan Masyarakat (publik). Data kepemilikan (nama,
lembar saham, %) ter-embed statis di `index.html`; harga saham & valuasi
di-fetch live dari Supabase, di-update tiap 15 menit oleh serverless
function + cron (lihat bagian Harga Saham di bawah).

Style disamain dengan [pp.sahamdarinol.com](https://pp.sahamdarinol.com)
(font, warna, komponen).

## Struktur

- `index.html` — halaman utama yang di-deploy. Data kepemilikan ter-embed di dalamnya.
- `logo.png`, `favicon-32.png` — aset brand Saham Dari Nol.
- `scripts/build.py` — regenerate `index.html` + `api/tickers.json` dari PDF laporan KSEI terbaru.
- `scripts/template.html` — template HTML yang dipakai `build.py` (placeholder `__DATA__`).
- `api/update-prices.js` — Vercel serverless function, update harga di Supabase.
- `api/tickers.json` — daftar kode saham, auto-generate oleh `build.py`, dibaca oleh `update-prices.js`.
- `supabase/001_stock_prices.sql` — migration tabel harga saham.
- `.github/workflows/update-prices.yml` — cron tiap 15 menit (jam bursa) yang manggil `api/update-prices.js`.

## Update data (kalau ada laporan KSEI baru)

```bash
pip3 install --user pdfplumber   # sekali saja
python3 scripts/build.py /path/ke/laporan-ksei-terbaru.pdf
```

Ini bakal nulis ulang `index.html` dengan data baru. Commit & push, Vercel
otomatis re-deploy.

Sumber data: [IDX pengumuman keterbukaan kepemilikan](https://www.idx.co.id/StaticData/NewsAndAnnouncement/ANNOUNCEMENTSTOCK/From_EREP/202606/c3afea116e_700b93231b.pdf)

## Keterbatasan data yang diketahui

Untuk beberapa emiten, kolom nama emiten dan nama pemegang saham di PDF
render-nya nempel jadi satu (`scripts/build.py` otomatis mendeteksi &
memperbaiki sebagian besar kasus ini lewat penanda "Tbk"). Tapi untuk
laporan 29-May-2026, ada **3 emiten** yang teksnya rusak parah di sumber
PDF-nya sendiri (bukan bug parser) sehingga sebagian/seluruh baris
pemegang sahamnya di-skip:

- **CARS** (Bintraco Dharma) — seluruh 26 baris pemegang saham rusak,
  emiten ini nggak muncul sama sekali di pencarian untuk laporan ini.
- **JIHD** (Jakarta International Hotels & Dev) — 10 dari ~19 baris rusak,
  jadi % Masyarakat yang ditampilkan lebih tinggi dari yang sebenarnya.
- **ULTJ** (Ultrajaya Milk Industry) — 6 baris rusak, sama seperti JIHD.

Kalau laporan KSEI berikutnya nggak punya bug rendering yang sama, ketiga
emiten ini otomatis balik normal pas di-generate ulang.

## Harga saham (live, update tiap 15 menit)

Pakai project Supabase yang sama dengan `pp-sahamdarinol`, tabel baru
`stock_prices` yang terpisah total dari data portofolio (public read-only,
gak nyentuh data yang di-gate password).

Setup (sekali saja):

1. **Supabase**: buka SQL Editor di project Supabase yang sama dengan
   pp-sahamdarinol, jalanin `supabase/001_stock_prices.sql`.
2. **Vercel** (project `pemegang-saham-1persen`, bukan pp-sahamdarinol) →
   Settings → Environment Variables, tambahin:
   - `SUPABASE_URL` — sama kayak punya pp-sahamdarinol
   - `SUPABASE_SERVICE_ROLE_KEY` — sama kayak punya pp-sahamdarinol (secret,
     JANGAN taruh di kode/env yang ke-expose ke browser)
   - `CRON_SECRET` — bikin random string baru sendiri (boleh beda dari punya
     pp-sahamdarinol, biar independen)
3. **GitHub** → repo ini → Settings → Secrets and variables → Actions,
   tambahin secret `CRON_SECRET` dengan nilai yang sama persis kayak di Vercel.
4. `scripts/template.html` udah punya `SUPABASE_URL` + `SUPABASE_ANON_KEY`
   ter-embed langsung (anon key aman buat public karena cuma bisa read,
   dibatasi RLS) — kalau ganti project Supabase, update dua constant itu.

Setelah itu, GitHub Action bakal manggil `/api/update-prices` tiap 15 menit
selama jam bursa (09:00-15:00 WIB), Senin-Jumat. Bisa juga trigger manual
dari tab **Actions** di GitHub kalau mau tes duluan.

Harga dari Yahoo Finance (`{TICKER}.JK`), gratis, delay ~15-20 menit —
cukup buat konten edukasi ini, bukan buat trading real-time.

## Deploy

Repo ini di-deploy lewat Vercel, domain `1.sahamdarinol.com`. Push ke
`main` = auto re-deploy. `index.html` murni statis (gak ada build step),
`api/update-prices.js` otomatis ke-detect Vercel sebagai serverless function.
