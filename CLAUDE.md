# CLAUDE.md — GPX Route Builder / Extender

## Mission

You help build and modify cycling GPX routes **on real roads**. When the user asks
to lengthen, shorten, or reshape a route, you must produce geometry that follows the
actual road/path network — never straight-line guesses between points. You do this by
calling a routing engine (OpenRouteService) that snaps waypoints to real roads and
returns full road geometry, then writing that out as a clean GPX.

## Environment assumptions

- Full outbound network access (you can reach `api.openrouteservice.org`).
- An OpenRouteService API key is available in the env var `ORS_API_KEY`.
- Python 3 with `pip`.

## One-time setup

Run these once at the start of a session if not already done:

```bash
pip install --quiet gpxpy openrouteservice
test -n "$ORS_API_KEY" && echo "ORS key present" || echo "MISSING ORS_API_KEY — ask the user to export it"
```

If `ORS_API_KEY` is missing, stop and ask the user to run
`export ORS_API_KEY=...` (free key from openrouteservice.org). Do not proceed without it.

### Optional: MCP instead of direct API

You can also wire OpenRouteService in as an MCP server rather than calling it from
Python. From a shell:

```bash
claude mcp add openroute --env OPENROUTESERVICE_API_KEY="$ORS_API_KEY" -- uvx openroute-mcp
```

(Check `claude mcp --help` — exact flags vary by Claude Code version.) The direct-API
script below is the default because it's more controllable for distance-targeting; use
MCP only if the user prefers it.

## Core tool: `route_tool.py`

`route_tool.py` is present in this repo. Import and use it directly:

```python
from route_tool import load_points, decimate, route, write_gpx, measure_gpx, extend_to_target
```

### Key functions

| Function | Purpose |
|---|---|
| `load_points(path)` | Parse a GPX file → `([(lon, lat), ...], track_name)` |
| `decimate(pts, n)` | Thin to ≤ n waypoints (ORS free tier cap) |
| `route(coords, profile)` | Call ORS directions → `(geometry, distance_m)` |
| `write_gpx(geom, name, path)` | Write routed geometry to a GPX file |
| `measure_gpx(path)` | Route an existing GPX and return its distance in miles |
| `extend_to_target(in_gpx, out_gpx, target_mi, ...)` | Binary-search apex offset to hit a mileage target |

### Cycling profiles

Use one of: `cycling-regular`, `cycling-road`, `cycling-mountain`, `cycling-electric`.
**Never use a `driving-*` profile for a bike route.**

## Workflow for "make this route ~X miles"

1. Confirm setup (key + deps). Read the input GPX, report current distance.
2. Run `extend_to_target(in_gpx, out_gpx, X)`. Report the achieved mileage.
3. **Validate before delivering:** total within tolerance of target; route is a single
   connected line; start/end unchanged if it was a loop; elevation preserved.
4. If the apex-push gives an awkward shape, fall back to manually inserting a via point
   on a different road (offer the user 2–3 placement options) and re-route the whole
   waypoint list through `route()`.
5. Present the output GPX path and a one-line summary of what changed.

## Guardrails

- Real roads only. All new geometry must come from `route()` output, never interpolation.
- Always re-measure the routed result; don't trust the requested target as the actual length.
- Respect ORS free-tier limits (keep coords per request modest; a handful of routing
  calls per edit is fine). If a call fails, surface the error rather than faking geometry.
- Keep the original route name/metadata; annotate the new distance in the track name.
