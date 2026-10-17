"""Native GNOME app (GTK 4 + libadwaita) for the AJAZZ AK820 Pro. All hardware logic lives in ops.py."""
import sys
import threading
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import __version__, lighting  # noqa: E402
from .ops import Backend  # noqa: E402

APP_ID = 'org.ak820linux.Configurator'


def run_async(work, done):
    """Run work() in a thread; call done(result, error) on the GTK main loop."""
    def target():
        try:
            res, err = work(), None
        except Exception as e:                                  # reported to the user in the UI
            res, err = None, e

        def deliver():
            done(res, err)
            return False                                        # run once
        GLib.idle_add(deliver)
    threading.Thread(target=target, daemon=True).start()


def combo(title, items, selected=0):
    row = Adw.ComboRow(title=title)
    row.set_model(Gtk.StringList.new(list(items)))
    row.set_selected(selected)
    return row


def spin(title, lo, hi, value, subtitle=None):
    row = Adw.SpinRow.new_with_range(lo, hi, 1)
    row.set_title(title)
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_value(value)
    return row


class Window(Adw.ApplicationWindow):
    def __init__(self, app, backend):
        super().__init__(application=app, title='AK820 Pro', default_width=980, default_height=760)
        self.backend = backend
        self.status = backend.status()
        self.action_buttons = []           # enabled only while a keyboard is usable
        self.busy = False

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(policy=Adw.ViewSwitcherPolicy.WIDE)
        switcher.set_stack(self.stack)
        header.set_title_widget(switcher)
        menu = Gio.Menu()
        menu.append('About', 'app.about')
        header.pack_end(Gtk.MenuButton(icon_name='open-menu-symbolic', menu_model=menu, primary=True))
        view.add_top_bar(header)

        self.banner = Adw.Banner()
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self.banner)
        self.stack.set_vexpand(True)
        body.append(self.stack)
        view.set_content(body)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        self.stack.add_titled_with_icon(self._light_page(), 'light', 'Lighting', 'preferences-color-symbolic')
        self.stack.add_titled_with_icon(self._screen_page(), 'screen', 'Screen', 'video-display-symbolic')
        self.stack.add_titled_with_icon(self._clock_page(), 'clock', 'Clock', 'preferences-system-time-symbolic')

        self._apply_status()
        GLib.timeout_add_seconds(3, self._poll_status)

    # ---------- shared helpers
    def _poll_status(self):
        self.status = self.backend.status()
        self._apply_status()
        return True

    def _apply_status(self):
        self.banner.set_title(self.status.text)
        self.banner.set_revealed(self.status.mode != 'wired')
        self._refresh_buttons()

    def _refresh_buttons(self):
        for btn, extra in self.action_buttons:
            btn.set_sensitive(self.status.usable and not self.busy and extra())

    def _add_action(self, button, extra=lambda: True):
        self.action_buttons.append((button, extra))
        return button

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast.new(text))

    def error(self, err):
        dlg = Adw.AlertDialog(heading='Something went wrong', body=str(err))
        dlg.add_response('ok', 'OK')
        dlg.present(self)

    def run_hw(self, work, success, on_done=None):
        """Run a hardware job in a thread with the action buttons disabled meanwhile."""
        self.busy = True
        self._refresh_buttons()

        def done(res, err):
            self.busy = False
            self._refresh_buttons()
            if err:
                self.error(err)
            else:
                self.toast(success)
                if on_done:
                    on_done(res)
        run_async(work, done)

    @staticmethod
    def _page(*groups):
        page = Adw.PreferencesPage()
        for g in groups:
            page.add(g)
        return page

    # ---------- lighting
    def _light_page(self):
        group = Adw.PreferencesGroup(title='Lighting effect',
                                     description='Static, Breath and Flowing are tested on real hardware; other effects are '
                                                 'marked unverified (their names are guesses).')
        names = [n + ('' if i in lighting.VERIFIED else ' (unverified)') for i, n in enumerate(lighting.EFFECTS)]
        self.l_effect = combo('Effect', names, 1)
        group.add(self.l_effect)

        self.l_color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(), valign=Gtk.Align.CENTER)
        rgba = Gdk.RGBA()
        rgba.parse('#00ff00')
        self.l_color.set_rgba(rgba)
        row = Adw.ActionRow(title='Colour')
        row.add_suffix(self.l_color)
        group.add(row)

        self.l_rainbow = Adw.SwitchRow(title='Rainbow colours', subtitle='Cycles through colours and ignores the colour above')
        group.add(self.l_rainbow)
        self.l_bri = spin('Brightness', 0, 5, 5)
        self.l_spd = spin('Speed', 0, 5, 0, 'Animated effects only')
        self.l_dir = spin('Direction / variant', 0, 3, 0, 'Meaning depends on the effect')
        for r in (self.l_bri, self.l_spd, self.l_dir):
            group.add(r)

        act = Adw.PreferencesGroup()
        btn = self._add_action(Gtk.Button(label='Apply to keyboard', halign=Gtk.Align.CENTER))
        btn.add_css_class('suggested-action')
        btn.add_css_class('pill')
        btn.connect('clicked', self._on_light_apply)
        act.add(btn)
        return self._page(group, act)

    def _on_light_apply(self, _btn):
        c = self.l_color.get_rgba()
        rgb = tuple(round(v * 255) for v in (c.red, c.green, c.blue))
        args = (self.l_effect.get_selected(), rgb, self.l_rainbow.get_active(), int(self.l_bri.get_value()),
                int(self.l_spd.get_value()), int(self.l_dir.get_value()))
        self.run_hw(lambda: self.backend.apply_light(*args), 'Lighting applied')

    # ---------- screen
    def _screen_page(self):
        self.s_path = None
        self.s_prepared = None
        self.s_token = 0
        group = Adw.PreferencesGroup(title='Screen image',
                                     description='128×128 pixels. The keyboard stores one animation; each upload replaces it.')
        self.s_file_row = Adw.ActionRow(title='Image or GIF', subtitle='No file chosen')
        pick = Gtk.Button(label='Choose…', valign=Gtk.Align.CENTER)
        pick.connect('clicked', self._on_pick_image)
        self.s_file_row.add_suffix(pick)
        group.add(self.s_file_row)
        self.s_fit = combo('Fit', ['Stretch to 128×128', 'Contain (black bars)', 'Cover (crop)'])
        self.s_fit.connect('notify::selected', self._on_screen_options)
        group.add(self.s_fit)
        self.s_focus = spin('Crop position', 0, 100, 50, 'Cover only: 0 = left/top, 100 = right/bottom')
        self.s_focus.set_visible(False)
        self.s_focus.connect('notify::value', self._on_screen_options)
        group.add(self.s_focus)

        prev = Adw.PreferencesGroup(title='Preview')
        self.s_picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=False)
        self.s_picture.set_size_request(256, 256)
        self.s_picture.set_halign(Gtk.Align.CENTER)
        prev.add(self.s_picture)
        self.s_info = Gtk.Label(label='Choose an image to see how it will look on the screen.', wrap=True)
        self.s_info.add_css_class('dim-label')
        prev.add(self.s_info)

        act = Adw.PreferencesGroup()
        self.s_progress = Gtk.ProgressBar(visible=False)
        act.add(self.s_progress)
        btn = self._add_action(Gtk.Button(label='Upload to screen', halign=Gtk.Align.CENTER),
                               extra=lambda: self.s_prepared is not None)
        btn.add_css_class('suggested-action')
        btn.add_css_class('pill')
        btn.connect('clicked', self._on_upload)
        act.add(btn)
        return self._page(group, prev, act)

    def _on_pick_image(self, _btn):
        dlg = Gtk.FileDialog(title='Choose an image or GIF')
        flt = Gtk.FileFilter()
        flt.set_name('Images')
        flt.add_mime_type('image/*')
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(flt)
        dlg.set_filters(store)

        def done(d, res):
            try:
                f = d.open_finish(res)
            except GLib.Error:
                return                                           # cancelled
            self.s_path = f.get_path()
            self.s_file_row.set_subtitle(f.get_basename())
            self._refresh_preview()
        dlg.open(self, None, done)

    def _on_screen_options(self, *_):
        self.s_focus.set_visible(self.s_fit.get_selected() == 2)
        self._refresh_preview()

    def _refresh_preview(self):
        if not self.s_path:
            return
        self.s_token += 1
        token = self.s_token
        path, fit = self.s_path, ('stretch', 'contain', 'cover')[self.s_fit.get_selected()]
        focus = self.s_focus.get_value() / 100
        self.s_info.set_label('Preparing…')

        def done(prep, err):
            if token != self.s_token:
                return                                           # superseded by a newer request
            if err:
                self.s_prepared = None
                self.s_info.set_label(f'Cannot use this file: {err}')
            else:
                self.s_prepared = prep
                tex = Gdk.Texture.new_from_bytes(GLib.Bytes.new(prep.preview_png))
                self.s_picture.set_paintable(tex)
                self.s_info.set_label(f'{prep.frames} frame(s), {prep.blocks} blocks to upload')
            self._refresh_buttons()
        run_async(lambda: self.backend.prepare_image(path, fit, focus), done)

    def _on_upload(self, _btn):
        prep = self.s_prepared
        self.s_progress.set_visible(True)
        self.s_progress.set_fraction(0)

        def progress(i, n):
            GLib.idle_add(lambda: self.s_progress.set_fraction(i / n) and False)
        self.run_hw(lambda: self.backend.upload(prep.buf, 1, progress), 'Image uploaded',
                    on_done=lambda _r: self.s_progress.set_visible(False))

    # ---------- clock
    def _clock_page(self):
        group = Adw.PreferencesGroup(title='Keyboard clock', description='Sets the clock shown on the keyboard’s screen.')
        self.c_row = Adw.ActionRow(title='Computer time')
        group.add(self.c_row)
        self._tick()
        GLib.timeout_add_seconds(1, self._tick)
        act = Adw.PreferencesGroup()
        btn = self._add_action(Gtk.Button(label='Set keyboard clock', halign=Gtk.Align.CENTER))
        btn.add_css_class('suggested-action')
        btn.add_css_class('pill')
        btn.connect('clicked', lambda _b: self.run_hw(self.backend.apply_time, 'Clock set'))
        act.add(btn)
        return self._page(group, act)

    def _tick(self):
        self.c_row.set_subtitle(time.strftime('%A %Y-%m-%d  %H:%M:%S'))
        return True


class App(Adw.Application):
    def __init__(self, demo=False):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.backend = Backend(demo)
        about = Gio.SimpleAction.new('about', None)
        about.connect('activate', self._on_about)
        self.add_action(about)

    def do_activate(self):
        win = self.props.active_window or Window(self, self.backend)
        win.present()

    def _on_about(self, *_):
        dlg = Adw.AboutDialog(application_name='AK820 Pro Configurator', application_icon=APP_ID, version=__version__,
                              comments='Lighting, screen and clock for the AJAZZ AK820 Pro. '
                                       'The protocol was reverse engineered from the vendor driver.')
        dlg.present(self.props.active_window)


def main(demo=False):
    return App(demo).run([sys.argv[0]])
