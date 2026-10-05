from __future__ import annotations

import ipaddress
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.web_scan_geography import GeoEndpoint, GeoPoint

logger = logging.getLogger("signal_scanner.web_scan.geolocation")

# Standardized offline lookup database for public IP ranges and known Anycast/Cloud networks
OFFLINE_KNOWN_RANGES: List[Dict[str, Any]] = [
    {
        "cidr": "1.1.1.0/24",
        "city": "Sydney",
        "region": "New South Wales",
        "country": "Australia",
        "country_code": "AU",
        "lat": -33.8688,
        "lon": 151.2093,
        "provider": "Cloudflare Anycast",
    },
    {
        "cidr": "1.0.0.0/24",
        "city": "Sydney",
        "region": "New South Wales",
        "country": "Australia",
        "country_code": "AU",
        "lat": -33.8688,
        "lon": 151.2093,
        "provider": "Cloudflare Anycast",
    },
    {
        "cidr": "8.8.8.0/24",
        "city": "Mountain View",
        "region": "California",
        "country": "United States",
        "country_code": "US",
        "lat": 37.3861,
        "lon": -122.0839,
        "provider": "Google Public DNS",
    },
    {
        "cidr": "8.8.4.0/24",
        "city": "Mountain View",
        "region": "California",
        "country": "United States",
        "country_code": "US",
        "lat": 37.3861,
        "lon": -122.0839,
        "provider": "Google Public DNS",
    },
    {
        "cidr": "9.9.9.0/24",
        "city": "Zurich",
        "region": "Zurich",
        "country": "Switzerland",
        "country_code": "CH",
        "lat": 47.3769,
        "lon": 8.5417,
        "provider": "Quad9 Anycast",
    },
    {
        "cidr": "93.184.216.0/24",
        "city": "Norwell",
        "region": "Massachusetts",
        "country": "United States",
        "country_code": "US",
        "lat": 42.1596,
        "lon": -70.8217,
        "provider": "Edgecast / Example Networks",
    },
    {
        "cidr": "76.76.21.0/24",
        "city": "San Francisco",
        "region": "California",
        "country": "United States",
        "country_code": "US",
        "lat": 37.7749,
        "lon": -122.4194,
        "provider": "Vercel Edge Network",
    },
    {
        "cidr": "104.16.0.0/12",
        "city": "San Francisco",
        "region": "California",
        "country": "United States",
        "country_code": "US",
        "lat": 37.7749,
        "lon": -122.4194,
        "provider": "Cloudflare CDN Edge",
    },
    {
        "cidr": "172.64.0.0/13",
        "city": "San Francisco",
        "region": "California",
        "country": "United States",
        "country_code": "US",
        "lat": 37.7749,
        "lon": -122.4194,
        "provider": "Cloudflare CDN Edge",
    },
    {
        "cidr": "140.82.112.0/20",
        "city": "Seattle",
        "region": "Washington",
        "country": "United States",
        "country_code": "US",
        "lat": 47.6062,
        "lon": -122.3321,
        "provider": "GitHub Inc",
    },
    {
        "cidr": "185.199.108.0/22",
        "city": "Amsterdam",
        "region": "North Holland",
        "country": "Netherlands",
        "country_code": "NL",
        "lat": 52.3676,
        "lon": 4.9041,
        "provider": "Fastly CDN / GitHub Pages",
    },
    {
        "cidr": "151.101.0.0/16",
        "city": "San Francisco",
        "region": "California",
        "country": "United States",
        "country_code": "US",
        "lat": 37.7749,
        "lon": -122.4194,
        "provider": "Fastly Global Edge",
    },
    {
        "cidr": "103.0.0.0/8",
        "city": "Singapore",
        "region": "Central",
        "country": "Singapore",
        "country_code": "SG",
        "lat": 1.3521,
        "lon": 103.8198,
        "provider": "APNIC Regional Block",
    },
    {
        "cidr": "185.0.0.0/8",
        "city": "Frankfurt",
        "region": "Hesse",
        "country": "Germany",
        "country_code": "DE",
        "lat": 50.1109,
        "lon": 8.6821,
        "provider": "RIPE NCC European Block",
    },
    {
        "cidr": "200.0.0.0/8",
        "city": "São Paulo",
        "region": "São Paulo",
        "country": "Brazil",
        "country_code": "BR",
        "lat": -23.5505,
        "lon": -46.6333,
        "provider": "LACNIC Regional Block",
    },
    {
        "cidr": "196.0.0.0/8",
        "city": "Johannesburg",
        "region": "Gauteng",
        "country": "South Africa",
        "country_code": "ZA",
        "lat": -26.2041,
        "lon": 28.0473,
        "provider": "AFRINIC Regional Block",
    },
]

# Pre-parsed CIDR networks
PARSED_NETWORKS = [
    (ipaddress.ip_network(entry["cidr"]), entry)
    for entry in OFFLINE_KNOWN_RANGES
]


