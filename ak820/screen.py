"""Screen upload: 128x128 RGB565 animation (verified on hardware). Needs Pillow for image loading."""
import io, struct, time
from .hid import packet

W = H = 128
BLOCK = 4096
MAX_FRAMES = 140
FITS = ('stretch', 'contain', 'cover')


class ScreenError(RuntimeError):
    pass


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def _pil():
    try:
        from PIL import Image, ImageSequence
        return Image, ImageSequence
    except ImportError:
        raise ScreenError('Pillow is required for images: sudo dnf install python3-pillow  (or pip install pillow)')


def load_frames(data, fit='stretch', focus=0.5):
    """Image bytes (GIF/PNG/JPEG/...) -> (list of PIL RGB 128x128 frames, list of delay bytes = gif ms / 2)."""
    Image, ImageSequence = _pil()
    if fit not in FITS:
        raise ScreenError(f'fit must be one of {FITS}')
    try:
        im = Image.open(io.BytesIO(data))
        frames, delays = [], []
        for fr in ImageSequence.Iterator(im):
            delays.append(fr.info.get('duration', 100))
            rgba = fr.convert('RGBA')
            rgb = Image.alpha_composite(Image.new('RGBA', rgba.size, (0, 0, 0, 255)), rgba).convert('RGB')
            if fit == 'stretch':
                rgb = rgb.resize((W, H), Image.LANCZOS)
            else:
                sc = (max if fit == 'cover' else min)(W / rgb.width, H / rgb.height)
                sz = (max(1, round(rgb.width * sc)), max(1, round(rgb.height * sc)))
                rs = rgb.resize(sz, Image.LANCZOS)
                canvas = Image.new('RGB', (W, H), (0, 0, 0))
                if fit == 'cover':
                    off = (-round((sz[0] - W) * focus), -round((sz[1] - H) * focus))
                else:
                    off = ((W - sz[0]) // 2, (H - sz[1]) // 2)
                canvas.paste(rs, off)
                rgb = canvas
            frames.append(rgb)
            if len(frames) >= MAX_FRAMES:
                break
    except ScreenError:
        raise
    except Exception as e:
        raise ScreenError(f'cannot read image: {e}')
    return frames, [max(1, min(255, d // 2)) for d in delays]


def pack_frame(img):
    px = img.tobytes()
    out = bytearray(W * H * 2)
    for i in range(W * H):
        struct.pack_into('<H', out, 2 * i, rgb565(px[3 * i], px[3 * i + 1], px[3 * i + 2]))
    return bytes(out)


def build_buffer(frames, delays):
    hdr = bytearray(256)
    hdr[0] = len(frames)
    for i, d in enumerate(delays):
        hdr[1 + i] = d
    buf = bytes(hdr) + b''.join(pack_frame(f) for f in frames)
    return buf + b'\0' * (-len(buf) % BLOCK)


def preview_png(frame, scale=2):
    Image, _ = _pil()
    out = io.BytesIO()
    frame.resize((W * scale, H * scale), Image.NEAREST).save(out, 'PNG')
    return out.getvalue()


def upload(dev, buf, slot=1, retries=4, progress=lambda done, total: None, log=lambda s: None):
    nblk = len(buf) // BLOCK
    log(f'begin: {dev.feature(packet(4, 0x18))[:8].hex(" ")}')
    log(f'04 72: {dev.feature(packet(4, 0x72, b2=slot, b8=nblk & 0xFF, b9=nblk >> 8))[:12].hex(" ")}')
    retried = 0
    for i in range(nblk):
        for attempt in range(1, retries + 1):
            ack = dev.bulk_write(buf[i * BLOCK:(i + 1) * BLOCK])
            if ack[:1] == b'\x01':
                retried += attempt > 1
                break
            log(f'block {i} rejected (ack {ack[:4].hex(" ") or "TIMEOUT"}), retry {attempt}/{retries}')
            time.sleep(0.3 * attempt)
        else:
            raise ScreenError(f'block {i} failed repeatedly; replug the keyboard if the screen looks stuck')
        progress(i + 1, nblk)
    log(f'end: {dev.feature(packet(4, 0x02))[:8].hex(" ")} ({retried} blocks needed a retry)')
    return dict(blocks=nblk, retried=retried)
