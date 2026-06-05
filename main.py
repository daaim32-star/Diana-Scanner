import os, json, math, random, asyncio, threading, logging

os.environ.setdefault('KIVY_WINDOW', 'x11')

from kivy.config import Config
Config.set('input', 'mouse', 'mouse,disable_multitouch')
Config.set('graphics', 'show_cursor', '1')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.uix.progressbar import ProgressBar
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from bleak import BleakScanner, BleakClient, BleakError

logging.basicConfig(level=logging.INFO, format='[DIANA] %(levelname)s: %(message)s')
log = logging.getLogger(__name__)

Window.clearcolor = (0.006, 0.035, 0.047, 1)

VERSION = 'v0.3'

# ── Colour palette ─────────────────────────────────────────────────────────────
C = {
    'cyan':       (0.00, 0.90, 0.95, 1.0),
    'cyan_dim':   (0.00, 0.90, 0.95, 0.40),
    'cyan_bg':    (0.00, 0.90, 0.95, 0.07),
    'green':      (0.18, 0.95, 0.45, 1.0),
    'green_dim':  (0.18, 0.95, 0.45, 0.40),
    'green_bg':   (0.18, 0.95, 0.45, 0.07),
    'red':        (1.00, 0.22, 0.35, 1.0),
    'red_dim':    (1.00, 0.22, 0.35, 0.40),
    'red_bg':     (1.00, 0.22, 0.35, 0.07),
    'yellow':     (1.00, 0.82, 0.00, 1.0),
    'yellow_dim': (1.00, 0.82, 0.00, 0.40),
    'yellow_bg':  (1.00, 0.82, 0.00, 0.07),
    'white':      (0.88, 0.96, 1.00, 1.0),
    'white_dim':  (0.88, 0.96, 1.00, 0.35),
    'white_bg':   (0.88, 0.96, 1.00, 0.04),
    'bg':         (0.006, 0.035, 0.047, 1.0),
    'panel':      (0.012, 0.055, 0.072, 1.0),
}

REGISTRY_PATH = os.path.expanduser('~/diana/registry.json')
DEVICE_TYPES  = ['generic', 'light', 'speaker', 'tv', 'phone', 'computer', 'other']
SCAN_TIMEOUT  = 10.0

TYPE_ICON = {
    'light': '💡', 'speaker': '🔊', 'tv': '📺',
    'phone': '📱', 'computer': '💻', 'other': '🔧', 'generic': '',
}

# ── Persistence ────────────────────────────────────────────────────────────────
def load_registry() -> dict:
    try:
        with open(REGISTRY_PATH) as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError('registry root must be a JSON object')
            return data
    except FileNotFoundError:
        return {}
    except Exception as e:
        log.warning('Could not load registry: %s — starting fresh', e)
        return {}

def save_registry(reg: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
        tmp = REGISTRY_PATH + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(reg, f, indent=2)
        os.replace(tmp, REGISTRY_PATH)
        return True
    except Exception as e:
        log.error('Failed to save registry: %s', e)
        return False

# ── Widget helpers ─────────────────────────────────────────────────────────────
def panel(border_color_key: str, radius=6) -> BoxLayout:
    bk = C[border_color_key]
    layout = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
    with layout.canvas.before:
        Color(*C['panel'])
        layout._bg = RoundedRectangle(pos=layout.pos, size=layout.size, radius=[dp(radius)])
        Color(*bk[:3], 0.30)
        layout._bd = Line(rounded_rectangle=(layout.x, layout.y, layout.width, layout.height,
                                             dp(radius)), width=1)
    def _upd(inst, _):
        inst._bg.pos  = inst.pos;  inst._bg.size = inst.size
        inst._bg.radius = [dp(radius)]
        inst._bd.rounded_rectangle = (inst.x, inst.y, inst.width, inst.height, dp(radius))
    layout.bind(pos=_upd, size=_upd)
    return layout

def lbl(text: str, color_key: str, size=11, bold=False,
        halign='left', height=dp(20)) -> Label:
    l = Label(text=text, font_size=dp(size), color=C[color_key],
              size_hint_y=None, height=height,
              halign=halign, valign='middle', bold=bold)
    l.bind(size=lambda inst, v: setattr(inst, 'text_size', v))
    return l

def section_title(text: str, color_key: str) -> BoxLayout:
    row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(22), spacing=dp(8))
    ck = C[color_key]
    tick = Widget(size_hint_x=None, width=dp(3))
    with tick.canvas:
        Color(*ck[:3], 0.9)
        tick._rect = Rectangle(pos=tick.pos, size=tick.size)
    tick.bind(pos=lambda i, _: setattr(i._rect, 'pos', i.pos),
              size=lambda i, _: setattr(i._rect, 'size', i.size))
    row.add_widget(tick)
    row.add_widget(lbl(text, color_key, size=10, bold=True, height=dp(22)))
    return row

