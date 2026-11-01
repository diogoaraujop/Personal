"""Amazon UK stock watcher. Run --setup, then --dry-run, then normally."""
import argparse
import getpass
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import random
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
CONFIG = BASE / 'config.json'
STATE = BASE / 'state.json'
MODEL = re.compile(r'\biphone\s*18\s*pro\s*max\b', re.I)
ACCESSORIES = re.compile(r'\b(case|cover|protector|charger|cable|wallet|skin|sleeve|pouch|dummy|refurbished|renewed)\b', re.I)


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def soup_for(html):
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.get_text(' ', strip=True).lower()
    if soup.select_one('#captchacharacters, form[action*="validateCaptcha"]') or any(
        phrase in body for phrase in ['enter the characters you see below', 'sorry, we just need to make sure', 'robot check']
    ):
        raise RuntimeError('Amazon blocked the request with a robot check; no stock conclusion drawn.')
    return soup


def fetch(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'amazon.co.uk', 'www.amazon.co.uk'}:
        raise ValueError('Only HTTPS amazon.co.uk URLs are allowed')
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36', 'Accept-Language': 'en-GB,en;q=0.9'})
    with urlopen(req, timeout=35) as response:
        if urlparse(response.url).hostname not in {'amazon.co.uk', 'www.amazon.co.uk'}:
            raise RuntimeError('Unexpected redirect away from Amazon UK')
        return response.read().decode('utf-8', errors='replace')


def discover(html):
    soup = soup_for(html)
    rows = soup.select('[data-component-type="s-search-result"][data-asin]')
    if not rows and not soup.select_one('.s-no-results, [data-component-type="s-search-results"]'):
        raise RuntimeError('Search layout not recognised; discovery could not be verified')
    return [row['data-asin'] for row in rows if re.fullmatch(r'[A-Z0-9]{10}', row['data-asin'])
            and MODEL.search(row.get_text(' ', strip=True))
            and not ACCESSORIES.search(row.get_text(' ', strip=True))]


def classify(html, amazon_only=False):
    soup = soup_for(html)
    title_node = soup.select_one('#productTitle')
    if not title_node:
        raise RuntimeError('Product title missing; page unavailable or layout changed')
    title = title_node.get_text(' ', strip=True)
    if not MODEL.search(title) or ACCESSORIES.search(title):
        return {'status': 'mismatch', 'title': title}
    colour_node = soup.select_one('#variation_color_name .selection')
    colour = colour_node.get_text(' ', strip=True) if colour_node else title
    if not re.search(r'\bburgundy\b', colour, re.I):
        return {'status': 'mismatch', 'title': title}
    availability = ' '.join(n.get_text(' ', strip=True) for n in soup.select('#availability, #availabilityInsideBuyBox_feature_div'))
    seller_node = soup.select_one('#sellerProfileTriggerId, #merchant-info, #tabular-buybox')
    seller = seller_node.get_text(' ', strip=True) if seller_node else 'Unknown seller'
    if amazon_only and not re.search(r'(?:sold by\s*|^)(?:Amazon\.co\.uk|Amazon EU S\.?a\.?r\.?l\.?)\b', seller, re.I):
        return {'status': 'unknown', 'title': title, 'reason': 'Amazon seller not confirmed'}
    unavailable = re.search(r'currently unavailable|temporarily out of stock|unavailable|out of stock', availability, re.I)
    positive = re.search(r'\bin stock\b|only \d+ left', availability, re.I)
    buttons = soup.select('#add-to-cart-button, #buy-now-button')
    enabled = any(not b.has_attr('disabled') and b.get('aria-disabled') != 'true' and b.get('type') != 'hidden'
                  and not any('aok-hidden' in p.get('class', []) or 'display:none' in p.get('style', '').replace(' ', '') for p in [b, *b.parents] if p.name)
                  for b in buttons)
    status = 'unavailable' if unavailable else 'available' if positive and enabled else 'unknown'
    price_node = soup.select_one('#corePriceDisplay_desktop_feature_div .a-offscreen, #corePrice_feature_div .a-offscreen')
    return {'status': status, 'title': title, 'availability': availability, 'seller': seller,
            'price': price_node.get_text(strip=True) if price_node else 'See product page'}


def email(config, subject, body, password):
    mail = config['email']
    msg = EmailMessage()
    msg['From'], msg['To'], msg['Subject'] = mail['from'], mail['to'], subject
    msg.set_content(body)
    context = ssl.create_default_context()
    if mail.get('ssl', False):
        client = smtplib.SMTP_SSL(mail['host'], int(mail['port']), timeout=30, context=context)
    else:
        client = smtplib.SMTP(mail['host'], int(mail['port']), timeout=30)
    with client:
        if not mail.get('ssl', False):
            client.starttls(context=context)
        client.login(mail['username'], password)
        client.send_message(msg)


