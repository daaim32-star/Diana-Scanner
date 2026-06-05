import os, json, math, random, asyncio, threading
os.environ['KIVY_MOUSE'] = 'mouse,disable_multitouch'

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
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from bleak import BleakScanner

Window.clearcolor = (0.008, 0.047, 0.063, 1)
Window.show_cursor = True

# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    'cyan':       (0.00, 0.96, 1.00, 1.0),
    'cyan_dim':   (0.00, 0.96, 1.00, 0.35),
    'cyan_bg':    (0.00, 0.96, 1.00, 0.06),
    'green':      (0.20, 1.00, 0.40, 1.0),
    'green_dim':  (0.20, 1.00, 0.40, 0.35),
    'green_bg':   (0.20, 1.00, 0.40, 0.06),
    'red':        (1.00, 0.24, 0.36, 1.0),
    'red_dim':    (1.00, 0.24, 0.36, 0.35),
    'red_bg':     (1.00, 0.24, 0.36, 0.06),
    'yellow':     (1.00, 0.85, 0.00, 1.0),
    'yellow_dim': (1.00, 0.85, 0.00, 0.35),
    'yellow_bg':  (1.00, 0.85, 0.00, 0.06),
    'white':      (0.88, 0.97, 1.00, 1.0),
    'white_dim':  (0.88, 0.97, 1.00, 0.35),
    'white_bg':   (0.88, 0.97, 1.00, 0.05),
}

REGISTRY_PATH = os.path.expanduser('~/diana/registry.json')
DEVICE_TYPES  = ['generic', 'light', 'speaker', 'tv', 'phone', 'computer', 'other']

# ── Persistence ───────────────────────────────────────────────────────────────
def load_registry():
    try:
        with open(REGISTRY_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def save_registry(reg):
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(reg, f, indent=2)

# ── Widget helpers ─────────────────────────────────────────────────────────────
def panel(border_color_key):
    bk = C[border_color_key]
    layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(6))
    with layout.canvas.before:
        Color(*bk[:3], 0.07)
        layout._bg = Rectangle(pos=layout.pos, size=layout.size)
        Color(*bk[:3], 0.22)
        layout._bd = Line(rectangle=(layout.x, layout.y, layout.width, layout.height), width=1)
    def _upd(i, _):
        i._bg.pos = i.pos; i._bg.size = i.size
        i._bd.rectangle = (i.x, i.y, i.width, i.height)
    layout.bind(pos=_upd, size=_upd)
    return layout

def lbl(text, color_key, size=11, bold=False, halign='left', height=dp(20)):
    l = Label(text=text, font_size=dp(size), color=C[color_key],
              size_hint_y=None, height=height,
              halign=halign, valign='middle', bold=bold)
    l.bind(size=lambda i, v: setattr(i, 'text_size', v))
    return l

def btn(text, color_key, cb=None, height=dp(34)):
    ck = C[color_key]
    b = Button(text=text, size_hint_y=None, height=height,
               background_color=(0,0,0,0), color=ck, font_size=dp(11))
    with b.canvas.before:
        Color(*ck[:3], 0.10); b._bg = Rectangle(pos=b.pos, size=b.size)
        Color(*ck[:3], 0.35); b._bd = Line(rectangle=(b.x, b.y, b.width, b.height), width=0.8)
    def _upd(i, _):
        i._bg.pos = i.pos; i._bg.size = i.size
        i._bd.rectangle = (i.x, i.y, i.width, i.height)
    b.bind(pos=_upd, size=_upd)
    if cb: b.bind(on_press=cb)
    return b

def divider(color_key):
    w = Widget(size_hint_y=None, height=dp(1))
    with w.canvas:
        Color(*C[color_key][:3], 0.18)
        w._line = Rectangle(pos=w.pos, size=w.size)
    w.bind(pos=lambda i, _: setattr(i._line, 'pos', i.pos),
           size=lambda i, _: setattr(i._line, 'size', i.size))
    return w

