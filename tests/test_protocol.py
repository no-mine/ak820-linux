"""Protocol tests - no hardware involved (FakeDevice only). Run: python -m unittest discover -s tests"""
import io, os, sys, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ak820 import clock, hid, keys, lighting, ops, screen


class Lighting(unittest.TestCase):
    def test_record_layout(self):
        r = lighting.build_record(7, (1, 2, 3), rainbow=True, brightness=4, speed=2, direction=1)
        self.assertEqual(r[:16].hex(), '07010203' '00000000' '01040201' '0000aa55')
        self.assertEqual(len(r), 64)

    def test_range_checks(self):
        with self.assertRaises(ValueError): lighting.build_record(99)
        with self.assertRaises(ValueError): lighting.build_record(1, brightness=6)

    def test_apply_checksum(self):
        d = hid.FakeDevice()
        res = lighting.apply(d, lighting.build_record(1, (0, 255, 0)))
        self.assertTrue(res['ok'])
        self.assertEqual(res['checksum'], 1 + 255 + 5 + 0xAA + 0x55)
        self.assertEqual(d.log[-1][1][:2], b'\x04\xf0')            # flush


class Clock(unittest.TestCase):
    def test_build(self):
        t = time.strptime('2026-10-17 14:30:05', '%Y-%m-%d %H:%M:%S')    # a Saturday
        p = clock.build(t)
        self.assertEqual(list(p[:11]), [0, 1, 0x5A, 26, 10, 17, 14, 30, 5, 0, 6])
        self.assertEqual(p[62:], b'\xaa\x55')


class Keys(unittest.TestCase):
    def test_default_table_is_identity(self):
        t, ch = keys.build_table({})
        self.assertEqual(len(t), 576)
        self.assertEqual(ch, [])
        self.assertEqual(t[-2:], b'\xaa\x55')
        names = keys.by_name()
        self.assertEqual(t[names['esc']['index'] * 4:][:4], bytes([2, 0, 0x29, 0]))
        self.assertEqual(t[names['ctrl_l']['index'] * 4:][:4], bytes([2, 1, 0, 0]))     # modifier key alone
        self.assertEqual(t[names['fn']['index'] * 4:][:4], bytes([5, 3, 0, 0]))

    def test_targets(self):
        self.assertEqual(keys.parse_target('ctrl+shift+C'), bytes([2, 3, 6, 0]))
        self.assertEqual(keys.parse_target('media:mute'), bytes([3, 0xE2, 0, 0]))
        self.assertEqual(keys.parse_target('usage:0x29'), bytes([2, 0, 0x29, 0]))
        with self.assertRaises(ValueError): keys.parse_target('nonsense')
        with self.assertRaises(ValueError): keys.parse_target('media:nope')

    def test_remap_and_fn_protection(self):
        t, ch = keys.build_table({'CapsLock': 'Esc'})
        self.assertEqual([c[0] for c in ch], ['CapsLock'])
        with self.assertRaises(ValueError): keys.build_table({'Fn': 'Esc'})
        with self.assertRaises(ValueError): keys.build_table({'Nope': 'Esc'})

    def test_layout_indices_fit_table(self):
        idx = [k['index'] for k in keys.layout()['keys']]
        self.assertEqual(len(idx), len(set(idx)))
        self.assertLess(max(idx), keys.TABLE_ENTRIES)

    def test_apply_sends_nine_chunks(self):
        d = hid.FakeDevice()
        t, _ = keys.build_table({})
        self.assertTrue(keys.apply(d, t)['ok'])
        self.assertEqual(sum(1 for k, p in d.log if k == 'feature'), 2 + 9 + 1)


class Screen(unittest.TestCase):
    def test_buffer_and_pixels(self):
        from PIL import Image
        im = Image.new('RGB', (10, 10), (255, 0, 0)); b = io.BytesIO(); im.save(b, 'PNG')
        frames, delays = screen.load_frames(b.getvalue(), 'stretch')
        buf = screen.build_buffer(frames, delays)
        self.assertEqual(len(buf) % screen.BLOCK, 0)
        self.assertEqual(buf[0], 1)
        self.assertEqual(buf[256:258], b'\x00\xf8')             # red = F800 little endian

    def test_upload_blocks(self):
        d = hid.FakeDevice()
        info = screen.upload(d, bytes(screen.BLOCK * 3))
        self.assertEqual(info['blocks'], 3)
        self.assertEqual(sum(1 for k, p in d.log if k == 'bulk'), 3)


class Backend(unittest.TestCase):
    def setUp(self):
        self.be = ops.Backend(demo=True)

    def test_status_demo(self):
        st = self.be.status()
        self.assertEqual((st.mode, st.usable), ('demo', True))

    def test_light_and_time(self):
        res, log = self.be.apply_light(1, (0, 255, 0), False, 5, 0, 0)
        self.assertTrue(res['ok'])
        res, log = self.be.apply_time()
        self.assertTrue(res['ok'])

    def test_structured_key_targets(self):
        self.assertEqual(keys.parse_target('ctrl++='), keys.parse_target(('key', 1, '+=')))

    def test_prepare_image(self):
        from PIL import Image
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'x.png')
            Image.new('RGB', (30, 20), (0, 0, 255)).save(path)
            prep = self.be.prepare_image(path, 'cover', 0.5)
        self.assertEqual((prep.frames, prep.blocks), (1, 9))
        self.assertTrue(prep.preview_png.startswith(b'\x89PNG'))
        res, log = self.be.upload(prep.buf)
        self.assertEqual(res['blocks'], 9)

    def test_rejection_is_an_error(self):
        class Rejecting(hid.FakeDevice):
            def feature(self, payload):
                r = bytearray(super().feature(payload))
                if payload[1] == 0x02:
                    r[4] = 0xFF
                return bytes(r)
        orig, ops.hid.open_device = ops.hid.open_device, lambda demo=False: Rejecting()
        orig_sleep, hid.time.sleep = hid.time.sleep, lambda s: None
        try:
            with self.assertRaises(hid.DeviceError): self.be.apply_light(1, (1, 2, 3), False, 5, 0, 0)
        finally:
            ops.hid.open_device, hid.time.sleep = orig, orig_sleep


if __name__ == '__main__':
    unittest.main()
