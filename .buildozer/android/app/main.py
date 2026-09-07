# -*- coding: utf-8 -*-
import rpc
rpc_server, rpc_thread = rpc.start_rpc_server(port=1133, key='', globals=globals(), locals=locals())

import os
import traceback
import hashlib
import random
import struct
import threading
import time
import io
import json

from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.camera import Camera
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line

from jnius import autoclass, PythonJavaClass, java_method, cast

# ------------------- Java classes --------------------
try:
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    YoloBridgeClass = autoclass('org.qgb.yolo.YoloBridge')
    YoloBridgeInstance = YoloBridgeClass()
except Exception as exc:
    print(f"[YoloInit] failed to resolve Java bridge classes: {exc}")
    traceback.print_exc()
    PythonActivity = None
    YoloBridgeClass = None
    YoloBridgeInstance = None
Context = autoclass('android.content.Context')
Build_VERSION = autoclass('android.os.Build$VERSION')
PackageManager = autoclass('android.content.pm.PackageManager')
BluetoothProfile = autoclass('android.bluetooth.BluetoothProfile')
BluetoothGattDescriptor = autoclass('android.bluetooth.BluetoothGattDescriptor')
UUID = autoclass('java.util.UUID')
String = autoclass('java.lang.String')
BleBridge = autoclass('org.qgb.ble.BleBridge')
KeyPairGenerator = autoclass('java.security.KeyPairGenerator')
KeyAgreement = autoclass('javax.crypto.KeyAgreement')
KeyFactory = autoclass('java.security.KeyFactory')
ECGenParameterSpec = autoclass('java.security.spec.ECGenParameterSpec')
ECPublicKeySpec = autoclass('java.security.spec.ECPublicKeySpec')
ECPoint = autoclass('java.security.spec.ECPoint')
BigInteger = autoclass('java.math.BigInteger')

# Android 原生高性能图像处理类
YuvImage = autoclass('android.graphics.YuvImage')
Rect = autoclass('android.graphics.Rect')
ImageFormat = autoclass('android.graphics.ImageFormat')
ByteArrayOutputStream = autoclass('java.io.ByteArrayOutputStream')

# 全局数据流载体
GLOBAL_JPEG_BYTES = None
GLOBAL_CAM_WIDTH = 640
GLOBAL_CAM_HEIGHT = 480
GLOBAL_YUV_DATA = None
DETECTION_RESULTS = []
FPS = 0

# 线程锁
result_lock = threading.Lock()
yuv_lock = threading.Lock()

# ---------- Pyjnius 原生零轮询异步回调接口 ----------
class AndroidPreviewCallback(PythonJavaClass):
    __javainterfaces__ = ['android/hardware/Camera$PreviewCallback']
    __javacontext__ = 'app'

    def __init__(self):
        super().__init__()

    @java_method('([BLandroid/hardware/Camera;)V')
    def onPreviewFrame(self, data, camera):
        global GLOBAL_JPEG_BYTES, GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT, GLOBAL_YUV_DATA
        try:
            w, h = GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
            GLOBAL_YUV_DATA = bytes(data)
            yuv = YuvImage(data, ImageFormat.NV21, w, h, None)
            bos = ByteArrayOutputStream()
            yuv.compressToJpeg(Rect(0, 0, w, h), 70, bos)
            GLOBAL_JPEG_BYTES = bos.toByteArray()
        except Exception as e:
            print(f"[NativeCallbackError] {e}")

NATIVE_CALLBACK = AndroidPreviewCallback()

