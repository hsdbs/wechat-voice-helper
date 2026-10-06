import os
import sys
import time
import threading
import subprocess
import re
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import winreg
import ctypes
from ctypes import wintypes
import comtypes
from comtypes import GUID, IUnknown, COMMETHOD, HRESULT

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
import pygame
import pygame._sdl2.audio as sdl2_audio
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(WEB_DIR, exist_ok=True)

# =========================================================================
# Windows CoreAudio & PolicyConfig 接口
# =========================================================================
CLSID_MMDeviceEnumerator = GUID('{BCDE0395-E52F-467C-8E3D-C4579291692E}')
IID_IMMDeviceEnumerator = GUID('{A95664D2-9614-4F35-A746-DE8DB63617E6}')

class PROPERTYKEY(ctypes.Structure):
    _fields_ = [('fmtid', GUID), ('pid', wintypes.DWORD)]

class PROPVARIANT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('pwszVal', wintypes.LPWSTR)]
    _fields_ = [('vt', wintypes.WORD), ('wReserved1', wintypes.WORD), ('wReserved2', wintypes.WORD), ('wReserved3', wintypes.WORD), ('u', _U)]

class IPropertyStore(IUnknown):
    _iid_ = GUID('{886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}')
    _methods_ = [
        COMMETHOD([], HRESULT, 'GetCount', (['out'], ctypes.POINTER(wintypes.DWORD), 'cProps')),
        COMMETHOD([], HRESULT, 'GetAt', (['in'], wintypes.DWORD, 'iProp'), (['out'], ctypes.POINTER(PROPERTYKEY), 'pkey')),
        COMMETHOD([], HRESULT, 'GetValue', (['in'], ctypes.POINTER(PROPERTYKEY), 'key'), (['out'], ctypes.POINTER(PROPVARIANT), 'pv')),
    ]

class IMMDevice(IUnknown):
    _iid_ = GUID('{D666063F-1587-4E43-81F1-B948E807363F}')
    _methods_ = [
        COMMETHOD([], HRESULT, 'Activate'),
        COMMETHOD([], HRESULT, 'OpenPropertyStore', (['in'], wintypes.DWORD, 'stgmAccess'), (['out'], ctypes.POINTER(ctypes.POINTER(IPropertyStore)), 'ppProperties')),
        COMMETHOD([], HRESULT, 'GetId', (['out'], ctypes.POINTER(wintypes.LPWSTR), 'ppstrId')),
        COMMETHOD([], HRESULT, 'GetState', (['out'], ctypes.POINTER(wintypes.DWORD), 'pdwState')),
    ]

class IMMDeviceCollection(IUnknown):
    _iid_ = GUID('{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}')
    _methods_ = [
        COMMETHOD([], HRESULT, 'GetCount', (['out'], ctypes.POINTER(wintypes.UINT), 'pcDevices')),
        COMMETHOD([], HRESULT, 'Item', (['in'], wintypes.UINT, 'nDevice'), (['out'], ctypes.POINTER(ctypes.POINTER(IMMDevice)), 'ppDevice')),
    ]

class IMMDeviceEnumerator(IUnknown):
    _iid_ = IID_IMMDeviceEnumerator
    _methods_ = [
        COMMETHOD([], HRESULT, 'EnumAudioEndpoints', (['in'], wintypes.DWORD, 'dataFlow'), (['in'], wintypes.DWORD, 'dwStateMask'), (['out'], ctypes.POINTER(ctypes.POINTER(IMMDeviceCollection)), 'ppDevices')),
        COMMETHOD([], HRESULT, 'GetDefaultAudioEndpoint', (['in'], wintypes.DWORD, 'dataFlow'), (['in'], wintypes.DWORD, 'role'), (['out'], ctypes.POINTER(ctypes.POINTER(IMMDevice)), 'ppEndpoint')),
    ]

CLSID_CPolicyConfigClient = GUID('{870AF99C-171D-4F9E-AF0D-E63DF40C2BC9}')
IID_IPolicyConfig = GUID('{F8679F50-850A-41CF-9C72-430F290290C8}')

