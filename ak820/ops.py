"""Toolkit-free backend used by the GTK app (and testable without a display or a keyboard)."""
import threading, time
from dataclasses import dataclass

from . import clock, hid, lighting, screen


@dataclass
class Status:
    mode: str          # 'wired' | 'dongle' | 'none' | 'demo'
    usable: bool
    text: str


@dataclass
class Prepared:
    buf: bytes
    frames: int
    blocks: int
    preview_png: bytes


class Backend:
    def __init__(self, demo=False):
        self.demo = demo
        self._lock = threading.Lock()

    def status(self):
        if self.demo:
            return Status('demo', True, 'Demo mode: nothing is sent to a keyboard')
        modes = {n.mode for n in hid.find_nodes()}
        if 'wired' in modes:
            return Status('wired', True, 'Keyboard connected (USB cable)')
        if 'dongle' in modes:
            return Status('dongle', False, 'Only the 2.4G dongle was found. Settings can only be written over the USB '
                                           'cable: plug the keyboard in and switch it to wired mode.')
        return Status('none', False, 'No keyboard found. Connect it with the USB cable. If it is connected, the udev '
                                     'rule may be missing (see the README).')

    def _run(self, fn):
        """Run fn(dev, log) while holding the hardware lock; raises DeviceError if the keyboard rejects the write."""
        if not self._lock.acquire(blocking=False):
            raise hid.DeviceError('Another operation is still running.')
        lines = []
        try:
            with hid.open_device(self.demo) as dev:
                res = fn(dev, lines.append)
        finally:
            self._lock.release()
        if isinstance(res, dict) and 'ok' in res and not res['ok']:
            raise hid.DeviceError('The keyboard rejected the write. Replug it and try again.\n' + '\n'.join(lines))
        return res, lines

    # ---- features
    def apply_light(self, effect, rgb, rainbow, brightness, speed, direction):
        rec = lighting.build_record(effect, rgb, rainbow, brightness, speed, direction)
        return self._run(lambda d, lg: lighting.apply(d, rec, log=lg))

    def apply_time(self, t=None):
        return self._run(lambda d, lg: clock.apply(d, t or time.localtime(), log=lg))

    def prepare_image(self, path, fit, focus):
        with open(path, 'rb') as f:
            data = f.read()
        frames, delays = screen.load_frames(data, fit, focus)
        buf = screen.build_buffer(frames, delays)
        return Prepared(buf, len(frames), len(buf) // screen.BLOCK, screen.preview_png(frames[0]))

    def upload(self, buf, slot=1, progress=lambda done, total: None):
        return self._run(lambda d, lg: screen.upload(d, buf, slot, progress=progress, log=lg))
