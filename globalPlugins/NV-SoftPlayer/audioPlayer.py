# -*- coding: UTF-8 -*-
import os
import time
import random
import queue
import threading
import subprocess
import json
import wx
import config
import ui
import gui

from .common import (
	_,
	apply_ui_layout,
	handle_error,
	FocusPanel,
	_cancel_speech,
	get_repeat_on,
	get_shuffle_on,
	save_addon_store,
	format_time,
	display_name,
	get_audio_duration_seconds,
	SEEK_SECONDS,
	VOLUME_STEP,
	SOFT_DUCK_RATIO,
	SOFT_RESTORE_DELAY_MS,
	SOFT_RESTORE_STEP_MS,
	_find_powershell,
	_creation_flags,
	_plugin_dir,
	HAS_COMTYPES,
)

if HAS_COMTYPES:
	try:
		import comtypes.client
	except ImportError:
		pass


class WmpComBackend:
	def __init__(self):
		if not HAS_COMTYPES:
			raise RuntimeError("comtypes is not available")
		self._wmp = comtypes.client.CreateObject("WMPlayer.OCX")
		self._was_playing = False
		self._finished_callback = None
		self.isolates_volume = False
		try:
			self._wmp.settings.autoStart = False
		except Exception:
			pass

	def set_finished_callback(self, callback):
		self._finished_callback = callback

	def load(self, path_or_url):
		try:
			try:
				self._wmp.settings.autoStart = False
			except Exception:
				pass
			self._wmp.URL = path_or_url
			try:
				self._wmp.controls.stop()
			except Exception:
				pass
			try:
				self._wmp.controls.currentPosition = 0
			except Exception:
				pass
			self._was_playing = False
			return True
		except Exception:
			return False

	def play(self):
		try:
			self._wmp.controls.play()
		except Exception:
			pass

	def pause(self):
		self._wmp.controls.pause()
		self._was_playing = False

	def stop(self):
		self._wmp.controls.stop()
		try:
			self._wmp.controls.currentPosition = 0
		except Exception:
			pass
		self._was_playing = False

	def seek(self, seconds):
		try:
			duration = self.duration_seconds()
			pos = max(0.0, float(seconds))
			if duration > 0:
				pos = min(pos, max(0.0, duration - 0.15))
			self._wmp.controls.currentPosition = pos
			return pos
		except Exception:
			return self.position_seconds()

	def seek_by(self, delta_seconds):
		duration = self.duration_seconds()
		current = self.position_seconds()
		target = current + float(delta_seconds)
		if target < 0:
			target = 0.0
		elif duration > 0 and target > duration:
			target = duration
		return self.seek(target), duration

	def get_volume(self):
		try:
			return int(self._wmp.settings.volume)
		except Exception:
			return 100

	def set_volume(self, value):
		try:
			value = int(max(0, min(100, value)))
			self._wmp.settings.volume = value
			return value
		except Exception:
			return self.get_volume()

	def is_playing(self):
		try:
			state = int(self._wmp.playState)
			playing = state == 3
			if playing:
				self._was_playing = True
			elif self._was_playing and state in (1, 8):
				self._was_playing = False
				if self._finished_callback:
					wx.CallAfter(self._finished_callback)
			return playing
		except Exception:
			return False

	def is_paused(self):
		try:
			return int(self._wmp.playState) == 2
		except Exception:
			return False

	def is_stopped(self):
		try:
			return int(self._wmp.playState) in (1, 8)
		except Exception:
			return True

	def position_seconds(self):
		try:
			return float(self._wmp.controls.currentPosition or 0)
		except Exception:
			return 0.0

	def duration_seconds(self):
		try:
			dur = float(self._wmp.currentMedia.duration or 0)
			return dur if dur > 0 else 0.0
		except Exception:
			return 0.0

	def close(self):
		try:
			self._wmp.close()
		except Exception:
			pass


