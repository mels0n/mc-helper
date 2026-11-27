"""Client address from the socket peer, trusting X-Forwarded-For only behind a known proxy."""

import ipaddress
from collections.abc import Iterable, Sequence

type IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
type IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

# Used when the peer is missing or not an IP, so every request lands in some bucket.
UNKNOWN = "0.0.0.0"


def parse_networks(entries: Iterable[str]) -> tuple[IPNetwork, ...]:
    """Parse IPs and CIDRs; raises ValueError on a malformed entry."""
    return tuple(ipaddress.ip_network(entry.strip(), strict=False) for entry in entries)


def _parse(text: str) -> IPAddress | None:
    try:
        address = ipaddress.ip_address(text.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _trusted(address: IPAddress, networks: Sequence[IPNetwork]) -> bool:
    return any(address.version == net.version and address in net for net in networks)


def client_ip(peer: str | None, forwarded: Sequence[str], trusted: Sequence[IPNetwork]) -> str:
    """The address to attribute a request to.

    The peer is used unless it is a trusted proxy; then the right-most X-Forwarded-For
    entry that is not itself a trusted proxy is used. A malformed entry reached first,
    or no untrusted entry, falls back to the peer.
    """
    if peer is None:
        return UNKNOWN
    peer_address = _parse(peer)
    if peer_address is None:
        return UNKNOWN
    if not _trusted(peer_address, trusted):
        return str(peer_address)
    entries = [part for header in forwarded for part in header.split(",")]
    for raw in reversed(entries):
        address = _parse(raw)
        if address is None:
            break
        if not _trusted(address, trusted):
            return str(address)
    return str(peer_address)


def bucket_key(ip: str) -> str:
    """The key lockouts count against: IPv6 addresses collapse to their /64."""
    address = _parse(ip)
    if address is None:
        return UNKNOWN
    if isinstance(address, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)