def btn(text: str, color_key: str, cb=None, height=dp(32), radius=5) -> Button:
    ck = C[color_key]
    b = Button(text=text, size_hint_y=None, height=height,
               background_color=(0, 0, 0, 0), color=ck, font_size=dp(10), bold=True)
    with b.canvas.before:
        Color(*ck[:3], 0.10)
        b._bg = RoundedRectangle(pos=b.pos, size=b.size, radius=[dp(radius)])
        Color(*ck[:3], 0.40)
        b._bd = Line(rounded_rectangle=(b.x, b.y, b.width, b.height, dp(radius)), width=0.9)
    def _upd(inst, _):
        inst._bg.pos = inst.pos; inst._bg.size = inst.size
        inst._bg.radius = [dp(radius)]
        inst._bd.rounded_rectangle = (inst.x, inst.y, inst.width, inst.height, dp(radius))
    b.bind(pos=_upd, size=_upd)
    if cb:
        b.bind(on_press=cb)
    return b

def divider(color_key: str) -> Widget:
    w = Widget(size_hint_y=None, height=dp(1))
    with w.canvas:
        Color(*C[color_key][:3], 0.12)
        w._line = Rectangle(pos=w.pos, size=w.size)
    w.bind(pos=lambda inst, _: setattr(inst._line, 'pos', inst.pos),
           size=lambda inst, _: setattr(inst._line, 'size', inst.size))
    return w

def signal_bars(rssi: int) -> str:
    if rssi >= -50: return '▂▄▆█'
    if rssi >= -65: return '▂▄▆░'
    if rssi >= -75: return '▂▄░░'
    return '▂░░░'

def plural(n: int, word: str) -> str:
    return f'{n} {word}{"s" if n != 1 else ""}'

# ── Radar ──────────────────────────────────────────────────────────────────────
class RadarWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.angle    = 0.0
        self.blips    = []
        self._clock   = None
        self.scanning = False
        self.bind(pos=self._draw, size=self._draw)

    def start(self):
        self.scanning = True
        if self._clock:
            self._clock.cancel()
        self._clock = Clock.schedule_interval(self._tick, 1 / 30)

    def stop(self):
        self.scanning = False
        if self._clock:
            self._clock.cancel()
        self._draw()

    def clear_blips(self):
        self.blips.clear()
        self._draw()

    def add_blip(self, rssi: int, color_key='cyan'):
        cx, cy = self.center
        r = min(self.width, self.height) * 0.42
        d = max(0.08, min(0.92, (rssi + 20) / 70.0)) * r
        a = random.uniform(0, 2 * math.pi)
        self.blips.append({
            'x': cx + d * math.cos(a), 'y': cy + d * math.sin(a),
            'color': color_key, 'alpha': 1.0, 'rssi': rssi,
        })

    def _tick(self, dt):
        self.angle = (self.angle + 2) % 360
        for b in self.blips:
            b['alpha'] = max(0.28, b['alpha'] - 0.0006)
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        cx, cy = self.center
        r = min(self.width, self.height) * 0.42
        with self.canvas:
            # Rings
            for i in range(1, 5):
                Color(0, 0.90, 0.95, 0.06)
                Line(circle=(cx, cy, r * i / 4), width=1)
            # Cross hairs
            Color(0, 0.90, 0.95, 0.04)
            Line(points=[cx - r, cy, cx + r, cy], width=1)
            Line(points=[cx, cy - r, cx, cy + r], width=1)
            # Sweep
            if self.scanning:
                for i in range(80):
                    t = math.radians(self.angle - i * 0.85)
                    a = (80 - i) / 80 * 0.22
                    Color(0, 0.90, 0.95, a)
                    Line(points=[cx, cy, cx + r * math.cos(t), cy + r * math.sin(t)], width=1.2)
                Color(0, 0.90, 0.95, 0.90)
                s = math.radians(self.angle)
                Line(points=[cx, cy, cx + r * math.cos(s), cy + r * math.sin(s)], width=1.6)
            # Blips
            for b in self.blips:
                ck = C.get(b['color'], C['cyan'])
                Color(*ck[:3], b['alpha'])
                Ellipse(pos=(b['x'] - dp(4), b['y'] - dp(4)), size=(dp(8), dp(8)))
                Color(*ck[:3], b['alpha'] * 0.15)
                Ellipse(pos=(b['x'] - dp(10), b['y'] - dp(10)), size=(dp(20), dp(20)))
            # Centre dot
            Color(0, 0.90, 0.95, 1)
            Ellipse(pos=(cx - dp(3), cy - dp(3)), size=(dp(6), dp(6)))

