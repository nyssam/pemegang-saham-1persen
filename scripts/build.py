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

# Closed vocabulary of KSEI investor classifications. Used both to render a
# clean badge and, unusually, to detect a specific PDF rendering bug (see
# below): for some issuers, the ISSUER_NAME column is just wide enough that
# it visually collides with INVESTOR_NAME, and every row for that ticker
# reads one column short -- what we parse as "investor name" is actually
# this classification value, and the real investor name is stuck as a
# suffix on the issuer name (right after the literal "Tbk").
KNOWN_CLASSES = {
    'Individual', 'Corporate', 'Mutual Funds', 'Securities Company', 'Private Equity',
    'Investment Advisors', 'Private Bank', 'Firm', 'Bank', 'Insurance',
    'State Owned Enterprises', 'State Owned Company', 'Investment Manager', 'Pension Funds',
    'Venture Capital', 'Partnership', 'Trustee Bank', 'Sovereign Wealth Fund',
    'Sole Proprietorship', 'Financial Institutional', 'Permanent Establishment',
    'Brokerage Firms', 'Exchange Traded Funds', 'Hedge Fund', 'Cooperatives',
    'Investment Fund Selling Agent',
    'Commanditaire Vennootschap (CV) Or Limited Partnership',
    'Capital Market Supporting Institutions And Professions',
}


def cluster_row(row_words):
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
    return clusters


def clean_classification(raw):
    if not raw:
        return None
    words = raw.replace('PermanentEstablishment', 'Permanent Establishment').split()
    if words and words[-1] in ('L', 'F'):
        words = words[:-1]
    text = ' '.join(words).strip()
    if not text or text in ('0', 'L', 'F'):
        return None
    return text


def parse_pdf(pdf_path):
    import pdfplumber

    records = []
    anomalies = 0
    dropped_corrupt = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
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

                clusters = cluster_row(row_words)
                if len(clusters) < 5:
                    anomalies += 1
                    continue

                first_tok = clusters[0][0]['text']
                m = re.match(r'^(\d{2}-\w{3}-\d{4})([A-Z0-9]+)$', first_tok)
                if not m:
                    anomalies += 1
                    continue
                date, ticker = m.group(1), m.group(2)

                pm = re.match(r'^(\d+,\d+)$', clusters[-1][-1]['text'])
                if not pm:
                    anomalies += 1
                    continue
                percentage = float(pm.group(1).replace(',', '.'))

                sm = re.match(r'^([\d.]+)$', clusters[-2][-1]['text'])
                if not sm:
                    anomalies += 1
                    continue
                shares = int(sm.group(1).replace('.', ''))

                issuer_name = ' '.join(w['text'] for w in clusters[1])
                investor_name = ' '.join(w['text'] for w in clusters[2])
                classification = clean_classification(' '.join(w['text'] for w in clusters[3]))

                if investor_name in KNOWN_CLASSES:
                    # ISSUER_NAME/INVESTOR_NAME collided into one column (see
                    # KNOWN_CLASSES docstring above) -- the real investor name
                    # is stuck after "Tbk" inside the issuer cluster, and what
                    # we read as investor_name is actually the classification.
                    tm = re.search(r'Tbk\.?|TBK\.?', issuer_name)
                    if not tm:
                        dropped_corrupt += 1
                        continue
                    recovered = issuer_name[tm.end():].strip(' ,.')
                    if not recovered:
                        dropped_corrupt += 1
                        continue
                    issuer_name = issuer_name[:tm.end()].strip()
                    classification = investor_name
                    investor_name = recovered

                records.append({
                    'date': date,
                    'ticker': ticker,
                    'issuer': issuer_name,
                    'investor': investor_name,
                    'class': classification,
                    'percentage': percentage,
                    'shares': shares,
                })

    print(f'Parsed {len(records)} rows ({dropped_corrupt} dropped: unrecoverable column collision), '
          f'{anomalies} skipped as noise (page headers/footers).')
    return records


def aggregate(records):
    report_date = records[0]['date']
    by_ticker = defaultdict(list)
    issuer_names = {}
    by_investor = defaultdict(list)

    for r in records:
        by_ticker[r['ticker']].append(r)
        issuer_names[r['ticker']] = r['issuer']
        by_investor[r['investor']].append(r)

    issuers = []
    for ticker in sorted(by_ticker.keys()):
        rows = by_ticker[ticker]
        holders = sorted(
            [{'name': r['investor'], 'pct': round(r['percentage'], 2), 'cls': r['class'], 'shares': r['shares']} for r in rows],
            key=lambda h: -h['pct']
        )
        total = round(sum(h['pct'] for h in holders), 2)
        public = round(max(0.0, 100 - total), 2)
        issuers.append({
            'ticker': ticker,
            'issuer': issuer_names[ticker],
            'holders': holders,
            'totalTracked': total,
            'public': public,
        })

    investors = []
    for name in sorted(by_investor.keys()):
        rows = by_investor[name]
        cls = next((r['class'] for r in rows if r['class']), None)
        holdings = sorted(
            [{'ticker': r['ticker'], 'issuer': r['issuer'], 'pct': round(r['percentage'], 2), 'shares': r['shares']} for r in rows],
            key=lambda h: -h['pct']
        )
        investors.append({'name': name, 'cls': cls, 'holdings': holdings})

    return {'reportDate': report_date, 'issuers': issuers, 'investors': investors}


def build_html(payload):
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = f.read()
    data_js = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</script', '<\\/script')
    html = template.replace('__DATA__', data_js)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Wrote {OUT_PATH} ({os.path.getsize(OUT_PATH)} bytes, '
          f'{len(payload["issuers"])} issuers, {len(payload["investors"])} unique investors)')


def write_tickers(payload):
    tickers_path = os.path.join(ROOT, 'api', 'tickers.json')
    tickers = sorted(i['ticker'] for i in payload['issuers'])
    with open(tickers_path, 'w', encoding='utf-8') as f:
        json.dump(tickers, f)
    print(f'Wrote {tickers_path} ({len(tickers)} tickers)')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    records = parse_pdf(sys.argv[1])
    payload = aggregate(records)
    build_html(payload)
    write_tickers(payload)
