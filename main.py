import os, json, math, random, asyncio, threading, logging, socket, time

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
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget
from kivy.uix.progressbar import ProgressBar
from kivy.uix.checkbox import CheckBox
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from bleak import BleakScanner, BleakClient, BleakError

logging.basicConfig(level=logging.INFO, format='[DIANA] %(levelname)s: %(message)s')
log = logging.getLogger(__name__)

Window.clearcolor = (0.025, 0.020, 0.055, 1)

VERSION = 'v1.1'

REGISTRY_PATH = os.path.expanduser('~/diana/registry.json')
GROUPS_PATH   = os.path.expanduser('~/diana/groups.json')
SCENES_PATH   = os.path.expanduser('~/diana/scenes.json')

DEVICE_TYPES = ['generic', 'light', 'speaker', 'tv', 'phone', 'computer', 'other']
SCAN_TIMEOUT = 10.0

TYPE_ICON = {
    'light': '💡', 'speaker': '🔊', 'tv': '📺',
    'phone': '📱', 'computer': '💻', 'other': '🔧', 'generic': '◈',
}

C = {
    'cyan':        (0.00, 0.92, 1.00, 1.0),
    'cyan_dim':    (0.00, 0.92, 1.00, 0.45),
    'cyan_bg':     (0.00, 0.92, 1.00, 0.12),
    'green':       (0.12, 1.00, 0.50, 1.0),
    'green_dim':   (0.12, 1.00, 0.50, 0.45),
    'green_bg':    (0.12, 1.00, 0.50, 0.12),
    'red':         (1.00, 0.18, 0.38, 1.0),
    'red_dim':     (1.00, 0.18, 0.38, 0.45),
    'red_bg':      (1.00, 0.18, 0.38, 0.10),
    'yellow':      (1.00, 0.78, 0.00, 1.0),
    'yellow_dim':  (1.00, 0.78, 0.00, 0.45),
    'yellow_bg':   (1.00, 0.78, 0.00, 0.10),
    'purple':      (0.72, 0.30, 1.00, 1.0),
    'purple_dim':  (0.72, 0.30, 1.00, 0.45),
    'purple_bg':   (0.72, 0.30, 1.00, 0.12),
    'orange':      (1.00, 0.55, 0.10, 1.0),
    'orange_dim':  (1.00, 0.55, 0.10, 0.45),
    'orange_bg':   (1.00, 0.55, 0.10, 0.12),
    'white':       (0.90, 0.95, 1.00, 1.0),
    'white_dim':   (0.90, 0.95, 1.00, 0.40),
    'white_bg':    (0.90, 0.95, 1.00, 0.05),
    'bg':          (0.025, 0.020, 0.055, 1.0),
    'panel':       (0.055, 0.048, 0.110, 1.0),
}

class GoveeController:
    MULTICAST_IP  = '239.255.255.250'
    DISCOVER_PORT = 4001
    LISTEN_PORT   = 4002
    CONTROL_PORT  = 4003

    def _send(self, ip, payload):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.sendto(json.dumps(payload).encode(), (ip, self.CONTROL_PORT))
            s.close()
        except Exception as e:
            log.warning('Govee send error: %s', e)

    def discover(self, timeout=3):
        scan_msg = json.dumps({'msg': {'cmd': 'scan', 'data': {'account_topic': 'reserve'}}}).encode()
        results = {}
        try:
            recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            recv.bind(('', self.LISTEN_PORT))
            recv.settimeout(timeout)
            send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            send.sendto(scan_msg, (self.MULTICAST_IP, self.DISCOVER_PORT))
            send.close()
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    data, (ip, _) = recv.recvfrom(4096)
                    j = json.loads(data)
                    d = j.get('msg', {}).get('data', {})
                    did = d.get('device') or ip
                    results[did] = {'ip': ip, 'sku': d.get('sku', ''), 'name': d.get('device', ip)}
                except socket.timeout:
                    break
            recv.close()
        except Exception as e:
            log.warning('Govee discover error: %s', e)
        return results

    def _cmd(self, ip, cmd, val):
        self._send(ip, {'msg': {'cmd': cmd, 'data': val}})

    def turn_on(self, ip):        self._cmd(ip, 'turn', {'value': 1})
    def turn_off(self, ip):       self._cmd(ip, 'turn', {'value': 0})
    def set_brightness(self, ip, v): self._cmd(ip, 'brightness', {'value': max(1, min(100, v))})
    def set_color(self, ip, r, g, b): self._cmd(ip, 'colorwc', {'color': {'r':r,'g':g,'b':b}, 'colorTemInKelvin':0})

GOVEE = GoveeController()

def _load_json(path):
    try:
        with open(path) as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        log.warning('Load %s: %s', path, e)
        return {}

def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        log.error('Save %s: %s', path, e)
        return False

def panel(border_color_key, radius=8):
    ck = C[border_color_key]
    layout = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(8))
    with layout.canvas.before:
        Color(*C['panel'])
        layout._bg = RoundedRectangle(pos=layout.pos, size=layout.size, radius=[dp(radius)])
        Color(*ck[:3], 0.22)
        layout._bd = Line(rounded_rectangle=(layout.x, layout.y, layout.width, layout.height, dp(radius)), width=1.2)
    def _upd(inst, _):
        inst._bg.pos = inst.pos; inst._bg.size = inst.size
        inst._bg.radius = [dp(radius)]
        inst._bd.rounded_rectangle = (inst.x, inst.y, inst.width, inst.height, dp(radius))
    layout.bind(pos=_upd, size=_upd)
    return layout

def lbl(text, color_key, size=11, bold=False, halign='left', height=dp(20)):
    l = Label(text=text, font_size=dp(size), color=C[color_key],
              size_hint_y=None, height=height, halign=halign, valign='middle', bold=bold)
    l.bind(size=lambda inst, v: setattr(inst, 'text_size', v))
    return l

def section_title(text, color_key):
    row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(24), spacing=dp(8))
    ck = C[color_key]
    tick = Widget(size_hint_x=None, width=dp(3))
    with tick.canvas:
        Color(*ck[:3], 1.0)
        tick._rect = RoundedRectangle(pos=tick.pos, size=tick.size, radius=[dp(2)])
    tick.bind(pos=lambda i,_: setattr(i._rect,'pos',i.pos),
              size=lambda i,_: setattr(i._rect,'size',i.size))
    row.add_widget(tick)
    row.add_widget(lbl(text, color_key, size=10, bold=True, height=dp(24)))
    return row