# ── Device list item ───────────────────────────────────────────────────────────
class DeviceItem(BoxLayout):
    def __init__(self, display_name: str, address: str, rssi: int,
                 dtype: str, on_select, **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None,
                         height=dp(56), padding=(dp(10), dp(5)), spacing=dp(2), **kwargs)
        self.address      = address
        self.rssi         = rssi
        self.dtype        = dtype
        self.display_name = display_name
        self.on_select    = on_select
        self.connected    = False

        self._draw_bg(False)
        self.bind(pos=self._refresh_bg, size=self._refresh_bg)

        icon = TYPE_ICON.get(dtype, '')
        self._name_lbl = Label(
            text=f'{icon} {display_name}'.strip() if icon else display_name,
            font_size=dp(11), color=C['white'], bold=True,
            size_hint_y=None, height=dp(20),
            halign='left', valign='middle',
        )
        self._name_lbl.bind(size=lambda inst, v: setattr(inst, 'text_size', v))
        self.add_widget(self._name_lbl)

        self._sub_lbl = Label(
            text=f'{address}   {signal_bars(rssi)}  {rssi} dBm',
            font_size=dp(8.5), color=C['cyan_dim'],
            size_hint_y=None, height=dp(15),
            halign='left', valign='middle',
        )
        self._sub_lbl.bind(size=lambda inst, v: setattr(inst, 'text_size', v))
        self.add_widget(self._sub_lbl)

        self.bind(on_touch_down=self._on_touch)

    def update_name(self, name: str):
        self.display_name = name
        icon = TYPE_ICON.get(self.dtype, '')
        self._name_lbl.text = f'{icon} {name}'.strip() if icon else name

    def _update_sub(self):
        conn = '  ● CONNECTED' if self.connected else ''
        self._sub_lbl.text  = f'{self.address}   {signal_bars(self.rssi)}  {self.rssi} dBm{conn}'
        self._sub_lbl.color = C['green_dim'] if self.connected else C['cyan_dim']

    def set_connected(self, val: bool):
        self.connected = val
        self._update_sub()
        self._draw_bg(App.get_running_app().sel_item is self)
        self.bind(pos=self._refresh_bg, size=self._refresh_bg)

    def _draw_bg(self, selected: bool):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.connected:
                Color(*C['green_bg'])
                self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(5)])
                Color(*C['green'][:3], 0.45)
                self._bd = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(5)), width=1)
            elif selected:
                Color(*C['cyan_bg'])
                self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(5)])
                Color(*C['cyan'][:3], 0.50)
                self._bd = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(5)), width=1)
            else:
                Color(*C['white_bg'])
                self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(5)])
                Color(*C['white'][:3], 0.08)
                self._bd = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(5)), width=0.7)

    def _refresh_bg(self, *_):
        self._bg.pos = self.pos; self._bg.size = self.size
        self._bg.radius = [dp(5)]
        self._bd.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(5))

    def _on_touch(self, inst, touch):
        if touch.button == 'left' and self.collide_point(*touch.pos):
            self.on_select(self)
            return True

    def set_selected(self, val: bool):
        self._draw_bg(val)
        self.bind(pos=self._refresh_bg, size=self._refresh_bg)

