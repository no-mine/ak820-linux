"""Command line interface: ak820 {devices,light,time,screen,gui}."""
import argparse, sys, time
from . import __version__, clock, hid, lighting, screen


def _dev(a):
    return hid.open_device(demo=a.demo)


def _report(res):
    if not res['ok']:
        sys.exit(f'keyboard rejected the write: {res}')
    print('OK')


def cmd_devices(a):
    nodes = hid.find_nodes()
    if not nodes:
        print('no AK820 Pro found')
    for n in nodes:
        print(f'{n.path}  {n.vid:04x}:{n.pid:04x}  interface {n.interface}  ({n.mode})')


def cmd_light(a):
    rgb = bytes.fromhex(a.rgb.lstrip('#'))
    if len(rgb) != 3:
        sys.exit('--rgb needs 6 hex digits, e.g. ff0000')
    if a.list:
        for i, n in enumerate(lighting.EFFECTS):
            print(f'{i:2d} {n}{"" if i in lighting.VERIFIED else "  (unverified)"}')
        return
    rec = lighting.build_record(a.effect, rgb, a.rainbow, a.brightness, a.speed, a.direction)
    print('record', rec[:16].hex(' '))
    if a.dry_run:
        return
    with _dev(a) as d:
        _report(lighting.apply(d, rec, log=print))


def cmd_time(a):
    t = time.strptime(a.set, '%Y-%m-%d %H:%M:%S') if a.set else time.localtime()
    print('time', time.strftime('%Y-%m-%d %H:%M:%S', t))
    if a.dry_run:
        return
    with _dev(a) as d:
        _report(clock.apply(d, t, log=print))


def cmd_screen(a):
    if a.solid:
        from PIL import Image
        frames = [Image.new('RGB', (screen.W, screen.H), tuple(bytes.fromhex(c.lstrip('#')))) for c in a.solid.split(',')]
        delays = [25] * len(frames)
    elif a.image:
        frames, delays = screen.load_frames(open(a.image, 'rb').read(), a.fit, a.focus)
    else:
        sys.exit('give --image FILE or --solid RRGGBB')
    if a.delay is not None:
        delays = [a.delay] * len(frames)
    if a.preview:
        open(a.preview, 'wb').write(screen.preview_png(frames[0]))
        return print('wrote', a.preview)
    buf = screen.build_buffer(frames, delays)
    print(f'frames={len(frames)} buffer={len(buf)} bytes blocks={len(buf) // screen.BLOCK}')
    if not a.go:
        return print('dry run, nothing sent (add --go)')
    with _dev(a) as d:
        screen.upload(d, buf, a.slot, progress=lambda i, n: print(f'\r{i}/{n}', end='', flush=True) if i % 50 == 0 or i == n else None,
                      log=print)
    print()


def cmd_gui(a):
    try:
        from . import app
    except ImportError as e:
        sys.exit(f'GTK 4 / libadwaita bindings missing ({e}). On Fedora: sudo dnf install python3-gobject libadwaita')
    sys.exit(app.main(demo=a.demo))


def main(argv=None):
    p = argparse.ArgumentParser(prog='ak820', description='AJAZZ AK820 Pro configuration (wired USB mode).')
    p.add_argument('--version', action='version', version=__version__)
    p.add_argument('--demo', action='store_true', help='use a fake device, send nothing to hardware')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('devices', help='list detected interfaces').set_defaults(f=cmd_devices)
    s = sub.add_parser('light', help='set the lighting effect')
    s.add_argument('effect', type=int, nargs='?', default=1, help='effect index (see --list)')
    s.add_argument('--list', action='store_true')
    s.add_argument('--rgb', default='ffffff')
    s.add_argument('--rainbow', action='store_true')
    s.add_argument('--brightness', type=int, default=5)
    s.add_argument('--speed', type=int, default=0)
    s.add_argument('--direction', type=int, default=0)
    s.add_argument('--dry-run', action='store_true')
    s.set_defaults(f=cmd_light)
    s = sub.add_parser('time', help='set the keyboard clock')
    s.add_argument('--set', metavar='"YYYY-MM-DD HH:MM:SS"')
    s.add_argument('--dry-run', action='store_true')
    s.set_defaults(f=cmd_time)
    s = sub.add_parser('screen', help='upload an image/GIF to the screen')
    s.add_argument('--image')
    s.add_argument('--solid', help='RRGGBB[,RRGGBB...]')
    s.add_argument('--fit', choices=screen.FITS, default='stretch')
    s.add_argument('--focus', type=float, default=0.5)
    s.add_argument('--delay', type=int)
    s.add_argument('--slot', type=int, default=1)
    s.add_argument('--preview', metavar='PNG')
    s.add_argument('--go', action='store_true', help='really send')
    s.set_defaults(f=cmd_screen)
    s = sub.add_parser('gui', help='open the graphical interface (GTK 4 / libadwaita)')
    s.set_defaults(f=cmd_gui)
    a = p.parse_args(argv)
    try:
        a.f(a)
    except (hid.DeviceError, screen.ScreenError, ValueError) as e:
        sys.exit(f'error: {e}')


if __name__ == '__main__':
    main()