class IPolicyConfig(IUnknown):
    _iid_ = IID_IPolicyConfig
    _methods_ = [
        COMMETHOD([], HRESULT, 'GetMixFormat', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['out'], ctypes.c_void_p, 'ppFormat')),
        COMMETHOD([], HRESULT, 'GetDeviceFormat', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['in'], wintypes.INT, 'bDefault'), (['out'], ctypes.c_void_p, 'ppFormat')),
        COMMETHOD([], HRESULT, 'ResetDeviceFormat', (['in'], wintypes.LPCWSTR, 'pszDeviceName')),
        COMMETHOD([], HRESULT, 'SetDeviceFormat', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['in'], ctypes.c_void_p, 'pEndpointFormat'), (['in'], ctypes.c_void_p, 'mixFormat')),
        COMMETHOD([], HRESULT, 'GetProcessingPeriod', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['in'], wintypes.INT, 'bDefault'), (['out'], ctypes.c_void_p, 'pmftDefaultPeriod'), (['out'], ctypes.c_void_p, 'pmftMinimumPeriod')),
        COMMETHOD([], HRESULT, 'SetProcessingPeriod', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['in'], ctypes.c_void_p, 'pmftPeriod')),
        COMMETHOD([], HRESULT, 'GetShareMode', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['out'], ctypes.c_void_p, 'pMode')),
        COMMETHOD([], HRESULT, 'SetShareMode', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['in'], ctypes.c_void_p, 'mode')),
        COMMETHOD([], HRESULT, 'GetPropertyValue', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['in'], ctypes.c_void_p, 'pKey'), (['out'], ctypes.c_void_p, 'pv')),
        COMMETHOD([], HRESULT, 'SetPropertyValue', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['in'], ctypes.c_void_p, 'pKey'), (['in'], ctypes.c_void_p, 'pv')),
        COMMETHOD([], HRESULT, 'SetDefaultEndpoint', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['in'], wintypes.DWORD, 'role')),
        COMMETHOD([], HRESULT, 'SetEndpointVisibility', (['in'], wintypes.LPCWSTR, 'pszDeviceName'), (['in'], wintypes.INT, 'bVisible')),
    ]

PKEY_Device_FriendlyName = PROPERTYKEY(GUID('{A45C254E-DF1C-4EFD-8020-67D146A850E0}'), 14)

def with_com(func):
    def wrapper(*args, **kwargs):
        comtypes.CoInitialize()
        try:
            return func(*args, **kwargs)
        finally:
            comtypes.CoUninitialize()
    return wrapper

