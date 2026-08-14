#!/usr/bin/env python3
"""
Regenerate index.html from a KSEI shareholder disclosure PDF (>=1% holders per issuer).

Usage:
    python3 scripts/build.py /path/to/laporan.pdf

Requires: pip3 install --user pdfplumber
"""
import sys
import re
import json
import os
from collections import defaultdict

GAP_THRESHOLD = 6
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template.html')
OUT_PATH = os.path.join(ROOT, 'index.html')


def parse_pdf(pdf_path):
    import pdfplumber

    records = []
    anomalies = []

    with pdfplumber.open(pdf_path) as pdf:
        # page 1 has a disclaimer block with garbled font encoding above the
        # real data table -- those lines fail the row regexes below and are
        # skipped as anomalies, so it's safe to process every page uniformly.
        for pidx, page in enumerate(pdf.pages):
            words = page.extract_words()
            if not words:
                continue
            rows = defaultdict(list)
            for w in words:
                rows[round(w['top'], 1)].append(w)
            for top in sorted(rows.keys()):
                row_words = sorted(rows[top], key=lambda w: w['x0'])
                texts = [w['text'] for w in row_words]
                if texts and texts[0] == 'DATE':
                    continue  # header row

                clusters = []
                cur = [row_words[0]]
                for prev, w in zip(row_words, row_words[1:]):
                    gap = w['x0'] - prev['x1']
                    if gap > GAP_THRESHOLD:
                        clusters.append(cur)
                        cur = [w]
                    else:
                        cur.append(w)
                clusters.append(cur)

                if len(clusters) < 4:
                    anomalies.append((pidx + 1, top, texts))
                    continue

                first_tok = clusters[0][0]['text']
                m = re.match(r'^(\d{2}-\w{3}-\d{4})([A-Z0-9]+)$', first_tok)
                if not m:
                    anomalies.append((pidx + 1, top, texts))
                    continue
                date, ticker = m.group(1), m.group(2)

                issuer_name = ' '.join(w['text'] for w in clusters[1])
                investor_name = ' '.join(w['text'] for w in clusters[2])
                pm = re.match(r'^(\d+,\d+)$', clusters[-1][-1]['text'])
                if not pm:
                    anomalies.append((pidx + 1, top, texts))
                    continue
                percentage = float(pm.group(1).replace(',', '.'))

                records.append({
                    'date': date,
                    'ticker': ticker,
                    'issuer': issuer_name,
                    'investor': investor_name,
                    'percentage': percentage,
                })

    print(f'Parsed {len(records)} rows, {len(anomalies)} skipped as noise (page headers/footers).')
    return records


def aggregate(records):
    report_date = records[0]['date']
    by_ticker = defaultdict(list)
    issuer_names = {}
    for r in records:
        by_ticker[r['ticker']].append(r)
        issuer_names[r['ticker']] = r['issuer']

    out = []
    for ticker in sorted(by_ticker.keys()):
        rows = by_ticker[ticker]
        holders = sorted(
            [{'name': r['investor'], 'pct': round(r['percentage'], 2)} for r in rows],
            key=lambda h: -h['pct']
        )
        total = round(sum(h['pct'] for h in holders), 2)
        public = round(max(0.0, 100 - total), 2)
        out.append({
            'ticker': ticker,
            'issuer': issuer_names[ticker],
            'holders': holders,
            'totalTracked': total,
            'public': public,
        })

    return {'reportDate': report_date, 'issuers': out}


def build_html(payload):
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = f.read()
    data_js = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</script', '<\\/script')
    html = template.replace('__DATA__', data_js)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Wrote {OUT_PATH} ({os.path.getsize(OUT_PATH)} bytes, {len(payload["issuers"])} issuers)')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    records = parse_pdf(sys.argv[1])
    payload = aggregate(records)
    build_html(payload)
