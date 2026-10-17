# Geography Assets & Provenance

This directory stores the offline, zero-external-egress geographic data for the **SignalScanner 3D Telemetry Globe**.

## Provenance & License

- **Source:** [Natural Earth](https://www.naturalearthdata.com/)
- **License:** Public Domain / [Creative Commons CC0 1.0 Universal](LICENSE)
- **Redistribution:** Derived from the official npm packages [`world-atlas`](https://github.com/topojson/world-atlas) (ISC) and [`topojson-client`](https://github.com/topojson/topojson-client) (ISC).
- **Network Policy:** All assets are bundled as local static files. No runtime connection is made to any tile server, geocoding service, or external CDN.

## Files & Resolution Characteristics

| File | Resolution | Description & Characteristics |
|---|---|---|
| `ne_110m_land.geojson` | 1:110m | 125 physical land polygons, 126 rings, 1 interior hole (Caspian Sea). Covers the 13 major Indonesian islands (Sumatra, Java, Kalimantan, Sulawesi, Papua, Halmahera, Seram, Buru, Timor, Flores, Sumbawa, Sumba, Aru), Japan, Philippines, UK, NZ, Madagascar, Cuba, Fiji. Micro-islands below threshold (Singapore, Malta) are not separated. |
| `ne_110m_admin_0_countries.geojson` | 1:110m | 177 country features (148 Polygon + 29 MultiPolygon) incl. the Lesotho enclave hole inside South Africa. |
| `ne_110m_admin_0_boundary_lines.geojson` | 1:110m | Interior country borders (MultiLineString) computed via `topojson.mesh(countries, (a, b) => a !== b)`. |
| `land-110m.json`, `countries-110m.json` | 1:110m | Raw TopoJSON source files. |
| `land-50m.json`, `countries-50m.json` | 1:50m | 1:50m TopoJSON source files (>1,400 polygons). Separates small islands (Bali, Bangka, Belitung, Madura, Singapore, Malta, Bahrain). |

## Regenerating / Switching Resolution

To generate 110m assets (default):
```bash
pnpm --prefix frontend run geo:110m
```

To switch to 50m higher-resolution assets:
```bash
pnpm --prefix frontend run geo:50m
```
Then set `GEO_RESOLUTION = "50m"` in `frontend/components/web-scanner/WebScanGlobe.tsx`.