class AudioDeviceManager:
    @staticmethod
    @with_com
    def ensure_friendly_names_and_cleanup():
        # 1. 禁用无关 16ch
        try:
            policy = comtypes.CoCreateInstance(CLSID_CPolicyConfigClient, interface=IPolicyConfig)
            enum = comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, interface=IMMDeviceEnumerator)
            all_rens = enum.EnumAudioEndpoints(0, 15)
            for i in range(all_rens.GetCount()):
                d = all_rens.Item(i)
                did = d.GetId()
                store = d.OpenPropertyStore(0)
                name = store.GetValue(ctypes.byref(PKEY_Device_FriendlyName)).u.pwszVal
                if '16ch' in name or 'CABLE In 16' in name:
                    policy.SetEndpointVisibility(did, 0)
                    guid_match = re.search(r'\{[0-9a-fA-F-]+\}$', did)
                    if guid_match:
                        guid = guid_match.group(0)
                        path = fr'SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render\{guid}'
                        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE)
                        winreg.SetValueEx(k, 'DeviceState', 0, winreg.REG_DWORD, 2)
                        winreg.CloseKey(k)
        except Exception as e:
            print("Cleanup 16ch error:", e)

        # 2. 命名 Capture -> 微信专用 (虚拟麦克风)
        try:
            enum = comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, interface=IMMDeviceEnumerator)
            caps = enum.EnumAudioEndpoints(1, 1)
            for i in range(caps.GetCount()):
                d = caps.Item(i)
                did = d.GetId()
                store = d.OpenPropertyStore(0)
                name = store.GetValue(ctypes.byref(PKEY_Device_FriendlyName)).u.pwszVal
                if 'CABLE Output' in name or '虚拟麦克风' in name or '微信专用' in name:
                    guid_match = re.search(r'\{[0-9a-fA-F-]+\}$', did)
                    if guid_match:
                        guid = guid_match.group(0)
                        key_path = fr'SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture\{guid}\Properties'
                        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE)
                        winreg.SetValueEx(k, '{a45c254e-df1c-4efd-8020-67d146a850e0},2', 0, winreg.REG_SZ, '微信专用')
                        winreg.SetValueEx(k, '{b3f8fa53-0004-438e-9003-51a46e139bfc},6', 0, winreg.REG_SZ, '虚拟麦克风')
                        winreg.CloseKey(k)
        except Exception as e:
            print("Rename capture device error:", e)

        # 3. 命名 Render -> 微信专用 (虚拟声卡)
        try:
            enum = comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, interface=IMMDeviceEnumerator)
            rens = enum.EnumAudioEndpoints(0, 1)
            for i in range(rens.GetCount()):
                d = rens.Item(i)
                did = d.GetId()
                store = d.OpenPropertyStore(0)
                name = store.GetValue(ctypes.byref(PKEY_Device_FriendlyName)).u.pwszVal
                if 'CABLE Input' in name or '虚拟声卡' in name or '微信专用' in name:
                    guid_match = re.search(r'\{[0-9a-fA-F-]+\}$', did)
                    if guid_match:
                        guid = guid_match.group(0)
                        key_path = fr'SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render\{guid}\Properties'
                        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE)
                        winreg.SetValueEx(k, '{a45c254e-df1c-4efd-8020-67d146a850e0},2', 0, winreg.REG_SZ, '微信专用')
                        winreg.SetValueEx(k, '{b3f8fa53-0004-438e-9003-51a46e139bfc},6', 0, winreg.REG_SZ, '虚拟声卡')
                        winreg.CloseKey(k)
        except Exception as e:
            print("Rename render device error:", e)

    @staticmethod
    @with_com
    def get_current_default_mic():
        try:
            enum = comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, interface=IMMDeviceEnumerator)
            def_dev = enum.GetDefaultAudioEndpoint(1, 0)
            store = def_dev.OpenPropertyStore(0)
            name = store.GetValue(ctypes.byref(PKEY_Device_FriendlyName)).u.pwszVal
            return def_dev.GetId(), name
        except Exception as e:
            return None, "未知麦克风"

    @staticmethod
    @with_com
    def get_virtual_mic_info():
        try:
            enum = comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, interface=IMMDeviceEnumerator)
            caps = enum.EnumAudioEndpoints(1, 1)
            for i in range(caps.GetCount()):
                d = caps.Item(i)
                st = d.OpenPropertyStore(0)
                name = st.GetValue(ctypes.byref(PKEY_Device_FriendlyName)).u.pwszVal
                if '虚拟麦克风' in name or 'CABLE Output' in name or '微信专用' in name:
                    return d.GetId(), name
        except Exception as e:
            pass
        return None, None

    @staticmethod
    @with_com
    def set_default_mic(device_id):
        if not device_id:
            return False
        try:
            policy = comtypes.CoCreateInstance(CLSID_CPolicyConfigClient, interface=IPolicyConfig)
            for role in [0, 1, 2]:
                policy.SetDefaultEndpoint(device_id, role)
            return True
        except Exception as e:
            return False

    @staticmethod
    def get_virtual_render_name():
        try:
            was_inited = pygame.mixer.get_init() is not None
            if not was_inited:
                pygame.mixer.init()
            names = sdl2_audio.get_audio_device_names(False)
            if not was_inited:
                pygame.mixer.quit()

            for n in names:
                if '微信专用' in n or '虚拟声卡' in n or 'CABLE Input' in n:
                    return n
        except Exception as e:
            pass
        return None