def btn(text, color_key, cb=None, height=dp(34), radius=6):
    ck = C[color_key]
    b = Button(text=text, size_hint_y=None, height=height,
               background_color=(0,0,0,0), color=ck, font_size=dp(10.5), bold=True)
    with b.canvas.before:
        Color(*ck[:3], 0.18)
        b._bg = RoundedRectangle(pos=b.pos, size=b.size, radius=[dp(radius)])
        Color(*ck[:3], 0.65)
        b._bd = Line(rounded_rectangle=(b.x, b.y, b.width, b.height, dp(radius)), width=1.1)
    def _upd(inst, _):
        inst._bg.pos = inst.pos; inst._bg.size = inst.size
        inst._bg.radius = [dp(radius)]
        inst._bd.rounded_rectangle = (inst.x, inst.y, inst.width, inst.height, dp(radius))
    b.bind(pos=_upd, size=_upd)
    if cb:
        b.bind(on_press=cb)
    return b

def divider(color_key):
    w = Widget(size_hint_y=None, height=dp(1))
    with w.canvas:
        Color(*C[color_key][:3], 0.18)
        w._line = Rectangle(pos=w.pos, size=w.size)
    w.bind(pos=lambda i,_: setattr(i._line,'pos',i.pos),
           size=lambda i,_: setattr(i._line,'size',i.size))
    return w

def mk_slider(min_v=1, max_v=100, value=100):
    return Slider(min=min_v, max=max_v, value=value,
                  size_hint_y=None, height=dp(36), cursor_size=(dp(22), dp(22)))

def signal_bars(rssi):
    if rssi >= -50: return '▂▄▆█'
    if rssi >= -65: return '▂▄▆░'
    if rssi >= -75: return '▂▄░░'
    return '▂░░░'

def plural(n, word):
    return f'{n} {word}{"s" if n != 1 else ""}'

class RadarWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.angle = 0.0; self.blips = []; self._clock = None; self.scanning = False
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
        self.blips.clear(); self._draw()

    def add_blip(self, rssi, color_key='cyan'):
        cx, cy = self.center
        r = min(self.width, self.height) * 0.43
        d = max(0.08, min(0.92, (rssi + 20) / 70.0)) * r
        a = random.uniform(0, 2 * math.pi)
        self.blips.append({'x': cx + d*math.cos(a), 'y': cy + d*math.sin(a),
                            'color': color_key, 'alpha': 1.0, 'rssi': rssi})

    def _tick(self, dt):
        self.angle = (self.angle + 1.8) % 360
        for b in self.blips:
            b['alpha'] = max(0.22, b['alpha'] - 0.0005)
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        cx, cy = self.center
        r = min(self.width, self.height) * 0.43
        with self.canvas:
            Color(0.00, 0.92, 1.00, 0.04)
            Line(circle=(cx, cy, r*1.02), width=8)
            for i in range(1, 6):
                Color(0.00, 0.92, 1.00, 0.10 if i%2==0 else 0.06)
                Line(circle=(cx, cy, r*i/5), width=1)
            Color(0.00, 0.92, 1.00, 0.06)
            Line(points=[cx-r, cy, cx+r, cy], width=1)
            Line(points=[cx, cy-r, cx, cy+r], width=1)
            Color(0.00, 0.92, 1.00, 0.03)
            d45 = r * 0.707
            Line(points=[cx-d45, cy-d45, cx+d45, cy+d45], width=1)
            Line(points=[cx+d45, cy-d45, cx-d45, cy+d45], width=1)
            if self.scanning:
                for i in range(90):
                    t = math.radians(self.angle - i*0.8)
                    Color(0.00, 0.92, 1.00, (90-i)/90*0.28)
                    Line(points=[cx, cy, cx+r*math.cos(t), cy+r*math.sin(t)], width=1.3)
                Color(0.00, 0.92, 1.00, 0.95)
                s = math.radians(self.angle)
                Line(points=[cx, cy, cx+r*math.cos(s), cy+r*math.sin(s)], width=2.0)
                Color(0.00, 0.92, 1.00, 0.40)
                tx = cx+r*math.cos(s); ty = cy+r*math.sin(s)
                Ellipse(pos=(tx-dp(5), ty-dp(5)), size=(dp(10), dp(10)))
            for b in self.blips:
                ck = C.get(b['color'], C['cyan'])
                Color(*ck[:3], b['alpha'])
                Ellipse(pos=(b['x']-dp(4.5), b['y']-dp(4.5)), size=(dp(9), dp(9)))
                Color(*ck[:3], b['alpha']*0.20)
                Ellipse(pos=(b['x']-dp(12), b['y']-dp(12)), size=(dp(24), dp(24)))
            Color(0.00, 0.92, 1.00, 0.25)
            Ellipse(pos=(cx-dp(6), cy-dp(6)), size=(dp(12), dp(12)))
            Color(0.00, 0.92, 1.00, 1.0)
            Ellipse(pos=(cx-dp(3), cy-dp(3)), size=(dp(6), dp(6)))

class DeviceItem(BoxLayout):
    def __init__(self, display_name, address, rssi, dtype, on_select, **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None,
                         height=dp(60), padding=(dp(12), dp(6)), spacing=dp(2), **kwargs)
        self.address = address; self.rssi = rssi; self.dtype = dtype
        self.display_name = display_name; self.on_select = on_select
        self.connected = False; self._multi_sel = False
        self._draw_bg('normal')
        self.bind(pos=self._refresh_bg, size=self._refresh_bg)
        icon = TYPE_ICON.get(dtype, '')
        self._name_lbl = Label(
            text=f'{icon}  {display_name}'.strip() if icon else display_name,
            font_size=dp(11.5), color=C['white'], bold=True,
            size_hint_y=None, height=dp(22), halign='left', valign='middle')
        self._name_lbl.bind(size=lambda inst,v: setattr(inst,'text_size',v))
        self.add_widget(self._name_lbl)
        self._sub_lbl = Label(
            text=f'{address}   {signal_bars(rssi)}  {rssi} dBm',
            font_size=dp(9), color=C['cyan_dim'],
            size_hint_y=None, height=dp(16), halign='left', valign='middle')
        self._sub_lbl.bind(size=lambda inst,v: setattr(inst,'text_size',v))
        self.add_widget(self._sub_lbl)
        self.bind(on_touch_down=self._on_touch)

    def update_name(self, name):
        self.display_name = name
        icon = TYPE_ICON.get(self.dtype, '')
        self._name_lbl.text = f'{icon}  {name}'.strip() if icon else name

    def _update_sub(self):
        conn = '   ● LIVE' if self.connected else ''
        self._sub_lbl.text  = f'{self.address}   {signal_bars(self.rssi)}  {self.rssi} dBm{conn}'
        self._sub_lbl.color = C['green_dim'] if self.connected else C['cyan_dim']

    def set_connected(self, val):
        self.connected = val; self._update_sub()
        self._draw_bg('connected' if val else 'normal')
        self.bind(pos=self._refresh_bg, size=self._refresh_bg)

    def set_multi_selected(self, val):
        self._multi_sel = val
        self._draw_bg('multi' if val else 'normal')
        self.bind(pos=self._refresh_bg, size=self._refresh_bg)

    def set_selected(self, val):
        if self._multi_sel: return
        self._draw_bg('selected' if val else 'normal')
        self.bind(pos=self._refresh_bg, size=self._refresh_bg)

    def _draw_bg(self, state):
        self.canvas.before.clear()
        states = {
            'normal':    (C['white_bg'],   C['white'][:3]  + (0.10,)),
            'selected':  (C['cyan_bg'],    C['cyan'][:3]   + (0.60,)),
            'connected': (C['green_bg'],   C['green'][:3]  + (0.55,)),
            'multi':     (C['orange_bg'],  C['orange'][:3] + (0.70,)),
        }
        bg_c, bd_c = states.get(state, states['normal'])
        with self.canvas.before:
            Color(*bg_c)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
            Color(*bd_c)
            self._bd = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(6)), width=1.1)

    def _refresh_bg(self, *_):
        self._bg.pos = self.pos; self._bg.size = self.size; self._bg.radius = [dp(6)]
        self._bd.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(6))

    def _on_touch(self, inst, touch):
        if touch.button == 'left' and self.collide_point(*touch.pos):
            self.on_select(self); return True

