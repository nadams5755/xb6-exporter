"""Parsers for the XB6 gateway's server-rendered admin HTML pages."""
from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

_FREQ_MHZ_RE = re.compile(r"([\d.]+)\s*MHz", re.IGNORECASE)
_NUMBER_RE = re.compile(r"[-\d.]+")


def _text(el) -> str:
    return el.get_text(strip=True) if el is not None else ""


def _float(value: str) -> float | None:
    match = _NUMBER_RE.search(value)
    return float(match.group()) if match else None


def _parse_frequency_hz(value: str) -> float | None:
    """Downstream OFDM channels render as a bare Hz integer; everything else is "N MHz"."""
    mhz_match = _FREQ_MHZ_RE.search(value)
    if mhz_match:
        return float(mhz_match.group(1)) * 1_000_000
    return _float(value)


def _netflow_table(soup: BeautifulSoup, header_text: str):
    """Find a `module netFlow` table whose header row cell contains `header_text`."""
    for module in soup.select("div.module.netFlow"):
        header_cell = module.select_one("thead td")
        if header_cell and header_text.lower() in _text(header_cell).lower():
            return module.select_one("table")
    return None


def _table_rows_by_label(table) -> dict[str, list[str]]:
    """Map each row's label (first cell) to its list of value cells, in column order."""
    rows: dict[str, list[str]] = {}
    for tr in table.select("tbody tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        label = _text(cells[0])
        values = [_text(td) for td in cells[1:]]
        rows[label] = values
    return rows


def _channels_from_table(table, value_parsers: dict[str, str]) -> list[dict]:
    """Zip a netFlow table's rows into a list of per-channel dicts keyed by `value_parsers`.

    `value_parsers` maps the table's row label -> the output dict key to store it under.
    """
    rows = _table_rows_by_label(table)
    channel_ids = rows.get("Channel ID", [])
    channels = [{"channel_id": cid} for cid in channel_ids]
    for row_label, out_key in value_parsers.items():
        values = rows.get(row_label, [])
        for channel, value in zip(channels, values):
            channel[out_key] = value
    return channels


@dataclass
class DownstreamChannel:
    channel_id: str
    locked: bool
    frequency_hz: float
    snr_db: float
    power_dbmv: float
    modulation: str


@dataclass
class UpstreamChannel:
    channel_id: str
    locked: bool
    frequency_hz: float
    symbol_rate: float
    power_dbmv: float
    modulation: str
    channel_type: str


@dataclass
class CodewordCounts:
    channel_id: str
    unerrored: float
    correctable: float
    uncorrectable: float


@dataclass
class NetworkSetup:
    downstream: list[DownstreamChannel]
    upstream: list[UpstreamChannel]
    codewords: list[CodewordCounts]
    registration_complete: bool


def parse_network_setup(html: str) -> NetworkSetup:
    soup = BeautifulSoup(html, "lxml")

    downstream_table = _netflow_table(soup, "Downstream")
    downstream_raw = _channels_from_table(
        downstream_table,
        {
            "Lock Status": "lock_status",
            "Frequency": "frequency",
            "SNR": "snr",
            "Power Level": "power",
            "Modulation": "modulation",
        },
    )
    downstream = [
        DownstreamChannel(
            channel_id=c["channel_id"],
            locked=c.get("lock_status", "").lower() == "locked",
            frequency_hz=_parse_frequency_hz(c.get("frequency", "")),
            snr_db=_float(c.get("snr", "")),
            power_dbmv=_float(c.get("power", "")),
            modulation=c.get("modulation", ""),
        )
        for c in downstream_raw
    ]

    upstream_table = _netflow_table(soup, "Upstream")
    upstream_raw = _channels_from_table(
        upstream_table,
        {
            "Lock Status": "lock_status",
            "Frequency": "frequency",
            "Symbol Rate": "symbol_rate",
            "Power Level": "power",
            "Modulation": "modulation",
            "Channel Type": "channel_type",
        },
    )
    upstream = [
        UpstreamChannel(
            channel_id=c["channel_id"],
            locked=c.get("lock_status", "").lower() == "locked",
            frequency_hz=_parse_frequency_hz(c.get("frequency", "")),
            symbol_rate=_float(c.get("symbol_rate", "")),
            power_dbmv=_float(c.get("power", "")),
            modulation=c.get("modulation", ""),
            channel_type=c.get("channel_type", ""),
        )
        for c in upstream_raw
    ]

    codewords_table = _netflow_table(soup, "CM Error Codewords")
    codewords_raw = _channels_from_table(
        codewords_table,
        {
            "Unerrored Codewords": "unerrored",
            "Correctable Codewords": "correctable",
            "Uncorrectable Codewords": "uncorrectable",
        },
    )
    codewords = [
        CodewordCounts(
            channel_id=c["channel_id"],
            unerrored=_float(c.get("unerrored", "")),
            correctable=_float(c.get("correctable", "")),
            uncorrectable=_float(c.get("uncorrectable", "")),
        )
        for c in codewords_raw
    ]

    registration_complete = False
    for row in soup.select("div.module.forms div.form-row"):
        label = _text(row.select_one(".readonlyLabel"))
        if label.strip().rstrip(":") == "Registration":
            value = _text(row.select_one(".value"))
            registration_complete = value.strip().lower() == "complete"
            break

    return NetworkSetup(
        downstream=downstream,
        upstream=upstream,
        codewords=codewords,
        registration_complete=registration_complete,
    )


def _labeled_values(soup: BeautifulSoup) -> dict[str, str]:
    """Map every "<label>: <value>" form-row on the page to its value text."""
    result: dict[str, str] = {}
    for row in soup.select(".form-row"):
        label_el = row.select_one(".readonlyLabel")
        value_el = row.select_one(".value")
        if label_el is None or value_el is None:
            continue
        label = _text(label_el).rstrip(":")
        result[label] = _text(value_el)
    return result


def _value_for_label_containing(values: dict[str, str], substr: str) -> str:
    for label, value in values.items():
        if substr in label:
            return value
    return ""


@dataclass
class HardwareInfo:
    model: str
    vendor: str
    hardware_revision: str
    serial_number: str


def parse_hardware(html: str) -> HardwareInfo:
    soup = BeautifulSoup(html, "lxml")
    values = _labeled_values(soup)
    return HardwareInfo(
        model=values.get("Model", ""),
        vendor=values.get("Vendor", ""),
        hardware_revision=values.get("Hardware Revision", ""),
        serial_number=values.get("Serial Number", ""),
    )


@dataclass
class SoftwareInfo:
    docsis_software_version: str
    image_name: str
    packet_cable_version: str


def parse_software(html: str) -> SoftwareInfo:
    soup = BeautifulSoup(html, "lxml")
    values = _labeled_values(soup)
    return SoftwareInfo(
        docsis_software_version=_value_for_label_containing(values, "Software Version"),
        image_name=values.get("Software Image Name", ""),
        packet_cable_version=values.get("Packet Cable", ""),
    )


@dataclass
class WanInfo:
    operational_mode: str
    ip4: str
    ip6: str


def parse_wan(html: str) -> WanInfo:
    soup = BeautifulSoup(html, "lxml")
    values = _labeled_values(soup)
    return WanInfo(
        operational_mode=values.get("Current Operational Mode", ""),
        ip4=values.get("WAN IP Address (IPv4)", ""),
        ip6=values.get("WAN IP Address (IPv6)", ""),
    )
