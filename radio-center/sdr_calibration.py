"""SDR parameters are loaded at worker startup from shared station settings."""
from station_common import load
_settings=load()
SDR_PPM=_settings["ppm"]
SDR_GAIN=_settings["gain"]
SDR_DEVICE=_settings["device"]

# rtl_433 requires a colon to distinguish a serial number from a numeric index.
RTL433_DEVICE=SDR_DEVICE if SDR_DEVICE.isdecimal() and len(SDR_DEVICE)<=2 else ':'+SDR_DEVICE