class OfflineGeoIPService:
    """
    Offline-only, zero-external-egress IP Geolocation enrichment service.
    Complies with PRD safety, airgap, and data privacy policies.
    """

    @staticmethod
    def parse_ip(ip_str: Optional[str]) -> Tuple[bool, Optional[ipaddress._BaseAddress]]:
        if not ip_str or not isinstance(ip_str, str):
            return False, None
        clean_str = ip_str.strip()
        try:
            parsed = ipaddress.ip_address(clean_str)
            return True, parsed
        except ValueError:
            return False, None

    @classmethod
    def lookup_target_ip(cls, ip_str: Optional[str]) -> Tuple[Optional[GeoPoint], str, str, Optional[str], Optional[str]]:
        """
        Performs offline geolocation lookup for a target IP.
        Returns: (geo_point, location_level, location_status, location_basis, status_reason)
        """
        valid, ip = cls.parse_ip(ip_str)
        if not valid or ip is None:
            return None, "unknown", "unknown", "unknown", "IP address unresolvable or missing"

        # Check for non-public IPs (RFC 1918, loopback, link-local, multicast, reserved)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
        ):
            return (
                None,
                "unknown",
                "unsupported",
                "unknown",
                "Private, loopback, or reserved IP address not eligible for public geolocation",
            )

        # Match against parsed offline networks
        for net, data in PARSED_NETWORKS:
            if ip in net:
                point = GeoPoint(
                    latitude=data["lat"],
                    longitude=data["lon"],
                    city=data.get("city"),
                    region=data.get("region"),
                    country=data.get("country"),
                    country_code=data.get("country_code"),
                )
                level = "city" if data.get("city") else "country"
                return point, level, "located", "ip_lookup_estimate", None

        # General IANA Regional Fallback based on first octet
        if isinstance(ip, ipaddress.IPv4Address):
            first_octet = int(ip_str.split(".")[0])
            if first_octet < 127:
                # North America / ARIN generic
                point = GeoPoint(
                    latitude=37.751,
                    longitude=-97.822,
                    city=None,
                    region=None,
                    country="United States",
                    country_code="US",
                )
                return point, "country", "located", "ip_lookup_estimate", None
            elif 128 <= first_octet < 192:
                # Europe / RIPE generic
                point = GeoPoint(
                    latitude=50.8503,
                    longitude=4.3517,
                    city=None,
                    region=None,
                    country="European Union",
                    country_code="EU",
                )
                return point, "country", "located", "ip_lookup_estimate", None
            else:
                # Global generic
                point = GeoPoint(
                    latitude=1.3521,
                    longitude=103.8198,
                    city=None,
                    region=None,
                    country="Asia-Pacific",
                    country_code="AP",
                )
                return point, "country", "located", "ip_lookup_estimate", None

        # IPv6 Generic Global Point
        point = GeoPoint(
            latitude=37.751,
            longitude=-97.822,
            city=None,
            region=None,
            country="Global Anycast",
            country_code="US",
        )
        return point, "country", "located", "ip_lookup_estimate", None

    @classmethod
    def resolve_source_endpoint(cls, config_settings: Any = None) -> GeoEndpoint:
        """
        Resolves the backend execution worker (Source) endpoint using configured server metadata.
        Explicitly distinguishes configured values from measured egress.
        """
        from app.config import settings

        cfg = config_settings or settings
        executor_id = getattr(cfg, "WEB_SCAN_EXECUTOR_ORIGIN_ID", "scanner-backend-worker-1")
        lat = getattr(cfg, "WEB_SCAN_EXECUTOR_LATITUDE", None)
        lon = getattr(cfg, "WEB_SCAN_EXECUTOR_LONGITUDE", None)
        country = getattr(cfg, "WEB_SCAN_EXECUTOR_COUNTRY", "Indonesia")
        city = getattr(cfg, "WEB_SCAN_EXECUTOR_CITY", "Jakarta")

        endpoint_id = f"src_{executor_id}"

        if lat is not None and lon is not None:
            location = GeoPoint(
                latitude=float(lat),
                longitude=float(lon),
                city=city,
                region=city,
                country=country,
                country_code="ID" if country == "Indonesia" else None,
            )
            return GeoEndpoint(
                id=endpoint_id,
                role="source",
                display_name=f"Executor: {executor_id}",
                ip=None,
                address_basis="configured",
                executor_id=executor_id,
                location=location,
                location_level="coordinates",
                location_basis="configured",
                location_status="located",
                status_reason="Source location determined from verified server executor configuration",
                provider_info="Server Executor Configuration",
            )
        else:
            return GeoEndpoint(
                id=endpoint_id,
                role="source",
                display_name=f"Executor: {executor_id}",
                ip=None,
                address_basis="configured",
                executor_id=executor_id,
                location=None,
                location_level="unknown",
                location_basis="unknown",
                location_status="unknown",
                status_reason="Executor location not configured in environment",
                provider_info=None,
            )
