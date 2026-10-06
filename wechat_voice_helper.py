import os
import sys
import time
import threading
import subprocess
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import winreg
import ctypes
from ctypes import wintypes
import comtypes
from comtypes import GUID, IUnknown, COMMETHOD, HRESULT

# 隐藏 pygame 欢迎语
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
import pygame
import pygame._sdl2.audio as sdl2_audio
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

# =========================================================================
# Windows CoreAudio & PolicyConfig 接口定义
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


# =========================================================================
# 音频设备管理类 (设备重命名、清理冗余输出、自动切流)
# =========================================================================
class AudioDeviceManager:
    @staticmethod
    def ensure_friendly_names_and_cleanup():
        """重命名虚拟声卡/麦克风，并禁用/删除冗余的 CABLE In 16ch 输出设备"""
        # 1. 禁用无关设备: CABLE In 16ch
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

        # 2. 命名 Capture 录音端 -> 微信专用 (虚拟麦克风)
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

        # 3. 命名 Render 播放端 -> 微信专用 (虚拟声卡)
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
    def get_current_default_mic():
        """获取当前系统默认麦克风的 ID 与友好名称"""
        try:
            enum = comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, interface=IMMDeviceEnumerator)
            def_dev = enum.GetDefaultAudioEndpoint(1, 0)
            store = def_dev.OpenPropertyStore(0)
            name = store.GetValue(ctypes.byref(PKEY_Device_FriendlyName)).u.pwszVal
            return def_dev.GetId(), name
        except Exception as e:
            print("Get default mic error:", e)
            return None, "未知麦克风"

    @staticmethod
    def get_virtual_mic_info():
        """获取微信虚拟麦克风的 ID 与名称"""
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
            print("Get virtual mic error:", e)
        return None, None

    @staticmethod
    def set_default_mic(device_id):
        """设置默认麦克风 (同时更新 Console, Multimedia, Communications 角色)"""
        if not device_id:
            return False
        try:
            policy = comtypes.CoCreateInstance(CLSID_CPolicyConfigClient, interface=IPolicyConfig)
            for role in [0, 1, 2]:
                policy.SetDefaultEndpoint(device_id, role)
            return True
        except Exception as e:
            print("Set default mic error:", e)
            return False

    @staticmethod
    def get_virtual_render_name():
        """获取 pygame 播放时用的虚拟声卡名字 (保证 SDL2 初始化后读取)"""
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
            print("Get SDL2 render device error:", e)
        return None


