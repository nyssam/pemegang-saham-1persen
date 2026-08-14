# Pemegang Saham ≥1%

Static site pencarian pemegang saham ≥1% per emiten (IDX/KSEI), sisanya
dihitung otomatis sebagai kepemilikan Masyarakat (publik). Satu file HTML,
data ter-embed langsung di dalamnya — nggak butuh backend atau database.

Style disamain dengan [pp.sahamdarinol.com](https://pp.sahamdarinol.com)
(font, warna, komponen).

## Struktur

- `index.html` — satu-satunya file yang di-deploy. Data ter-embed di dalamnya.
- `logo.png`, `favicon-32.png` — aset brand Saham Dari Nol.
- `scripts/build.py` — regenerate `index.html` dari PDF laporan KSEI terbaru.
- `scripts/template.html` — template HTML yang dipakai `build.py` (placeholder `__DATA__`).

## Update data (kalau ada laporan KSEI baru)

```bash
pip3 install --user pdfplumber   # sekali saja
python3 scripts/build.py /path/ke/laporan-ksei-terbaru.pdf
```

Ini bakal nulis ulang `index.html` dengan data baru. Commit & push, Vercel
otomatis re-deploy.

Sumber data: [IDX pengumuman keterbukaan kepemilikan](https://www.idx.co.id/StaticData/NewsAndAnnouncement/ANNOUNCEMENTSTOCK/From_EREP/202606/c3afea116e_700b93231b.pdf)

## Deploy

Repo ini di-deploy statis lewat Vercel, domain `1.sahamdarinol.com`. Push ke
`main` = auto re-deploy, gak ada build step (murni static file).
