# -*- coding: utf-8 -*-
"""
upnp.py - Geraetesuche (SSDP) und Steuerung (UPnP/SOAP) fuer Raumfeld-Lautsprecher.

Unterschied zum Linux-Skript:
  Unter Windows hat ein PC oft mehrere Netzwerkadapter (WLAN, LAN, VPN,
  WSL, Hyper-V ...). Ein einzelner Multicast-Socket sendet dann gern ueber
  den falschen Adapter. Darum wird die Suche hier ueber JEDE lokale
  IPv4-Adresse einzeln gesendet.
"""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from xml.sax.saxutils import escape as xml_escape

# Multicast-Adresse/Port fuer SSDP (im UPnP-Standard festgelegt)
SSDP_ADDR = ("239.255.255.250", 1900)

# Wir suchen "MediaRenderer" = Geraete, die Medien abspielen koennen
ST_MEDIA_RENDERER = "urn:schemas-upnp-org:device:MediaRenderer:1"

# UPnP-Dienste: AVTransport (Play/Stop/...) und RenderingControl (Lautstaerke)
SERVICE_AVTRANSPORT = "urn:schemas-upnp-org:service:AVTransport:1"
SERVICE_RENDERING = "urn:schemas-upnp-org:service:RenderingControl:1"

# XML-Namespace der Geraetebeschreibung
NS_DEVICE = "{urn:schemas-upnp-org:device-1-0}"


@dataclass
class Renderer:
    """Ein UPnP-MediaRenderer (z. B. ein Raumfeld-Lautsprecher)."""
    name: str                  # Anzeigename, z. B. "Stereo Cubes"
    location: str              # URL der Geraetebeschreibung (XML)
    host: str                  # IP-Adresse des Geraets
    avtransport_url: str       # SOAP-Endpunkt fuer Play/Stop/...
    rendering_url: str | None  # SOAP-Endpunkt fuer Lautstaerke (falls vorhanden)


# ---------------------------------------------------------------------------
# Netzwerk-Hilfen
# ---------------------------------------------------------------------------

def lokale_ipv4_adressen() -> list[str]:
    """
    Ermittelt alle brauchbaren lokalen IPv4-Adressen dieses PCs.
    Loopback (127.x) und Link-Local (169.254.x) werden ausgelassen.
    """
    adressen: set[str] = set()

    # 1) Alle Adressen, die zum Rechnernamen gehoeren
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            adressen.add(info[4][0])
    except OSError:
        pass

    # 2) Die Adresse der Standardroute (UDP-connect sendet kein Paket)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # Testadresse, wird nicht wirklich erreicht
            adressen.add(s.getsockname()[0])
    except OSError:
        pass

    brauchbar = {a for a in adressen
                 if not a.startswith("127.") and not a.startswith("169.254.")}
    return sorted(brauchbar)