# ---------- UI KV Definition (移除了Camera和detect_overlay，改为动态添加) ----------
KV = r'''
<RootWidget>:
    canvas.before:
        Color:
            rgba: 0.1, 0.1, 0.1, 1
        Rectangle:
            pos: self.pos
            size: self.size

    # Camera和overlay将在Python中动态添加

    BoxLayout:
        orientation: 'vertical'
        pos_hint: {'center_x': 0.5, 'center_y': 0.5}
        size_hint: None, None
        size: (dp(240), dp(100))
        opacity: 0
        padding: dp(15)
        spacing: dp(10)
        canvas.before:
            Color:
                rgba: 0.0, 0.0, 0.0, 0.75
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(12)]
        Label:
            text: "Connecting Hardware..."
            font_size: '16sp'
            bold: True
            color: 1, 1, 1, 1
        Label:
            text: "Initializing video feed..."
            font_size: '12sp'
            color: 0.7, 0.7, 0.7, 1

    BoxLayout:
        orientation: 'vertical'
        size_hint: 1, None
        height: dp(260)
        pos_hint: {'x': 0, 'y': 0}
        padding: dp(12)
        spacing: dp(8)
        canvas.before:
            Color:
                rgba: 0, 0, 0, 0.65
            Rectangle:
                pos: self.pos
                size: self.size

        Label:
            size_hint_y: None
            height: dp(18)
            text: 'Professional Camera Controller'
            font_size: '14sp'
            color: 1, 1, 1, 0.85

        BoxLayout:
            size_hint_y: None
            height: dp(38)
            spacing: dp(8)

            Button:
                text: 'Start' if not app.camera_play else 'Stop'
                background_normal: ''
                background_color: (0.2, 0.6, 0.2, 0.6)
                on_release: app.toggle_preview()

            Button:
                text: 'Switch Cam'
                background_normal: ''
                background_color: (0.2, 0.4, 0.8, 0.6)
                on_release: app.switch_camera()

            Button:
                text: 'YOLO: ON' if app.yolo_enabled else 'YOLO: OFF'
                background_normal: ''
                background_color: (0.2, 0.8, 0.2, 0.6) if app.yolo_enabled else (0.5, 0.5, 0.5, 0.6)
                on_release: app.toggle_yolo()

            Button:
                text: app.flash_mode_text
                background_normal: ''
                background_color: (0.5, 0.5, 0.5, 0.6)
                on_release: app.toggle_flash()

        BoxLayout:
            orientation: 'horizontal'
            spacing: dp(12)

            BoxLayout:
                orientation: 'vertical'
                spacing: dp(6)

                BoxLayout:
                    orientation: 'horizontal'
                    size_hint_y: None
                    height: dp(32)
                    Label:
                        text: 'Brightness'
                        size_hint_x: 0.35
                        font_size: '12sp'
                        halign: 'left'
                    Slider:
                        size_hint_x: 0.65
                        min: -4
                        max: 4
                        value: app.brightness_value
                        step: 1
                        on_value: app.brightness_value = self.value

                BoxLayout:
                    orientation: 'horizontal'
                    size_hint_y: None
                    height: dp(32)
                    Label:
                        text: 'Chroma'
                        size_hint_x: 0.35
                        font_size: '12sp'
                        halign: 'left'
                    Slider:
                        size_hint_x: 0.65
                        min: 0
                        max: 6
                        value: app.chroma_value
                        step: 1
                        on_value: app.chroma_value = self.value

                Label:
                    id: status_label
                    text: 'Initializing...'
                    font_size: '12sp'
                    color: 0.7, 0.9, 0.7, 0.8
                    halign: 'center'
                    valign: 'middle'

                Label:
                    id: fps_label
                    text: 'FPS: --'
                    font_size: '12sp'
                    color: 1, 0.8, 0.3, 0.9
                    halign: 'center'

            FloatLayout:
                size_hint: None, None
                size: dp(140), dp(140)
                pos_hint: {'center_y': 0.5}
                canvas.before:
                    Color:
                        rgba: 0.35, 0.35, 0.35, 0.5
                    Ellipse:
                        pos: self.pos
                        size: self.size
                    Color:
                        rgba: 0.05, 0.05, 0.05, 0.85
                    Ellipse:
                        pos: self.x + dp(22), self.y + dp(22)
                        size: self.width - dp(44), self.height - dp(44)

                Button:
                    text: 'UP' if app.preview_angle != 0 else 'UP *'
                    size_hint: None, None
                    size: dp(42), dp(42)
                    pos_hint: {'center_x': 0.5, 'top': 1}
                    background_normal: ''
                    background_color: (0.85, 0.45, 0.1, 0.9) if app.preview_angle == 0 else (0.2, 0.2, 0.2, 0.6)
                    on_release: app.set_preview_angle(0)

                Button:
                    text: 'RIGHT' if app.preview_angle != 90 else 'RIGHT *'
                    size_hint: None, None
                    size: dp(42), dp(42)
                    pos_hint: {'right': 1, 'center_y': 0.5}
                    background_normal: ''
                    background_color: (0.85, 0.45, 0.1, 0.9) if app.preview_angle == 90 else (0.2, 0.2, 0.2, 0.6)
                    on_release: app.set_preview_angle(90)

                Button:
                    text: 'DOWN' if app.preview_angle != 180 else 'DOWN *'
                    size_hint: None, None
                    size: dp(42), dp(42)
                    pos_hint: {'center_x': 0.5, 'y': 0}
                    background_normal: ''
                    background_color: (0.85, 0.45, 0.1, 0.9) if app.preview_angle == 180 else (0.2, 0.2, 0.2, 0.6)
                    on_release: app.set_preview_angle(180)

                Button:
                    text: 'LEFT' if app.preview_angle != 270 else 'LEFT *'
                    size_hint: None, None
                    size: dp(42), dp(42)
                    pos_hint: {'x': 0, 'center_y': 0.5}
                    background_normal: ''
                    background_color: (0.85, 0.45, 0.1, 0.9) if app.preview_angle == 270 else (0.2, 0.2, 0.2, 0.6)
                    on_release: app.set_preview_angle(270)
'''
Builder.load_string(KV)

