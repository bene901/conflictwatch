from .base import FetchResult  # noqa: F401
from . import usgs, noaa_swpc

# Nur Quellen mit Adapter dürfen in der Registry stehen (Validator prüft das).
ADAPTERS = {"usgs": usgs.parse, "noaa-swpc": noaa_swpc.parse}