class ExternalWmpBackend:
	def __init__(self):
		self._lock = threading.Lock()
		self._proc = None
		self._was_playing = False
		self._finished_callback = None
		self._last = {"state": 1, "pos": 0.0, "dur": 0.0, "vol": 100}
		self.isolates_volume = True
		self._start_host()

	def _host_script_path(self):
		here = os.path.join(_plugin_dir(), "player_host.ps1")
		if os.path.isfile(here):
			return here
		temp_path = os.path.join(
			os.environ.get("TEMP", os.path.expanduser("~")),
			"nvSoftPlayer_player_host.ps1",
		)
		src = None
		try:
			with open(here, "r", encoding="utf-8") as f:
				src = f.read()
		except Exception:
			src = None
		if not src:
			src = (
				"Add-Type -AssemblyName System.Windows.Forms\n"
				"$ErrorActionPreference = 'Continue'\n"
				"[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false\n"
				"[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false\n"
				"$s = @'\n"
				"using System; using System.Threading; using System.Collections.Concurrent;\n"
				"public static class PipeReader {\n"
				"    private static ConcurrentQueue<string> q = new ConcurrentQueue<string>();\n"
				"    public static void Start() {\n"
				"        Thread t = new Thread(() => { string l; while ((l = Console.ReadLine()) != null) { l = l.Trim(); if (l.Length > 0) q.Enqueue(l); } q.Enqueue(\"{\\\"cmd\\\":\\\"quit\\\"}\"); });\n"
				"        t.IsBackground = true; t.Start();\n"
				"    }\n"
				"    public static string TryRead() { string r; if (q.TryDequeue(out r)) return r; return null; }\n"
				"}\n"
				"'@\n"
				"try { Add-Type -TypeDefinition $s; [PipeReader]::Start() } catch {}\n"
				"$wmp = New-Object -ComObject WMPlayer.OCX\n"
				"try { $wmp.settings.autoStart = $false } catch {}\n"
				"try { $wmp.uiMode = 'invisible' } catch {}\n"
				"function W([string]$m){[Console]::Out.WriteLine($m); [Console]::Out.Flush()}\n"
				"W '{\"ok\":true,\"event\":\"ready\"}'\n"
				"$rn = $true\n"
				"while ($rn) {\n"
				"    [System.Windows.Forms.Application]::DoEvents()\n"
				"    $raw = $null; try { $raw = [PipeReader]::TryRead() } catch { $raw = $null }\n"
				"    if ($null -ne $raw) {\n"
				"        try {\n"
				"            $j = $raw | ConvertFrom-Json; switch ([string]$j.cmd) {\n"
				"                'load' { $wmp.URL = [string]$j.url; try{$wmp.controls.stop()}catch{}; W '{\"ok\":true}' }\n"
				"                'play' { $wmp.controls.play(); W '{\"ok\":true}' }\n"
				"                'pause' { $wmp.controls.pause(); W '{\"ok\":true}' }\n"
				"                'stop' { $wmp.controls.stop(); W '{\"ok\":true}' }\n"
				"                'seek' { $wmp.controls.currentPosition = [double]$j.value; W '{\"ok\":true}' }\n"
				"                'volume' { $wmp.settings.volume = [int]$j.value; W '{\"ok\":true}' }\n"
				"                'query' { $st=1;$p=0.0;$d=0.0;$v=100; try{$st=[int]$wmp.playState}catch{}; try{$p=[double]$wmp.controls.currentPosition}catch{}; try{$d=[double]$wmp.currentMedia.duration}catch{}; try{$v=[int]$wmp.settings.volume}catch{}; if($d -lt 0){$d=0}; if($p -lt 0){$p=0}; W (\"{\\`\"ok\\`\":true,\\`\"state\\`\":$st,\\`\"pos\\`\":$p,\\`\"dur\\`\":$d,\\`\"vol\\`\":$v}\") }\n"
				"                'quit' { try{$wmp.controls.stop()}catch{}; try{$wmp.close()}catch{}; W '{\"ok\":true}'; $rn = $false }\n"
				"                default { W '{\"ok\":false}' }\n"
				"            }\n"
				"        } catch { W '{\"ok\":false}' }\n"
				"    } else { Start-Sleep -Milliseconds 25 }\n"
				"}\n"
				"try { $wmp.close() } catch {}\n"
			)
		with open(temp_path, "w", encoding="utf-8") as f:
			f.write(src)
		return temp_path

	def _start_host(self):
		powershell = _find_powershell()
		if not powershell:
			raise RuntimeError("PowerShell was not found.")
		ps1 = self._host_script_path()
		self._proc = subprocess.Popen(
			[
				powershell,
				"-STA",
				"-NoProfile",
				"-ExecutionPolicy", "Bypass",
				"-WindowStyle", "Hidden",
				"-File", ps1,
			],
			stdin=subprocess.PIPE,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			encoding="utf-8",
			errors="replace",
			bufsize=1,
			creationflags=_creation_flags(),
		)
		raw = self._readline(timeout=10)
		if not raw:
			raise RuntimeError("Player host failed to start (no ready signal).")
		reply = self._rpc({"cmd": "query"}, timeout=5)
		if not reply or not reply.get("ok"):
			err = (reply or {}).get("error") if reply else "no reply"
			raise RuntimeError(f"Player host failed: {err}")

	def _readline(self, timeout):
		q = queue.Queue()

		def reader():
			try:
				q.put(self._proc.stdout.readline())
			except Exception as e:
				q.put(e)

		t = threading.Thread(target=reader, daemon=True)
		t.start()
		try:
			item = q.get(timeout=timeout)
		except queue.Empty:
			return None
		if isinstance(item, Exception):
			return None
		return item

	def _rpc(self, payload, timeout=8):
		if not self._proc or self._proc.poll() is not None:
			return None
		line = json.dumps(payload, ensure_ascii=False) + "\n"
		with self._lock:
			try:
				self._proc.stdin.write(line)
				self._proc.stdin.flush()
			except Exception:
				return None
			raw = self._readline(timeout)
		if not raw:
			return None
		try:
			return json.loads(raw)
		except Exception:
			return None

	def _query(self):
		reply = self._rpc({"cmd": "query"}, timeout=4)
		if reply and reply.get("ok"):
			v = reply.get("vol")
			self._last = {
				"state": int(reply.get("state") or 1),
				"pos": float(reply.get("pos") or 0),
				"dur": float(reply.get("dur") or 0),
				"vol": int(v) if v is not None else 100,
			}
		return self._last

	def set_finished_callback(self, callback):
		self._finished_callback = callback

	def load(self, path_or_url):
		reply = self._rpc({"cmd": "load", "url": path_or_url}, timeout=15)
		self._was_playing = False
		return bool(reply and reply.get("ok"))

	def play(self):
		self._rpc({"cmd": "play"})

	def pause(self):
		self._rpc({"cmd": "pause"})
		self._was_playing = False

	def stop(self):
		self._rpc({"cmd": "stop"})
		self._was_playing = False

	def seek(self, seconds):
		duration = self.duration_seconds()
		pos = max(0.0, float(seconds))
		if duration > 0:
			pos = min(pos, max(0.0, duration - 0.15))
		self._rpc({"cmd": "seek", "value": pos})
		self._last["pos"] = pos
		return pos

	def seek_by(self, delta_seconds):
		info = self._query()
		duration = float(info.get("dur") or 0)
		current = float(info.get("pos") or 0)
		target = current + float(delta_seconds)
		if target < 0:
			target = 0.0
		elif duration > 0 and target > duration:
			target = duration
		return self.seek(target), duration

	def _post(self, payload):
		if not self._proc or self._proc.poll() is not None:
			return
		line = json.dumps(payload, ensure_ascii=False) + "\n"
		with self._lock:
			try:
				self._proc.stdin.write(line)
				self._proc.stdin.flush()
			except Exception:
				pass

	def get_volume(self):
		v = self._last.get("vol")
		return int(v) if v is not None else 100

	def set_volume(self, value):
		value = int(max(0, min(100, value)))
		self._last["vol"] = value
		self._post({"cmd": "volume", "value": value})
		return value

	def is_playing(self):
		info = self._query()
		state = int(info.get("state") or 1)
		playing = state == 3
		if playing:
			self._was_playing = True
		elif self._was_playing and state in (1, 8):
			self._was_playing = False
			if self._finished_callback:
				wx.CallAfter(self._finished_callback)
		return playing

	def is_paused(self):
		return int(self._query().get("state") or 1) == 2

	def is_stopped(self):
		return int(self._query().get("state") or 1) in (1, 8)

	def position_seconds(self):
		return float(self._last.get("pos") or 0)

	def duration_seconds(self):
		dur = float(self._last.get("dur") or 0)
		return dur if dur > 0 else 0.0

	def close(self):
		try:
			self._rpc({"cmd": "quit"}, timeout=3)
		except Exception:
			pass
		if self._proc:
			try:
				self._proc.terminate()
			except Exception:
				pass
			self._proc = None