def cycle(config, state, password, dry_run=False):
    errors = 0
    asins = set(state.get('known_asins', []))
    pinned_asins = set()
    for url in config.get('product_urls', []):
        match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
        if not match or urlparse(url).hostname not in {'amazon.co.uk', 'www.amazon.co.uk'}:
            raise ValueError('Invalid Amazon product URL: ' + url)
        pinned_asins.add(match[1])
        asins.add(match[1])
    if config.get('search', True):
        try:
            for page in range(1, 3):
                url = 'https://www.amazon.co.uk/s?' + urlencode({'k': 'Apple iPhone 18 Pro Max Burgundy', 'page': page})
                asins.update(discover(fetch(url)))
                time.sleep(random.uniform(3, 6))
        except Exception as exc:
            logging.error('Discovery failed: %s', exc)
            errors += 1
    records = state.setdefault('products', {})
    for asin in sorted(asins):
        url = 'https://www.amazon.co.uk/dp/' + asin
        try:
            result = classify(fetch(url), config.get('amazon_only', False))
            logging.info('%s: %s | %s', asin, result['status'], result['title'])
            if result['status'] == 'mismatch' and asin not in pinned_asins:
                logging.info('%s: removing stale search candidate', asin)
                asins.discard(asin)
                records.pop(asin, None)
                continue
            previous = records.get(asin, {})
            if result['status'] == 'available' and not previous.get('notified', False):
                body = '\n'.join([result['title'], result['price'], result['availability'], result['seller'], url,
                                  '\nStock was detected now; confirm the selected colour, seller and delivery date on Amazon.'])
                if dry_run:
                    logging.info('DRY RUN: would email: %s', body)
                else:
                    email(config, 'Amazon UK: iPhone 18 Pro Max Burgundy available', body, password)
                    previous['notified'] = True
                    logging.info('Availability email sent for %s', asin)
            elif result['status'] == 'unavailable':
                previous['notified'] = False
            # Unknown/mismatched pages never reset the alert latch.
            previous.update(result)
            previous['checked_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
            records[asin] = previous
            if not dry_run:
                save_json(STATE, state)
        except Exception as exc:
            logging.error('%s: check/email failed: %s', asin, exc)
            errors += 1
        time.sleep(random.uniform(3, 6))
    if not asins:
        logging.warning('No candidate listings found. Add exact product URLs for more reliable coverage.')
    if not dry_run:
        state['known_asins'] = sorted(asins)
        state['last_cycle'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
        state['last_cycle_errors'] = errors
        save_json(STATE, state)
    return errors


def setup():
    config = read_json(CONFIG, read_json(BASE / 'config.example.json', {}))
    mail = config['email']
    for key, label in [('to', 'Recipient email'), ('from', 'Sender email'), ('host', 'SMTP server'), ('username', 'SMTP username')]:
        mail[key] = input(f'{label} [{mail[key]}]: ').strip() or mail[key]
    mail['port'] = int(input(f'SMTP port [{mail["port"]}]: ').strip() or mail['port'])
    mail['ssl'] = mail['port'] == 465
    save_json(CONFIG, config)
    print('Saved config.json. Password is requested at startup or read from AMAZON_MONITOR_SMTP_PASSWORD.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup', action='store_true')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='One check, no email or state writes')
    parser.add_argument('--test-email', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[
        logging.StreamHandler(), RotatingFileHandler(BASE / 'monitor.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')])
    if args.setup:
        setup()
        return 0
    config = read_json(CONFIG, read_json(BASE / 'config.example.json', {}))
    password = ''
    if not args.dry_run:
        if not CONFIG.exists() or any(not config['email'].get(k) for k in ['host', 'username', 'to', 'from']):
            parser.error('Email is not configured. Run python monitor.py --setup first.')
        password = os.environ.get('AMAZON_MONITOR_SMTP_PASSWORD') or getpass.getpass('SMTP app password (hidden): ')
        if not password:
            parser.error('An SMTP password is required')
    if args.test_email:
        email(config, 'Amazon monitor test', 'Your Amazon availability monitor email settings work.', password)
        logging.info('Test email sent')
        return 0
    state = read_json(STATE, {})
    failures = 0
    while True:
        errors = cycle(config, state, password, args.dry_run)
        if args.once or args.dry_run:
            return 1 if errors else 0
        failures = min(failures + 1, 3) if errors else 0
        delay = max(300, config.get('interval_seconds', 900)) * (2 ** failures) + random.uniform(0, 30)
        logging.info('Next check in %.0f minutes. Keep this window open and the PC awake.', delay / 60)
        time.sleep(delay)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nMonitor stopped.')