class RootWidget(FloatLayout):
    pass

class PermissionCallback(PythonJavaClass):
    __javainterfaces__ = ['org/kivy/android/PythonActivity$PermissionsCallback']
    __javacontext__ = 'app'
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
    @java_method('(I[Ljava/lang/String;[I)V')
    def onRequestPermissionsResult(self, requestCode, permissions, grantResults):
        Clock.schedule_once(lambda dt: self.owner._on_permissions_result(permissions, grantResults), 0)

# ---------- Native High-Performance Stream Server ----------
class NativeMJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/mjpeg_stream'):
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.end_headers()

            while True:
                global GLOBAL_JPEG_BYTES
                if GLOBAL_JPEG_BYTES is None:
                    time.sleep(0.05)
                    continue

                try:
                    jpeg_bytes = bytes(GLOBAL_JPEG_BYTES)
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'Content-Length: {len(jpeg_bytes)}\r\n\r\n'.encode())
                    self.wfile.write(jpeg_bytes)
                    self.wfile.write(b'\r\n')
                    time.sleep(0.03)
                except Exception:
                    break

        elif self.path == '/' or self.path == '/index.html':
            preview_html(self)

        else:
            self.send_response(404)
            self.end_headers()

    def set_header(self, key, value):
        self.send_header(key, value)

    def set_data(self, data):
        self.end_headers()
        self.wfile.write(data)

    def set_status(self, code):
        self.send_response(code)

    def log_message(self, format, *args):
        pass

def run_stream_server():
    try:
        server = HTTPServer(('0.0.0.0', 1134), NativeMJPEGHandler)
        server.serve_forever()
    except Exception as e:
        print(f"[StreamServer] Error: {e}")

# ---------- 检测线程（仅保留原生YoloBridge） ----------
def detection_worker():
    global DETECTION_RESULTS, FPS

    # 原生检测函数（直接使用全局桥接）
    def run_native_bridge(data, width, height):
        if YoloBridgeInstance is None:
            print('[Detection] YoloBridgeInstance is None')
            return None
        if YoloBridgeClass is not None and not YoloBridgeClass.isLibraryLoaded():
            try:
                print(f"[Detection] JNI library not loaded; status={YoloBridgeClass.getLoadStatus()}")
            except Exception as exc:
                print(f"[Detection] JNI library not loaded; status unavailable: {exc}")
            return None
        try:
            print(f'[Detection] calling native runDetection with frame {width}x{height}')
            raw = YoloBridgeInstance.runDetection(data, width, height)
            print(f'[Detection] native raw result: {raw[:200]}')
            payload = json.loads(raw)
            if isinstance(payload, list):
                # 修正点：逐个字典提取键值
                boxes = [(float(d['x1']), float(d['y1']), float(d['x2']), float(d['y2']), float(d['conf']), int(d['label'])) 
                        for d in payload]
                print(f'[Detection] parsed boxes: {boxes}')
                return boxes
            else:
                print(f'[Detection] unexpected payload type: {type(payload)}')
        except Exception as exc:
            print(f'[Detection] native bridge failed: {exc}')
            traceback.print_exc()
        return None
    prev_time = time.time()
    last_detection_run = time.time()
    frame_count = 0
    while True:
        try:
            app = App.get_running_app()
            if app and (not app.yolo_enabled or not getattr(app, 'yolo_ready', False)):
                with result_lock:
                    DETECTION_RESULTS = []
                FPS = 0
                time.sleep(0.1)
                continue
        except Exception:
            pass

        with yuv_lock:
            data = GLOBAL_YUV_DATA if 'GLOBAL_YUV_DATA' in globals() else None

        if data is None:
            time.sleep(0.01)
            continue

        try:
            now = time.time()
            if now - last_detection_run < 0.2:
                time.sleep(0.01)
                continue
            last_detection_run = now

            boxes = []
            native_boxes = run_native_bridge(data, GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT)
            if native_boxes is not None:
                boxes = native_boxes
            # 若原生桥接返回None则无检测结果，boxes保持空列表

            with result_lock:
                DETECTION_RESULTS = boxes
            frame_count += 1
            if now - prev_time >= 1.0:
                FPS = frame_count
                frame_count = 0
                prev_time = now
        except Exception as e:
            print(f'[Detection] error: {e}')
            traceback.print_exc()
        time.sleep(0.01)