# =========================================================================
# 主程序 GUI
# =========================================================================
class WeChatVoiceHelperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("微信语音发送助手 (自动切声卡版)")
        self.root.geometry("640x720")
        self.root.minsize(620, 680)

        # 启动时确保重命名与清理多余设备
        AudioDeviceManager.ensure_friendly_names_and_cleanup()

        # 状态变量
        self.current_file = None
        self.temp_wav = None
        self.duration = 0.0
        self.is_playing = False
        self.stop_requested = False
        self.split_files = []

        # 记录切换前的原始麦克风 ID 和名称
        self.original_mic_id = None
        self.original_mic_name = "日常麦克风"

        # 虚拟麦克风 ID 和名称
        self.virtual_mic_id, self.virtual_mic_name = AudioDeviceManager.get_virtual_mic_info()

        # 窗口关闭保护
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._init_audio_device()
        self._build_ui()
        self._refresh_mic_status()

    def _init_audio_device(self):
        dev_name = AudioDeviceManager.get_virtual_render_name()
        if dev_name:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.quit()
                pygame.mixer.init(devicename=dev_name)
                self.device_ready = True
                self.render_device_name = dev_name
            except Exception as e:
                self.device_ready = False
                self.render_device_name = f"初始化异常: {e}"
        else:
            self.device_ready = False
            self.render_device_name = "未找到虚拟声卡 (请检查驱动)"

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', font=('Microsoft YaHei UI', 10))
        style.configure('TButton', font=('Microsoft YaHei UI', 10), padding=6)
        style.configure('Primary.TButton', font=('Microsoft YaHei UI', 11, 'bold'), foreground='#07c160', padding=8)
        style.configure('Danger.TButton', font=('Microsoft YaHei UI', 10), padding=6)

        main_frame = ttk.Frame(self.root, padding=18)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 顶部声卡与麦克风状态卡片
        status_box = ttk.LabelFrame(main_frame, text=" 麦克风与虚拟声卡状态 (全自动接管) ", padding=12)
        status_box.pack(fill=tk.X, pady=(0, 12))

        # 当前默认麦克风
        self.lbl_current_mic = ttk.Label(status_box, text="当前默认麦克风: 检测中...", font=('Microsoft YaHei UI', 10, 'bold'), foreground='#1890ff')
        self.lbl_current_mic.pack(anchor=tk.W, pady=(0, 4))

        # 虚拟设备状态
        if self.device_ready:
            dev_desc = (
                f"✅ 设备已规范命名并绑定成功：\n"
                f"   • 麦克风端：{self.virtual_mic_name}\n"
                f"   • 投放声卡：{self.render_device_name}\n"
                f"   • 冗余设备：已清理并禁用多余的 16ch 播放设备\n"
                f"⚡ 机制：点击播放瞬间自动切入虚拟麦克风，发送完毕立即切回原麦克风！"
            )
            dev_lbl = ttk.Label(status_box, text=dev_desc, foreground='#07c160', font=('Microsoft YaHei UI', 9))
        else:
            dev_desc = f"⚠️ 虚拟声卡未就绪：{self.render_device_name}"
            dev_lbl = ttk.Label(status_box, text=dev_desc, foreground='#e64340', font=('Microsoft YaHei UI', 9, 'bold'))
        dev_lbl.pack(anchor=tk.W, pady=(0, 6))

        mic_btn_row = ttk.Frame(status_box)
        mic_btn_row.pack(fill=tk.X)
        self.btn_manual_restore = ttk.Button(mic_btn_row, text="🔄 手动恢复日常麦克风", command=self._manual_restore_mic)
        self.btn_manual_restore.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_manual_virtual = ttk.Button(mic_btn_row, text="🎙️ 手动测试切到虚拟麦克风", command=self._manual_switch_virtual)
        self.btn_manual_virtual.pack(side=tk.LEFT)

        # 2. 文件选择区
        file_box = ttk.LabelFrame(main_frame, text=" 音频文件选择 ", padding=12)
        file_box.pack(fill=tk.X, pady=(0, 12))

        btn_row = ttk.Frame(file_box)
        btn_row.pack(fill=tk.X, pady=(0, 6))

        self.btn_browse = ttk.Button(btn_row, text=" 📂 选择音频文件 (MP3/WAV/M4A/FLAC/AAC等)... ", command=self._browse_file)
        self.btn_browse.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_filename = ttk.Label(file_box, text="尚未选择文件", foreground='#666666')
        self.lbl_filename.pack(anchor=tk.W, pady=2)

        self.lbl_duration = ttk.Label(file_box, text="", font=('Microsoft YaHei UI', 10, 'bold'))
        self.lbl_duration.pack(anchor=tk.W, pady=2)

        # 切片提示与切片选择容器
        self.split_frame = ttk.Frame(file_box)
        self.lbl_split_warn = ttk.Label(self.split_frame, text="⚠️ 该音频超过微信 60 秒上限，建议切片后依次发送！", foreground='#d48806', font=('Microsoft YaHei UI', 9, 'bold'))
        self.lbl_split_warn.pack(anchor=tk.W, pady=(4, 4))

        self.btn_split = ttk.Button(self.split_frame, text="✂️ 一键智能切分为 55 秒片段", command=self._split_audio)
        self.btn_split.pack(anchor=tk.W, pady=(0, 4))

        self.split_select_frame = ttk.Frame(self.split_frame)
        ttk.Label(self.split_select_frame, text="选择要发送的切片: ").pack(side=tk.LEFT)
        self.split_combobox = ttk.Combobox(self.split_select_frame, state="readonly", width=35)
        self.split_combobox.bind("<<ComboboxSelected>>", self._on_split_selected)
        self.split_combobox.pack(side=tk.LEFT, padx=5)

        # 3. 播放与发送控制区
        control_box = ttk.LabelFrame(main_frame, text=" 发送控制与实时状态 ", padding=12)
        control_box.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        self.lbl_big_status = tk.Label(control_box, text="请先选择音频文件", font=('Microsoft YaHei UI', 12, 'bold'), fg='#333333', bg='#f0f2f5', height=3, relief=tk.GROOVE)
        self.lbl_big_status.pack(fill=tk.X, pady=(0, 10))

        self.progress_bar = ttk.Progressbar(control_box, orient=tk.HORIZONTAL, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 4))

        self.lbl_progress_time = ttk.Label(control_box, text="00:00 / 00:00", font=('Consolas', 10), foreground='#666666')
        self.lbl_progress_time.pack(anchor=tk.CENTER, pady=(0, 10))

        action_btn_row = ttk.Frame(control_box)
        action_btn_row.pack(fill=tk.X)

        self.btn_start = ttk.Button(action_btn_row, text="▶️ 开始播放 (自动切声卡+倒计时)", style='Primary.TButton', command=self._start_send_process, state=tk.DISABLED)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.btn_stop = ttk.Button(action_btn_row, text="⏹️ 停止", style='Danger.TButton', command=self._stop_playback, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.RIGHT, padx=(8, 0))

        # 4. 底部工具
        bottom_box = ttk.Frame(main_frame)
        bottom_box.pack(fill=tk.X)

        btn_cpl = ttk.Button(bottom_box, text="⚙️ 系统声音控制面板 (开启耳机侦听)", command=self._open_sound_control_panel)
        btn_cpl.pack(side=tk.LEFT)

        self.topmost_var = tk.BooleanVar(value=True)
        self.root.wm_attributes("-topmost", True)
        chk_top = ttk.Checkbutton(bottom_box, text="窗口置顶", variable=self.topmost_var, command=self._toggle_topmost)
        chk_top.pack(side=tk.RIGHT)

    def _refresh_mic_status(self):
        cur_id, cur_name = AudioDeviceManager.get_current_default_mic()
        is_virt = ('虚拟麦克风' in cur_name or 'CABLE Output' in cur_name or '微信专用' in cur_name)
        if is_virt:
            self.lbl_current_mic.config(text=f"当前默认麦克风: [虚拟麦克风已接管] {cur_name}", foreground='#07c160')
        else:
            self.lbl_current_mic.config(text=f"当前默认麦克风: [日常物理设备] {cur_name}", foreground='#1890ff')
            self.original_mic_id = cur_id
            self.original_mic_name = cur_name

    def _manual_restore_mic(self):
        if self.original_mic_id:
            AudioDeviceManager.set_default_mic(self.original_mic_id)
        self._refresh_mic_status()
        messagebox.showinfo("提示", "已切换回日常麦克风！")

    def _manual_switch_virtual(self):
        if self.virtual_mic_id:
            AudioDeviceManager.set_default_mic(self.virtual_mic_id)
        self._refresh_mic_status()
        messagebox.showinfo("提示", "已切换到微信专用虚拟麦克风！")

    def _toggle_topmost(self):
        self.root.wm_attributes("-topmost", self.topmost_var.get())

    def _open_sound_control_panel(self):
        try:
            subprocess.Popen(["rundll32.exe", "Shell32.dll,Control_RunDLL", "mmsys.cpl,,1"])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开声音面板: {e}")

    def _browse_file(self):
        filetypes = [
            ("音频文件", "*.mp3 *.wav *.m4a *.flac *.aac *.ogg *.wma *.opus *.amr"),
            ("所有文件", "*.*")
        ]
        path = filedialog.askopenfilename(title="选择音频文件", filetypes=filetypes)
        if path:
            self._load_audio_file(path)

    def _get_audio_duration(self, path):
        try:
            res = subprocess.run([FFMPEG_EXE, '-i', path], capture_output=True, text=True, errors='ignore')
            match = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', res.stderr)
            if match:
                h, m, s = match.groups()
                return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception as e:
            print("Get duration error:", e)
        return 0.0

    def _convert_to_temp_wav(self, input_path):
        out_wav = os.path.join(os.path.dirname(input_path), f".temp_preview_{int(time.time())}.wav")
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
            print("Convert error:", e)
            return input_path

    def _load_audio_file(self, path):
        self.current_file = path
        self.split_files = []
        self.split_frame.pack_forget()
        self.split_select_frame.pack_forget()

        self.lbl_filename.config(text=f"已选: {os.path.basename(path)}", foreground='#333333')
        dur = self._get_audio_duration(path)
        self.duration = dur

        mins = int(dur // 60)
        secs = dur % 60
        self.lbl_duration.config(text=f"时长: {mins:02d}:{secs:05.2f} 秒")

        if dur > 60:
            self.lbl_duration.config(foreground='#d48806')
            self.split_frame.pack(fill=tk.X, pady=(4, 0))
            self.lbl_big_status.config(text="⚠️ 音频超过 60 秒！建议点击上方【一键智能切分】", fg='#d48806')
        else:
            self.lbl_duration.config(foreground='#07c160')
            self.lbl_big_status.config(text="准备就绪！点击【开始播放】自动切声卡并发送", fg='#07c160')

        self.btn_start.config(state=tk.NORMAL)
        self.lbl_progress_time.config(text=f"00:00 / {int(dur // 60):02d}:{int(dur % 60):02d}")
        self.progress_bar['value'] = 0

    def _split_audio(self):
        if not self.current_file or self.duration <= 60:
            return

        base_name, ext = os.path.splitext(self.current_file)
        target_dir = os.path.dirname(self.current_file)
        pure_name = os.path.basename(base_name)

        segment_len = 55.0
        total_parts = int(self.duration // segment_len) + (1 if self.duration % segment_len > 0 else 0)

        self.lbl_big_status.config(text="正在切分音频，请稍候...", fg='#1890ff')
        self.root.update()

        self.split_files = []
        for i in range(total_parts):
            start_sec = i * segment_len
            part_path = os.path.join(target_dir, f"{pure_name}_第{i+1}段{ext}")
            cmd = [
                FFMPEG_EXE, '-y',
                '-ss', str(start_sec),
                '-t', str(segment_len),
                '-i', self.current_file,
                '-c', 'copy',
                part_path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            part_dur = self._get_audio_duration(part_path)
            self.split_files.append((part_path, part_dur))

        options = [f"第 {idx+1} 段 ({dur:.1f}s) - {os.path.basename(p)}" for idx, (p, dur) in enumerate(self.split_files)]
        self.split_combobox['values'] = options
        self.split_combobox.current(0)
        self.split_select_frame.pack(fill=tk.X, pady=(4, 0))

        self._on_split_selected(None)
        messagebox.showinfo("切分完成", f"已成功将音频切分为 {total_parts} 个片段（每段 ≤55 秒）！")

    def _on_split_selected(self, event):
        idx = self.split_combobox.current()
        if 0 <= idx < len(self.split_files):
            part_path, part_dur = self.split_files[idx]
            self.current_file = part_path
            self.duration = part_dur
            mins = int(part_dur // 60)
            secs = part_dur % 60
            self.lbl_duration.config(text=f"当前切片时长: {mins:02d}:{secs:05.2f} 秒", foreground='#07c160')
            self.lbl_big_status.config(text=f"已选切片: 第 {idx+1} 段\n点击【开始播放】准备发送！", fg='#07c160')
            self.lbl_progress_time.config(text=f"00:00 / {mins:02d}:{int(secs):02d}")
            self.progress_bar['value'] = 0

    def _start_send_process(self):
        if not self.current_file or self.is_playing:
            return

        self.btn_start.config(state=tk.DISABLED)
        self.btn_browse.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.stop_requested = False

        t = threading.Thread(target=self._play_worker, daemon=True)
        t.start()

    def _stop_playback(self):
        self.stop_requested = True
        try:
            pygame.mixer.music.stop()
        except:
            pass

    def _play_worker(self):
        comtypes.CoInitialize()
        try:
            # 1. 确保虚拟声卡播放端精准绑定
            target_render = AudioDeviceManager.get_virtual_render_name()
            if not target_render:
                self.lbl_big_status.config(text="错误：未找到【微信专用 (虚拟声卡)】！请检查驱动", fg='#e64340')
                return

            if pygame.mixer.get_init():
                pygame.mixer.quit()
            pygame.mixer.init(devicename=target_render)

            # 2. 记录当前默认麦克风（若当前不是虚拟麦克风）
            cur_id, cur_name = AudioDeviceManager.get_current_default_mic()
            if '虚拟麦克风' not in cur_name and 'CABLE Output' not in cur_name and '微信专用' not in cur_name:
                self.original_mic_id = cur_id
                self.original_mic_name = cur_name

            # 3. 自动将系统默认麦克风切换到微信虚拟麦克风
            if self.virtual_mic_id:
                AudioDeviceManager.set_default_mic(self.virtual_mic_id)
            self._refresh_mic_status()

            # 4. 倒计时 3 秒
            countdown_steps = [
                ("🎙️ 麦克风已自动切换至：【微信专用 (虚拟麦克风)】\n【3】请在微信中打开目标聊天框...", "#1890ff"),
                ("【2】请长按微信 Alt 键（或按住话筒）准备录音！", "#fa8c16"),
                ("【1】保持按住 Alt 键不松手，马上开始投放声音！", "#d4380d"),
            ]

            for text, color in countdown_steps:
                if self.stop_requested:
                    break
                self.lbl_big_status.config(text=text, fg=color)
                for _ in range(10):
                    if self.stop_requested:
                        break
                    time.sleep(0.1)

            if self.stop_requested:
                self._reset_ui("已取消播放")
                return

            # 5. 播放音频
            self.lbl_big_status.config(text="🔊 正在向微信录音投放音频...\n请务必【保持按住 Alt 键】！", fg='#07c160')
            wav_path = self._convert_to_temp_wav(self.current_file)
            self.temp_wav = wav_path

            pygame.mixer.music.load(wav_path)
            pygame.mixer.music.play()
            self.is_playing = True
            start_time = time.time()

            total_dur = self.duration
            while pygame.mixer.music.get_busy() and not self.stop_requested:
                elapsed = time.time() - start_time
                pct = min(100.0, (elapsed / total_dur) * 100) if total_dur > 0 else 0
                self.progress_bar['value'] = pct

                el_min, el_sec = int(elapsed // 60), int(elapsed % 60)
                tot_min, tot_sec = int(total_dur // 60), int(total_dur % 60)
                self.lbl_progress_time.config(text=f"{el_min:02d}:{el_sec:02d} / {tot_min:02d}:{tot_sec:02d}")
                time.sleep(0.1)

            pygame.mixer.music.stop()

            if not self.stop_requested:
                self.progress_bar['value'] = 100
                self.lbl_big_status.config(
                    text="🎉 播放已完成！\n请立即【松开微信 Alt 键】完成发送！\n(等待 1.5 秒缓冲后自动恢复麦克风...)",
                    fg='#07c160'
                )
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except:
                    pass

                # 给用户 1.5 秒松手缓冲时间，确保微信完整将尾音封包保存，防止过早切断麦克风
                time.sleep(1.5)
            else:
                self.lbl_big_status.config(text="已停止播放", fg='#666666')

        except Exception as e:
            self.lbl_big_status.config(text=f"发生错误: {e}", fg='#e64340')

        finally:
            # 6. 安全切回原来的日常麦克风！
            if self.original_mic_id:
                AudioDeviceManager.set_default_mic(self.original_mic_id)
            self._refresh_mic_status()

            self.is_playing = False
            if self.temp_wav and os.path.exists(self.temp_wav) and self.temp_wav != self.current_file:
                try:
                    os.remove(self.temp_wav)
                except:
                    pass
            self.btn_start.config(state=tk.NORMAL)
            self.btn_browse.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            comtypes.CoUninitialize()

    def _reset_ui(self, msg):
        self.lbl_big_status.config(text=msg, fg='#666666')
        self.btn_start.config(state=tk.NORMAL)
        self.btn_browse.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0

    def _on_close(self):
        if self.original_mic_id:
            try:
                AudioDeviceManager.set_default_mic(self.original_mic_id)
            except:
                pass
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    app = WeChatVoiceHelperApp(root)
    root.mainloop()