# =========================================================================
# 状态全局管理器
# =========================================================================
class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.current_file = None
        self.original_filename = ""
        self.duration = 0.0
        self.filesize = 0
        self.split_parts = []
        self.active_part_idx = -1

        self.is_playing = False
        self.stop_requested = False
        self.state = "idle" # idle, countdown, playing, completed, stopped, error
        self.countdown = 0
        self.elapsed = 0.0
        self.status_message = "请拖拽或选择音频文件"

        self.original_mic_id = None
        self.original_mic_name = "日常麦克风"
        self.virtual_mic_id = None
        self.virtual_mic_name = "微信专用 (虚拟麦克风)"

    def to_dict(self):
        with self.lock:
            cur_id, cur_name = AudioDeviceManager.get_current_default_mic()
            is_virt = ('虚拟麦克风' in cur_name or 'CABLE Output' in cur_name or '微信专用' in cur_name)
            return {
                "current_file": self.current_file,
                "original_filename": self.original_filename,
                "duration": round(self.duration, 2),
                "duration_str": f"{int(self.duration//60):02d}:{int(self.duration%60):02d}",
                "filesize": self.filesize,
                "split_parts": self.split_parts,
                "active_part_idx": self.active_part_idx,
                "is_playing": self.is_playing,
                "state": self.state,
                "countdown": self.countdown,
                "elapsed": round(self.elapsed, 1),
                "progress_pct": min(100.0, round((self.elapsed / self.duration * 100), 1)) if self.duration > 0 else 0,
                "status_message": self.status_message,
                "current_mic_name": cur_name,
                "is_virtual_mic_active": is_virt,
                "virtual_mic_name": self.virtual_mic_name
            }

STATE = AppState()

# 初始化设备命名
AudioDeviceManager.ensure_friendly_names_and_cleanup()
STATE.virtual_mic_id, STATE.virtual_mic_name = AudioDeviceManager.get_virtual_mic_info()
init_id, init_name = AudioDeviceManager.get_current_default_mic()
if '虚拟麦克风' not in init_name and '微信专用' not in init_name:
    STATE.original_mic_id = init_id
    STATE.original_mic_name = init_name


def fast_get_duration(path):
    """极速检测音频时长（异步调用，不卡主线程）"""
    try:
        cmd = [FFMPEG_EXE, '-i', path]
        res = subprocess.run(cmd, capture_output=True, text=True, errors='ignore')
        m = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', res.stderr)
        if m:
            h, mi, s = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(s)
    except Exception as e:
        print("fast_get_duration error:", e)
    return 0.0

