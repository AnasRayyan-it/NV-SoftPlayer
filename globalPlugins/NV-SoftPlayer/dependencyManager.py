# -*- coding: UTF-8 -*-
"""
Dependency Manager for NV-SoftPlayer.
Automatically verifies and downloads required playback tools (yt-dlp and ffmpeg)
to the add-on's bin folder when the YouTube player is opened for the first time.
"""

import os
import sys
import subprocess
import shutil
import zipfile
import gzip
import urllib.request
import urllib.error
import threading
import time
import wx

import ui
import gui
from .common import (
	_,
	handle_error,
	USER_AGENT,
	_find_ffmpeg,
	_find_ytdlp,
	_addon_bin_dirs,
	_plugin_dir,
	_creation_flags,
)


def _verify_binary(path, flag="--version"):
	"""Test if an executable file actually runs and exits with code 0 on this system."""
	if not path or not os.path.isfile(path) or os.path.getsize(path) < 1024 * 1024:
		return False
	try:
		p = subprocess.run(
			[path, flag],
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			timeout=8,
			creationflags=_creation_flags(),
		)
		return p.returncode == 0
	except Exception:
		return False

YTDLP_URLS = [
	"https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
]

FFMPEG_URLS = [
	"https://github.com/eugeneware/ffmpeg-static/releases/latest/download/ffmpeg-win32-x64.gz",
	"https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
	"https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
]


def get_target_bin_dir():
	"""Determine the primary writable bin directory to install executables."""
	primary = os.path.join(_plugin_dir(), "bin")
	try:
		os.makedirs(primary, exist_ok=True)
		test_file = os.path.join(primary, ".perm_test")
		with open(test_file, "w") as f:
			f.write("ok")
		os.remove(test_file)
		return primary
	except Exception:
		pass
	# Fallback to local appdata which is always writable by the current user
	fallback = os.path.join(
		os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
		"NV-SoftPlayer",
		"bin",
	)
	os.makedirs(fallback, exist_ok=True)
	return fallback


def download_ytdlp(target_dir, progress_cb=None, is_cancelled=None):
	"""Download yt-dlp.exe into target_dir."""
	dest = os.path.join(target_dir, "yt-dlp.exe")
	if _verify_binary(dest, "--version"):
		return dest, None
	tmp = dest + ".download"
	last_err = None
	for url in YTDLP_URLS:
		try:
			if progress_cb:
				progress_cb(0, _("Connecting to download yt-dlp..."))
			req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
			with urllib.request.urlopen(req, timeout=45) as resp:
				total = int(resp.headers.get("Content-Length") or 0)
				downloaded = 0
				with open(tmp, "wb") as f:
					while True:
						if is_cancelled and is_cancelled():
							return None, _("Download cancelled.")
						chunk = resp.read(64 * 1024)
						if not chunk:
							break
						f.write(chunk)
						downloaded += len(chunk)
						if progress_cb and total > 0:
							pct = int((downloaded / total) * 100)
							mb_down = downloaded // (1024 * 1024)
							mb_total = total // (1024 * 1024)
							progress_cb(pct, f"yt-dlp: {pct}% ({mb_down}MB / {mb_total}MB)")
			if os.path.isfile(tmp) and os.path.getsize(tmp) > 1024 * 1024:
				if not _verify_binary(tmp, "--version"):
					last_err = _("Downloaded yt-dlp is not compatible with your Windows system.")
					continue
				if os.path.isfile(dest):
					try:
						os.remove(dest)
					except Exception:
						pass
				os.replace(tmp, dest)
				return dest, None
			last_err = _("Downloaded yt-dlp file is incomplete.")
		except Exception as e:
			last_err = f"yt-dlp error: {e}"
		finally:
			if os.path.isfile(tmp):
				try:
					os.remove(tmp)
				except Exception:
					pass
	return None, last_err or _("Failed to download yt-dlp.")


def download_and_extract_ffmpeg(target_dir, progress_cb=None, is_cancelled=None):
	"""Download ffmpeg archive and extract ffmpeg.exe into target_dir."""
	dest = os.path.join(target_dir, "ffmpeg.exe")
	if _verify_binary(dest, "-version"):
		return dest, None
	last_err = None
	for url in FFMPEG_URLS:
		is_gz = url.endswith(".gz")
		tmp_archive = os.path.join(target_dir, "ffmpeg_dl.gz" if is_gz else "ffmpeg_dl.zip")
		tmp_dest = dest + ".tmp"
		try:
			if progress_cb:
				progress_cb(0, _("Connecting to download ffmpeg..."))
			req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
			with urllib.request.urlopen(req, timeout=60) as resp:
				total = int(resp.headers.get("Content-Length") or 0)
				downloaded = 0
				with open(tmp_archive, "wb") as f:
					while True:
						if is_cancelled and is_cancelled():
							return None, _("Download cancelled.")
						chunk = resp.read(128 * 1024)
						if not chunk:
							break
						f.write(chunk)
						downloaded += len(chunk)
						if progress_cb and total > 0:
							pct = int((downloaded / total) * 100)
							mb_down = downloaded // (1024 * 1024)
							mb_total = total // (1024 * 1024)
							progress_cb(pct, f"ffmpeg: {pct}% ({mb_down}MB / {mb_total}MB)")
			if os.path.isfile(tmp_archive) and os.path.getsize(tmp_archive) > 1024 * 1024:
				if progress_cb:
					progress_cb(None, _("Extracting ffmpeg.exe... Please wait."))
				if is_gz:
					with gzip.open(tmp_archive, "rb") as f_in, open(tmp_dest, "wb") as f_out:
						shutil.copyfileobj(f_in, f_out)
					if _verify_binary(tmp_dest, "-version"):
						if os.path.isfile(dest):
							try:
								os.remove(dest)
							except Exception:
								pass
						os.replace(tmp_dest, dest)
						return dest, None
				else:
					extracted = False
					with zipfile.ZipFile(tmp_archive, "r") as z:
						for name in z.namelist():
							if os.path.basename(name).lower() == "ffmpeg.exe":
								with z.open(name) as src, open(tmp_dest, "wb") as dst:
									shutil.copyfileobj(src, dst)
								if _verify_binary(tmp_dest, "-version"):
									if os.path.isfile(dest):
										try:
											os.remove(dest)
										except Exception:
											pass
									os.replace(tmp_dest, dest)
									extracted = True
								break
					if extracted:
						return dest, None
				last_err = _("ffmpeg.exe was not extracted properly or is not executable.")
		except Exception as e:
			last_err = f"ffmpeg error: {e}"
		finally:
			if os.path.isfile(tmp_archive):
				try:
					os.remove(tmp_archive)
				except Exception:
					pass
			if os.path.isfile(tmp_dest):
				try:
					os.remove(tmp_dest)
				except Exception:
					pass
	return None, last_err or _("Failed to download ffmpeg.")