class GroupItem(BoxLayout):
    def __init__(self, name, addresses, on_select, on_delete, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None,
                         height=dp(52), padding=(dp(10), dp(6)), spacing=dp(8), **kwargs)
        self.group_name = name; self.addresses = addresses
        with self.canvas.before:
            Color(*C['purple_bg'])
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
            Color(*C['purple'][:3], 0.30)
            self._bd = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(6)), width=1)
        self.bind(pos=self._upd, size=self._upd)
        info = BoxLayout(orientation='vertical', spacing=dp(2))
        nl = Label(text=name, font_size=dp(11.5), color=C['purple'], bold=True,
                   halign='left', valign='middle', size_hint_y=None, height=dp(22))
        nl.bind(size=lambda i,v: setattr(i,'text_size',v))
        sl = Label(text=f'{len(addresses)} light{"s" if len(addresses)!=1 else ""}',
                   font_size=dp(9), color=C['white_dim'], halign='left', valign='middle',
                   size_hint_y=None, height=dp(16))
        sl.bind(size=lambda i,v: setattr(i,'text_size',v))
        info.add_widget(nl); info.add_widget(sl)
        self.add_widget(info)
        self.add_widget(btn('SELECT', 'purple', lambda x: on_select(self), height=dp(34), radius=5))
        self.add_widget(btn('✕', 'red', lambda x: on_delete(name), height=dp(34), radius=5))

    def _upd(self, *_):
        self._bg.pos = self.pos; self._bg.size = self.size; self._bg.radius = [dp(6)]
        self._bd.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(6))