class HualingACApp(App):
    title_text = StringProperty('Camera Preview')
    status_text = StringProperty('')
    log_text = StringProperty('')
    flash_mode_text = StringProperty('Flash: Off')

    preview_angle = NumericProperty(270)   # 默认270度，竖屏正向
    brightness_value = NumericProperty(0)
    chroma_value = NumericProperty(3)
    yolo_enabled = BooleanProperty(True)
    yolo_ready = BooleanProperty(False)
    camera_play = BooleanProperty(False)   # 新增属性用于绑定UI按钮

    def build(self):
        self.root_widget = RootWidget()
        self.activity = PythonActivity.mActivity
        self.context = self.activity.getApplicationContext()
        self.permission_callback = PermissionCallback(self)

        self.is_paused = False
        self.permissions_ok = False
        self.flash_mode = 0
        self._pending_start = False

        # 摄像头和覆盖层将在权限授予后创建
        self.camera_widget = None
        self.overlay_widget = None

        self._log('App starting...')
        if YoloBridgeClass is not None and self.context is not None:
            try:
                loaded = YoloBridgeClass.initializeNativeLibrary()
                self._log(f'YOLO native library init -> {loaded}')
                if loaded:
                    model_ready = YoloBridgeClass.initModelFromAssets(self.context)
                    self.yolo_ready = model_ready
                    self._log(f'YOLO native model init -> {model_ready}')
                    if model_ready:
                        self._log('YOLO native runtime initialized')
                    else:
                        self._log('YOLO native runtime init failed: model init returned false')
                else:
                    self.yolo_ready = False
                    self._log('YOLO native runtime init failed: library not loaded')
            except Exception as exc:
                self._log(f'YOLO native init failed: {exc}')
                traceback.print_exc()

        # 启动流服务器（与权限无关）
        t = threading.Thread(target=run_stream_server, daemon=True)
        t.start()

        # 启动检测线程（依赖摄像头数据，但会等待数据到来）
        if not getattr(self, '_detection_thread_started', False):
            self._detection_thread_started = True
            threading.Thread(target=detection_worker, daemon=True).start()
        Clock.schedule_interval(self.update_detection_display, 1.0 / 15.0)

        # 请求权限（异步）
        Clock.schedule_once(lambda dt: self.request_permissions(), 0.2)

        return self.root_widget

    # ---------- 新权限系统 ----------
    def _required_permissions(self):
        """根据Android版本返回需要动态申请的危险权限列表"""
        from jnius import autoclass
        VERSION = autoclass('android.os.Build$VERSION')
        sdk = VERSION.SDK_INT

        dynamic_perms = []

        # 基础危险权限
        dynamic_perms.append("android.permission.CAMERA")
        dynamic_perms.append("android.permission.RECORD_AUDIO")
        dynamic_perms.append("android.permission.READ_PHONE_STATE")

        # 存储权限适配
        if sdk >= 33:  # Android 13+
            dynamic_perms.extend([
                "android.permission.READ_MEDIA_IMAGES",
                "android.permission.READ_MEDIA_VIDEO",
                "android.permission.READ_MEDIA_AUDIO",
                "android.permission.POST_NOTIFICATIONS"
            ])
        else:  # Android 12 及以下
            dynamic_perms.extend([
                "android.permission.READ_EXTERNAL_STORAGE",
                "android.permission.WRITE_EXTERNAL_STORAGE"
            ])

        # 蓝牙与定位权限适配
        if sdk >= 31:  # Android 12+
            dynamic_perms.extend([
                "android.permission.BLUETOOTH_SCAN",
                "android.permission.BLUETOOTH_CONNECT",
                "android.permission.ACCESS_FINE_LOCATION"
            ])
        else:  # Android 11 及以下
            dynamic_perms.extend([
                "android.permission.ACCESS_FINE_LOCATION",
                "android.permission.ACCESS_COARSE_LOCATION"
            ])

        return dynamic_perms

    def request_permissions(self):
        perms = self._required_permissions()
        missing = [p for p in perms if self.activity.checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED]
        if not missing:
            self.permissions_ok = True
            Clock.schedule_once(lambda dt: self._on_permission_granted(), 0.2)
            return
        self._set_status('[PERM] Requesting permissions...')
        self.activity.addPermissionsCallback(self.permission_callback)
        self.activity.requestPermissions(missing, 1001)

    def _on_permissions_result(self, permissions, grantResults):
        ok = True
        if grantResults is None:
            ok = False
        else:
            for i in range(len(grantResults)):
                if int(grantResults[i]) != PackageManager.PERMISSION_GRANTED:
                    ok = False
                    break
        self.permissions_ok = ok
        if ok:
            self._set_status('[PERM] Permissions granted')
            Clock.schedule_once(lambda dt: self._on_permission_granted(), 0.2)
        else:
            self._set_status('[PERM] Permission denied')

    def _on_permission_granted(self):
        """权限已获取，初始化摄像头并启动预览"""
        self._init_camera_and_overlay()
        self._start_camera_preview()

    # ---------- 动态创建摄像头和覆盖层 ----------
    def _init_camera_and_overlay(self):
        if self.camera_widget is not None:
            return  # 已创建

        root = self.root_widget

        # 创建摄像头
        camera = Camera(resolution=(640, 480), play=False, allow_stretch=True, keep_ratio=False,
                        size_hint=(None, None), index=0)
        self.camera_widget = camera

        # 创建覆盖层
        overlay = Widget(size_hint=(None, None))
        self.overlay_widget = overlay

        # 添加到RootWidget（插入到最底层，位于控制栏下方）
        root.add_widget(camera, index=0)
        root.add_widget(overlay, index=1)

        # 为覆盖层绑定尺寸变化
        camera.bind(size=self._update_overlay_size)
        root.bind(size=self._update_overlay_size)

        # 初始设置尺寸
        Clock.schedule_once(lambda dt: self._update_overlay_size(), 0.1)

    def _update_overlay_size(self, *args):
        if self.camera_widget is None or self.overlay_widget is None:
            return
        angle = self.preview_angle
        root = self.root_widget
        if angle % 180 != 0:
            w, h = root.height, root.width
        else:
            w, h = root.width, root.height
        self.camera_widget.size = (w, h)
        self.camera_widget.pos_hint = {'center_x': 0.5, 'center_y': 0.5}
        self.overlay_widget.size = (w, h)
        self.overlay_widget.pos_hint = {'center_x': 0.5, 'center_y': 0.5}

    # ---------- 原有方法，修改为使用动态camera ----------
    def _start_camera_preview(self):
        if self.camera_widget is None:
            self._log('Camera not initialized')
            return
        if self.camera_widget.play or self._pending_start:
            return
        try:
            self._pending_start = True
            self.camera_widget.play = True
            self.camera_play = True
            # 设置底层显示方向
            Clock.schedule_once(lambda dt: self._set_camera_orientation(), 0.6)
            # 设置原生回调和预览尺寸
            Clock.schedule_once(lambda dt: self._setup_native_callback(), 1.0)
            self._set_status('Preview started')
        except Exception as e:
            self._set_status(f'Start failed: {e}')
            self._log(f'Start camera error: {e}')
        finally:
            self._pending_start = False

    def _set_camera_orientation(self):
        camera = self.camera_widget
        if not camera or not camera.play:
            return
        try:
            internal_camera = camera._camera
            if internal_camera is None:
                Clock.schedule_once(lambda dt: self._set_camera_orientation(), 0.3)
                return

            orientation = 90 if camera.index == 0 else 270
            applied = False

            for method_name in ('setDisplayOrientation', 'setPreviewOrientation', 'setRotation'):
                if hasattr(internal_camera, method_name):
                    try:
                        getattr(internal_camera, method_name)(orientation)
                        applied = True
                        self._log(f'Camera orientation applied via {method_name} -> {orientation}°')
                        break
                    except Exception as exc:
                        self._log(f'Camera orientation method {method_name} failed: {exc}')

            if not applied:
                android_camera = None
                if hasattr(internal_camera, '_android_camera') and internal_camera._android_camera is not None:
                    android_camera = internal_camera._android_camera

                if android_camera is not None:
                    try:
                        params = android_camera.getParameters()
                        params.setRotation(orientation)
                        android_camera.setParameters(params)
                        applied = True
                        self._log(f'Camera orientation applied via parameters rotation -> {orientation}°')
                    except Exception as exc:
                        self._log(f'Camera orientation via parameters failed: {exc}')

            if not applied:
                self._log('Camera orientation not supported by this camera implementation; using default preview behavior')
        except Exception as e:
            self._log(f'Set orientation failed: {e}')

    def _setup_native_callback(self):
        global GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
        camera = self.camera_widget
        if not camera or not camera.play:
            return
        try:
            internal_camera = camera._camera
            if internal_camera and hasattr(internal_camera, '_android_camera') and internal_camera._android_camera is not None:
                native_cam = internal_camera._android_camera

                params = native_cam.getParameters()
                w, h = GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
                try:
                    params.setPreviewSize(w, h)
                    native_cam.setParameters(params)
                except Exception as e:
                    self._log(f'Failed to set preview size {w}x{h}: {e}')

                native_cam.setPreviewCallback(NATIVE_CALLBACK)
                self._apply_professional_settings()
                self._set_status(f'Native callback linked at {w}x{h}')
        except Exception as e:
            self._log(f'Failed to hook native callback: {e}')

    def _apply_professional_settings(self):
        camera = self.camera_widget
        if not camera or not camera.play:
            return
        try:
            internal_camera = camera._camera
            if internal_camera is None:
                return

            native_cam = None
            if hasattr(internal_camera, '_android_camera') and internal_camera._android_camera is not None:
                native_cam = internal_camera._android_camera

            if native_cam is not None:
                params = native_cam.getParameters()
                if self.flash_mode == 0:
                    params.setFlashMode('off')
                elif self.flash_mode == 1:
                    params.setFlashMode('torch')
                else:
                    params.setFlashMode('auto')
                try:
                    params.setExposureCompensation(int(self.brightness_value))
                except Exception:
                    pass
                try:
                    params.set("saturation", int(self.chroma_value))
                except Exception:
                    pass
                native_cam.setParameters(params)
        except Exception as e:
            self._log(f'Apply hardware settings failed: {e}')

    def toggle_preview(self):
        if not self.permissions_ok:
            self.request_permissions()
            return
        camera = self.camera_widget
        if camera is None:
            self._init_camera_and_overlay()
            Clock.schedule_once(lambda dt: self.toggle_preview(), 0.3)
            return
        if camera.play:
            camera.play = False
            self.camera_play = False
            self._set_status('Preview stopped')
        else:
            Clock.schedule_once(lambda dt: self._start_camera_preview(), 0.6)

    def switch_camera(self):
        if not self.permissions_ok:
            self.request_permissions()
            return
        camera = self.camera_widget
        if camera is None:
            return
        if camera.play:
            camera.play = False
            self.camera_play = False
            self._set_status('Switching camera...')
            Clock.schedule_once(lambda dt: self._do_switch_camera(), 0.6)
        else:
            self._do_switch_camera()

    def _do_switch_camera(self, *args):
        camera = self.camera_widget
        if camera is None:
            return
        new_index = 1 - camera.index
        camera.index = new_index
        self._start_camera_preview()
        self._set_status(f'Switched to camera {"rear" if new_index==0 else "front"}')

    def toggle_flash(self):
        self.flash_mode = (self.flash_mode + 1) % 3
        mode_names = ['Off', 'On', 'Auto']
        self.flash_mode_text = f'Flash: {mode_names[self.flash_mode]}'
        self._apply_professional_settings()

    def toggle_yolo(self):
        self.yolo_enabled = not self.yolo_enabled
        print(f'[CameraApp] toggle_yolo -> {self.yolo_enabled}')
        self._set_status('YOLO enabled' if self.yolo_enabled else 'YOLO disabled')

    def update_detection_display(self, dt):
        if hasattr(self.root_widget.ids, 'fps_label'):
            self.root_widget.ids.fps_label.text = f'FPS: {FPS}'

        overlay = self.overlay_widget
        if overlay is None:
            return
        overlay.canvas.clear()
        with result_lock:
            results = list(DETECTION_RESULTS)
        w_cam, h_cam = GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
        w_scr, h_scr = overlay.width, overlay.height
        if w_scr <= 0 or h_scr <= 0 or not results:
            return

        angle = self.preview_angle
        with overlay.canvas:
            Color(0, 1, 0, 0.8)
            for (x1, y1, x2, y2, conf, cls) in results:
                nx1, ny1 = x1 / w_cam, y1 / h_cam
                nx2, ny2 = x2 / w_cam, y2 / h_cam
                if angle == 270:
                    sx1, sy1 = ny1 * w_scr, (1 - nx2) * h_scr
                    sx2, sy2 = ny2 * w_scr, (1 - nx1) * h_scr
                elif angle == 90:
                    sx1, sy1 = (1 - ny2) * w_scr, nx1 * h_scr
                    sx2, sy2 = (1 - ny1) * w_scr, nx2 * h_scr
                elif angle == 180:
                    sx1, sy1 = (1 - nx2) * w_scr, ny1 * h_scr
                    sx2, sy2 = (1 - nx1) * w_scr, ny2 * h_scr
                else:
                    sx1, sy1 = nx1 * w_scr, (1 - ny2) * h_scr
                    sx2, sy2 = nx2 * w_scr, (1 - ny1) * h_scr
                box_w = abs(sx2 - sx1)
                box_h = abs(sy2 - sy1)
                left = min(sx1, sx2)
                bottom = min(sy1, sy2)
                Line(rectangle=(left, bottom, box_w, box_h), width=2.0)

    def on_brightness_value(self, instance, value):
        self._apply_professional_settings()

    def on_chroma_value(self, instance, value):
        self._apply_professional_settings()

    def set_preview_angle(self, angle):
        self.preview_angle = angle
        self._update_overlay_size()
        self._set_status(f'Preview orientation locked to {angle} deg')

    def get_supported_resolutions(self):
        """返回摄像头支持的分辨率字符串，格式如 '[(w,h),...]' """
        try:
            cam = self.camera_widget
            if cam and cam._camera and hasattr(cam._camera, '_android_camera') and cam._camera._android_camera is not None:
                sizes = cam._camera._android_camera.getParameters().getSupportedPreviewSizes()
                res = [(s.width, s.height) for s in sizes]
                return str(res)
        except Exception as e:
            self._log(f'Failed to get resolutions: {e}')
        return '[(640, 480)]'

    def set_preview_resolution(self, w, h):
        global GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
        if w == GLOBAL_CAM_WIDTH and h == GLOBAL_CAM_HEIGHT:
            return
        GLOBAL_CAM_WIDTH = w
        GLOBAL_CAM_HEIGHT = h
        self._set_status(f'Resolution set to {w}x{h}, restarting preview...')
        camera = self.camera_widget
        if camera and camera.play:
            camera.play = False
            self.camera_play = False
            Clock.schedule_once(lambda dt: self._start_camera_preview(), 0.6)
        else:
            self._start_camera_preview()

    def _log(self, msg):
        print(f'[CameraApp] {msg}')
        lines = self.log_text.split('\n') if self.log_text else []
        lines.append(msg)
        if len(lines) > 120:
            lines = lines[-120:]
        self.log_text = '\n'.join(lines)

    def _set_status(self, msg):
        self.status_text = msg
        self._log(msg)
        if hasattr(self.root_widget.ids, 'status_label'):
            self.root_widget.ids.status_label.text = msg

    def on_pause(self):
        self.is_paused = True
        if self.camera_widget and self.camera_widget.play:
            self.camera_widget.play = False
            self.camera_play = False
        return True

    def on_resume(self):
        self.is_paused = False

    def on_stop(self):
        if self.camera_widget and self.camera_widget.play:
            self.camera_widget.play = False
            self.camera_play = False

