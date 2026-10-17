"""Lighting effect record (04 13). Verified on hardware: effect 1/7/16, RGB, rainbow, brightness, speed, direction."""
from .hid import write_session

# Effect indices: order of the vendor language file (ids 521-540). 1, 7 and 16 were confirmed by looking at the keyboard,
# the rest are unverified guesses at the names.
EFFECTS = ['LED Off', 'Static', 'Single On', 'Single Off', 'Glittering', 'Falling', 'Colourful', 'Breath', 'Spectrum',
           'Outward', 'Scrolling', 'Rolling', 'Rotating', 'Explode', 'Launch', 'Ripples', 'Flowing', 'Pulsating',
           'Tilt', 'Shuttle']
VERIFIED = {1, 7, 16}


def build_record(effect, rgb=(255, 255, 255), rainbow=False, brightness=5, speed=0, direction=0):
    if not 0 <= effect < len(EFFECTS):
        raise ValueError(f'effect must be 0..{len(EFFECTS) - 1}')
    if not 0 <= brightness <= 5 or not 0 <= speed <= 5 or not 0 <= direction <= 3:
        raise ValueError('brightness/speed must be 0..5, direction 0..3')
    rec = bytearray(64)
    rec[0] = effect
    rec[1:4] = bytes(rgb)
    rec[8:12] = bytes([int(bool(rainbow)), brightness, speed, direction])
    rec[14], rec[15] = 0xAA, 0x55
    return bytes(rec)


def apply(dev, record, retries=6, log=lambda s: None):
    return write_session(dev, 0x13, [record], header=dict(b8=1), expect_sum=sum(record[:16]), retries=retries, log=log)