def lokale_ip_zu(ziel_ip: str) -> str:
    """
    Eigene IP, ueber die das Ziel erreichbar ist (wichtig bei mehreren
    Adaptern: genau diese Adresse muss der Lautsprecher fuer den Stream nutzen).
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((ziel_ip, 9))
        return s.getsockname()[0]


# ---------------------------------------------------------------------------
# 1) Suche per SSDP
# ---------------------------------------------------------------------------

def ssdp_suche(timeout: float = 3.0) -> list[str]:
    """
    Sendet eine SSDP-M-SEARCH-Anfrage ueber alle lokalen Adapter und
    sammelt die LOCATION-URLs der antwortenden MediaRenderer.
    """
    anfrage = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_ADDR[0]}:{SSDP_ADDR[1]}\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 2\r\n"
        f"ST: {ST_MEDIA_RENDERER}\r\n"
        "\r\n"
    ).encode("ascii")

    # Pro lokaler IP ein eigener Socket, der an diese IP gebunden ist
    sockets: list[socket.socket] = []
    for ip in lokale_ipv4_adressen():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            # Ausgehenden Multicast-Verkehr ueber genau diesen Adapter schicken
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                         socket.inet_aton(ip))
            s.bind((ip, 0))
            s.settimeout(0.3)
            sockets.append(s)
        except OSError:
            continue  # Adapter nicht nutzbar -> ueberspringen

    # Fallback: wenn keine Adresse ermittelt wurde, Standard-Socket verwenden
    if not sockets:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        s.settimeout(0.3)
        sockets.append(s)

    # Zweimal senden - UDP kann verloren gehen
    for _ in range(2):
        for s in sockets:
            try:
                s.sendto(anfrage, SSDP_ADDR)
            except OSError:
                pass

    locations: list[str] = []
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        for s in sockets:
            try:
                daten, _addr = s.recvfrom(65507)
            except (socket.timeout, OSError):
                continue
            for zeile in daten.decode("utf-8", errors="replace").split("\r\n"):
                schluessel, trenner, wert = zeile.partition(":")
                if trenner and schluessel.strip().lower() == "location":
                    url = wert.strip()
                    if url not in locations:
                        locations.append(url)
    for s in sockets:
        s.close()
    return locations


def renderer_laden(location: str) -> Renderer | None:
    """Laedt die Geraetebeschreibung und liest die Steuer-URLs aus."""
    try:
        with urllib.request.urlopen(location, timeout=5) as antwort:
            xml_daten = antwort.read()
        wurzel = ET.fromstring(xml_daten)
    except (urllib.error.URLError, OSError, ET.ParseError):
        return None

    # Basis-URL fuer relative controlURLs
    basis = wurzel.findtext(f"{NS_DEVICE}URLBase") or location
    name = wurzel.findtext(f".//{NS_DEVICE}friendlyName") or "Unbekannt"

    avt_url = None
    rc_url = None
    for dienst in wurzel.iter(f"{NS_DEVICE}service"):
        typ = (dienst.findtext(f"{NS_DEVICE}serviceType") or "").strip()
        ctrl = (dienst.findtext(f"{NS_DEVICE}controlURL") or "").strip()
        if not ctrl:
            continue
        voll = urllib.parse.urljoin(basis, ctrl)
        if typ.startswith("urn:schemas-upnp-org:service:AVTransport:"):
            avt_url = voll
        elif typ.startswith("urn:schemas-upnp-org:service:RenderingControl:"):
            rc_url = voll

    if not avt_url:
        return None
    host = urllib.parse.urlparse(location).hostname or ""
    return Renderer(name=name, location=location, host=host,
                    avtransport_url=avt_url, rendering_url=rc_url)


def renderer_suchen(timeout: float = 3.0) -> list[Renderer]:
    """Suche + Beschreibung laden; nach Namen sortiert."""
    gefunden = []
    for loc in ssdp_suche(timeout):
        r = renderer_laden(loc)
        if r:
            gefunden.append(r)
    return sorted(gefunden, key=lambda r: r.name.lower())


# ---------------------------------------------------------------------------
# 2) Steuerung per SOAP
# ---------------------------------------------------------------------------

def soap_aufruf(control_url: str, service_typ: str, aktion: str,
                argumente: dict[str, object]) -> dict[str, str]:
    """Fuehrt eine UPnP-Aktion aus und gibt die Antwortwerte als Dict zurueck."""
    args_xml = "".join(f"<{k}>{xml_escape(str(v))}</{k}>"
                       for k, v in argumente.items())
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        f'<u:{aktion} xmlns:u="{service_typ}">{args_xml}</u:{aktion}>'
        "</s:Body></s:Envelope>"
    ).encode("utf-8")

    anfrage = urllib.request.Request(
        control_url, data=body, method="POST",
        headers={"Content-Type": 'text/xml; charset="utf-8"',
                 "SOAPACTION": f'"{service_typ}#{aktion}"'})
    try:
        with urllib.request.urlopen(anfrage, timeout=10) as antwort:
            antwort_xml = antwort.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"UPnP-Aktion {aktion} fehlgeschlagen "
                           f"(HTTP {exc.code}): {detail[:300]}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"Lautsprecher nicht erreichbar: {exc}") from exc

    ergebnis: dict[str, str] = {}
    wurzel = ET.fromstring(antwort_xml)
    for elem in wurzel.iter():
        if elem.tag.endswith(f"{aktion}Response"):
            for kind in elem:
                ergebnis[kind.tag.split("}")[-1]] = kind.text or ""
            break
    return ergebnis


def avt(renderer: Renderer, aktion: str, **argumente) -> dict[str, str]:
    """Kurzform fuer AVTransport-Aufrufe (InstanceID ist immer 0)."""
    return soap_aufruf(renderer.avtransport_url, SERVICE_AVTRANSPORT, aktion,
                       {"InstanceID": 0, **argumente})


def hole_zustand(renderer: Renderer) -> str:
    """Aktueller Zustand: PLAYING, PAUSED_PLAYBACK, STOPPED, TRANSITIONING ..."""
    return avt(renderer, "GetTransportInfo").get("CurrentTransportState", "")


def setze_lautstaerke(renderer: Renderer, lautstaerke: int) -> None:
    """Setzt die Lautstaerke (0-100)."""
    if not renderer.rendering_url:
        raise RuntimeError("Dieses Gerät bietet keine Lautstärkeregelung per UPnP an.")
    lautstaerke = max(0, min(100, int(lautstaerke)))
    soap_aufruf(renderer.rendering_url, SERVICE_RENDERING, "SetVolume",
                {"InstanceID": 0, "Channel": "Master", "DesiredVolume": lautstaerke})


def hole_lautstaerke(renderer: Renderer) -> int:
    """Liest die aktuelle Lautstaerke (0-100)."""
    if not renderer.rendering_url:
        raise RuntimeError("Keine Lautstärkeregelung verfügbar.")
    antwort = soap_aufruf(renderer.rendering_url, SERVICE_RENDERING, "GetVolume",
                          {"InstanceID": 0, "Channel": "Master"})
    return int(antwort.get("CurrentVolume", "0") or 0)


def baue_didl(titel: str, stream_url: str) -> str:
    """DIDL-Lite-Metadaten (Titel, Format) - viele Renderer verlangen diese."""
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="raumfeldremote" parentID="0" restricted="1">'
        f"<dc:title>{xml_escape(titel)}</dc:title>"
        "<upnp:class>object.item.audioItem.musicTrack</upnp:class>"
        f'<res protocolInfo="http-get:*:audio/mpeg:*">{xml_escape(stream_url)}</res>'
        "</item></DIDL-Lite>"
    )