def preview_html(response_obj):
    app_instance = App.get_running_app()
    current_angle = app_instance.preview_angle if app_instance else 270
    h = html_content.replace("__INITIAL_ANGLE__", str(current_angle))
    response_obj.set_header("Content-Type", "text/html; charset=utf-8")
    response_obj.set_data(h.encode('utf-8'))

html_content = r"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Kivy Native Stream Live View</title>
    <style>
        body { margin: 0; background-color: #000; overflow: hidden; display: flex; align-items: center; justify-content: center; height: 100vh; font-family: sans-serif; }
        #native_stream { width: 100vw; height: 100vh; object-fit: contain; transform-origin: center; transition: transform 0.2s; }
        .controls { position: fixed; bottom: 20px; left: 0; right: 0; display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; z-index: 100; padding: 0 10px; }
        button { background: rgba(255,255,255,0.2); color: white; border: none; padding: 10px 15px; border-radius: 8px; cursor: pointer; backdrop-filter: blur(5px); }
        .settings { background: rgba(0,0,0,0.6); padding: 5px; border-radius: 8px; display: flex; gap: 5px; align-items: center; }
        select { background: rgba(255,255,255,0.1); border: 1px solid #555; color: white; border-radius: 4px; padding: 5px; }
    </style>
</head>
<body>
    <div class="controls">
        <button onclick="rotate(-90)">↺</button>
        <button onclick="rotate(90)">↻</button>
        <button onclick="toggleFullscreen()">FS</button>
        <button onclick="window.location.reload()" style="background: rgba(200,0,0,0.5);">Refresh</button>
        <div class="settings">
            <select id="resolutionSelect"></select>
            <button onclick="setResolution()" style="background: rgba(0,100,200,0.5);">Apply</button>
        </div>
    </div>

    <script>
        let angle = __INITIAL_ANGLE__;
        const rpcPort = "1133";
        const streamUrl = window.location.protocol + '//' + window.location.hostname + ':1134/mjpeg_stream';

        const defaultResolutions = [
            { w: 320, h: 240 },
            { w: 640, h: 480 },
            { w: 800, h: 600 },
            { w: 1024, h: 768 },
            { w: 1280, h: 720 },
            { w: 1280, h: 960 },
            { w: 1920, h: 1080 },
            { w: 2592, h: 1944 },
            { w: 3840, h: 2160 }
        ];

        async function fetchSupportedResolutions() {
            try {
                const resp = await fetch(`http://${window.location.hostname}:${rpcPort}/r=app.get_supported_resolutions()`);
                if (resp.ok) {
                    const text = await resp.text();
                    const matches = text.match(/\((\d+)\s*,\s*(\d+)\)/g);
                    if (matches) {
                        return matches.map(m => {
                            const [w, h] = m.replace(/[()]/g, '').split(',').map(Number);
                            return { w, h };
                        });
                    }
                }
            } catch (e) {
                console.warn("Failed to fetch supported resolutions", e);
            }
            return defaultResolutions;
        }

        function populateResolutionSelect(resolutions, currentW, currentH) {
            const select = document.getElementById('resolutionSelect');
            select.innerHTML = '';
            resolutions.forEach(({w, h}) => {
                const option = document.createElement('option');
                option.value = `${w},${h}`;
                option.textContent = `${w} x ${h}`;
                if (w === currentW && h === currentH) {
                    option.selected = true;
                }
                select.appendChild(option);
            });
        }

        async function init() {
            let currentW = 640, currentH = 480;
            try {
                const resp = await fetch(`http://${window.location.hostname}:${rpcPort}/r=app.preview_angle-180,GLOBAL_CAM_WIDTH,GLOBAL_CAM_HEIGHT`);
                const text = await resp.text();
                const vals = text.replace(/[()]/g, '').split(',').map(s => parseInt(s.trim()));
                angle = vals[0] || 270;
                currentW = vals[1] || 640;
                currentH = vals[2] || 480;
            } catch(e) {
                console.error("RPC Init Error", e);
            }

            const resolutions = await fetchSupportedResolutions();
            populateResolutionSelect(resolutions, currentW, currentH);

            startStream();
        }

        function startStream() {
            const oldImg = document.getElementById('native_stream');
            if (oldImg) oldImg.remove();

            const newImg = document.createElement('img');
            newImg.id = 'native_stream';
            newImg.style.cssText = "width: 100vw; height: 100vh; object-fit: contain; transform-origin: center; transition: transform 0.2s;";
            newImg.style.transform = `rotate(${angle}deg) scaleY(-1)`;
            newImg.src = streamUrl + "?t=" + new Date().getTime();
            newImg.onerror = () => setTimeout(startStream, 2000);
            document.body.prepend(newImg);
        }

        async function setResolution() {
            const select = document.getElementById('resolutionSelect');
            const [w, h] = select.value.split(',').map(Number);
            if(!w || !h) return;
            await fetch(`http://${window.location.hostname}:${rpcPort}/r=app.set_preview_resolution(${w},${h})`);
            console.log(`Resolution set to ${w}x${h}`);
        }

        function rotate(deg) {
            angle = (angle + deg) % 360;
            const img = document.getElementById('native_stream');
            if (img) img.style.transform = `rotate(${angle}deg) scaleY(-1)`;
        }

        function toggleFullscreen() {
            if (!document.fullscreenElement) document.documentElement.requestFullscreen();
            else document.exitFullscreen();
        }

        init();
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    app = HualingACApp()
    app.run()