from .base import FetchResult  # noqa: F401
from . import usgs, noaa_swpc, gdacs, gdacs_vo_dr, ucdp_candidate, gdelt

# Nur Quellen mit Adapter dürfen in der Registry stehen (Validator prüft das).
ADAPTERS = {
    "usgs": usgs.parse,
    "noaa-swpc": noaa_swpc.parse,
    "gdacs": gdacs.parse,
    "gdacs-volcano": gdacs_vo_dr.parse_volcano,
    "gdacs-drought": gdacs_vo_dr.parse_drought,
    "ucdp-candidate": ucdp_candidate.parse,
    "gdelt": gdelt.parse,
}

SOURCE_FETCHERS = {
    "ucdp-candidate": ucdp_candidate.fetch_latest,
    "gdelt": gdelt.fetch_recent,
}

RAW_SUFFIXES = {
    "ucdp-candidate": ".csv",
    "gdelt": ".tsv",
}