class DianaApp(App):
    def build(self):
        self.registry     = _load_json(REGISTRY_PATH)
        self.groups       = _load_json(GROUPS_PATH)
        self.scenes       = _load_json(SCENES_PATH)
        self.live_devices = {}; self.connections = {}
        self.selected = None; self.sel_item = None
        self._ble_loop = None; self._ble_thread = None; self._scan_start = 0
        self._govee_devs = {}; self._multi_mode = False; self._multi_sel = {}
        self._active_tab = 'scan'
        self._start_ble_thread()

        root = BoxLayout(orientation='vertical', spacing=0, padding=0)

        # Header
        hdr = BoxLayout(size_hint_y=None, height=dp(52), padding=(dp(18), 0), spacing=dp(14))
        with hdr.canvas.before:
            Color(0.040, 0.032, 0.090, 1)
            hdr._bg = Rectangle(pos=hdr.pos, size=hdr.size)
            Color(*C['cyan'][:3], 0.18)
            hdr._bd = Rectangle(pos=(0,0), size=(0, dp(1)))
        def _hdr_upd(inst, _):
            inst._bg.pos = inst.pos; inst._bg.size = inst.size
            inst._bd.pos = (inst.x, inst.y); inst._bd.size = (inst.width, dp(1))
        hdr.bind(pos=_hdr_upd, size=_hdr_upd)
        tc = BoxLayout(orientation='vertical', size_hint_x=None, width=dp(210))
        t1 = Label(text='DIANA', font_size=dp(22), color=C['cyan'], bold=True,
                   halign='left', text_size=(dp(120), None), size_hint_y=None, height=dp(28))
        t2 = Label(text='Device Interface & Network Analyser',
                   font_size=dp(7.5), color=C['white_dim'],
                   halign='left', text_size=(dp(250), None), size_hint_y=None, height=dp(14))
        tc.add_widget(t1); tc.add_widget(t2)
        hdr.add_widget(tc); hdr.add_widget(Widget())
        self.status_lbl = Label(text='● READY', font_size=dp(10), color=C['cyan_dim'],
                                halign='right', text_size=(dp(400), None))
        hdr.add_widget(self.status_lbl)
        hdr.add_widget(Label(text=VERSION, font_size=dp(8.5), color=C['purple_dim'],
                             size_hint_x=None, width=dp(36),
                             halign='right', text_size=(dp(36), None)))
        root.add_widget(hdr)

        # Body
        body = BoxLayout(orientation='horizontal', spacing=dp(10),
                         padding=(dp(10), dp(10), dp(10), dp(0)))

        # Left
        left = BoxLayout(orientation='vertical', size_hint_x=0.23, spacing=dp(6))
        tab_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
        self._tab_btns = {}
        for tab, label in [('scan','SCAN'),('saved','SAVED'),('groups','GROUPS'),('multi','MULTI')]:
            color = 'purple' if tab in ('groups','multi') else 'cyan'
            b = Button(text=label, font_size=dp(9.5), bold=True,
                       background_color=(0,0,0,0), size_hint_y=None, height=dp(34))
            b.color = C[color+'_dim']
            with b.canvas.before:
                Color(*C[color][:3], 0.08)
                b._bg = RoundedRectangle(pos=b.pos, size=b.size, radius=[dp(5)])
                Color(*C[color][:3], 0.30)
                b._bd = Line(rounded_rectangle=(b.x,b.y,b.width,b.height,dp(5)), width=1)
            def _bu(inst, _):
                inst._bg.pos=inst.pos; inst._bg.size=inst.size; inst._bg.radius=[dp(5)]
                inst._bd.rounded_rectangle=(inst.x,inst.y,inst.width,inst.height,dp(5))
            b.bind(pos=_bu, size=_bu, on_press=lambda x, tb=tab: self._switch_tab(tb))
            self._tab_btns[tab] = b; tab_row.add_widget(b)
        left.add_widget(tab_row)

        self._left_panel = panel('white')
        self._left_panel.padding = (dp(10), dp(10))
        self.count_lbl = lbl('No devices', 'white_dim', size=9)
        self._left_panel.add_widget(self.count_lbl)
        self._left_panel.add_widget(divider('white'))
        self._left_scroll = ScrollView(bar_width=dp(2), bar_color=C['cyan_dim'],
                                       bar_inactive_color=C['white_bg'])
        self._left_list = GridLayout(cols=1, spacing=dp(4), size_hint_y=None, padding=(0,dp(2)))
        self._left_list.bind(minimum_height=self._left_list.setter('height'))
        self._left_scroll.add_widget(self._left_list)
        self._left_panel.add_widget(self._left_scroll)
        left.add_widget(self._left_panel)
        body.add_widget(left)

        # Middle
        mid = BoxLayout(orientation='vertical', spacing=dp(10), size_hint_x=0.54)
        radar_panel = panel('green'); radar_panel.size_hint_y = 0.62
        rh = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(8))
        rh.add_widget(section_title('SIGNAL RADAR', 'green')); rh.add_widget(Widget())
        self._govee_count_lbl = lbl('', 'green_dim', size=8, halign='right', height=dp(24))
        rh.add_widget(self._govee_count_lbl)
        radar_panel.add_widget(rh)
        self.radar = RadarWidget(size_hint_y=1)
        radar_panel.add_widget(self.radar)
        scan_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        self.scan_btn = btn('⬡  INITIATE SCAN', 'green', self._start_scan, height=dp(36))
        scan_row.add_widget(self.scan_btn)
        scan_row.add_widget(btn('FIND GOVEE', 'yellow', self._find_govee, height=dp(36)))
        scan_row.add_widget(btn('SCENES', 'purple', self._open_scenes_popup, height=dp(36)))
        radar_panel.add_widget(scan_row)
        self.progress = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(3))
        with self.progress.canvas.before:
            Color(*C['green'][:3], 0.12)
            self.progress._bg = Rectangle(pos=self.progress.pos, size=self.progress.size)
        self.progress.bind(
            pos=lambda i,_: setattr(i._bg,'pos',i.pos),
            size=lambda i,_: setattr(i._bg,'size',i.size))
        radar_panel.add_widget(self.progress)
        mid.add_widget(radar_panel)
        ctrl_panel = panel('cyan'); ctrl_panel.size_hint_y = 0.38
        ctrl_panel.add_widget(section_title('DEVICE CONTROLS', 'cyan'))
        ctrl_panel.add_widget(divider('cyan'))
        self.ctrl_box = BoxLayout(orientation='vertical', spacing=dp(6))
        self.ctrl_box.add_widget(lbl('Select a device to see controls', 'white_dim', size=9))
        ctrl_panel.add_widget(self.ctrl_box)
        mid.add_widget(ctrl_panel)
        body.add_widget(mid)

        # Right
        right = panel('cyan'); right.size_hint_x = 0.23
        right.add_widget(section_title('DEVICE OPTIONS', 'cyan'))
        right.add_widget(divider('cyan'))
        self.opts_box = BoxLayout(orientation='vertical', spacing=dp(6))
        self.opts_box.add_widget(lbl('Select a device', 'white_dim', size=9))
        right.add_widget(self.opts_box)
        body.add_widget(right)
        root.add_widget(body)

        # Status bar
        bar = BoxLayout(size_hint_y=None, height=dp(24), padding=(dp(14),0), spacing=dp(16))
        with bar.canvas.before:
            Color(0.035, 0.028, 0.075, 1)
            bar._bg = Rectangle(pos=bar.pos, size=bar.size)
            Color(*C['cyan'][:3], 0.10)
            bar._top = Rectangle(pos=(0,0), size=(0,dp(1)))
        def _bar_upd(inst, _):
            inst._bg.pos=inst.pos; inst._bg.size=inst.size
            inst._top.pos=(inst.x,inst.top-dp(1)); inst._top.size=(inst.width,dp(1))
        bar.bind(pos=_bar_upd, size=_bar_upd)
        self.bar_lbl = Label(text='● IDLE', font_size=dp(8.5), color=C['cyan_dim'],
                             halign='left', text_size=(dp(500), None))
        bar.add_widget(self.bar_lbl)
        bar.add_widget(Label(text=f'DIANA {VERSION}  ·  BLE + Govee LAN',
                             font_size=dp(8.5), color=C['white_dim'],
                             halign='right', text_size=(dp(300), None)))
        root.add_widget(bar)

        self._switch_tab('scan')
        Clock.schedule_once(self._load_saved_into_list, 0.3)
        return root

    def on_start(self):
        Window.show_cursor = True
        Clock.schedule_once(lambda dt: setattr(Window,'show_cursor',True), 0.5)

    def on_stop(self):
        for client in list(self.connections.values()):
            if self._ble_loop and self._ble_loop.is_running():
                asyncio.run_coroutine_threadsafe(self._force_disconnect(client), self._ble_loop)
        if self._ble_loop:
            self._ble_loop.call_soon_threadsafe(self._ble_loop.stop)

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

    def _switch_tab(self, tab):
        self._active_tab = tab
        color_map = {'scan':'cyan','saved':'cyan','groups':'purple','multi':'purple'}
        for t, b in self._tab_btns.items():
            ck = color_map.get(t, 'cyan'); is_active = t == tab
            b.canvas.before.clear(); b.color = C[ck] if is_active else C[ck+'_dim']
            with b.canvas.before:
                Color(*C[ck][:3], 0.22 if is_active else 0.08)
                b._bg = RoundedRectangle(pos=b.pos, size=b.size, radius=[dp(5)])
                Color(*C[ck][:3], 0.80 if is_active else 0.30)
                b._bd = Line(rounded_rectangle=(b.x,b.y,b.width,b.height,dp(5)), width=1.2)
            def _bu(inst, _, bref=b):
                bref._bg.pos=bref.pos; bref._bg.size=bref.size; bref._bg.radius=[dp(5)]
                bref._bd.rounded_rectangle=(bref.x,bref.y,bref.width,bref.height,dp(5))
            b.bind(pos=_bu, size=_bu)
        self._left_list.clear_widgets()
        if tab == 'scan':
            self.count_lbl.text = plural(len(self.live_devices),'device') if self.live_devices else 'No scan yet'
            for addr, info in self.live_devices.items():
                saved = self.registry.get(addr, {})
                display = saved.get('name') or info.get('name') or 'Unknown'
                dtype = saved.get('type','generic'); rssi = info.get('rssi',-70)
                item = DeviceItem(display, addr, rssi, dtype, self._select_device)
                if addr in self.connections: item.set_connected(True)
                self._left_list.add_widget(item)
        elif tab == 'saved':
            self._load_saved_into_list()
        elif tab == 'groups':
            self._load_groups_tab()
        elif tab == 'multi':
            self._multi_mode = True
            self._load_saved_into_list(multi=True)
            self.count_lbl.text = 'Tap lights to select multiple'

    def _load_saved_into_list(self, *_, multi=False):
        if not multi: self._left_list.clear_widgets()
        self.count_lbl.text = plural(len(self.registry), 'saved device')
        for addr, info in self.registry.items():
            name = info.get('name') or 'Unknown'; dtype = info.get('type','generic')
            rssi = info.get('last_rssi', -70)
            cb = self._multi_select_device if self._multi_mode else self._select_device
            item = DeviceItem(name, addr, rssi, dtype, cb)
            if addr in self._multi_sel: item.set_multi_selected(True)
            self._left_list.add_widget(item)
            self.radar.add_blip(rssi, 'green')

    def _load_groups_tab(self):
        self._left_list.clear_widgets()
        self.count_lbl.text = plural(len(self.groups), 'group')
        for name, addrs in self.groups.items():
            self._left_list.add_widget(GroupItem(name, addrs, self._select_group, self._delete_group))
        self._left_list.add_widget(btn('+ CREATE GROUP', 'purple', self._create_group_popup))

    def _start_scan(self, *_):
        self._switch_tab('scan')
        self.scan_btn.text = '◌  SCANNING...'; self.scan_btn.disabled = True
        self.live_devices = {}; self._left_list.clear_widgets()
        self.radar.clear_blips(); self.radar.start()
        self.progress.value = 0; self._scan_start = 0
        self._set_status('Scanning for Bluetooth LE devices…', 'SCANNING')
        self.count_lbl.text = 'Scanning...'
        self._progress_clock = Clock.schedule_interval(self._tick_progress, 0.1)
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
                    Clock.schedule_once(lambda dt, d=device, r=rssi: self._add_device_to_list(d.name, d.address, r))
            async with BleakScanner(cb):
                await asyncio.sleep(SCAN_TIMEOUT)
        except BleakError as e:
            Clock.schedule_once(lambda dt: self._set_status(f'Scan error: {e}', 'ERROR'))
        finally:
            Clock.schedule_once(lambda dt: self._scan_done())

    def _scan_done(self):
        if hasattr(self, '_progress_clock'): self._progress_clock.cancel()
        self.progress.value = 100; self.radar.stop()
        self.scan_btn.text = '⬡  RESCAN'; self.scan_btn.disabled = False
        n = len(self.live_devices)
        self.count_lbl.text = f'{plural(n,"device")}  ·  by signal'
        self._set_status(f'Scan complete — {plural(n,"device")} found', 'IDLE')
        self._sort_list()
        Clock.schedule_once(lambda dt: setattr(self.progress,'value',0), 1.5)

    def _add_device_to_list(self, name, address, rssi):
        if self._active_tab != 'scan': return
        saved = self.registry.get(address, {})
        display = saved.get('name') or name or 'Unknown'
        dtype = saved.get('type','generic')
        color = 'green' if address in self.registry else 'cyan'
        item = DeviceItem(display, address, rssi, dtype, self._select_device)
        if address in self.connections: item.set_connected(True)
        self._left_list.add_widget(item)
        self.radar.add_blip(rssi, color)
        self.count_lbl.text = plural(len(self.live_devices), 'device')

    def _sort_list(self):
        items = [i for i in self._left_list.children if isinstance(i, DeviceItem)]
        items.sort(key=lambda i: i.rssi, reverse=True)
        self._left_list.clear_widgets()
        for item in items: self._left_list.add_widget(item)

    def _find_govee(self, *_):
        self._set_status('Searching for Govee lights on LAN…', 'SCANNING')
        threading.Thread(target=lambda: Clock.schedule_once(
            lambda dt: self._govee_found(GOVEE.discover(timeout=3))), daemon=True).start()

    def _govee_found(self, devs):
        self._govee_devs = devs; n = len(devs)
        self._govee_count_lbl.text = f'{n} Govee' if n else ''
        self._set_status(f'Found {plural(n,"Govee light")} on LAN', 'IDLE')

    def _govee_ip(self, addr):
        return self.registry.get(addr, {}).get('govee_ip')

    def _select_device(self, item):
        if self.sel_item and self.sel_item is not item: self.sel_item.set_selected(False)
        item.set_selected(True); self.sel_item = item
        self.selected = {'name':item.display_name,'address':item.address,'rssi':item.rssi,'type':item.dtype}
        self._multi_mode = False; self._multi_sel = {}
        self._refresh_opts(); self._refresh_ctrl()

    def _multi_select_device(self, item):
        addr = item.address
        if addr in self._multi_sel:
            del self._multi_sel[addr]; item.set_multi_selected(False)
        else:
            self._multi_sel[addr] = item; item.set_multi_selected(True)
        self.count_lbl.text = f'{len(self._multi_sel)} selected'
        self._refresh_ctrl_multi()

    def _refresh_ctrl_multi(self):
        self.ctrl_box.clear_widgets()
        ips = [self._govee_ip(a) for a in self._multi_sel if self._govee_ip(a)]
        n = len(self._multi_sel)
        if n == 0:
            self.ctrl_box.add_widget(lbl('Tap saved lights to select', 'white_dim', size=9)); return
        self.ctrl_box.add_widget(lbl(f'{n} lights selected', 'orange', size=11, bold=True))
        if ips: self._add_light_controls(ips)
        else: self.ctrl_box.add_widget(lbl('No Govee IPs assigned to selection', 'white_dim', size=9))

    def _refresh_opts(self):
        self.opts_box.clear_widgets()
        d = self.selected
        if not d:
            self.opts_box.add_widget(lbl('Select a device', 'white_dim', size=9)); return
        addr = d['address']; saved = self.registry.get(addr, {})
        name = saved.get('name') or d['name'] or 'Unknown'
        dtype = saved.get('type','generic')
        is_saved = addr in self.registry; is_conn = addr in self.connections
        icon = TYPE_ICON.get(dtype,'')
        self.opts_box.add_widget(lbl(f'{icon}  {name}' if icon else name, 'white', size=13, bold=True, height=dp(24)))
        self.opts_box.add_widget(lbl(addr, 'white_dim', size=8))
        self.opts_box.add_widget(lbl(f"{dtype.upper()}   {signal_bars(d['rssi'])}  {d['rssi']} dBm", 'cyan_dim', size=8.5, height=dp(18)))
        self.opts_box.add_widget(divider('cyan'))
        if is_conn:
            cr = BoxLayout(size_hint_y=None, height=dp(20), spacing=dp(6))
            cr.add_widget(Label(text='●', font_size=dp(10), color=C['green'], size_hint_x=None, width=dp(16)))
            cr.add_widget(lbl('CONNECTED', 'green', size=9.5, bold=True, height=dp(20)))
            self.opts_box.add_widget(cr)
            self.opts_box.add_widget(btn('DISCONNECT', 'red', self._do_disconnect))
        else:
            self.opts_box.add_widget(btn('CONNECT', 'green', self._do_connect))
        self.opts_box.add_widget(divider('cyan'))
        self.opts_box.add_widget(btn('UPDATE INFO' if is_saved else 'SAVE DEVICE', 'cyan', self._open_save_popup))
        self.opts_box.add_widget(btn('RENAME', 'yellow', self._open_rename_popup))
        if is_saved: self.opts_box.add_widget(btn('REMOVE', 'red_dim', self._remove_device))

    def _refresh_ctrl(self):
        self.ctrl_box.clear_widgets()
        d = self.selected
        if not d:
            self.ctrl_box.add_widget(lbl('Select a device to see controls', 'white_dim', size=9)); return
        addr = d['address']; saved = self.registry.get(addr, {})
        dtype = saved.get('type', d.get('type','generic'))
        name = saved.get('name') or d['name'] or 'Unknown'
        self.ctrl_box.add_widget(lbl(name, 'yellow', size=11, bold=True))
        if dtype == 'light':
            ip = self._govee_ip(addr)
            if ip: self._add_light_controls([ip])
            else:
                row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
                row.add_widget(btn('CONNECT','green',self._do_connect))
                row.add_widget(btn('DISCONNECT','red',self._do_disconnect))
                self.ctrl_box.add_widget(row)
                self.ctrl_box.add_widget(lbl('Save device & assign Govee IP for LAN control','white_dim',size=8.5))
        elif dtype == 'speaker':
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
            row.add_widget(btn('CONNECT','green',self._do_connect))
            row.add_widget(btn('DISCONNECT','red',self._do_disconnect))
            self.ctrl_box.add_widget(row)
            self.ctrl_box.add_widget(lbl('Audio controls coming soon','white_dim',size=8.5))
        elif dtype == 'tv':
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
            row.add_widget(btn('POWER ON','green',lambda x: self._set_status('TV: Power On','CMD')))
            row.add_widget(btn('POWER OFF','red',lambda x: self._set_status('TV: Power Off','CMD')))
            self.ctrl_box.add_widget(row)
            self.ctrl_box.add_widget(lbl('IR blaster required for full TV control','white_dim',size=8.5))
        else:
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
            row.add_widget(btn('CONNECT','green',self._do_connect))
            row.add_widget(btn('DISCONNECT','red',self._do_disconnect))
            self.ctrl_box.add_widget(row)
            self.ctrl_box.add_widget(lbl('Tag a device type to unlock controls','white_dim',size=8.5))

    def _add_light_controls(self, ips):
        on_off = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        on_off.add_widget(btn('◉  ON','green',lambda x: self._lc_all(ips,'on')))
        on_off.add_widget(btn('○  OFF','red',lambda x: self._lc_all(ips,'off')))
        self.ctrl_box.add_widget(on_off)
        self.ctrl_box.add_widget(lbl('Brightness','white_dim',size=9))
        sl = mk_slider()
        sl.bind(on_touch_up=lambda inst,touch: self._lc_all(ips,'brightness',int(inst.value)) if inst.collide_point(*touch.pos) else None)
        self.ctrl_box.add_widget(sl)
        self.ctrl_box.add_widget(lbl('Color','white_dim',size=9))
        cr = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(5))
        for (label,ck,(r,g,b)) in [('WHITE','white',(255,255,220)),('WARM','yellow',(255,160,40)),
                ('RED','red',(255,20,20)),('BLUE','cyan',(20,140,255)),
                ('GREEN','green',(20,255,80)),('PURPLE','purple',(160,40,255))]:
            cr.add_widget(btn(label,ck,lambda x,ri=r,gi=g,bi=b: self._lc_all(ips,'color',(ri,gi,bi)),height=dp(34)))
        self.ctrl_box.add_widget(cr)
        rgb = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        ti_args = dict(multiline=False, font_size=dp(11), size_hint_x=None, width=dp(42),
                       height=dp(34), size_hint_y=None, background_color=(0.04,0.04,0.10,1),
                       foreground_color=C['white'], cursor_color=C['cyan'], padding=(dp(6),dp(8)))
        self._r_in = TextInput(hint_text='R', **ti_args)
        self._g_in = TextInput(hint_text='G', **ti_args)
        self._b_in = TextInput(hint_text='B', **ti_args)
        rgb.add_widget(self._r_in); rgb.add_widget(self._g_in); rgb.add_widget(self._b_in)
        rgb.add_widget(btn('SET','cyan',
            lambda x: self._lc_all(ips,'color',(int(self._r_in.text or 0),int(self._g_in.text or 0),int(self._b_in.text or 0))),
            height=dp(34)))
        self.ctrl_box.add_widget(rgb)

    def _lc_all(self, ips, cmd, val=None):
        def _do():
            for ip in ips:
                try:
                    if cmd=='on': GOVEE.turn_on(ip)
                    elif cmd=='off': GOVEE.turn_off(ip)
                    elif cmd=='brightness': GOVEE.set_brightness(ip, val)
                    elif cmd=='color': GOVEE.set_color(ip, *val)
                except Exception as e: log.warning('Govee %s %s: %s', cmd, ip, e)
        threading.Thread(target=_do, daemon=True).start()
        self._set_status(f'Govee {cmd} → {len(ips)} light(s)', 'CMD')

    def _do_connect(self, *_):
        if not self.selected: return
        addr = self.selected['address']
        if addr in self.connections: self._set_status('Already connected','INFO'); return
        name = self.selected.get('name') or addr
        self._set_status(f'Connecting to {name}…','CONNECTING')
        self.scan_btn.disabled = True
        self._run_ble(self._connect_device(addr, name))

    async def _connect_device(self, addr, name):
        for attempt in range(3):
            try:
                client = BleakClient(addr)
                try:
                    client.set_disconnected_callback(
                        lambda c: Clock.schedule_once(lambda dt: self._on_disconnected(c.address)))
                except AttributeError: pass
                await client.connect(timeout=15.0)
                self.connections[addr] = client
                Clock.schedule_once(lambda dt: self._on_connected(addr, name)); return
            except (BleakError, OSError) as e:
                if attempt < 2: await asyncio.sleep(2)
                else:
                    err = str(e)
                    Clock.schedule_once(lambda dt: self._on_connect_failed(addr, name, err))

    def _on_connected(self, addr, name):
        self.scan_btn.disabled = False
        self._set_status(f'Connected: {name}','CONNECTED')
        self._update_item_connection(addr, True)
        if self.selected and self.selected['address'] == addr:
            self._refresh_opts(); self._refresh_ctrl()

    def _on_connect_failed(self, addr, name, reason):
        self.scan_btn.disabled = False
        self._set_status(f'Connection failed: {name} — {reason}','ERROR')

    def _do_disconnect(self, *_):
        if not self.selected: return
        addr = self.selected['address']; client = self.connections.get(addr)
        if not client: self._set_status('Not connected','INFO'); return
        self._run_ble(self._disconnect_device(addr, client))

    async def _disconnect_device(self, addr, client):
        try: await client.disconnect()
        except BleakError as e: log.warning('Disconnect error: %s', e)
        finally: Clock.schedule_once(lambda dt: self._on_disconnected(addr))

    async def _force_disconnect(self, client):
        try:
            if client.is_connected: await client.disconnect()
        except Exception: pass

    def _on_disconnected(self, addr):
        self.connections.pop(addr, None)
        label = self.registry.get(addr, {}).get('name') or addr
        self._set_status(f'Disconnected: {label}','IDLE')
        self._update_item_connection(addr, False)
        if self.selected and self.selected['address'] == addr:
            self._refresh_opts(); self._refresh_ctrl()

    def _update_item_connection(self, addr, connected):
        for item in self._left_list.children:
            if isinstance(item, DeviceItem) and item.address == addr:
                item.set_connected(connected); break

    def _create_group_popup(self, *_):
        wrap = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(16))
        wrap.add_widget(lbl('Group name:','cyan_dim',size=10))
        name_in = TextInput(hint_text='e.g. Bedroom Pair', font_size=dp(13), multiline=False,
                            size_hint_y=None, height=dp(40), background_color=(0.04,0.04,0.10,1),
                            foreground_color=C['white'], cursor_color=C['cyan'], padding=(dp(8),dp(10)))
        wrap.add_widget(name_in)
        wrap.add_widget(lbl('Select lights:','cyan_dim',size=10))
        scroll = ScrollView(size_hint_y=None, height=dp(160))
        cb_grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        cb_grid.bind(minimum_height=cb_grid.setter('height'))
        checkboxes = {}
        for addr, info in self.registry.items():
            if info.get('type') == 'light':
                row = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(8))
                cb = CheckBox(size_hint_x=None, width=dp(30), color=C['purple'])
                row.add_widget(cb); row.add_widget(lbl(info.get('name',addr),'white',size=10,height=dp(30)))
                cb_grid.add_widget(row); checkboxes[addr] = cb
        scroll.add_widget(cb_grid); wrap.add_widget(scroll)
        p = self._popup('CREATE GROUP', wrap, size=(0.45, 0.60))
        def confirm(*_):
            gname = name_in.text.strip()
            if not gname: return
            selected = [a for a,c in checkboxes.items() if c.active]
            if not selected: return
            self.groups[gname] = selected; _save_json(GROUPS_PATH, self.groups)
            self._set_status(f'Group "{gname}" created','INFO')
            p.dismiss()
            if self._active_tab == 'groups': self._load_groups_tab()
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        row.add_widget(btn('CREATE','purple',confirm)); row.add_widget(btn('CANCEL','red',lambda x: p.dismiss()))
        wrap.add_widget(row); p.open()

    def _select_group(self, item):
        self._multi_mode = True; self._multi_sel = {}
        self._switch_tab('saved')
        Clock.schedule_once(lambda dt: self._activate_group_lights(item.addresses), 0.1)

    def _activate_group_lights(self, addresses):
        for child in self._left_list.children:
            if isinstance(child, DeviceItem) and child.address in addresses:
                self._multi_sel[child.address] = child; child.set_multi_selected(True)
        self._refresh_ctrl_multi()

    def _delete_group(self, name):
        self.groups.pop(name, None); _save_json(GROUPS_PATH, self.groups)
        self._set_status(f'Group "{name}" deleted','INFO'); self._load_groups_tab()

    def _open_scenes_popup(self, *_):
        wrap = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(16))
        if not self.scenes:
            wrap.add_widget(lbl('No scenes saved yet.','white_dim',size=10))
        else:
            scroll = ScrollView(size_hint_y=None, height=dp(200))
            grid = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
            grid.bind(minimum_height=grid.setter('height'))
            for sname in list(self.scenes.keys()):
                row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
                row.add_widget(lbl(sname,'purple',size=11,bold=True,height=dp(42)))
                row.add_widget(btn('▶ RUN','green',lambda x,n=sname: self._run_scene(n),height=dp(34)))
                row.add_widget(btn('✕','red',lambda x,n=sname: self._delete_scene(n),height=dp(34)))
                grid.add_widget(row)
            scroll.add_widget(grid); wrap.add_widget(scroll)
        p = self._popup('SCENES', wrap, size=(0.50, 0.60))
        btm = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        btm.add_widget(btn('+ NEW SCENE','purple',
            lambda x: (p.dismiss(), Clock.schedule_once(lambda dt: self._create_scene_popup(), 0.1))))
        btm.add_widget(btn('CLOSE','cyan',lambda x: p.dismiss()))
        wrap.add_widget(btm); p.open()

    def _create_scene_popup(self, *_):
        wrap = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(16))
        wrap.add_widget(lbl('Scene name:','cyan_dim',size=10))
        name_in = TextInput(hint_text='e.g. Movie Mode', font_size=dp(13), multiline=False,
                            size_hint_y=None, height=dp(40), background_color=(0.04,0.04,0.10,1),
                            foreground_color=C['white'], cursor_color=C['cyan'], padding=(dp(8),dp(10)))
        wrap.add_widget(name_in)
        wrap.add_widget(lbl('Select lights:','cyan_dim',size=10))
        scroll = ScrollView(size_hint_y=None, height=dp(110))
        cb_grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        cb_grid.bind(minimum_height=cb_grid.setter('height'))
        checkboxes = {}
        for addr, info in self.registry.items():
            if info.get('type') == 'light':
                row = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(8))
                cb = CheckBox(size_hint_x=None, width=dp(28), color=C['purple'])
                row.add_widget(cb); row.add_widget(lbl(info.get('name',addr),'white',size=10,height=dp(28)))
                cb_grid.add_widget(row); checkboxes[addr] = cb
        scroll.add_widget(cb_grid); wrap.add_widget(scroll)
        wrap.add_widget(lbl('Brightness:','cyan_dim',size=10))
        bright_sl = mk_slider(); wrap.add_widget(bright_sl)
        wrap.add_widget(lbl('Color:','cyan_dim',size=10))
        sel_c = {'r':255,'g':255,'b':220}
        cr = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(5))
        for (label,(r,g,b)),ck in zip([('WHITE',(255,255,220)),('WARM',(255,160,40)),('RED',(255,20,20)),
                ('BLUE',(20,140,255)),('GREEN',(20,255,80)),('PURPLE',(160,40,255))],
                ['white','yellow','red','cyan','green','purple']):
            def _pick(x,ri=r,gi=g,bi=b): sel_c['r']=ri; sel_c['g']=gi; sel_c['b']=bi
            cr.add_widget(btn(label,ck,_pick,height=dp(34)))
        wrap.add_widget(cr)
        p = self._popup('NEW SCENE', wrap, size=(0.50, 0.76))
        def save_scene(*_):
            sname = name_in.text.strip()
            if not sname: return
            addrs = [a for a,c in checkboxes.items() if c.active]
            if not addrs: return
            self.scenes[sname] = {'addresses':addrs,'brightness':int(bright_sl.value),'r':sel_c['r'],'g':sel_c['g'],'b':sel_c['b']}
            _save_json(SCENES_PATH, self.scenes)
            self._set_status(f'Scene "{sname}" saved','INFO'); p.dismiss()
        btm = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        btm.add_widget(btn('SAVE SCENE','purple',save_scene)); btm.add_widget(btn('CANCEL','red',lambda x: p.dismiss()))
        wrap.add_widget(btm); p.open()

    def _run_scene(self, scene_name):
        scene = self.scenes.get(scene_name)
        if not scene: return
        ips = [self._govee_ip(a) for a in scene.get('addresses',[]) if self._govee_ip(a)]
        if not ips:
            self._set_status(f'Scene "{scene_name}": no Govee IPs found','ERROR'); return
        brightness = scene.get('brightness',100)
        r = scene.get('r',255); g = scene.get('g',255); b = scene.get('b',220)
        def _do():
            for ip in ips:
                GOVEE.turn_on(ip); GOVEE.set_brightness(ip,brightness); GOVEE.set_color(ip,r,g,b)
        threading.Thread(target=_do, daemon=True).start()
        self._set_status(f'Scene "{scene_name}" → {len(ips)} light(s)','CMD')

    def _delete_scene(self, name):
        self.scenes.pop(name,None); _save_json(SCENES_PATH,self.scenes)
        self._set_status(f'Scene "{name}" deleted','INFO')

    def _popup(self, title, content, size=(0.44, 0.42)):
        return Popup(title=title, title_color=C['cyan'], content=content, size_hint=size,
                     background_color=(0.040,0.032,0.090,1),
                     separator_color=C['cyan'][:3]+(0.35,), title_size=dp(13))

    def _open_rename_popup(self, *_):
        if not self.selected: return
        wrap = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(16))
        wrap.add_widget(lbl('New name:','cyan_dim',size=10))
        txt = TextInput(text=self.selected.get('name',''), font_size=dp(13), multiline=False,
                        size_hint_y=None, height=dp(40), background_color=(0.04,0.04,0.10,1),
                        foreground_color=C['white'], cursor_color=C['cyan'], padding=(dp(8),dp(10)))
        wrap.add_widget(txt)
        p = self._popup('RENAME DEVICE', wrap)
        def confirm(*_):
            new = txt.text.strip()
            if not new: return
            addr = self.selected['address']
            self.registry.setdefault(addr,{})['name'] = new
            if not _save_json(REGISTRY_PATH, self.registry): self._set_status('Save failed','ERROR'); return
            self.selected['name'] = new
            if self.sel_item: self.sel_item.update_name(new)
            self._set_status(f'Renamed → {new}','INFO')
            self._refresh_opts(); self._refresh_ctrl(); p.dismiss()
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        row.add_widget(btn('CONFIRM','green',confirm)); row.add_widget(btn('CANCEL','red',lambda x: p.dismiss()))
        wrap.add_widget(row); p.open()

    def _open_save_popup(self, *_):
        if not self.selected: return
        addr = self.selected['address']; saved = self.registry.get(addr,{})
        wrap = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(16))
        wrap.add_widget(lbl('Device name:','cyan_dim',size=10))
        name_in = TextInput(text=saved.get('name') or self.selected.get('name',''),
                            font_size=dp(13), multiline=False, size_hint_y=None, height=dp(40),
                            background_color=(0.04,0.04,0.10,1),
                            foreground_color=C['white'], cursor_color=C['cyan'], padding=(dp(8),dp(10)))
        wrap.add_widget(name_in)
        wrap.add_widget(lbl('Device type:','cyan_dim',size=10))
        type_spin = Spinner(text=saved.get('type','generic'), values=DEVICE_TYPES,
                            size_hint_y=None, height=dp(36), background_color=(0.04,0.04,0.10,1),
                            color=C['white'], font_size=dp(11))
        wrap.add_widget(type_spin)
        govee_spinner = None
        if saved.get('type')=='light' or self.selected.get('type')=='light':
            wrap.add_widget(lbl('Govee light (LAN):','cyan_dim',size=10))
            govee_vals = ['None'] + [f"{v['sku']} ({v['ip']})" for v in self._govee_devs.values()]
            cur_ip = saved.get('govee_ip','')
            cur_sel = next((f"{v['sku']} ({v['ip']})" for v in self._govee_devs.values() if v['ip']==cur_ip),'None')
            govee_spinner = Spinner(text=cur_sel, values=govee_vals,
                                    size_hint_y=None, height=dp(36), background_color=(0.04,0.04,0.10,1),
                                    color=C['yellow'], font_size=dp(11))
            wrap.add_widget(govee_spinner)
            if not self._govee_devs:
                wrap.add_widget(lbl('Tap FIND GOVEE first to populate list','yellow_dim',size=8.5))
        p = self._popup('SAVE DEVICE', wrap, size=(0.46, 0.56))
        def confirm(*_):
            name = name_in.text.strip() or 'Unknown'; dtype = type_spin.text
            entry = {'name':name,'type':dtype,'last_rssi':self.selected.get('rssi',-70)}
            if govee_spinner and govee_spinner.text != 'None':
                for v in self._govee_devs.values():
                    if f"{v['sku']} ({v['ip']})" == govee_spinner.text:
                        entry['govee_ip'] = v['ip']; break
            self.registry[addr] = entry
            if not _save_json(REGISTRY_PATH, self.registry): self._set_status('Save failed','ERROR'); return
            self.selected['name'] = name; self.selected['type'] = dtype
            if self.sel_item: self.sel_item.update_name(name); self.sel_item.dtype = dtype
            self._set_status(f'Saved: {name}  [{dtype}]','INFO')
            self._refresh_opts(); self._refresh_ctrl(); p.dismiss()
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        row.add_widget(btn('SAVE','cyan',confirm)); row.add_widget(btn('CANCEL','red',lambda x: p.dismiss()))
        wrap.add_widget(row); p.open()

    def _remove_device(self, *_):
        if not self.selected: return
        addr = self.selected['address']; name = self.registry.get(addr,{}).get('name',addr)
        self.registry.pop(addr,None)
        if not _save_json(REGISTRY_PATH, self.registry): self._set_status('Save failed','ERROR'); return
        self._set_status(f'Removed: {name}','INFO')
        self._refresh_opts(); self._refresh_ctrl()

    def _set_status(self, text, state='IDLE'):
        colors = {'IDLE':C['cyan_dim'],'SCANNING':C['green'],'CONNECTED':C['green'],
                  'CONNECTING':C['yellow'],'CMD':C['yellow'],'INFO':C['white_dim'],'ERROR':C['red']}
        c = colors.get(state, C['cyan_dim'])
        self.status_lbl.text = f'● {text}'; self.status_lbl.color = c
        dots = {'SCANNING':'▶','CONNECTED':'●','CONNECTING':'◌','ERROR':'✕','CMD':'▷'}
        self.bar_lbl.text = f'{dots.get(state,"●")}  {text}'; self.bar_lbl.color = c

if __name__ == '__main__':
    DianaApp().run()
