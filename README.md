# xb6-exporter

A Prometheus exporter for Xfinity XB6 gateways. It scrapes the gateway's admin web UI
(there is no official API) for DOCSIS downstream/upstream channel signal quality,
codeword error counts, WAN up/down status, software versions, and hardware identity
(model/serial number).

Every Prometheus scrape triggers a fresh login → page fetch → logout cycle against the
gateway — no session is left open between scrapes.

## Setup

```
cp .credentials_template .credentials
# edit .credentials: GWADDR (gateway IP, e.g. 10.0.0.1), GWUSER, GWPASSWORD

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running it

```
source venv/bin/activate
python -m xb6_exporter.main
```

```
curl localhost:9938/metrics
```

Config is via environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `EXPORTER_BIND` | `::` | Address the `/metrics` HTTP server binds to (`::` listens on both IPv4 and IPv6) |
| `EXPORTER_PORT` | `9938` | Port the `/metrics` HTTP server listens on |

**Scrape interval**: each scrape does a full login/fetch-4-pages/logout cycle against the
gateway, which in practice takes on the order of 10-20 seconds. Set Prometheus's
`scrape_interval` for this job to **30s or more**, and set `scrape_timeout` to comfortably
cover the slow end (e.g. 25s). The gateway also only supports one logged-in admin session
at a time, so scraping too aggressively risks colliding with someone else logging into
the gateway.

**Concurrent requests**: if a request to `/metrics` arrives while a previous scrape is
still logged into the gateway, the exporter immediately returns `429 Too Many Requests`
rather than queueing behind it (which could leave two logins racing each other) or
starting a second, likely-conflicting login. This is normal and expected if
`scrape_timeout`/`scrape_interval` are set per the recommendation above — Prometheus will
just pick the value up on the next scrape.

## Running the tests

```
source venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/
```

Tests run entirely offline against sanitized HTML fixtures captured from a real gateway
(`tests/fixtures/`) — no network access or live gateway required.

## Metrics reference

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `xb6_up` | Gauge | | `1` if the last scrape (login, fetch, parse) succeeded, `0` otherwise |
| `xb6_scrape_duration_seconds` | Gauge | | Time spent on the last scrape's login/fetch/logout cycle |
| `xb6_downstream_frequency_hz` | Gauge | `channel_id` | Downstream channel center frequency, in Hz |
| `xb6_downstream_power_dbmv` | Gauge | `channel_id` | Downstream channel power level, in dBmV |
| `xb6_downstream_snr_db` | Gauge | `channel_id` | Downstream channel signal-to-noise ratio, in dB |
| `xb6_downstream_locked` | Gauge | `channel_id` | `1` if the downstream channel is locked, `0` otherwise |
| `xb6_downstream_channel_info` | Gauge | `channel_id`, `modulation` | Always `1`; carries the channel's modulation (e.g. `256 QAM`, `OFDM`) as a label |
| `xb6_upstream_frequency_hz` | Gauge | `channel_id` | Upstream channel center frequency, in Hz |
| `xb6_upstream_power_dbmv` | Gauge | `channel_id` | Upstream channel power level, in dBmV |
| `xb6_upstream_symbol_rate` | Gauge | `channel_id` | Upstream channel symbol rate, as reported by the gateway |
| `xb6_upstream_locked` | Gauge | `channel_id` | `1` if the upstream channel is locked, `0` otherwise |
| `xb6_upstream_channel_info` | Gauge | `channel_id`, `modulation`, `channel_type` | Always `1`; carries the channel's modulation (e.g. `QAM`, `OFDMA`) and channel type (e.g. `ATDMA`, `TDMA`) as labels |
| `xb6_downstream_codewords_unerrored_total` | Gauge | `channel_id` | Cumulative unerrored codewords received on a downstream channel (device counter; resets on modem reboot — use `rate()`/`increase()`) |
| `xb6_downstream_codewords_correctable_total` | Gauge | `channel_id` | Cumulative correctable codeword errors on a downstream channel |
| `xb6_downstream_codewords_uncorrectable_total` | Gauge | `channel_id` | Cumulative uncorrectable codeword errors on a downstream channel |
| `xb6_wan_up` | Gauge | | `1` if DOCSIS registration is complete and a WAN IPv4 address is assigned, `0` otherwise |
| `xb6_wan_info` | Gauge | `ip4`, `ip6`, `operational_mode` | Always `1`; carries the WAN IPv4/IPv6 addresses and operational mode (e.g. `DOCSIS`) as labels |
| `xb6_hardware_info` | Gauge | `model`, `vendor`, `hardware_revision`, `serial_number` | Always `1`; carries the gateway's hardware identity as labels |
| `xb6_software_info` | Gauge | `docsis_software_version`, `image_name`, `packet_cable_version` | Always `1`; carries the gateway's software identity as labels |

The `*_info` metrics follow the common Prometheus "info" pattern (a constant `1` with the
interesting data as labels) since fields like model, serial number, and modulation are
categorical/identity data rather than something to alert or chart directly on.