def convert_to_temp_wav(input_path):
    out_wav = os.path.join(UPLOADS_DIR, f".temp_render_{int(time.time()*1000)}.wav")
    try:
        cmd = [
            FFMPEG_EXE, '-y',
            '-i', input_path,
            '-ar', '44100',
            '-ac', '2',
            '-c:a', 'pcm_s16le',
            out_wav
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return out_wav
    except Exception as e:
        print("convert_to_temp_wav error:", e)
        return input_path

def play_worker():
    comtypes.CoInitialize()
    temp_wav = None
    try:
        with STATE.lock:
            file_to_play = STATE.current_file
            total_dur = STATE.duration
            STATE.is_playing = True
            STATE.stop_requested = False
            STATE.state = "countdown"
            STATE.status_message = "正在初始化虚拟音频通道..."

        # 1. 绑定虚拟声卡
        target_render = AudioDeviceManager.get_virtual_render_name()
        if not target_render:
            with STATE.lock:
                STATE.state = "error"
                STATE.status_message = "错误：未找到【微信专用 (虚拟声卡)】！请检查驱动"
                STATE.is_playing = False
            return

        if pygame.mixer.get_init():
            pygame.mixer.quit()
        pygame.mixer.init(devicename=target_render)

        # 2. 自动切换到微信虚拟麦克风
        cur_id, cur_name = AudioDeviceManager.get_current_default_mic()
        if '虚拟麦克风' not in cur_name and '微信专用' not in cur_name:
            STATE.original_mic_id = cur_id
            STATE.original_mic_name = cur_name

        if STATE.virtual_mic_id:
            AudioDeviceManager.set_default_mic(STATE.virtual_mic_id)

        # 3. 倒计时 3 秒
        countdown_texts = [
            (3, "【3】请在微信中打开目标聊天框..."),
            (2, "【2】请长按键盘 Alt 键（或按住话筒）准备录音！"),
            (1, "【1】保持按住 Alt 键不松手，马上开始投放声音！")
        ]
        for sec, txt in countdown_texts:
            if STATE.stop_requested:
                break
            with STATE.lock:
                STATE.countdown = sec
                STATE.status_message = txt
            for _ in range(10):
                if STATE.stop_requested:
                    break
                time.sleep(0.1)

        if STATE.stop_requested:
            with STATE.lock:
                STATE.state = "stopped"
                STATE.status_message = "已取消发送"
            return

        # 4. 播放音频
        with STATE.lock:
            STATE.state = "playing"
            STATE.countdown = 0
            STATE.status_message = "🔊 正在向微信录音投放音频... 请【保持按住 Alt 键】！"

        temp_wav = convert_to_temp_wav(file_to_play)
        pygame.mixer.music.load(temp_wav)
        pygame.mixer.music.play()

        start_time = time.time()
        while pygame.mixer.music.get_busy() and not STATE.stop_requested:
            el = time.time() - start_time
            with STATE.lock:
                STATE.elapsed = el
            time.sleep(0.08)

        pygame.mixer.music.stop()

        if not STATE.stop_requested:
            with STATE.lock:
                STATE.elapsed = total_dur
                STATE.state = "completed"
                STATE.status_message = "🎉 播放已完成！请立即【松开微信 Alt 键】完成发送！"
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except:
                pass
            # 给用户 1.5 秒松手缓冲时间
            time.sleep(1.5)
        else:
            with STATE.lock:
                STATE.state = "stopped"
                STATE.status_message = "已停止播放"

    except Exception as e:
        with STATE.lock:
            STATE.state = "error"
            STATE.status_message = f"播放出错: {e}"

    finally:
        # 5. 安全还原麦克风
        if STATE.original_mic_id:
            AudioDeviceManager.set_default_mic(STATE.original_mic_id)

        with STATE.lock:
            STATE.is_playing = False

        if temp_wav and os.path.exists(temp_wav) and temp_wav != file_to_play:
            try:
                os.remove(temp_wav)
            except:
                pass
        comtypes.CoUninitialize()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class VoiceWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 静默常规访问日志，减少终端刷屏
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '/index.html':
            index_path = os.path.join(WEB_DIR, 'index.html')
            if not os.path.exists(index_path):
                self.send_error(404, "index.html not found")
                return
            with open(index_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path == '/api/status':
            self._send_json(STATE.to_dict())
            return

        elif path.startswith('/uploads/'):
            # 允许前端试听预览已上传的音频
            rel_file = urllib.parse.unquote(path[9:])
            file_path = os.path.join(UPLOADS_DIR, rel_file)
            if os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                mime = 'audio/mpeg' if ext == '.mp3' else ('audio/wav' if ext == '.wav' else 'application/octet-stream')
                size = os.path.getsize(file_path)
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(size))
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
                return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/api/upload':
            # 支持极速二进制流上传
            query = urllib.parse.parse_qs(parsed.query)
            filename = query.get('filename', ['audio.mp3'])[0]
            filename = urllib.parse.unquote(filename)

            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_json({"error": "Empty body"}, 400)
                return

            save_path = os.path.join(UPLOADS_DIR, filename)
            with open(save_path, 'wb') as f:
                remaining = content_length
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)

            # 获取音频时长
            dur = fast_get_duration(save_path)
            size = os.path.getsize(save_path)

            with STATE.lock:
                STATE.current_file = save_path
                STATE.original_filename = filename
                STATE.duration = dur
                STATE.filesize = size
                STATE.split_parts = []
                STATE.active_part_idx = -1
                STATE.elapsed = 0.0
                STATE.state = "idle"
                if dur > 60:
                    STATE.status_message = f"⚠️ 音频时长 {dur:.1f} 秒，已超微信 60 秒上限！建议点击【智能切分】"
                else:
                    STATE.status_message = f"已就绪！点击【开始发送】自动切声卡并投放"

            self._send_json({
                "success": True,
                "filename": filename,
                "duration": dur,
                "duration_str": f"{int(dur//60):02d}:{int(dur%60):02d}",
                "is_over_limit": dur > 60,
                "preview_url": f"/uploads/{urllib.parse.quote(filename)}"
            })
            return

        elif path == '/api/split':
            if not STATE.current_file or STATE.duration <= 60:
                self._send_json({"error": "No file or not over 60s"}, 400)
                return

            base_name, ext = os.path.splitext(STATE.current_file)
            pure_name = os.path.splitext(STATE.original_filename)[0]
            segment_len = 55.0
            total_parts = int(STATE.duration // segment_len) + (1 if STATE.duration % segment_len > 0 else 0)

            parts = []
            for i in range(total_parts):
                start_sec = i * segment_len
                part_file_name = f"{pure_name}_第{i+1}段{ext}"
                part_path = os.path.join(UPLOADS_DIR, part_file_name)
                cmd = [
                    FFMPEG_EXE, '-y',
                    '-ss', str(start_sec),
                    '-t', str(segment_len),
                    '-i', STATE.current_file,
                    '-c', 'copy',
                    part_path
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                part_dur = fast_get_duration(part_path)
                parts.append({
                    "idx": i,
                    "name": f"第 {i+1} 段 ({part_dur:.1f}s)",
                    "filename": part_file_name,
                    "path": part_path,
                    "duration": part_dur,
                    "preview_url": f"/uploads/{urllib.parse.quote(part_file_name)}"
                })

            with STATE.lock:
                STATE.split_parts = parts
                if parts:
                    STATE.active_part_idx = 0
                    STATE.current_file = parts[0]["path"]
                    STATE.duration = parts[0]["duration"]
                    STATE.status_message = f"已智能切分为 {total_parts} 段！当前已选中第 1 段"

            self._send_json({"success": True, "parts": parts})
            return

        elif path == '/api/select_part':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
            idx = int(data.get('idx', 0))

            with STATE.lock:
                if 0 <= idx < len(STATE.split_parts):
                    p = STATE.split_parts[idx]
                    STATE.active_part_idx = idx
                    STATE.current_file = p["path"]
                    STATE.duration = p["duration"]
                    STATE.elapsed = 0.0
                    STATE.status_message = f"已选中：{p['name']}，点击【开始发送】"
                    self._send_json({"success": True, "part": p})
                    return
            self._send_json({"error": "Invalid index"}, 400)
            return

        elif path == '/api/play':
            if STATE.is_playing:
                self._send_json({"error": "Already playing"}, 400)
                return
            t = threading.Thread(target=play_worker, daemon=True)
            t.start()
            self._send_json({"success": True})
            return

        elif path == '/api/stop':
            STATE.stop_requested = True
            try:
                pygame.mixer.music.stop()
            except:
                pass
            self._send_json({"success": True})
            return

        elif path == '/api/restore_mic':
            if STATE.original_mic_id:
                AudioDeviceManager.set_default_mic(STATE.original_mic_id)
            self._send_json({"success": True})
            return

        elif path == '/api/switch_virtual_mic':
            if STATE.virtual_mic_id:
                AudioDeviceManager.set_default_mic(STATE.virtual_mic_id)
            self._send_json({"success": True})
            return

        elif path == '/api/open_sound_cpl':
            subprocess.Popen(["rundll32.exe", "Shell32.dll,Control_RunDLL", "mmsys.cpl,,1"])
            self._send_json({"success": True})
            return

        elif path == '/api/shutdown':
            self._send_json({"success": True})
            def do_shutdown():
                time.sleep(0.5)
                try:
                    if STATE.original_mic_id:
                        AudioDeviceManager.set_default_mic(STATE.original_mic_id)
                except:
                    pass
                os._exit(0)
            threading.Thread(target=do_shutdown, daemon=True).start()
            return

        self.send_error(404, "Not Found")


def launch_app_window(port):
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    ]
    for p in edge_paths:
        if os.path.exists(p):
            cmd = f'"{p}" --app=http://127.0.0.1:{port} --window-size=680,820'
            subprocess.Popen(cmd, shell=True)
            return True

    import webbrowser
    webbrowser.open(f"http://127.0.0.1:{port}")
    return False

if __name__ == '__main__':
    port = 8765

    # 1. 检查是否已有实例在运行，如果有直接唤起窗口并退出
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=0.8) as resp:
            if resp.status == 200:
                print("Server is already running, opening app window...")
                launch_app_window(port)
                sys.exit(0)
    except Exception:
        pass

    # 2. 启动本地多线程服务
    try:
        server = ThreadedHTTPServer(('127.0.0.1', port), VoiceWebHandler)
    except OSError as e:
        print(f"Port {port} error: {e}")
        # 如果端口被占用尝试打开界面
        launch_app_window(port)
        sys.exit(1)

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"Server started at http://127.0.0.1:{port}")

    # 3. 打开极简现代 Web 独立窗口 (无地址栏、无多余工具栏)
    launch_app_window(port)

    # 主线程维持服务
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
