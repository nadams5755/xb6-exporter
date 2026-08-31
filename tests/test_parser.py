from pathlib import Path

from xb6_exporter import parser

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_network_setup_downstream_channel():
    ns = parser.parse_network_setup(_fixture("network_setup.html"))

    assert len(ns.downstream) == 34
    ch28 = next(c for c in ns.downstream if c.channel_id == "28")
    assert ch28.locked is True
    assert ch28.frequency_hz == 543_000_000.0
    assert ch28.modulation == "256 QAM"
    assert isinstance(ch28.snr_db, float)
    assert isinstance(ch28.power_dbmv, float)


def test_parse_network_setup_downstream_ofdm_frequency_has_no_mhz_suffix():
    """OFDM channels render frequency as a bare Hz integer, unlike the QAM channels."""
    ns = parser.parse_network_setup(_fixture("network_setup.html"))

    ofdm_channels = {c.channel_id: c for c in ns.downstream if c.modulation == "OFDM"}
    assert ofdm_channels["193"].frequency_hz == 722_000_000.0
    assert ofdm_channels["194"].frequency_hz == 957_000_000.0


def test_parse_network_setup_upstream_channel():
    ns = parser.parse_network_setup(_fixture("network_setup.html"))

    assert len(ns.upstream) == 5
    ofdma = next(c for c in ns.upstream if c.modulation == "OFDMA")
    assert ofdma.channel_id == "43"
    assert ofdma.channel_type == "TDMA"
    assert ofdma.frequency_hz == 36_000_000.0

    atdma = next(c for c in ns.upstream if c.channel_type == "ATDMA")
    assert atdma.modulation == "QAM"
    assert atdma.symbol_rate == 5120.0


def test_parse_network_setup_codewords():
    ns = parser.parse_network_setup(_fixture("network_setup.html"))

    assert len(ns.codewords) == 34
    cw28 = next(c for c in ns.codewords if c.channel_id == "28")
    assert cw28.unerrored > 0
    assert cw28.correctable >= 0
    assert cw28.uncorrectable == 0


def test_parse_network_setup_registration_complete():
    ns = parser.parse_network_setup(_fixture("network_setup.html"))
    assert ns.registration_complete is True


def test_parse_hardware():
    hw = parser.parse_hardware(_fixture("hardware.html"))

    assert hw.model == "CGM4140COM"
    assert hw.vendor == "Technicolor"
    assert hw.hardware_revision == "2.2"
    assert hw.serial_number


def test_parse_software():
    sw = parser.parse_software(_fixture("software.html"))

    assert sw.image_name == "CGM4140COM_7.6p22s1_PROD_sey"
    assert sw.packet_cable_version == "2.0"
    assert "Prod_" in sw.docsis_software_version


def test_parse_wan():
    wan = parser.parse_wan(_fixture("wan_network.html"))

    assert wan.operational_mode == "DOCSIS"
    assert wan.ip4
    assert wan.ip6
