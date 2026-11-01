# Amazon UK iPhone availability monitor

Watches for new Apple iPhone 18 Pro Max phones in Burgundy, any storage and any seller by default. Checks two Amazon UK search pages and remembers candidates, then checks each product page. Exact product URLs in `config.json` improve coverage. Search cannot guarantee discovery of every listing or colour/storage variant.

## Start on Windows

Your `config.json` is already configured to send from and to `diogoaraujop@gmail.com` using Gmail SMTP over TLS. Create a Google app password at https://myaccount.google.com/apppasswords (requires 2-Step Verification; see https://support.google.com/mail/answer/185833). Enter that app password at startup, not your normal Gmail password. First run `python monitor.py --test-email` to verify delivery.

1. Double-click `start.cmd`. It creates a local Python environment and installs Beautiful Soup.
2. Enter recipient and sender addresses, SMTP server, username and port. Port 587 uses STARTTLS; 465 uses TLS from connection start.
3. Enter your sender provider's SMTP/app password at the hidden prompt. Do not put it in the script or share it in chat. Providers that require OAuth-only SMTP need a different mail integration; this version uses SMTP password authentication.
4. Leave the window open and the computer awake with internet access. Ctrl+C stops it. It does not run while the computer is asleep, shut down, or the window is closed, and does not auto-start with Windows.

The password remains in process memory and is not saved. An existing `AMAZON_MONITOR_SMTP_PASSWORD` environment variable can supply it for unattended launches. Avoid saving credentials under this OneDrive-synced directory. Config contains email addresses but no password.

## Commands (from this folder)

```powershell
python -m pip install -r requirements.txt
python monitor.py --setup
python monitor.py --test-email
python monitor.py --dry-run
python monitor.py --once
python monitor.py
python -m unittest -v
```

`--dry-run` checks Amazon once, without email or state changes. It works before email setup. `--test-email` sends a test only. Normal mode checks every 6 hours (four times per 24 hours), slowing down further after errors. Inspect `monitor.log` for errors and results.

To monitor known listings, add their full `https://www.amazon.co.uk/dp/ASIN` URLs to `product_urls` in `config.json`. You can disable search with `"search": false`. Set `amazon_only` to true to require an explicitly recognised Amazon seller. Unrecognised seller markup is skipped in that mode.

## Detection and limitations

An alert requires the correct model, Burgundy selected (or in the title when the colour selector is missing), positive in-stock text and a purchase button that is not explicitly disabled/hidden. Cases, covers, refurbished/renewed products and other common accessories are excluded. Preorders, backorders, offers available only through other sellers, and unrecognised layouts are not counted as confirmed stock.

Each listing alerts once until it is explicitly observed out of stock again. Failed emails are retried next cycle. Unknown pages, CAPTCHA challenges and network errors never reset the notification state. State persists in `state.json`; avoid running multiple instances simultaneously.

Amazon can block automated requests, change page markup, omit JavaScript-rendered content, or show location-dependent availability. This monitor does not bypass challenges, log in, purchase, or guarantee real-time/exhaustive coverage. Check the log periodically; errors are logged locally, not emailed. For delivery-specific results, confirm your address and variant on Amazon before buying.

Automated tests use synthetic HTML, not a verified current Amazon listing. Live availability and end-to-end mail delivery must be checked in your environment.
