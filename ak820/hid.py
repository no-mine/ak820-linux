"""Transport: hidraw access to the keyboard, plus a fake device for demo mode and tests."""
import fcntl, glob, os, select, time
from dataclasses import dataclass

WIRED_IDS = {(0x0C45, 0x8009), (0x0C45, 0x800A)}
DONGLE_ID = (0x0C45, 0xFDFD)


class DeviceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Node:
    path: str
    vid: int
    pid: int
    interface: int

    @property
    def mode(self):
        return 'wired' if (self.vid, self.pid) in WIRED_IDS else 'dongle'


def _ioc(d, t, nr, size):
    return (d << 30) | (size << 16) | (ord(t) << 8) | nr


def HIDIOCSFEATURE(n): return _ioc(3, 'H', 0x06, n)
def HIDIOCGFEATURE(n): return _ioc(3, 'H', 0x07, n)


def find_nodes(sysfs='/sys/class/hidraw'):
    out = []
    for h in sorted(glob.glob(sysfs + '/hidraw*')):
        try:
            with open(h + '/device/uevent') as f:
                uevent = f.read()
            hid_id = [l for l in uevent.splitlines() if l.startswith('HID_ID=')][0]
            _, vid, pid = hid_id.split('=')[1].split(':')
            ids = (int(vid, 16), int(pid, 16))
            if ids not in WIRED_IDS and ids != DONGLE_ID:
                continue
            with open(os.path.realpath(h + '/device/..') + '/bInterfaceNumber') as f:
                ifnum = int(f.read().strip(), 16)
            out.append(Node('/dev/' + os.path.basename(h), ids[0], ids[1], ifnum))
        except (OSError, IndexError, ValueError):
            pass
    return sorted(out, key=lambda n: (n.pid, n.interface))


def packet(cmd, sub, **fields):
    """64-byte command payload: byte0 = command class, byte1 = sub-command, fields b2=.., b8=.. set further bytes."""
    p = bytearray(64)
    p[0], p[1] = cmd, sub
    for off, val in fields.items():
        p[int(off[1:])] = val
    return bytes(p)


class Device:
    """Wired keyboard. Commands are 64-byte feature reports on interface 0 (report ID 0);
    bulk data (screen) goes to interface 2 as 4096-byte output reports."""

    def __init__(self, nodes=None):
        nodes = nodes if nodes is not None else find_nodes()
        wired = {n.interface: n for n in nodes if n.mode == 'wired'}
        if 0 not in wired:
            if any(n.mode == 'dongle' for n in nodes):
                raise DeviceError('Only the 2.4G dongle was found. This tool supports the wired (USB cable) mode only.')
            raise DeviceError('No AK820 Pro found. Connect it with the USB cable (and check the udev rule / permissions).')
        self._wired = wired
        self._fds = {}
        self.name = f'{wired[0].vid:04x}:{wired[0].pid:04x} ({wired[0].path})'

    def _fd(self, interface):
        if interface not in self._fds:
            if interface not in self._wired:
                raise DeviceError(f'interface {interface} of the keyboard not found')
            try:
                self._fds[interface] = os.open(self._wired[interface].path, os.O_RDWR)
            except PermissionError:
                raise DeviceError(f'No permission for {self._wired[interface].path}. Install the udev rule '
                                  f'(70-ak820.rules, see README) or run as root.')
        return self._fds[interface]

    def send(self, payload):
        """Set a feature report without reading a reply."""
        fcntl.ioctl(self._fd(0), HIDIOCSFEATURE(65), bytearray(b'\0' + payload))

    def feature(self, payload):
        """Set a feature report and read the 65-byte reply (report ID + 64 bytes)."""
        self.send(payload)
        time.sleep(0.005)
        rbuf = bytearray(65)
        fcntl.ioctl(self._fd(0), HIDIOCGFEATURE(65), rbuf)
        return bytes(rbuf)

    def bulk_write(self, block, timeout=1.0):
        """Write one 4096-byte block to interface 2; returns the ack (first byte 01 = ok, b'' = timeout)."""
        fd = self._fd(2)
        os.write(fd, b'\0' + block)                       # report ID 0; usbhid strips it
        rd, _, _ = select.select([fd], [], [], timeout)
        return os.read(fd, 64) if rd else b''

    def close(self):
        for fd in self._fds.values():
            os.close(fd)
        self._fds = {}

    def __enter__(self): return self
    def __exit__(self, *a): self.close()


class FakeDevice:
    """Imitates the wired keyboard's replies and records everything sent (demo mode / tests)."""
    name = 'demo device (nothing is sent to hardware)'
    DATA_PACKETS = {0x13: 1, 0x28: 1, 0x11: 9, 0x27: 9}

    def __init__(self):
        self.log = []          # (kind, bytes)
        self._pending = 0
        self._sum = 0

    def feature(self, payload):
        self.log.append(('feature', payload))
        reply = bytearray(65)
        if self._pending:
            self._pending -= 1
            self._sum += sum(payload)
            reply[1:3] = payload[:2]
            reply[4] = 1
        else:
            reply[1:3] = payload[:2]
            sub = payload[1]
            if sub == 0x18:
                reply[4] = 1
                self._sum = 0
            elif sub == 0x02:
                reply[4] = 1
                reply[5], reply[6] = self._sum & 0xFF, (self._sum >> 8) & 0xFF
            elif sub in self.DATA_PACKETS:
                self._pending = self.DATA_PACKETS[sub]
        return bytes(reply)

    def send(self, payload):
        self.log.append(('send', payload))

    def bulk_write(self, block, timeout=1.0):
        self.log.append(('bulk', block))
        return b'\x01\x5a\x02' + bytes(61)

    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass


def write_session(dev, sub, chunks, header=None, expect_sum=None, flush=True, retries=6, log=lambda s: None):
    """The vendor write sequence: 04 18 | 04 <sub> | data chunks | 04 02 [| 04 f0].
    The keyboard sometimes rejects the first attempt (status ff), so retry with back-off.
    Returns dict(ok, attempts, end, checksum, rejected_chunks)."""
    header = header or {}
    res = None
    for attempt in range(1, retries + 1):
        dev.feature(packet(4, 0x18))
        dev.feature(packet(4, sub, **header))
        rejected = sum(dev.feature(c)[4] == 0xFF for c in chunks)
        end = dev.feature(packet(4, 0x02))
        got = end[5] | end[6] << 8
        ok = end[4] == 1 and not rejected and (expect_sum is None or got == expect_sum)
        res = dict(ok=ok, attempts=attempt, end=end[:8].hex(' '), checksum=got, rejected_chunks=rejected)
        log(f'attempt {attempt}: {"OK" if ok else "REJECTED"}  end={res["end"]}')
        if ok:
            if flush:
                dev.send(packet(4, 0xF0))
            return res
        time.sleep(0.5 * attempt)
    return res


def open_device(demo=False):
    return FakeDevice() if demo else Device()
