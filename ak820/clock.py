"""Set the keyboard clock (04 28). Verified on hardware (wired)."""
import time
from .hid import write_session


def build(t, slot=1):
    rec = bytearray(64)
    rec[1] = slot
    rec[2] = 0x5A
    rec[3] = t.tm_year - 2000
    rec[4], rec[5] = t.tm_mon, t.tm_mday
    rec[6], rec[7], rec[8] = t.tm_hour, t.tm_min, t.tm_sec
    rec[10] = (t.tm_wday + 1) % 7              # Python Monday=0 -> Sunday=0
    rec[62], rec[63] = 0xAA, 0x55
    return bytes(rec)


def apply(dev, t=None, slot=1, retries=5, log=lambda s: None):
    return write_session(dev, 0x28, [build(t or time.localtime(), slot)], header=dict(b8=1), flush=False,
                         retries=retries, log=log)