# ── Main app ───────────────────────────────────────────────────────────────────
class DianaApp(App):
    def build(self):
        self.registry     = load_registry()
        self.live_devices = {}
        self.connections  = {}
        self.selected     = None
        self.sel_item     = None
        self._ble_loop    = None
        self._ble_thread  = None
        self._scan_start  = 0
        self._start_ble_thread()

        root = BoxLayout(orientation='vertical', spacing=0, padding=0)

        # ── Header bar ─────────────────────────────────────────
        hdr = BoxLayout(size_hint_y=None, height=dp(44),
                        padding=(dp(16), 0), spacing=dp(12))
        with hdr.canvas.before:
            Color(0.010, 0.048, 0.062, 1)
            hdr._bg = Rectangle(pos=hdr.pos, size=hdr.size)
            Color(*C['cyan'][:3], 0.12)
            hdr._bd = Rectangle(pos=(hdr.x, hdr.y), size=(hdr.width, dp(1)))
        def _hdr_upd(inst, _):
            inst._bg.pos = inst.pos; inst._bg.size = inst.size
            inst._bd.pos = (inst.x, inst.y); inst._bd.size = (inst.width, dp(1))
        hdr.bind(pos=_hdr_upd, size=_hdr_upd)

        hdr.add_widget(Label(
            text='DIANA', font_size=dp(16), color=C['cyan'], bold=True,
            size_hint_x=None, width=dp(70), halign='left',
            text_size=(dp(70), None),
        ))
        hdr.add_widget(Label(
            text='Device Interface & Network Analyser',
            font_size=dp(9), color=C['white_dim'],
            halign='left', text_size=(dp(300), None),
        ))
        self.status_lbl = Label(
            text='READY',
            font_size=dp(9), color=C['cyan_dim'],
            halign='right', text_size=(dp(300), None),
        )
        hdr.add_widget(self.status_lbl)
        hdr.add_widget(Label(
            text=VERSION, font_size=dp(8), color=C['white_dim'],
            size_hint_x=None, width=dp(30),
            halign='right', text_size=(dp(30), None),
        ))
        root.add_widget(hdr)

        # ── Body ───────────────────────────────────────────────
        body = BoxLayout(orientation='horizontal', spacing=dp(8),
                         padding=(dp(8), dp(8), dp(8), dp(0)))

        # LEFT: device list
        left = panel('white')
        left.size_hint_x = 0.23
        left.add_widget(section_title('DISCOVERED DEVICES', 'white'))
        self.count_lbl = lbl('No devices yet', 'white_dim', size=9)
        left.add_widget(self.count_lbl)
        left.add_widget(divider('white'))

        scroll = ScrollView(bar_width=dp(2), bar_color=C['cyan_dim'],
                            bar_inactive_color=C['white_bg'])
        self.dev_list = GridLayout(cols=1, spacing=dp(3), size_hint_y=None,
                                   padding=(0, dp(2)))
        self.dev_list.bind(minimum_height=self.dev_list.setter('height'))
        scroll.add_widget(self.dev_list)
        left.add_widget(scroll)
        body.add_widget(left)

        # MIDDLE
        mid = BoxLayout(orientation='vertical', spacing=dp(8), size_hint_x=0.54)

        # Radar panel
        radar_panel = panel('green')
        radar_panel.size_hint_y = 0.63
        radar_panel.add_widget(section_title('SIGNAL RADAR', 'green'))
        self.radar = RadarWidget(size_hint_y=1)
        radar_panel.add_widget(self.radar)

        # Scan button + progress row
        scan_row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        self.scan_btn = btn('INITIATE SCAN', 'green', self._start_scan)
        scan_row.add_widget(self.scan_btn)
        radar_panel.add_widget(scan_row)

        self.progress = ProgressBar(max=100, value=0,
                                    size_hint_y=None, height=dp(3))
        with self.progress.canvas.before:
            Color(*C['green'][:3], 0.15)
            self.progress._bg = Rectangle(pos=self.progress.pos, size=self.progress.size)
        def _pb_upd(inst, _):
            inst._bg.pos = inst.pos; inst._bg.size = inst.size
        self.progress.bind(pos=_pb_upd, size=_pb_upd)
        radar_panel.add_widget(self.progress)
        mid.add_widget(radar_panel)

        # Controls panel
        ctrl_panel = panel('cyan')
        ctrl_panel.size_hint_y = 0.37
        ctrl_panel.add_widget(section_title('DEVICE CONTROLS', 'cyan'))
        ctrl_panel.add_widget(divider('cyan'))
        self.ctrl_box = BoxLayout(orientation='vertical', spacing=dp(5))
        self.ctrl_box.add_widget(
            lbl('Select a device to see controls', 'white_dim', size=9))
        ctrl_panel.add_widget(self.ctrl_box)
        mid.add_widget(ctrl_panel)
        body.add_widget(mid)

        # RIGHT: options
        right = panel('cyan')
        right.size_hint_x = 0.23
        right.add_widget(section_title('DEVICE OPTIONS', 'cyan'))
        right.add_widget(divider('cyan'))
        self.opts_box = BoxLayout(orientation='vertical', spacing=dp(5))
        self.opts_box.add_widget(lbl('Select a device', 'white_dim', size=9))
        right.add_widget(self.opts_box)
        body.add_widget(right)

        root.add_widget(body)

        # ── Status bar ─────────────────────────────────────────
        bar = BoxLayout(size_hint_y=None, height=dp(22),
                        padding=(dp(12), 0), spacing=dp(16))
        with bar.canvas.before:
            Color(0.008, 0.040, 0.052, 1)
            bar._bg = Rectangle(pos=bar.pos, size=bar.size)
            Color(*C['cyan'][:3], 0.08)
            bar._top = Rectangle(pos=(bar.x, bar.top - dp(1)), size=(bar.width, dp(1)))
        def _bar_upd(inst, _):
            inst._bg.pos = inst.pos; inst._bg.size = inst.size
            inst._top.pos = (inst.x, inst.top - dp(1)); inst._top.size = (inst.width, dp(1))
        bar.bind(pos=_bar_upd, size=_bar_upd)

        self.bar_lbl = Label(text='● IDLE', font_size=dp(8), color=C['cyan_dim'],
                             halign='left', text_size=(dp(400), None))
        bar.add_widget(self.bar_lbl)
        bar.add_widget(Label(text=f'DIANA {VERSION}  //  Bluetooth LE Scanner',
                             font_size=dp(8), color=C['white_dim'],
                             halign='right', text_size=(dp(400), None)))
        root.add_widget(bar)

        Clock.schedule_once(self._load_saved_into_list, 0.3)
        return root

    def on_start(self):
        Window.show_cursor = True
        Clock.schedule_once(lambda dt: setattr(Window, 'show_cursor', True), 0.5)

    def on_stop(self):
        for client in list(self.connections.values()):
            if self._ble_loop and self._ble_loop.is_running():
                asyncio.run_coroutine_threadsafe(self._force_disconnect(client), self._ble_loop)
        if self._ble_loop:
            self._ble_loop.call_soon_threadsafe(self._ble_loop.stop)

    # ── BLE event loop thread ──────────────────────────────────
    def _start_ble_thread(self):
        def run_loop():
            self._ble_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._ble_loop)
            self._ble_loop.run_forever()
        self._ble_thread = threading.Thread(target=run_loop, daemon=True)
        self._ble_thread.start()

    def _run_ble(self, coro):
        if self._ble_loop and self._ble_loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, self._ble_loop)
        log.error('BLE event loop not running')

    # ── Startup: populate saved devices ───────────────────────
    def _load_saved_into_list(self, *_):
        for addr, info in self.registry.items():
            name  = info.get('name') or 'Unknown'
            dtype = info.get('type', 'generic')
            rssi  = info.get('last_rssi', -70)
            item  = DeviceItem(name, addr, rssi, dtype, self._select_device)
            self.dev_list.add_widget(item)
            self.radar.add_blip(rssi, 'green')
        n = len(self.registry)
        if n:
            self.count_lbl.text = f'{plural(n, "saved device")} loaded'
            self._set_status(f'{n} saved — tap scan for full sweep', 'IDLE')

    # ── Scan ───────────────────────────────────────────────────
    def _start_scan(self, *_):
        self.scan_btn.text     = 'SCANNING...'
        self.scan_btn.disabled = True
        self.dev_list.clear_widgets()
        self.live_devices      = {}
        self.radar.clear_blips()
        self.radar.start()
        self.progress.value    = 0
        self._scan_start       = 0
        self._set_status('Scanning for Bluetooth LE devices…', 'SCANNING')
        self.count_lbl.text    = 'Scanning...'
        self._progress_clock   = Clock.schedule_interval(self._tick_progress, 0.1)
        self._run_ble(self._do_scan())

    def _tick_progress(self, dt):
        self._scan_start += dt
        self.progress.value = min(100, (self._scan_start / SCAN_TIMEOUT) * 100)

    async def _do_scan(self):
        try:
            def cb(device, adv):
                if device.address not in self.live_devices:
                    rssi = adv.rssi if adv.rssi is not None else -99
                    self.live_devices[device.address] = {'name': device.name, 'rssi': rssi}
                    Clock.schedule_once(
                        lambda dt, d=device, r=rssi: self._add_device(d.name, d.address, r))
            async with BleakScanner(cb):
                await asyncio.sleep(SCAN_TIMEOUT)
        except BleakError as e:
            err = str(e)
            log.error('Scan failed: %s', err)
            Clock.schedule_once(lambda dt: self._set_status(f'Scan error: {err}', 'ERROR'))
        finally:
            Clock.schedule_once(lambda dt: self._scan_done())

    def _scan_done(self):
        if hasattr(self, '_progress_clock'):
            self._progress_clock.cancel()
        self.progress.value    = 100
        self.radar.stop()
        self.scan_btn.text     = 'RESCAN'
        self.scan_btn.disabled = False
        n = len(self.live_devices)
        self.count_lbl.text    = f'{plural(n, "device")}  ·  sorted by signal'
        self._set_status(f'Scan complete — {plural(n, "device")} found', 'IDLE')
        self._sort_list()
        Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 0), 1.5)

    def _add_device(self, name: str, address: str, rssi: int):
        saved   = self.registry.get(address, {})
        display = saved.get('name') or name or 'Unknown'
        dtype   = saved.get('type', 'generic')
        color   = 'green' if address in self.registry else 'cyan'
        item    = DeviceItem(display, address, rssi, dtype, self._select_device)
        if address in self.connections:
            item.set_connected(True)
        self.dev_list.add_widget(item)
        self.radar.add_blip(rssi, color)
        self.count_lbl.text = plural(len(self.live_devices), 'device')

    def _sort_list(self):
        items = sorted(self.dev_list.children[:], key=lambda i: i.rssi, reverse=True)
        self.dev_list.clear_widgets()
        for item in items:
            self.dev_list.add_widget(item)

    # ── Selection ──────────────────────────────────────────────
    def _select_device(self, item: DeviceItem):
        if self.sel_item:
            self.sel_item.set_selected(False)
        item.set_selected(True)
        self.sel_item = item
        self.selected = {
            'name':    item.display_name,
            'address': item.address,
            'rssi':    item.rssi,
            'type':    item.dtype,
        }
        self._refresh_opts()
        self._refresh_ctrl()

    # ── Options panel ───────────────────────────────────────────
    def _refresh_opts(self):
        self.opts_box.clear_widgets()
        d = self.selected
        if not d:
            self.opts_box.add_widget(lbl('Select a device', 'white_dim', size=9))
            return

        addr     = d['address']
        saved    = self.registry.get(addr, {})
        name     = saved.get('name') or d['name'] or 'Unknown'
        dtype    = saved.get('type', 'generic')
        is_saved = addr in self.registry
        is_conn  = addr in self.connections

        self.opts_box.add_widget(lbl(name, 'white', size=12, bold=True, height=dp(22)))
        self.opts_box.add_widget(lbl(addr, 'white_dim', size=8))
        self.opts_box.add_widget(lbl(
            f"{dtype.upper()}   {signal_bars(d['rssi'])}  {d['rssi']} dBm",
            'cyan_dim', size=8, height=dp(16)))
        self.opts_box.add_widget(divider('cyan'))

        if is_conn:
            conn_row = BoxLayout(size_hint_y=None, height=dp(18), spacing=dp(6))
            dot = Label(text='●', font_size=dp(9), color=C['green'],
                        size_hint_x=None, width=dp(14))
            conn_row.add_widget(dot)
            conn_row.add_widget(lbl('CONNECTED', 'green', size=9, bold=True, height=dp(18)))
            self.opts_box.add_widget(conn_row)
            self.opts_box.add_widget(btn('DISCONNECT', 'red', self._do_disconnect))
        else:
            self.opts_box.add_widget(btn('CONNECT', 'green', self._do_connect))

        self.opts_box.add_widget(divider('cyan'))
        save_label = 'UPDATE INFO' if is_saved else 'SAVE DEVICE'
        self.opts_box.add_widget(btn(save_label,  'cyan',   self._open_save_popup))
        self.opts_box.add_widget(btn('RENAME',    'yellow', self._open_rename_popup))
        if is_saved:
            self.opts_box.add_widget(btn('REMOVE', 'red_dim', self._remove_device))

    # ── Controls panel ──────────────────────────────────────────
    def _refresh_ctrl(self):
        self.ctrl_box.clear_widgets()
        d = self.selected
        if not d:
            self.ctrl_box.add_widget(
                lbl('Select a device to see controls', 'white_dim', size=9))
            return

        addr  = d['address']
        saved = self.registry.get(addr, {})
        dtype = saved.get('type', d.get('type', 'generic'))
        name  = saved.get('name') or d['name'] or 'Unknown'

        self.ctrl_box.add_widget(lbl(name, 'yellow', size=10, bold=True))

        if dtype == 'light':
            row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
            row.add_widget(btn('ON',     'green',      lambda x: self._light_cmd('on')))
            row.add_widget(btn('OFF',    'red',        lambda x: self._light_cmd('off')))
            row.add_widget(btn('DIM',    'yellow_dim', lambda x: self._light_cmd('dim')))
            row.add_widget(btn('BRIGHT', 'yellow',     lambda x: self._light_cmd('bright')))
            self.ctrl_box.add_widget(row)
            self.ctrl_box.add_widget(
                btn('DISCOVER SERVICES', 'cyan_dim', lambda x: self._discover_services(addr)))
            self.ctrl_box.add_widget(lbl('Connect first to send commands', 'white_dim', size=8))

        elif dtype == 'speaker':
            row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
            row.add_widget(btn('CONNECT',    'green', self._do_connect))
            row.add_widget(btn('DISCONNECT', 'red',   self._do_disconnect))
            self.ctrl_box.add_widget(row)
            self.ctrl_box.add_widget(lbl('Audio controls coming soon', 'white_dim', size=8))

        elif dtype == 'tv':
            row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
            row.add_widget(btn('POWER ON',  'green', lambda x: self._set_status('TV: Power On', 'CMD')))
            row.add_widget(btn('POWER OFF', 'red',   lambda x: self._set_status('TV: Power Off', 'CMD')))
            self.ctrl_box.add_widget(row)
            self.ctrl_box.add_widget(lbl('IR blaster required for full TV control', 'white_dim', size=8))

        else:
            row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
            row.add_widget(btn('CONNECT',    'green', self._do_connect))
            row.add_widget(btn('DISCONNECT', 'red',   self._do_disconnect))
            self.ctrl_box.add_widget(row)
            self.ctrl_box.add_widget(
                lbl('Tag a device type to unlock specific controls', 'white_dim', size=8))

    # ── BLE connect / disconnect ────────────────────────────────
    def _do_connect(self, *_):
        if not self.selected:
            return
        addr = self.selected['address']
        if addr in self.connections:
            self._set_status('Already connected', 'INFO')
            return
        name = self.selected.get('name') or addr
        self._set_status(f'Connecting to {name}…', 'CONNECTING')
        self.scan_btn.disabled = True
        self._run_ble(self._connect_device(addr, name))

    async def _connect_device(self, addr: str, name: str):
        try:
            client = BleakClient(
                addr,
                disconnected_callback=lambda c: Clock.schedule_once(
                    lambda dt: self._on_disconnected(c.address)),
            )
            await client.connect(timeout=10.0)
            self.connections[addr] = client
            Clock.schedule_once(lambda dt: self._on_connected(addr, name))
        except BleakError as e:
            err = str(e)
            Clock.schedule_once(lambda dt: self._on_connect_failed(addr, name, err))
        except asyncio.TimeoutError:
            Clock.schedule_once(lambda dt: self._on_connect_failed(addr, name, 'timeout'))

    def _on_connected(self, addr: str, name: str):
        self.scan_btn.disabled = False
        self._set_status(f'Connected: {name}', 'CONNECTED')
        self._update_item_connection(addr, True)
        if self.selected and self.selected['address'] == addr:
            self._refresh_opts()
            self._refresh_ctrl()

    def _on_connect_failed(self, addr: str, name: str, reason: str):
        self.scan_btn.disabled = False
        self._set_status(f'Connection failed: {name} — {reason}', 'ERROR')
        log.warning('Connection failed for %s: %s', addr, reason)

    def _do_disconnect(self, *_):
        if not self.selected:
            return
        addr   = self.selected['address']
        client = self.connections.get(addr)
        if not client:
            self._set_status('Not connected', 'INFO')
            return
        name = self.selected.get('name') or addr
        self._set_status(f'Disconnecting: {name}…', 'INFO')
        self._run_ble(self._disconnect_device(addr, name, client))

    async def _disconnect_device(self, addr: str, name: str, client: BleakClient):
        try:
            await client.disconnect()
        except BleakError as e:
            log.warning('Disconnect error for %s: %s', addr, e)
        finally:
            Clock.schedule_once(lambda dt: self._on_disconnected(addr, name))

    async def _force_disconnect(self, client: BleakClient):
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:
            pass

    def _on_disconnected(self, addr: str, name: str = ''):
        self.connections.pop(addr, None)
        label = name or self.registry.get(addr, {}).get('name') or addr
        self._set_status(f'Disconnected: {label}', 'IDLE')
        self._update_item_connection(addr, False)
        if self.selected and self.selected['address'] == addr:
            self._refresh_opts()
            self._refresh_ctrl()

    def _update_item_connection(self, addr: str, connected: bool):
        for item in self.dev_list.children:
            if item.address == addr:
                item.set_connected(connected)
                break

    # ── Service discovery ──────────────────────────────────────
    def _discover_services(self, addr: str):
        client = self.connections.get(addr)
        if not client:
            self._set_status('Not connected — connect first', 'ERROR')
            return
        self._run_ble(self._print_services(client))

    async def _print_services(self, client: BleakClient):
        lines = []
        for svc in client.services:
            lines.append(f'SVC: {svc.uuid}')
            for char in svc.characteristics:
                props = ','.join(char.properties)
                lines.append(f'  CHAR: {char.uuid}  [{props}]')
        output = '\n'.join(lines) if lines else 'No services found'
        log.info('=== GATT Services ===\n%s', output)
        Clock.schedule_once(lambda dt: self._show_services_popup(output))

    def _show_services_popup(self, text: str):
        wrap = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(12))
        wrap.add_widget(lbl('Copy these UUIDs to identify your device protocol.',
                            'cyan_dim', size=9))
        scroll = ScrollView()
        content = Label(
            text=text, font_size=dp(8), color=C['white'],
            size_hint_y=None, halign='left', valign='top',
            text_size=(dp(500), None),
        )
        content.bind(texture_size=lambda i, v: setattr(i, 'height', v[1]))
        scroll.add_widget(content)
        wrap.add_widget(scroll)
        p = self._popup('DISCOVERED SERVICES', wrap, size=(0.7, 0.7))
        wrap.add_widget(btn('CLOSE', 'red', lambda x: p.dismiss()))
        p.open()

    # ── Light commands ─────────────────────────────────────────
    def _light_cmd(self, cmd: str):
        if not self.selected:
            return
        addr   = self.selected['address']
        client = self.connections.get(addr)
        name   = self.selected.get('name', 'Light')
        if not client:
            self._set_status(f'Connect to {name} first', 'ERROR')
            return
        labels = {'on': 'On ◉', 'off': 'Off ○', 'dim': 'Dim ▽', 'bright': 'Bright △'}
        self._set_status(f'{name}: {labels.get(cmd, cmd)}', 'CMD')
        self._run_ble(self._write_light(client, cmd, name))

    async def _write_light(self, client: BleakClient, cmd: str, name: str):
        payload_map = {'on': b'\x01', 'off': b'\x00', 'dim': b'\x10', 'bright': b'\xff'}
        payload = payload_map.get(cmd, b'\x00')
        try:
            for svc in client.services:
                for char in svc.characteristics:
                    if 'write' in char.properties or 'write-without-response' in char.properties:
                        await client.write_gatt_char(char.uuid, payload, response=False)
                        Clock.schedule_once(
                            lambda dt, c=cmd: self._set_status(f'{name}: {c} sent', 'CMD'))
                        return
            Clock.schedule_once(
                lambda dt: self._set_status('No writable characteristic found', 'ERROR'))
        except BleakError as e:
            err = str(e)
            log.error('Light write failed: %s', err)
            Clock.schedule_once(lambda dt: self._set_status(f'Write error: {err}', 'ERROR'))

    # ── Popups ──────────────────────────────────────────────────
    def _popup(self, title: str, content, size=(0.42, 0.38)) -> Popup:
        return Popup(title=title, title_color=C['cyan'], content=content,
                     size_hint=size, background_color=(0.010, 0.048, 0.062, 1),
                     separator_color=C['cyan_dim'], title_size=dp(13))

    def _open_rename_popup(self, *_):
        if not self.selected:
            return
        wrap = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(16))
        wrap.add_widget(lbl('New name:', 'cyan_dim', size=10))
        txt = TextInput(
            text=self.selected.get('name', ''),
            font_size=dp(13), multiline=False,
            size_hint_y=None, height=dp(40),
            background_color=(0.015, 0.065, 0.085, 1),
            foreground_color=C['white'], cursor_color=C['cyan'],
            padding=(dp(8), dp(10)),
        )
        wrap.add_widget(txt)
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        p = self._popup('RENAME DEVICE', wrap)

        def confirm(*_):
            new = txt.text.strip()
            if not new:
                return
            addr = self.selected['address']
            self.registry.setdefault(addr, {})['name'] = new
            if not save_registry(self.registry):
                self._set_status('Error: could not save registry', 'ERROR')
                return
            self.selected['name'] = new
            if self.sel_item:
                self.sel_item.update_name(new)
            self._set_status(f'Renamed → {new}', 'INFO')
            self._refresh_opts(); self._refresh_ctrl()
            p.dismiss()

        row.add_widget(btn('CONFIRM', 'green', confirm))
        row.add_widget(btn('CANCEL',  'red',   lambda x: p.dismiss()))
        wrap.add_widget(row)
        p.open()

    def _open_save_popup(self, *_):
        if not self.selected:
            return
        addr  = self.selected['address']
        saved = self.registry.get(addr, {})
        wrap  = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(16))
        wrap.add_widget(lbl('Device name:', 'cyan_dim', size=10))
        name_in = TextInput(
            text=saved.get('name') or self.selected.get('name', ''),
            font_size=dp(13), multiline=False,
            size_hint_y=None, height=dp(40),
            background_color=(0.015, 0.065, 0.085, 1),
            foreground_color=C['white'], cursor_color=C['cyan'],
            padding=(dp(8), dp(10)),
        )
        wrap.add_widget(name_in)
        wrap.add_widget(lbl('Device type:', 'cyan_dim', size=10))
        type_spin = Spinner(
            text=saved.get('type', 'generic'),
            values=DEVICE_TYPES,
            size_hint_y=None, height=dp(36),
            background_color=(0.015, 0.065, 0.085, 1),
            color=C['white'], font_size=dp(11),
        )
        wrap.add_widget(type_spin)
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        p = self._popup('SAVE DEVICE', wrap, size=(0.42, 0.48))

        def confirm(*_):
            name  = name_in.text.strip() or 'Unknown'
            dtype = type_spin.text
            self.registry[addr] = {
                'name': name, 'type': dtype,
                'last_rssi': self.selected.get('rssi', -70),
            }
            if not save_registry(self.registry):
                self._set_status('Error: could not save registry', 'ERROR')
                return
            self.selected['name'] = name
            self.selected['type'] = dtype
            if self.sel_item:
                self.sel_item.update_name(name)
                self.sel_item.dtype = dtype
            self._set_status(f'Saved: {name}  [{dtype}]', 'INFO')
            self._refresh_opts(); self._refresh_ctrl()
            p.dismiss()

        row.add_widget(btn('SAVE',   'cyan', confirm))
        row.add_widget(btn('CANCEL', 'red',  lambda x: p.dismiss()))
        wrap.add_widget(row)
        p.open()

    def _remove_device(self, *_):
        if not self.selected:
            return
        addr = self.selected['address']
        name = self.registry.get(addr, {}).get('name', addr)
        self.registry.pop(addr, None)
        if not save_registry(self.registry):
            self._set_status('Error: could not save registry', 'ERROR')
            return
        self._set_status(f'Removed: {name}', 'INFO')
        self._refresh_opts(); self._refresh_ctrl()

    # ── Status helpers ─────────────────────────────────────────
    def _set_status(self, text: str, state: str = 'IDLE'):
        colors = {
            'IDLE':       C['cyan_dim'],
            'SCANNING':   C['green'],
            'CONNECTED':  C['green'],
            'CONNECTING': C['yellow'],
            'CMD':        C['yellow'],
            'INFO':       C['white_dim'],
            'ERROR':      C['red'],
        }
        self.status_lbl.text  = text
        self.status_lbl.color = colors.get(state, C['cyan_dim'])
        dot_colors = {
            'SCANNING': '▶', 'CONNECTED': '●', 'CONNECTING': '◌',
            'ERROR': '✕', 'CMD': '▷',
        }
        dot = dot_colors.get(state, '●')
        self.bar_lbl.text  = f'{dot} {text}'
        self.bar_lbl.color = colors.get(state, C['cyan_dim'])


if __name__ == '__main__':
    DianaApp().run()
