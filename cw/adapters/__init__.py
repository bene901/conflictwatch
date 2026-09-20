from .base import FetchResult  # noqa: F401
from . import usgs, noaa_swpc, gdacs

# Nur Quellen mit Adapter dürfen in der Registry stehen (Validator prüft das).
ADAPTERS = {"usgs": usgs.parse, "noaa-swpc": noaa_swpc.parse, "gdacs": gdacs.parse}