def create_media_backend():
	try:
		return ExternalWmpBackend()
	except Exception:
		if not HAS_COMTYPES:
			handle_error("Windows Media Player COM is not available.")
			return None
		try:
			return WmpComBackend()
		except Exception as e:
			handle_error(f"Could not create Windows Media Player: {e}")
			return None


class NVSoftPlayerDialog(wx.Dialog):
	def __init__(self, parent, paths, repeat_scope="playlist", titles=None, quiet_open=False):
		self.original_paths = list(paths)
		self.queue = list(paths)
		self.titles = list(titles) if titles else [display_name(p) for p in paths]
		self.repeat_scope = repeat_scope if repeat_scope in ("track", "playlist") else "playlist"
		self.repeat_on = get_repeat_on()
		self.shuffle_on = get_shuffle_on()
		self.index = 0
		self._closed = False
		self._stop_requested = False
		self._switching = False
		self._saved_volume = None
		self._volume_ducked = False
		self._quiet_open = bool(quiet_open)
		super().__init__(parent, title="NV-SoftPlayer", size=(720, 420))
		apply_ui_layout(self)
		panel = FocusPanel(self)
		self.panel = panel
		main_sizer = wx.BoxSizer(wx.VERTICAL)
		self.status_label = wx.StaticText(panel, label=_("Ready"))
		main_sizer.Add(self.status_label, 0, wx.EXPAND | wx.ALL, 10)
		self.track_label = wx.StaticText(panel, label="")
		self.track_label.SetFont(
			wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
		)
		main_sizer.Add(self.track_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
		self.mode_label = wx.StaticText(panel, label="")
		main_sizer.Add(self.mode_label, 0, wx.EXPAND | wx.ALL, 8)
		list_caption = wx.StaticText(panel, label=_("Playlist"))
		main_sizer.Add(list_caption, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
		self.track_list = wx.ListBox(panel, style=wx.LB_SINGLE)
		main_sizer.Add(self.track_list, 1, wx.EXPAND | wx.ALL, 10)

		self._full_help = (
			"Space play/pause. Z previous. X replay. C stop. V next. "
			"Left rewind 5 seconds. Right forward 5 seconds. "
			"Up/Down change player volume only, not NVDA speech. "
			"R repeat. Ctrl+R save repeat. S shuffle. Ctrl+S save shuffle. "
			"T duration. Application key or Shift+F10 for menu. Escape close."
		)
		panel.SetSizer(main_sizer)
		if self.shuffle_on and len(self.queue) > 1:
			combined = list(zip(self.queue, self.titles))
			random.shuffle(combined)
			self.queue = [c[0] for c in combined]
			self.titles = [c[1] for c in combined]
		self._fill_list()
		self.backend = create_media_backend()
		if self.backend:
			self.backend.set_finished_callback(self.on_media_finished)
		self.Bind(wx.EVT_CLOSE, self.on_close)
		self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)
		self.Bind(wx.EVT_CONTEXT_MENU, self.on_player_context_menu)
		self.track_list.Bind(wx.EVT_CONTEXT_MENU, self.on_player_context_menu)
		self.panel.Bind(wx.EVT_CONTEXT_MENU, self.on_player_context_menu)
		self.timer = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
		self.fade_timer = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self.on_fade_timer, self.fade_timer)
		if not self.queue:
			self.status_label.SetLabel("No audio files to play.")
			ui.message("No audio files to play.")
		elif not self.backend:
			ui.message(
				"Windows Media Player is not available. "
				"Install or repair Windows Media Player, then try again."
			)
		else:
			self._load_current(auto_play=True)
		self._refresh_mode_label()
		self.CentreOnParent()

		def _after_open():
			_cancel_speech()
			self._focus_player()
			if self._quiet_open:
				_cancel_speech()
		wx.CallAfter(_after_open)
		if self._quiet_open:
			wx.CallLater(120, _cancel_speech)
			wx.CallLater(350, _cancel_speech)

	def load_new_queue(self, paths, titles=None, repeat_scope=None, quiet_open=False):
		if self._closed:
			return False
		self._quiet_open = bool(quiet_open)
		self.original_paths = list(paths)
		self.queue = list(paths)
		self.titles = list(titles) if titles else [display_name(p) for p in paths]
		if repeat_scope in ("track", "playlist"):
			self.repeat_scope = repeat_scope
		self.index = 0
		if self.shuffle_on and len(self.queue) > 1:
			combined = list(zip(self.queue, self.titles))
			random.shuffle(combined)
			self.queue = [c[0] for c in combined]
			self.titles = [c[1] for c in combined]
		self._fill_list()
		self._refresh_mode_label()
		self.Raise()
		self._focus_player()
		return self._load_current(auto_play=True)

	def replace_upcoming(self, paths, titles=None):
		if self._closed or not paths:
			return
		current = self._current_path()
		self.original_paths = list(paths)
		self.queue = list(paths)
		self.titles = list(titles) if titles else [display_name(p) for p in paths]
		if current in self.queue:
			self.index = self.queue.index(current)
		self._fill_list()
		self._refresh_mode_label()

	def _focus_player(self):
		try:
			self.Raise()
			self.track_list.SetFocus()
		except Exception:
			try:
				self.panel.SetFocus()
			except Exception:
				pass

	def _fill_list(self):
		labels = []
		for i, p in enumerate(self.queue):
			if i < len(self.titles) and self.titles[i]:
				labels.append(self.titles[i])
			else:
				labels.append(display_name(p) if not str(p).startswith("http") else p)
		self.track_list.Set(labels)
		if self.queue:
			self.track_list.SetSelection(self.index)

	def _refresh_mode_label(self):
		repeat_txt = "on" if self.repeat_on else "off"
		scope_txt = "one track" if self.repeat_scope == "track" else "playlist"
		shuffle_txt = "on" if self.shuffle_on else "off"
		self.mode_label.SetLabel(
			f"Repeat {repeat_txt} ({scope_txt}). Shuffle {shuffle_txt}."
		)

	def _current_path(self):
		if not self.queue or self.index < 0 or self.index >= len(self.queue):
			return None
		return self.queue[self.index]

	def _current_title(self):
		if self.index < len(self.titles):
			return self.titles[self.index]
		path = self._current_path() or ""
		if str(path).startswith("http"):
			return "Stream"
		return display_name(path)

	def _load_current(self, auto_play=True):
		path = self._current_path()
		if not path or not self.backend:
			return False
		self._stop_requested = False
		ok = self.backend.load(path)
		if not ok:
			handle_error(f"Could not load {self._current_title()}")
			return False
		self._stop_fade(restore=True)
		name = self._current_title()
		pos = self.index + 1
		total = len(self.queue)
		self.track_label.SetLabel(f"{pos} of {total}: {name}")
		try:
			self.track_list.SetSelection(self.index)
		except Exception:
			pass
		if auto_play:
			self.backend.play()
			self.timer.Start(250)
			self.status_label.SetLabel("Playing")
			_cancel_speech()
			ui.message(f"Playing {name}")
			if self._quiet_open:
				self._quiet_open = False
				wx.CallLater(80, _cancel_speech)
		else:
			self.status_label.SetLabel("Ready")
		return True

	def on_timer(self, event):
		if self._closed or not self.backend:
			return
		self.backend.is_playing()

	def _stop_fade(self, restore=True):
		try:
			self.fade_timer.Stop()
		except Exception:
			pass
		if restore and self._volume_ducked and self.backend and self._saved_volume is not None:
			self.backend.set_volume(self._saved_volume)
		self._volume_ducked = False

	def on_fade_timer(self, event):
		if self._closed or not self.backend:
			self._stop_fade(restore=False)
			return
		current = self.backend.get_volume()
		target = self._saved_volume if self._saved_volume is not None else current
		if current >= target or target <= 0:
			self.backend.set_volume(target)
			self._volume_ducked = False
			self.fade_timer.Stop()
			return
		step = max(2, int((target - current) * 0.45) or 2)
		self.backend.set_volume(min(target, current + step))
		self.fade_timer.Start(SOFT_RESTORE_STEP_MS, oneShot=True)

	def _duck_for_seek(self):
		if not self.backend:
			return
		if not self._volume_ducked:
			try:
				self._saved_volume = self.backend.get_volume()
			except Exception:
				self._saved_volume = 100
		saved = self._saved_volume if self._saved_volume is not None else 100
		if saved <= 0:
			ducked = 0
		else:
			ducked = max(0, min(saved, int(saved * SOFT_DUCK_RATIO)))
			if ducked >= saved:
				ducked = max(0, saved - 4)
		self.backend.set_volume(ducked)
		self._volume_ducked = True
		try:
			self.fade_timer.Stop()
		except Exception:
			pass
		self.fade_timer.Start(SOFT_RESTORE_DELAY_MS, oneShot=True)

	def soft_seek(self, delta_seconds):
		if not self.backend:
			return
		if self.backend.is_stopped() and not self.backend.is_paused():
			return
		self._duck_for_seek()
		new_pos, duration = self.backend.seek_by(delta_seconds)
		if delta_seconds < 0 and new_pos <= 0.05:
			label = "Start of track"
		elif duration > 0 and new_pos >= max(0.0, duration - 0.2):
			label = "End of track"
		else:
			direction = "Forward" if delta_seconds > 0 else "Rewind"
			label = f"{direction} {format_time(new_pos)}"
			if duration > 0:
				label = f"{label} of {format_time(duration)}"
		self.status_label.SetLabel(label)

	def change_volume(self, delta):
		if not self.backend:
			return
		current = self.backend.get_volume()
		new_vol = max(0, min(100, current + delta))
		self.backend.set_volume(new_vol)
		self._saved_volume = new_vol
		self._volume_ducked = False
		try:
			self.fade_timer.Stop()
		except Exception:
			pass
		self.status_label.SetLabel(f"Player volume {new_vol} percent")
		ui.message(f"{new_vol}%")

	def on_media_finished(self):
		if self._closed or self._stop_requested or self._switching:
			return
		if self.repeat_on and self.repeat_scope == "track":
			self.backend.seek(0)
			self.backend.play()
			self.timer.Start(250)
			self.status_label.SetLabel("Playing")
			return
		if self.index < len(self.queue) - 1:
			self.play_next(announce=True)
			return
		if self.repeat_on and self.repeat_scope == "playlist" and self.queue:
			self.index = 0
			self._load_current(auto_play=True)
			return
		self.timer.Stop()
		self.status_label.SetLabel("Playback finished.")
		ui.message("Playback finished.")

	def toggle_play_pause(self):
		if not self.backend:
			ui.message("Media player is not available.")
			return
		if self.backend.is_playing():
			self._stop_fade(restore=True)
			self.backend.pause()
			self.timer.Stop()
			self.status_label.SetLabel("Paused")
			ui.message("Paused")
			return
		if self.backend.is_stopped():
			self._load_current(auto_play=True)
			return
		self._stop_requested = False
		self.backend.play()
		self.timer.Start(250)
		self.status_label.SetLabel("Playing")
		ui.message("Playing")

	def replay_current(self):
		if not self.backend:
			return
		self._stop_requested = False
		self.backend.seek(0)
		self.backend.play()
		self.timer.Start(250)
		self.status_label.SetLabel("Playing")
		ui.message("Replaying from the beginning")

	def stop_playback(self):
		if not self.backend:
			return
		self._stop_requested = True
		self._stop_fade(restore=True)
		self.backend.stop()
		self.timer.Stop()
		self.status_label.SetLabel("Stopped")
		ui.message("Stopped")

	def play_previous(self):
		if not self.queue:
			return
		if self.index <= 0:
			ui.message("This is the first track.")
			return
		self._switching = True
		self.index -= 1
		self._load_current(auto_play=True)
		self._switching = False

	def play_next(self, announce=True):
		if not self.queue:
			return
		if self.index >= len(self.queue) - 1:
			if self.repeat_on and self.repeat_scope == "playlist":
				self.index = 0
			else:
				ui.message("This is the last track.")
				return
		else:
			self.index += 1
		self._switching = True
		self._load_current(auto_play=True)
		self._switching = False

	def toggle_repeat(self, persist=False):
		self.repeat_on = not self.repeat_on
		self._refresh_mode_label()
		scope = "one track" if self.repeat_scope == "track" else "playlist"
		state = "on" if self.repeat_on else "off"
		if persist:
			try:
				config.conf["nvSoftPlayer"]["repeatOn"] = self.repeat_on
			except Exception:
				pass
			save_addon_store(repeat_on=self.repeat_on)
			ui.message(f"Repeat {state} for {scope}, saved")
		else:
			ui.message(f"Repeat {state} for {scope}")

	def toggle_shuffle(self, persist=False):
		current = self._current_path()
		self.shuffle_on = not self.shuffle_on
		if self.shuffle_on:
			combined = list(zip(
				self.original_paths,
				self.titles if len(self.titles) == len(self.original_paths)
				else [display_name(p) for p in self.original_paths]
			))
			random.shuffle(combined)
			self.queue = [c[0] for c in combined]
			self.titles = [c[1] for c in combined]
		else:
			self.queue = list(self.original_paths)
			if len(self.titles) != len(self.original_paths):
				self.titles = [display_name(p) for p in self.original_paths]
		if current in self.queue:
			self.index = self.queue.index(current)
		else:
			self.index = 0
		self._fill_list()
		self._refresh_mode_label()
		state = "on" if self.shuffle_on else "off"
		if persist:
			try:
				config.conf["nvSoftPlayer"]["shuffleOn"] = self.shuffle_on
			except Exception:
				pass
			save_addon_store(shuffle_on=self.shuffle_on)
			ui.message(f"Shuffle {state}, saved")
		else:
			ui.message(f"Shuffle {state}")

	def announce_duration(self):
		if not self.backend:
			ui.message("Media player is not available.")
			return
		self.backend.is_playing()
		duration = self.backend.duration_seconds()
		name = self._current_title()
		if duration <= 0:
			path = self._current_path()
			if path and os.path.isfile(path):
				duration = get_audio_duration_seconds(path)
		if duration <= 0:
			ui.message(f"Could not read the length of {name}")
			return
		ui.message(f"{name}, {format_time(duration)}")

	def announce_help(self, event=None):
		ui.message(self._full_help)

	def on_player_context_menu(self, event):
		menu = wx.Menu()
		id_play = wx.NewIdRef()
		id_prev = wx.NewIdRef()
		id_next = wx.NewIdRef()
		id_replay = wx.NewIdRef()
		id_stop = wx.NewIdRef()
		id_repeat = wx.NewIdRef()
		id_shuffle = wx.NewIdRef()
		id_dur = wx.NewIdRef()
		id_help = wx.NewIdRef()
		id_close = wx.NewIdRef()
		menu.Append(id_play, _("Play / Pause"))
		menu.Append(id_replay, _("Replay from start"))
		menu.Append(id_stop, _("Stop"))
		menu.AppendSeparator()
		menu.Append(id_prev, _("Previous track"))
		menu.Append(id_next, _("Next track"))
		menu.AppendSeparator()
		menu.Append(id_repeat, _("Toggle repeat"))
		menu.Append(id_shuffle, _("Toggle shuffle"))
		menu.Append(id_dur, _("Announce duration"))
		if not self._quiet_open:
			menu.AppendSeparator()
			menu.Append(id_help, _("Keyboard shortcuts"))
		menu.Append(id_close, _("Close"))
		self.Bind(wx.EVT_MENU, lambda e: self.toggle_play_pause(), id=id_play)
		self.Bind(wx.EVT_MENU, lambda e: self.replay_current(), id=id_replay)
		self.Bind(wx.EVT_MENU, lambda e: self.stop_playback(), id=id_stop)
		self.Bind(wx.EVT_MENU, lambda e: self.play_previous(), id=id_prev)
		self.Bind(wx.EVT_MENU, lambda e: self.play_next(), id=id_next)
		self.Bind(wx.EVT_MENU, lambda e: self.toggle_repeat(persist=False), id=id_repeat)
		self.Bind(wx.EVT_MENU, lambda e: self.toggle_shuffle(persist=False), id=id_shuffle)
		self.Bind(wx.EVT_MENU, lambda e: self.announce_duration(), id=id_dur)
		if not self._quiet_open:
			self.Bind(wx.EVT_MENU, self.announce_help, id=id_help)
		self.Bind(wx.EVT_MENU, self.on_close, id=id_close)
		try:
			self.PopupMenu(menu)
		finally:
			menu.Destroy()

	def on_key_down(self, event):
		if event.AltDown() or event.MetaDown():
			event.Skip()
			return
		ctrl = event.ControlDown()
		key = event.GetKeyCode()
		if key == wx.WXK_WINDOWS_MENU or (
			key == wx.WXK_F10 and event.ShiftDown()
		):
			self.on_player_context_menu(event)
			return
		if key == wx.WXK_ESCAPE:
			self.on_close(event)
			return
		if ctrl and key in (ord("R"), ord("r")):
			self.toggle_repeat(persist=True)
			return
		if ctrl and key in (ord("S"), ord("s")):
			self.toggle_shuffle(persist=True)
			return
		if ctrl:
			event.Skip()
			return
		if key == wx.WXK_SPACE:
			self.toggle_play_pause()
			return
		if key == wx.WXK_LEFT:
			self.soft_seek(-SEEK_SECONDS)
			return
		if key == wx.WXK_RIGHT:
			self.soft_seek(SEEK_SECONDS)
			return
		if key == wx.WXK_UP:
			self.change_volume(VOLUME_STEP)
			return
		if key == wx.WXK_DOWN:
			self.change_volume(-VOLUME_STEP)
			return
		if key in (ord("Z"), ord("z")):
			self.play_previous()
			return
		if key in (ord("X"), ord("x")):
			self.replay_current()
			return
		if key in (ord("C"), ord("c")):
			self.stop_playback()
			return
		if key in (ord("V"), ord("v")):
			self.play_next()
			return
		if key in (ord("R"), ord("r")):
			self.toggle_repeat(persist=False)
			return
		if key in (ord("S"), ord("s")):
			self.toggle_shuffle(persist=False)
			return
		if key in (ord("T"), ord("t")):
			self.announce_duration()
			return
		if key in (ord("H"), ord("h")):
			if not self._quiet_open:
				ui.message(self._full_help)
			return
		event.Skip()

	def on_close(self, event=None):
		if self._closed:
			return
		self._closed = True
		self._stop_requested = True
		try:
			self.timer.Stop()
		except Exception:
			pass
		self._stop_fade(restore=False)
		try:
			if self.backend:
				self.backend.stop()
				self.backend.close()
		except Exception:
			pass
		try:
			gui.mainFrame.postPopup()
		except Exception:
			pass
		self.Destroy()


def open_player(paths, repeat_scope="playlist", titles=None, quiet_open=False, existing_dialog=None):
	if not paths:
		handle_error("No audio files were found.")
		return None
	if existing_dialog:
		try:
			if existing_dialog.load_new_queue(
				paths, titles, repeat_scope, quiet_open=quiet_open
			):
				return existing_dialog
		except Exception:
			try:
				existing_dialog.Destroy()
			except Exception:
				pass
	gui.mainFrame.prePopup()
	dialog = NVSoftPlayerDialog(
		gui.mainFrame, paths, repeat_scope=repeat_scope, titles=titles,
		quiet_open=quiet_open,
	)
	dialog.Show()
	dialog.Raise()
	return dialog
