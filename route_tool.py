import os
import math

import gpxpy
import gpxpy.gpx
import openrouteservice

client = openrouteservice.Client(key=os.environ["ORS_API_KEY"])
M_PER_MILE = 1609.344


def load_points(path):
    with open(path) as f:
        g = gpxpy.parse(f)
    pts = []
    for trk in g.tracks:
        for seg in trk.segments:
            pts += [(p.longitude, p.latitude) for p in seg.points]
    name = g.tracks[0].name if (g.tracks and g.tracks[0].name) else "Route"
    return pts, name


def decimate(pts, n):
    """Reduce to ~n ordered waypoints (ORS free tier caps coords per request)."""
    if len(pts) <= n:
        return pts
    step = (len(pts) - 1) / (n - 1)
    return [pts[round(i * step)] for i in range(n)]


def route(coords, profile="cycling-regular"):
    """coords: list of (lon, lat). Returns (geometry[[lon,lat,ele]...], distance_m)."""
    res = client.directions(coords, profile=profile, format="geojson", elevation=True)
    feat = res["features"][0]
    return feat["geometry"]["coordinates"], feat["properties"]["summary"]["distance"]


def write_gpx(geom, name, path):
    g = gpxpy.gpx.GPX()
    g.name = name
    trk = gpxpy.gpx.GPXTrack(name=name)
    g.tracks.append(trk)
    seg = gpxpy.gpx.GPXTrackSegment()
    trk.segments.append(seg)
    for c in geom:
        ele = c[2] if len(c) > 2 else None
        seg.points.append(
            gpxpy.gpx.GPXTrackPoint(latitude=c[1], longitude=c[0], elevation=ele)
        )
    with open(path, "w") as f:
        f.write(g.to_xml())


def _haversine(a, b):
    R = 6371000
    dlon = math.radians(b[0] - a[0])
    dlat = math.radians(b[1] - a[1])
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a[1]))
        * math.cos(math.radians(b[1]))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(h))


def _bearing(a, b):
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    dlon = math.radians(b[0] - a[0])
    y = math.sin(dlon) * math.cos(lat2)
    x = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    )
    return math.atan2(y, x)


def _offset(lon, lat, bearing, dist_m):
    R = 6371000
    dr = dist_m / R
    lat1, lon1 = math.radians(lat), math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(dr)
        + math.cos(lat1) * math.sin(dr) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(dr) * math.cos(lat1),
        math.cos(dr) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lon2), math.degrees(lat2)


def measure_gpx(path):
    """Return the routed distance of an existing GPX in miles."""
    pts, _ = load_points(path)
    wpts = decimate(pts, 24)
    _, dist_m = route(wpts)
    return dist_m / M_PER_MILE


def extend_to_target(
    in_gpx,
    out_gpx,
    target_mi,
    profile="cycling-regular",
    tol_mi=0.25,
    n_wp=24,
    max_iter=9,
):
    """Push the farthest-from-start waypoint outward and binary-search the push
    distance until the re-routed total hits target_mi. Returns achieved mileage."""
    pts, name = load_points(in_gpx)
    wpts = decimate(pts, n_wp)
    s = wpts[0]
    apex = max(range(1, len(wpts) - 1), key=lambda i: _haversine(s, wpts[i]))
    brg = _bearing(s, wpts[apex])
    ap_lon, ap_lat = wpts[apex]
    lo, hi = 0.0, max(1.0, target_mi) * M_PER_MILE
    best = None
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        nl, na = _offset(ap_lon, ap_lat, brg, mid)
        trial = wpts[:apex] + [(nl, na)] + wpts[apex:]
        geom, dist = route(trial, profile)
        mi = dist / M_PER_MILE
        best = (geom, mi)
        if abs(mi - target_mi) <= tol_mi:
            break
        if mi < target_mi:
            lo = mid
        else:
            hi = mid
    write_gpx(best[0], f"{name} ({best[1]:.1f} mi)", out_gpx)
    return best[1]