# ── Radar ─────────────────────────────────────────────────────────────────────
class RadarWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.angle   = 0.0
        self.blips   = []
        self._clock  = None
        self.scanning= False
        self.bind(pos=self._draw, size=self._draw)

    def start(self):
        self.scanning = True
        if self._clock: self._clock.cancel()
        self._clock = Clock.schedule_interval(self._tick, 1/30)

    def stop(self):
        self.scanning = False
        if self._clock: self._clock.cancel()
        self._draw()

    def clear_blips(self):
        self.blips.clear()
        self._draw()

    def add_blip(self, rssi, color_key='cyan'):
        cx, cy = self.center
        r  = min(self.width, self.height) * 0.42
        d  = max(0.05, min(0.95, (rssi + 20) / 70.0)) * r
        a  = random.uniform(0, 2 * math.pi)
        self.blips.append({'x': cx + d*math.cos(a), 'y': cy + d*math.sin(a),
                           'color': color_key, 'alpha': 1.0, 'rssi': rssi})

    def _tick(self, dt):
        self.angle = (self.angle + 2) % 360
        for b in self.blips:
            b['alpha'] = max(0.3, b['alpha'] - 0.0008)
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        cx, cy = self.center
        r = min(self.width, self.height) * 0.42
        with self.canvas:
            for i in range(1, 5):
                Color(0, 0.96, 1, 0.07)
                Line(circle=(cx, cy, r * i / 4), width=1)
            Color(0, 0.96, 1, 0.05)
            Line(points=[cx-r, cy, cx+r, cy], width=1)
            Line(points=[cx, cy-r, cx, cy+r], width=1)
            if self.scanning:
                for i in range(72):
                    t = math.radians(self.angle - i * 0.9)
                    a = (72-i)/72 * 0.28
                    Color(0, 0.96, 1, a)
                    Line(points=[cx, cy, cx+r*math.cos(t), cy+r*math.sin(t)], width=1.2)
                Color(0, 0.96, 1, 0.95)
                s = math.radians(self.angle)
                Line(points=[cx, cy, cx+r*math.cos(s), cy+r*math.sin(s)], width=1.8)
            for b in self.blips:
                ck = C.get(b['color'], C['cyan'])
                Color(*ck[:3], b['alpha'])
                Ellipse(pos=(b['x']-dp(5), b['y']-dp(5)), size=(dp(10), dp(10)))
                Color(*ck[:3], b['alpha']*0.2)
                Ellipse(pos=(b['x']-dp(11), b['y']-dp(11)), size=(dp(22), dp(22)))
            Color(0, 0.96, 1, 1)
            Ellipse(pos=(cx-dp(4), cy-dp(4)), size=(dp(8), dp(8)))

# ── Device list item ──────────────────────────────────────────────────────────
class DeviceItem(BoxLayout):
    def __init__(self, display_name, address, rssi, dtype, on_select, **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None,
                         height=dp(60), padding=(dp(10), dp(6)), spacing=dp(2), **kwargs)
        self.address      = address
        self.rssi         = rssi
        self.dtype        = dtype
        self.display_name = display_name
        self.on_select    = on_select
        self._sel         = False
        self._draw_bg(False)
        self.bind(pos=self._refresh_bg, size=self._refresh_bg)

        type_icon = {'light':'💡','speaker':'🔊','tv':'📺','phone':'📱',
                     'computer':'💻','generic':'','other':'🔧'}.get(dtype, '')
        name_text = f'{type_icon} {display_name}'.strip()

        nl = Label(text=name_text, font_size=dp(12), color=C['white'],
                   size_hint_y=None, height=dp(22), halign='left', valign='middle')
        nl.bind(size=lambda i,v: setattr(i,'text_size',v))
        self.add_widget(nl)

        bars = self._signal_bars(rssi)
        sub  = f'{address}   {bars}  {rssi} dBm'
        sl = Label(text=sub, font_size=dp(9), color=C['cyan_dim'],
                   size_hint_y=None, height=dp(16), halign='left', valign='middle')
        sl.bind(size=lambda i,v: setattr(i,'text_size',v))
        self.add_widget(sl)
        self.bind(on_touch_down=self._on_touch)

    def _signal_bars(self, rssi):
        if rssi >= -50: return '▂▄▆█'
        if rssi >= -65: return '▂▄▆░'
        if rssi >= -75: return '▂▄░░'
        return '▂░░░'

    def _draw_bg(self, selected):
        self.canvas.before.clear()
        with self.canvas.before:
            if selected:
                Color(*C['cyan_bg']); self._bg = Rectangle(pos=self.pos, size=self.size)
                Color(*C['cyan'][:3], 0.45); self._bd = Line(rectangle=(self.x,self.y,self.width,self.height), width=1.2)
            else:
                Color(*C['white_bg']); self._bg = Rectangle(pos=self.pos, size=self.size)
                Color(*C['white'][:3], 0.1); self._bd = Line(rectangle=(self.x,self.y,self.width,self.height), width=0.7)

    def _refresh_bg(self, *_):
        self._bg.pos  = self.pos;  self._bg.size = self.size
        self._bd.rectangle = (self.x, self.y, self.width, self.height)

    def _on_touch(self, inst, touch):
        if touch.button == 'left' and self.collide_point(*touch.pos):
            self.on_select(self)
            return True

    def set_selected(self, val):
        self._sel = val
        self._draw_bg(val)
        self.bind(pos=self._refresh_bg, size=self._refresh_bg)