class DependencySetupDialog(wx.Dialog):
	"""Modal progress dialog for downloading required dependencies on first run."""

	def __init__(self, parent, need_ytdlp, need_ffmpeg, on_finished_cb):
		self.need_ytdlp = need_ytdlp
		self.need_ffmpeg = need_ffmpeg
		self.on_finished_cb = on_finished_cb
		self._cancelled = False
		self._last_speech_time = 0.0

		super().__init__(
			parent,
			title=_("Setting Up YouTube Tools — NV-SoftPlayer"),
			size=(520, 240),
			style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP,
		)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)

		info_msg = _(
			"NV-SoftPlayer is downloading the required components (yt-dlp and ffmpeg) "
			"for YouTube streaming and audio/video downloading.\n\n"
			"This setup only happens once. Please wait..."
		)
		self.info_label = wx.StaticText(panel, label=info_msg)
		sizer.Add(self.info_label, 0, wx.ALL | wx.EXPAND, 12)

		self.status_label = wx.StaticText(panel, label=_("Initializing download..."))
		sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 12)

		self.gauge = wx.Gauge(panel, range=100, style=wx.GA_HORIZONTAL)
		sizer.Add(self.gauge, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 12)

		btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
		self.cancel_btn = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
		btn_sizer.Add(self.cancel_btn, 0, wx.ALL, 4)
		sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

		panel.SetSizer(sizer)
		self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
		self.Bind(wx.EVT_CLOSE, self.on_cancel)
		self.CentreOnScreen()

		threading.Thread(target=self._worker, daemon=True).start()

	def _worker(self):
		target_dir = get_target_bin_dir()

		def update_progress(pct, msg):
			if self._cancelled:
				return

			def _apply():
				if self._cancelled:
					return
				self.status_label.SetLabel(msg)
				if pct is not None:
					self.gauge.SetValue(max(0, min(100, pct)))
				now = time.time()
				# Speak progress periodically or on key stages
				if now - self._last_speech_time > 6.0 or pct in (0, 50, 100):
					self._last_speech_time = now
					ui.message(msg)

			wx.CallAfter(_apply)

		# Download yt-dlp if missing
		if self.need_ytdlp:
			path, err = download_ytdlp(
				target_dir,
				progress_cb=update_progress,
				is_cancelled=lambda: self._cancelled,
			)
			if err:
				wx.CallAfter(self._on_failure, err)
				return

		# Download ffmpeg if missing
		if self.need_ffmpeg:
			path, err = download_and_extract_ffmpeg(
				target_dir,
				progress_cb=update_progress,
				is_cancelled=lambda: self._cancelled,
			)
			if err:
				wx.CallAfter(self._on_failure, err)
				return

		if not self._cancelled:
			wx.CallAfter(self._on_success)

	def _on_success(self):
		if self._cancelled:
			return
		ui.message(_("YouTube components installed successfully! Opening player..."))
		try:
			self.EndModal(wx.ID_OK)
		except Exception:
			pass
		self.Destroy()
		if self.on_finished_cb:
			self.on_finished_cb()

	def _on_failure(self, error_msg):
		if self._cancelled:
			return
		handle_error(f"{_('Failed to download components')}: {error_msg}")
		try:
			self.EndModal(wx.ID_CANCEL)
		except Exception:
			pass
		self.Destroy()

	def on_cancel(self, event=None):
		self._cancelled = True
		ui.message(_("Setup cancelled."))
		try:
			self.EndModal(wx.ID_CANCEL)
		except Exception:
			pass
		self.Destroy()


def ensure_youtube_dependencies(parent, on_success):
	"""
	Verifies that both yt-dlp and ffmpeg are available.
	If both are present, immediately executes on_success.
	If either is missing, prompts with progress dialog and calls on_success when finished.
	"""
	has_ytdlp = (_find_ytdlp() is not None)
	has_ffmpeg = (_find_ffmpeg() is not None)

	if has_ytdlp and has_ffmpeg:
		on_success()
		return

	dlg = DependencySetupDialog(
		parent,
		need_ytdlp=(not has_ytdlp),
		need_ffmpeg=(not has_ffmpeg),
		on_finished_cb=on_success,
	)
	dlg.ShowModal()
