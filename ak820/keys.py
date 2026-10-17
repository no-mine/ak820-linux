"""EXPERIMENTAL key remap (base layer, wired). Decoded from the vendor driver, NOT yet verified on hardware.

Key table: 144 entries x 4 bytes at key_index*4, 9 x 64-byte reports, AA 55 in the last two bytes. Entries:
  02 <modifier mask> <usage>   keyboard key (a modifier key on its own: 02 <mask> 00)
  03 <consumer usage low byte> media key
  05 03                        Fn (assumed)
The whole table is rewritten every time, so we always send the default layout plus the user's overrides."""
import json, os
from .hid import write_session

TABLE_ENTRIES, ENTRY = 144, 4
MEDIA = {'playpause': 0xCD, 'stop': 0xB7, 'prev': 0xB6, 'next': 0xB5, 'volup': 0xE9, 'voldown': 0xEA, 'mute': 0xE2}
MODS = {'ctrl': 1, 'shift': 2, 'alt': 4, 'gui': 8, 'win': 8}
FN_USAGE = 0xAF


def layout():
    with open(os.path.join(os.path.dirname(__file__), 'data', 'keys.json'), encoding='utf-8') as f:
        return json.load(f)


def by_name():
    return {k['name'].lower(): k for k in layout()['keys']}


def entry_for(usage, mods=0):
    if usage == FN_USAGE:
        return bytes([0x05, 0x03, 0, 0])
    if 0xE0 <= usage <= 0xE7 and not mods:
        return bytes([0x02, 1 << (usage - 0xE0), 0, 0])
    return bytes([0x02, mods, usage, 0])


def parse_target(target, names=None):
    """'Esc' | 'ctrl+shift+C' | 'usage:0x29' | 'media:mute' -> 4-byte entry.
    Also accepts structured targets: ('key', modifier_mask, key_name) and ('media', media_name)."""
    names = names or by_name()
    if isinstance(target, tuple):
        if target[0] == 'media':
            return parse_target('media:' + target[1], names)
        _, mods, key = target
        if key.lower() not in names:
            raise ValueError(f'unknown key {key!r}')
        return entry_for(names[key.lower()]['usage'], mods)
    t = target.strip()
    low = t.lower()
    if low.startswith('media:'):
        if low[6:] not in MEDIA:
            raise ValueError(f'unknown media key {t[6:]!r} (choose from {", ".join(MEDIA)})')
        return bytes([0x03, MEDIA[low[6:]], 0, 0])
    if low.startswith('usage:'):
        return entry_for(int(low[6:], 0))
    mods = 0
    while True:                                   # strip 'ctrl+' style prefixes; key names may contain '+' themselves
        head, sep, rest = t.partition('+')
        if sep and rest and head.lower() in MODS:
            mods |= MODS[head.lower()]
            t = rest
        else:
            break
    if t.lower() not in names:
        raise ValueError(f'unknown key {t!r}')
    return entry_for(names[t.lower()]['usage'], mods)


def describe(target):
    if isinstance(target, tuple):
        if target[0] == 'media':
            return 'Media: ' + target[1]
        _, mods, key = target
        return '+'.join([n.capitalize() for n, b in (('ctrl', 1), ('shift', 2), ('alt', 4), ('gui', 8)) if mods & b] + [key])
    return target


def default_entries():
    return {k['index']: entry_for(k['usage']) for k in layout()['keys']}


def build_table(maps):
    """maps: {key name: target string}. Returns (table bytes, [(key name, index, entry)] of changed keys)."""
    names = by_name()
    tbl = bytearray(TABLE_ENTRIES * ENTRY)
    for idx, e in default_entries().items():
        tbl[idx * ENTRY:idx * ENTRY + ENTRY] = e
    changes = []
    for key, target in maps.items():
        k = names.get(key.lower())
        if not k:
            raise ValueError(f'unknown key {key!r}')
        if k['usage'] == FN_USAGE:
            raise ValueError('the Fn key cannot be remapped')
        e = parse_target(target, names)
        tbl[k['index'] * ENTRY:k['index'] * ENTRY + ENTRY] = e
        if e != entry_for(k['usage']):
            changes.append((k['name'], k['index'], e))
    tbl[-2:] = b'\xAA\x55'
    return bytes(tbl), changes


def apply(dev, table, retries=5, log=lambda s: None):
    chunks = [table[i:i + 64] for i in range(0, len(table), 64)]
    return write_session(dev, 0x11, chunks, header=dict(b8=len(chunks)), retries=retries, log=log)