# ── Main app ──────────────────────────────────────────────────────────────────
class DianaApp(App):
    def build(self):
        self.registry     = load_registry()
        self.live_devices = {}
        self.selected     = None
        self.sel_item     = None

        root = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(8))

        # Header bar
        hdr = BoxLayout(size_hint_y=None, height=dp(30))
        hdr.add_widget(Label(text='D I A N A  //  DEVICE INTERFACE',
                             font_size=dp(13), color=C['cyan'],
                             halign='left', text_size=(dp(600), None)))
        self.status_lbl = Label(text='READY — TAP SCAN TO BEGIN',
                                font_size=dp(10), color=C['cyan_dim'],
                                halign='right', text_size=(dp(400), None))
        hdr.add_widget(self.status_lbl)
        root.add_widget(hdr)

        # Body
        body = BoxLayout(orientation='horizontal', spacing=dp(8))

        # ── LEFT: device list ──────────────────────────────
        left = panel('white')
        left.size_hint_x = 0.24

        left.add_widget(lbl('DISCOVERED DEVICES', 'white', size=10, bold=True))
        self.count_lbl = lbl('0 devices', 'white_dim', size=9)
        left.add_widget(self.count_lbl)

        scroll = ScrollView(bar_width=dp(3), bar_color=C['cyan_dim'],
                            bar_inactive_color=C['cyan_bg'])
        self.dev_list = GridLayout(cols=1, spacing=dp(4), size_hint_y=None,
                                   padding=(0, dp(2)))
        self.dev_list.bind(minimum_height=self.dev_list.setter('height'))
        scroll.add_widget(self.dev_list)
        left.add_widget(scroll)
        body.add_widget(left)

        # ── MIDDLE ────────────────────────────────────────
        mid = BoxLayout(orientation='vertical', spacing=dp(8), size_hint_x=0.52)

        # Top: radar
        top = panel('green')
        top.size_hint_y = 0.62
        top.add_widget(lbl('SIGNAL RADAR', 'green', size=10, bold=True))
        self.radar = RadarWidget(size_hint_y=1)
        top.add_widget(self.radar)
        self.scan_btn = btn('INITIATE SCAN', 'green', self.start_scan)
        top.add_widget(self.scan_btn)
        mid.add_widget(top)

        # Bottom: controls
        bot = panel('yellow')
        bot.size_hint_y = 0.38
        bot.add_widget(lbl('DEVICE CONTROLS', 'yellow', size=10, bold=True))
        bot.add_widget(divider('yellow'))
        self.ctrl_box = BoxLayout(orientation='vertical', spacing=dp(5))
        self.ctrl_box.add_widget(lbl('— select a device to see controls —', 'yellow_dim', size=10))
        bot.add_widget(self.ctrl_box)
        mid.add_widget(bot)

        body.add_widget(mid)

        # ── RIGHT: options ────────────────────────────────
        right = panel('red')
        right.size_hint_x = 0.24
        right.add_widget(lbl('DEVICE OPTIONS', 'red', size=10, bold=True))
        right.add_widget(divider('red'))
        self.opts_box = BoxLayout(orientation='vertical', spacing=dp(5))
        self.opts_box.add_widget(lbl('— select a device —', 'red_dim', size=10))
        right.add_widget(self.opts_box)
        body.add_widget(right)

        root.add_widget(body)

        # Load saved devices into list immediately on startup
        Clock.schedule_once(self._load_saved_into_list, 0.3)
        return root

    # ── Startup: populate saved devices ───────────────────
    def _load_saved_into_list(self, *_):
        if not self.registry:
            return
        for addr, info in self.registry.items():
            name  = info.get('name', 'Unknown')
            dtype = info.get('type', 'generic')
            rssi  = info.get('last_rssi', -70)
            item  = DeviceItem(name, addr, rssi, dtype, self.select_device)
            self.dev_list.add_widget(item)
            self.radar.add_blip(rssi, 'green')
        n = len(self.registry)
        self.count_lbl.text = f'{n} saved device{"s" if n!=1 else ""} loaded'
        self.status_lbl.text = f'{n} SAVED DEVICE{"S" if n!=1 else ""} — TAP SCAN FOR FULL SWEEP'

    # ── Scan ──────────────────────────────────────────────
    def start_scan(self, *_):
        self.status_lbl.text = 'SCANNING...'
        self.scan_btn.text   = 'SCANNING...'
        self.scan_btn.disabled = True
        self.dev_list.clear_widgets()
        self.live_devices = {}
        self.radar.clear_blips()
        self.radar.start()
        threading.Thread(target=lambda: asyncio.run(self._do_scan()),
                         daemon=True).start()

    async def _do_scan(self):
        def cb(device, adv):
            if device.address not in self.live_devices:
                self.live_devices[device.address] = {
                    'name': device.name, 'rssi': adv.rssi
                }
                Clock.schedule_once(
                    lambda dt, d=device, a=adv: self._add_device(d.name, d.address, a.rssi))
        async with BleakScanner(cb):
            await asyncio.sleep(10.0)
        Clock.schedule_once(lambda dt: self._scan_done())

    def _scan_done(self):
        self.radar.stop()
        self.scan_btn.text     = 'RESCAN'
        self.scan_btn.disabled = False
        n = len(self.live_devices)
        self.status_lbl.text   = f'{n} DEVICES FOUND'
        self.count_lbl.text    = f'{n} device{"s" if n!=1 else ""}  ·  sorted by signal strength'
        self._sort_list()

    def _add_device(self, name, address, rssi):
        saved = self.registry.get(address, {})
        display = saved.get('name') or name or 'Unknown'
        dtype   = saved.get('type', 'generic')
        color   = 'green' if address in self.registry else 'cyan'
        item    = DeviceItem(display, address, rssi, dtype, self.select_device)
        self.dev_list.add_widget(item)
        self.radar.add_blip(rssi, color)
        self.count_lbl.text = f'{len(self.live_devices)} device{"s" if len(self.live_devices)!=1 else ""}'

    def _sort_list(self):
        items = list(self.dev_list.children[:])
        items.sort(key=lambda i: i.rssi, reverse=True)
        self.dev_list.clear_widgets()
        for item in items:
            self.dev_list.add_widget(item)

    # ── Selection ─────────────────────────────────────────
    def select_device(self, item):
        if self.sel_item:
            self.sel_item.set_selected(False)
        item.set_selected(True)
        self.sel_item = item
        self.selected = {
            'name': item.display_name,
            'address': item.address,
            'rssi': item.rssi,
            'type': item.dtype,
        }
        self._refresh_opts()
        self._refresh_ctrl()

    # ── Options panel ──────────────────────────────────────
    def _refresh_opts(self):
        self.opts_box.clear_widgets()
        d = self.selected
        if not d:
            self.opts_box.add_widget(lbl('— select a device —', 'red_dim', size=10))
            return
        saved = self.registry.get(d['address'], {})
        name  = saved.get('name') or d['name'] or 'Unknown'
        dtype = saved.get('type', 'generic')
        is_saved = d['address'] in self.registry

        self.opts_box.add_widget(lbl(name, 'white', size=13, bold=True, height=dp(24)))
        self.opts_box.add_widget(lbl(d['address'], 'white_dim', size=9))
        self.opts_box.add_widget(lbl(f"TYPE: {dtype.upper()}   RSSI: {d['rssi']} dBm", 'red_dim', size=9))
        self.opts_box.add_widget(divider('red'))

        self.opts_box.add_widget(btn('CONNECT',    'green', self._do_connect))
        self.opts_box.add_widget(btn('DISCONNECT', 'red',   self._do_disconnect))
        self.opts_box.add_widget(divider('red'))

        save_label = 'UPDATE SAVED INFO' if is_saved else 'SAVE DEVICE'
        self.opts_box.add_widget(btn(save_label, 'cyan', self._open_save_popup))
        self.opts_box.add_widget(btn('RENAME',   'yellow', self._open_rename_popup))
        if is_saved:
            self.opts_box.add_widget(btn('REMOVE FROM REGISTRY', 'red_dim', self._remove_device))

    # ── Controls panel ─────────────────────────────────────
    def _refresh_ctrl(self):
        self.ctrl_box.clear_widgets()
        d = self.selected
        if not d:
            self.ctrl_box.add_widget(lbl('— select a device to see controls —', 'yellow_dim', size=10))
            return
        saved = self.registry.get(d['address'], {})
        dtype = saved.get('type', d.get('type', 'generic'))
        name  = saved.get('name') or d['name'] or 'Unknown'

        self.ctrl_box.add_widget(lbl(f'CONTROLLING: {name}', 'yellow', size=10, bold=True))

        if dtype == 'light':
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
            row.add_widget(btn('TURN ON',  'green', lambda x: self._light('on')))
            row.add_widget(btn('TURN OFF', 'red',   lambda x: self._light('off')))
            self.ctrl_box.add_widget(row)
            row2 = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
            row2.add_widget(btn('DIM',    'yellow_dim', lambda x: self._light('dim')))
            row2.add_widget(btn('BRIGHT', 'yellow',     lambda x: self._light('bright')))
            self.ctrl_box.add_widget(row2)

        elif dtype == 'speaker':
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
            row.add_widget(btn('CONNECT',    'green', self._do_connect))
            row.add_widget(btn('DISCONNECT', 'red',   self._do_disconnect))
            self.ctrl_box.add_widget(row)
            self.ctrl_box.add_widget(lbl('Audio controls coming in next update', 'yellow_dim', size=9))

        elif dtype == 'tv':
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
            row.add_widget(btn('POWER ON',  'green', lambda x: self._set_status('TV: POWER ON')))
            row.add_widget(btn('POWER OFF', 'red',   lambda x: self._set_status('TV: POWER OFF')))
            self.ctrl_box.add_widget(row)
            self.ctrl_box.add_widget(lbl('IR blaster required for full TV control', 'yellow_dim', size=9))

        else:
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
            row.add_widget(btn('CONNECT',    'green', self._do_connect))
            row.add_widget(btn('DISCONNECT', 'red',   self._do_disconnect))
            self.ctrl_box.add_widget(row)
            self.ctrl_box.add_widget(lbl('Save & tag device type to unlock full controls', 'yellow_dim', size=9))

    # ── Popups ─────────────────────────────────────────────
    def _popup(self, title, content, size=(0.44, 0.36)):
        p = Popup(title=title, title_color=C['cyan'], content=content,
                  size_hint=size, background_color=(0.01, 0.06, 0.09, 1),
                  separator_color=C['cyan'])
        return p

    def _open_rename_popup(self, *_):
        if not self.selected: return
        wrap = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))
        wrap.add_widget(lbl('New device name:', 'cyan_dim', size=11))
        txt = TextInput(
            text=self.selected.get('name',''),
            font_size=dp(13), multiline=False,
            size_hint_y=None, height=dp(40),
            background_color=(0.02,0.08,0.10,1),
            foreground_color=C['white'],
            cursor_color=C['cyan'],
        )
        wrap.add_widget(txt)
        row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        p = self._popup('RENAME DEVICE', wrap)

        def confirm(*_):
            new = txt.text.strip()
            if not new: return
            addr = self.selected['address']
            if addr not in self.registry:
                self.registry[addr] = {}
            self.registry[addr]['name'] = new
            save_registry(self.registry)
            self.selected['name'] = new
            if self.sel_item:
                self.sel_item.display_name = new
                self.sel_item.children[1].text = new
            self._set_status(f'RENAMED → {new}')
            self._refresh_opts(); self._refresh_ctrl()
            p.dismiss()

        row.add_widget(btn('CONFIRM', 'green', confirm))
        row.add_widget(btn('CANCEL',  'red',   lambda x: p.dismiss()))
        wrap.add_widget(row)
        p.open()

    def _open_save_popup(self, *_):
        if not self.selected: return
        addr  = self.selected['address']
        saved = self.registry.get(addr, {})
        wrap  = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))
        wrap.add_widget(lbl('Device name:', 'cyan_dim', size=11))
        name_in = TextInput(
            text=saved.get('name') or self.selected.get('name',''),
            font_size=dp(13), multiline=False,
            size_hint_y=None, height=dp(40),
            background_color=(0.02,0.08,0.10,1),
            foreground_color=C['white'], cursor_color=C['cyan'],
        )
        wrap.add_widget(name_in)
        wrap.add_widget(lbl('Device type:', 'cyan_dim', size=11))
        type_spin = Spinner(
            text=saved.get('type','generic'),
            values=DEVICE_TYPES,
            size_hint_y=None, height=dp(36),
            background_color=(0.02,0.08,0.10,1),
            color=C['white'], font_size=dp(12),
        )
        wrap.add_widget(type_spin)
        row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        p   = self._popup('SAVE DEVICE', wrap, size=(0.44, 0.46))

        def confirm(*_):
            name = name_in.text.strip() or 'Unknown'
            dtype= type_spin.text
            self.registry[addr] = {
                'name': name, 'type': dtype,
                'last_rssi': self.selected.get('rssi', -70)
            }
            save_registry(self.registry)
            self.selected['name'] = name
            self.selected['type'] = dtype
            if self.sel_item:
                self.sel_item.display_name = name
                self.sel_item.dtype        = dtype
                self.sel_item.children[1].text = name
            self._set_status(f'SAVED: {name}  [{dtype}]')
            self._refresh_opts(); self._refresh_ctrl()
            p.dismiss()

        row.add_widget(btn('SAVE',   'cyan', confirm))
        row.add_widget(btn('CANCEL', 'red',  lambda x: p.dismiss()))
        wrap.add_widget(row)
        p.open()

    def _remove_device(self, *_):
        if not self.selected: return
        addr = self.selected['address']
        name = self.registry.get(addr, {}).get('name', addr)
        self.registry.pop(addr, None)
        save_registry(self.registry)
        self._set_status(f'REMOVED FROM REGISTRY: {name}')
        self._refresh_opts(); self._refresh_ctrl()

    # ── Device actions ─────────────────────────────────────
    def _do_connect(self, *_):
        if self.selected:
            n = self.selected.get('name') or self.selected['address']
            self._set_status(f'CONNECTING → {n}')

    def _do_disconnect(self, *_):
        if self.selected:
            n = self.selected.get('name') or self.selected['address']
            self._set_status(f'DISCONNECTED: {n}')

    def _light(self, cmd):
        name = (self.selected or {}).get('name', 'Light')
        msgs = {'on':'ON ◉','off':'OFF ○','dim':'DIM ▽','bright':'BRIGHT △'}
        self._set_status(f'{name}: {msgs.get(cmd, cmd.upper())}')

    def _set_status(self, text):
        self.status_lbl.text = text


if __name__ == '__main__':
    DianaApp().run()
