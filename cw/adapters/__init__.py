from .base import FetchResult  # noqa: F401
from . import usgs, noaa_swpc, gdacs, gdacs_vo_dr

# Nur Quellen mit Adapter dürfen in der Registry stehen (Validator prüft das).
ADAPTERS = {
    "usgs": usgs.parse,
    "noaa-swpc": noaa_swpc.parse,
    "gdacs": gdacs.parse,
    "gdacs-volcano": gdacs_vo_dr.parse_volcano,
    "gdacs-drought": gdacs_vo_dr.parse_drought,
}
