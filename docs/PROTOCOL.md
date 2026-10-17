# AK820 Pro protocol notes

Observed from the keyboard's behaviour and the traffic of its configuration software. These notes describe the wire format only;
no vendor code or assets are included. Everything marked **verified** was tried on a real keyboard (wired, USB `0c45:8009`).

## Devices

| Mode | USB id | Notes |
|---|---|---|
| Wired | `0c45:8009` (also `800a`) | 4 HID interfaces; interface 0 carries commands, interface 2 bulk data |
| 2.4G dongle | `0c45:fdfd` | 5 interfaces; commands are different (see "Dongle") and are **not supported** |
| Bluetooth | none | no vendor interface expected |

Wired interfaces: 0 = boot keyboard (feature reports are used for commands), 1 = consumer/mouse/NKRO, 2 = vendor usage page `ff68`
(no report IDs, 64-byte input, 4096-byte output), 3 = vendor `ff13`.

## Command framing (verified)

A command is a 64-byte payload sent as a feature report with report ID 0 on interface 0 (`HIDIOCSFEATURE` with 65 bytes: ID + payload).
The reply is read back with `HIDIOCGFEATURE` (65 bytes: ID + payload).

- `payload[0]` = command class (always `04`), `payload[1]` = sub-command, further bytes are arguments.
- Reply: `00 04 <sub> 00 <status> ...`. Status `01` = accepted, `ff` = rejected.
- The keyboard occasionally rejects the first attempt of a write; retrying after ~0.5 s works.

### Write session

```
04 18                      begin
04 <sub> [b8 = packet count] header
<data packet(s), 64 bytes each>
04 02                      end   reply: 00 04 02 00 <status> <sum_lo> <sum_hi>
04 f0                      flush (no reply read)
```

For lighting the end reply carries the 16-bit sum of the 16 record bytes; a mismatch means the write was not applied.

## Lighting, sub-command `13` (verified)

Header `04 13` with `b8 = 1`, then one data packet whose first 16 bytes are:

| Byte | Meaning |
|---|---|
| 0 | effect index (1 Static, 7 Breath, 16 Flowing confirmed by eye; 0 = off; the names of the others are guesses) |
| 1-3 | R, G, B |
| 8 | rainbow flag (1 = cycle colours, ignores RGB) |
| 9 | brightness 0-5 |
| 10 | speed 0-5 (0 slow, 5 fast; visible on Breath) |
| 11 | direction/variant 0-3 (on Flowing: bit 0 = reverse, bit 1 = slower variant) |
| 14-15 | `AA 55` |

## Clock, sub-command `28` (verified)

Header `04 28` with `b8 = 1`; data: `[1]` screen index+1, `[2]` = `5A`, `[3]` year-2000, `[4]` month, `[5]` day, `[6]` hour, `[7]` minute,
`[8]` second, `[10]` weekday (0 = Sunday), `[62..63]` = `AA 55`. No `04 f0` is sent.

## Screen, sub-command `72` (verified)

Image: 128x128, max 140 frames. Buffer = 256-byte header (`[0]` frame count, `[1..n]` per-frame delay = GIF milliseconds / 2, min 1)
followed by the frames as RGB565 little-endian (`((R&F8)<<8)|((G&FC)<<3)|(B>>3)`, low byte first), padded to a multiple of 4096.

```
04 18
04 72   b2 = slot (1), b8..b9 = number of 4096-byte blocks, little-endian
N x bulk write on interface 2: 4096-byte output report; the first response byte is 01 on success
04 02
```

Linux detail: `hidraw` needs a leading `00` byte for a device without report IDs and strips it again; always write `00 + 4096 bytes`,
otherwise blocks that start with a zero byte lose a byte and the picture is corrupted.
The keyboard stores one animation; a new upload replaces it. A large GIF takes minutes.

## Key remap, sub-command `11` (decoded, NOT verified)

`04 18`, `04 11` with `b8 = 9`, a 576-byte table (9 packets), `04 02`, `04 f0`. The table has 144 entries of 4 bytes at
`key_index * 4`; the last two bytes are `AA 55`. Entry formats: `02 <modifier mask> <HID usage>` (key), `03 <consumer usage low byte>`
(media), `05 03` (assumed Fn). Whole-table rewrites only. The Fn layer uses sub-command `27`. The implementation is in
`ak820/keys.py` and is disabled in the app and CLI until someone confirms it on a keyboard.

## Dongle (not supported)

Commands go to the vendor interface `ff60` (32-byte input/output reports, no report IDs). The configuration software polls battery
with `20 01 00 ... [31] = sum of bytes` and expects `20 01 00 <percent>`; real dongles were observed to echo the request unchanged
(percent 0). A separate periodic report `55 fc 04 ...` appeared every 10 s; its meaning is unknown. Contributions welcome.
