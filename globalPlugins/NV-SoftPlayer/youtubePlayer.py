# -*- coding: UTF-8 -*-
import os
import re
import json
import time
import shutil
import subprocess
import threading
import urllib.parse
import urllib.request
import wx
import ui
import gui

from .common import (
	_,
	apply_ui_layout,
	handle_error,
	_cancel_speech,
	_beep_progress,
	USER_AGENT,
	_find_ffmpeg,
	_find_ytdlp,
	_creation_flags,
	get_download_folder,
)

YTDLP_OFFICIAL_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"


def _yt_cache_dir():
	path = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "nvSoftPlayer")
	try:
		os.makedirs(path, exist_ok=True)
	except Exception:
		pass
	return path


def _runtime_bin_dir():
	path = os.path.join(_yt_cache_dir(), "bin")
	try:
		os.makedirs(path, exist_ok=True)
	except Exception:
		pass
	return path


def _download_ytdlp_runtime():
	target = os.path.join(_runtime_bin_dir(), "yt-dlp.exe")
	tmp = target + ".download"
	try:
		if os.path.isfile(target) and os.path.getsize(target) > 1024 * 1024:
			return target
		request = urllib.request.Request(
			YTDLP_OFFICIAL_URL,
			headers={"User-Agent": USER_AGENT},
		)
		with urllib.request.urlopen(request, timeout=60) as response:
			with open(tmp, "wb") as f:
				while True:
					chunk = response.read(1024 * 1024)
					if not chunk:
						break
					f.write(chunk)
		if os.path.isfile(tmp) and os.path.getsize(tmp) > 1024 * 1024:
			os.replace(tmp, target)
			return target
	except Exception:
		pass
	finally:
		try:
			if os.path.isfile(tmp):
				os.remove(tmp)
		except Exception:
			pass
	return None


def _run_ytdlp(args, timeout=60):
	cmd_base = _find_ytdlp()
	if not cmd_base:
		return None, (
			"yt-dlp was not found. Place the Windows x64 yt-dlp.exe "
			"(not the arm64 build) in this add-on's bin folder."
		)
	cmd = list(cmd_base) + list(args)
	try:
		proc = subprocess.run(
			cmd,
			capture_output=True,
			text=True,
			timeout=timeout,
			creationflags=_creation_flags(),
		)
		return proc, None
	except subprocess.TimeoutExpired:
		return None, "yt-dlp timed out."
	except OSError as e:
		if getattr(e, "winerror", None) == 216:
			return None, (
				"This yt-dlp.exe does not match your PC. "
				"Download yt-dlp.exe (x64), not yt-dlp_arm64.exe, from "
				"https://github.com/yt-dlp/yt-dlp/releases/latest"
			)
		return None, f"yt-dlp error: {e}"
	except Exception as e:
		return None, f"yt-dlp error: {e}"


YT_CLIENT_ARGS = [
	"--extractor-args",
	"youtube:player_client=android,web",
	"--no-check-formats",
]
YT_AUDIO_FORMAT = "140/139/bestaudio[ext=m4a]/ba[ext=m4a]/ba/18"
YT_VIDEO_FORMAT = "18/22/17/best[ext=mp4][protocol^=https]/best[ext=mp4]/best"


def _yt_video_id(page_url):
	text = page_url or ""
	m = re.search(r"(?:v=|/shorts/|youtu\.be/)([A-Za-z0-9_-]{11})", text)
	if m:
		return m.group(1)
	m = re.search(r"([A-Za-z0-9_-]{11})", text)
	return m.group(1) if m else ""


def _cached_media(vid, exts):
	if not vid:
		return None
	folder = _yt_cache_dir()
	for ext in exts:
		path = os.path.join(folder, f"{vid}.{ext}")
		try:
			if os.path.isfile(path) and os.path.getsize(path) > 2048:
				return path
		except Exception:
			continue
	return None


def _is_wmp_friendly_url(url):
	if not url:
		return False
	u = url.lower()
	if any(x in u for x in ("audio/webm", "video/webm", ".webm", "codecs=opus", "m3u8", "mpegurl")):
		return False
	if any(x in u for x in (
		"audio/mp4", "video/mp4", "audio/mpeg", ".m4a", ".mp3", ".mp4",
		"itag=140", "itag=139", "itag=18", "itag=22", "itag=17",
	)):
		return True
	return "googlevideo.com" not in u


def youtube_search(query, max_results=20):
	search_term = (query or "").strip()
	if not search_term:
		return None, "Empty search query."
	is_url = search_term.startswith("http://") or search_term.startswith("https://")
	if is_url:
		args = list(YT_CLIENT_ARGS) + [
			"--flat-playlist", "--dump-single-json", "--no-warnings",
			"--socket-timeout", "15", search_term,
		]
	else:
		args = [
			f"ytsearch{max_results}:{search_term}",
			"--flat-playlist",
			"--dump-single-json",
			"--no-warnings",
			"--socket-timeout", "15",
		] + list(YT_CLIENT_ARGS)
	proc, err = _run_ytdlp(args, timeout=60)
	if err:
		return None, err
	if proc.returncode != 0:
		err_text = (proc.stderr or proc.stdout or "Unknown yt-dlp error").strip()
		return None, f"yt-dlp failed: {err_text[:300]}"
	try:
		data = json.loads(proc.stdout)
	except json.JSONDecodeError:
		return None, "yt-dlp returned invalid JSON."
	results = []
	entries = data.get("entries") if isinstance(data, dict) else None
	if entries is None and isinstance(data, dict) and data.get("id"):
		entries = [data]
	if not entries:
		return None, "No YouTube results found."
	for entry in entries:
		if not isinstance(entry, dict):
			continue
		vid = entry.get("id") or ""
		title = entry.get("title") or "Untitled"
		uploader = entry.get("uploader") or entry.get("channel") or "Unknown"
		duration = entry.get("duration")
		ie_key = (entry.get("ie_key") or entry.get("_type") or "").lower()
		url = entry.get("url") or entry.get("webpage_url") or ""
		if not url and vid:
			url = f"https://www.youtube.com/watch?v={vid}"
		is_playlist = (
			"playlist" in ie_key
			or entry.get("_type") == "playlist"
			or "/playlist" in (url or "")
		)
		results.append({
			"id": vid,
			"title": title,
			"uploader": uploader,
			"duration": duration,
			"url": url,
			"is_playlist": is_playlist,
		})
	if not results:
		return None, "No playable YouTube results."
	return results, None


def youtube_get_audio_url(page_url):
	args = list(YT_CLIENT_ARGS) + [
		"-f", YT_AUDIO_FORMAT,
		"-g",
		"--no-playlist",
		"--no-warnings",
		"--socket-timeout", "12",
		"--retries", "1",
		page_url,
	]
	proc, err = _run_ytdlp(args, timeout=20)
	if err:
		return None, err
	if proc is None or proc.returncode != 0:
		err_text = ""
		if proc is not None:
			err_text = (proc.stderr or proc.stdout or "").strip()
		return None, f"Could not extract audio: {(err_text or 'unknown')[:250]}"
	lines = [
		ln.strip() for ln in (proc.stdout or "").splitlines()
		if ln.strip().startswith("http")
	]
	if not lines:
		return None, "No audio stream URL returned."
	if len(lines) == 1:
		return lines[0], None
	audioish = [
		u for u in lines
		if "audio" in u.lower() or "m4a" in u.lower() or "mp4a" in u.lower() or "itag=140" in u.lower()
	]
	return (audioish[0] if audioish else lines[-1]), None


def youtube_download_temp(page_url, kind="audio"):
	vid = _yt_video_id(page_url) or str(int(time.time() * 1000))
	ext = "m4a" if kind == "audio" else "mp4"
	cached = _cached_media(vid, (ext, "m4a", "mp4", "mp3"))
	if cached:
		return cached, None
	out_path = os.path.join(_yt_cache_dir(), f"{vid}.{ext}")
	fmt = YT_AUDIO_FORMAT if kind == "audio" else YT_VIDEO_FORMAT
	ffmpeg = _find_ffmpeg()
	args = list(YT_CLIENT_ARGS) + [
		"-f", fmt,
		"--no-playlist",
		"--no-warnings",
		"--no-part",
		"--socket-timeout", "15",
		"--retries", "2",
		"-o", out_path,
	]
	if ffmpeg:
		args.extend(["--ffmpeg-location", os.path.dirname(ffmpeg)])
	args.append(page_url)
	proc, err = _run_ytdlp(args, timeout=90)
	if err:
		return None, err
	if os.path.isfile(out_path) and os.path.getsize(out_path) > 2048:
		return out_path, None
	cached = _cached_media(vid, (ext, "m4a", "mp4", "mp3"))
	if cached:
		return cached, None
	err_text = ""
	if proc is not None:
		err_text = (proc.stderr or proc.stdout or "").strip()
	return None, f"Could not prepare media: {(err_text or 'download failed')[:250]}"


def youtube_prepare_audio(page_url):
	vid = _yt_video_id(page_url)
	cached = _cached_media(vid, ("m4a", "mp3", "mp4"))
	if cached:
		return cached, None
	url, err = youtube_get_audio_url(page_url)
	if url:
		return url, None
	path, error = youtube_download_temp(page_url, kind="audio")
	if path:
		return path, None
	return None, err or error or "Could not prepare audio for playback."


def youtube_get_video_url(page_url):
	args = list(YT_CLIENT_ARGS) + [
		"-f", YT_VIDEO_FORMAT,
		"-g",
		"--no-playlist",
		"--no-warnings",
		"--socket-timeout", "12",
		"--retries", "1",
		page_url,
	]
	proc, err = _run_ytdlp(args, timeout=20)
	if err:
		return None, err
	if proc is None or proc.returncode != 0:
		err_text = ""
		if proc is not None:
			err_text = (proc.stderr or proc.stdout or "").strip()
		return None, f"Could not extract video: {(err_text or 'unknown')[:250]}"
	lines = [
		ln.strip() for ln in (proc.stdout or "").splitlines()
		if ln.strip().startswith("http")
	]
	if not lines:
		return None, "No video stream URL returned."
	return lines[-1] if len(lines) > 1 else lines[0], None


def youtube_prepare_video(page_url):
	vid = _yt_video_id(page_url)
	cached = _cached_media(vid, ("mp4", "m4a", "mp3"))
	if cached:
		return cached, None
	url, _ = youtube_get_video_url(page_url)
	if url:
		return url, None
	path, error = youtube_download_temp(page_url, kind="video")
	if path:
		return path, None
	return None, error or "Could not prepare a local video file."


def youtube_expand_playlist(playlist_url, max_items=50):
	args = list(YT_CLIENT_ARGS) + [
		"--flat-playlist",
		"--dump-single-json",
		"--no-warnings",
		"--playlist-end", str(max_items),
		"--socket-timeout", "15",
		playlist_url,
	]
	proc, err = _run_ytdlp(args, timeout=90)
	if err:
		return None, err
	if proc.returncode != 0:
		err_text = (proc.stderr or proc.stdout or "").strip()
		return None, f"Playlist load failed: {err_text[:250]}"
	try:
		data = json.loads(proc.stdout)
	except Exception as e:
		return None, f"Playlist error: {e}"
	entries = data.get("entries") or []
	results = []
	for entry in entries:
		if not isinstance(entry, dict):
			continue
		vid = entry.get("id") or ""
		title = entry.get("title") or "Untitled"
		url = entry.get("url") or entry.get("webpage_url") or ""
		if not url and vid:
			url = f"https://www.youtube.com/watch?v={vid}"
		results.append({
			"id": vid,
			"title": title,
			"uploader": entry.get("uploader") or entry.get("channel") or "",
			"duration": entry.get("duration"),
			"url": url,
			"is_playlist": False,
		})
	return results, None


def is_youtube_playlist_url(text):
	if not text:
		return False
	low = str(text).strip().lower()
	if "list=" in low and ("youtube." in low or "youtu.be" in low):
		return True
	if "youtube.com/playlist" in low or "youtu.be/playlist" in low:
		return True
	return False


def youtube_download(page_url, dest_dir=None, kind="mp3", progress_callback=None, is_playlist=False):
	if not page_url:
		return None, "Missing URL."
	if not dest_dir or not os.path.isdir(dest_dir):
		dest_dir = get_download_folder()
	ffmpeg = _find_ffmpeg()
	out_tmpl = os.path.join(dest_dir, "%(title)s.%(ext)s")
	cmd_base = _find_ytdlp()
	if not cmd_base:
		return None, (
			"yt-dlp was not found. Place the Windows x64 yt-dlp.exe "
			"(not the arm64 build) in this add-on's bin folder."
		)
	args = list(cmd_base) + [
		"--no-warnings",
		"--newline",
		"-o", out_tmpl,
	]
	if is_playlist:
		args.append("--yes-playlist")
	else:
		args.append("--no-playlist")
	if ffmpeg:
		args.extend(["--ffmpeg-location", os.path.dirname(ffmpeg)])
	if kind == "mp3":
		if ffmpeg:
			args.extend([
				"-f", "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio/best",
				"-x", "--audio-format", "mp3", "--audio-quality", "0",
			])
		else:
			args.extend(["-f", "bestaudio[ext=m4a]/bestaudio/best"])
	else:
		if ffmpeg:
			args.extend([
				"-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bv*+ba/b",
				"--merge-output-format", "mp4",
			])
		else:
			args.extend([
				"-f",
				"best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best",
			])
	args.append(page_url)

	try:
		proc = subprocess.Popen(
			args,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			text=True,
			encoding="utf-8",
			errors="replace",
			creationflags=_creation_flags(),
		)
	except OSError as e:
		if getattr(e, "winerror", None) == 216:
			return None, (
				"This yt-dlp.exe does not match your PC. "
				"Download yt-dlp.exe (x64), not yt-dlp_arm64.exe, from "
				"https://github.com/yt-dlp/yt-dlp/releases/latest"
			)
		return None, f"yt-dlp error: {e}"
	except Exception as e:
		return None, f"yt-dlp error: {e}"

	last_pct = -1
	output_lines = []
	pct_re = re.compile(r"\[download\]\s+(\d{1,3}(?:\.\d+)?)%")
	try:
		for line in proc.stdout:
			line = (line or "").rstrip()
			if not line:
				continue
			output_lines.append(line)
			m = pct_re.search(line)
			if m and progress_callback:
				try:
					pct = int(float(m.group(1)))
				except Exception:
					pct = None
				if pct is not None and pct != last_pct and (pct % 2 == 0 or pct >= 99):
					last_pct = pct
					try:
						progress_callback(pct, f"Downloading {pct} percent")
					except Exception:
						pass
			elif progress_callback and "[ExtractAudio]" in line:
				try:
					progress_callback(None, "Converting audio…")
				except Exception:
					pass
			elif progress_callback and "Merging" in line:
				try:
					progress_callback(None, "Merging video and audio…")
				except Exception:
					pass
		proc.wait(timeout=600)
	except subprocess.TimeoutExpired:
		try:
			proc.kill()
		except Exception:
			pass
		return None, "Download timed out."
	except Exception as e:
		try:
			proc.kill()
		except Exception:
			pass
		return None, f"Download error: {e}"

	if proc.returncode != 0:
		err_text = "\n".join(output_lines[-15:]).strip()
		if "ffmpeg" in err_text.lower() and not ffmpeg:
			return None, (
				"ffmpeg is required for MP3/MP4 conversion. "
				"Put ffmpeg.exe in the add-on bin folder next to yt-dlp.exe. "
				"Download: https://www.gyan.dev/ffmpeg/builds/"
			)
		return None, f"Download failed: {err_text[:300]}"
	if progress_callback:
		try:
			progress_callback(100, "Download finished")
		except Exception:
			pass
	return dest_dir, None


class YouTubePlaylistActionDialog(wx.Dialog):
	def __init__(self, parent, playlist_url, on_action_cb):
		self.playlist_url = playlist_url
		self.on_action_cb = on_action_cb
		super().__init__(
			parent,
			title=_("YouTube Playlist — NV-SoftPlayer"),
			size=(520, 260),
		)
		apply_ui_layout(self)
		panel = wx.Panel(self)
		main_sizer = wx.BoxSizer(wx.VERTICAL)

		prompt_label = wx.StaticText(
			panel,
			label=_("What do you want to do?"),
		)
		main_sizer.Add(prompt_label, 0, wx.ALL | wx.EXPAND, 12)

		btn_sizer1 = wx.BoxSizer(wx.HORIZONTAL)
		self.play_audio_btn = wx.Button(panel, label=_("Play as audio"))
		self.play_video_btn = wx.Button(panel, label=_("Play as video"))
		btn_sizer1.Add(self.play_audio_btn, 1, wx.ALL, 6)
		btn_sizer1.Add(self.play_video_btn, 1, wx.ALL, 6)
		main_sizer.Add(btn_sizer1, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)

		btn_sizer2 = wx.BoxSizer(wx.HORIZONTAL)
		self.dl_mp3_btn = wx.Button(panel, label=_("Download as MP3"))
		self.dl_mp4_btn = wx.Button(panel, label=_("Download as MP4"))
		btn_sizer2.Add(self.dl_mp3_btn, 1, wx.ALL, 6)
		btn_sizer2.Add(self.dl_mp4_btn, 1, wx.ALL, 6)
		main_sizer.Add(btn_sizer2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)

		close_sizer = wx.BoxSizer(wx.HORIZONTAL)
		self.cancel_btn = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
		close_sizer.Add(self.cancel_btn, 0, wx.ALL, 6)
		main_sizer.Add(close_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 6)

		panel.SetSizer(main_sizer)

		self.play_audio_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose("audio"))
		self.play_video_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose("video"))
		self.dl_mp3_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose("dl_mp3"))
		self.dl_mp4_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose("dl_mp4"))
		self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
		self.Bind(wx.EVT_CLOSE, self.on_cancel)
		self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)

		self.play_audio_btn.SetFocus()
		self.CentreOnParent()

	def on_key_down(self, event):
		if event.GetKeyCode() == wx.WXK_ESCAPE:
			self.on_cancel(event)
			return
		event.Skip()

	def _choose(self, action):
		self.EndModal(wx.ID_OK)
		if self.on_action_cb:
			wx.CallAfter(self.on_action_cb, action, self.playlist_url)

	def on_cancel(self, event=None):
		self.EndModal(wx.ID_CANCEL)


class YouTubeDialog(wx.Dialog):
	def __init__(self, parent, plugin):
		self.plugin = plugin
		self.results = []
		self._closed = False
		self._busy = False
		self._dl_progress = None
		super().__init__(parent, title=_("YouTube — NV-SoftPlayer"), size=(760, 560))
		apply_ui_layout(self)
		panel = wx.Panel(self)
		main_sizer = wx.BoxSizer(wx.VERTICAL)
		label = wx.StaticText(
			panel,
			label=_("Search YouTube, or paste a video / playlist URL:"),
		)
		main_sizer.Add(label, 0, wx.EXPAND | wx.ALL, 8)
		self.query_ctrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
		main_sizer.Add(self.query_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
		self.status_label = wx.StaticText(
			panel,
			label=_("Type a search and press Enter. This window stays open."),
		)
		main_sizer.Add(self.status_label, 0, wx.EXPAND | wx.ALL, 8)
		self.list_box = wx.ListBox(panel, style=wx.LB_SINGLE)
		main_sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 8)
		row1 = wx.BoxSizer(wx.HORIZONTAL)
		self.search_button = wx.Button(panel, label="&" + _("Search"))
		self.play_audio_button = wx.Button(panel, label=_("Play &audio"))
		self.play_video_button = wx.Button(panel, label=_("Play &video"))
		self.play_queue_button = wx.Button(panel, label=_("Play as queue"))
		row1.Add(self.search_button, 0, wx.ALL, 4)
		row1.Add(self.play_audio_button, 0, wx.ALL, 4)
		row1.Add(self.play_video_button, 0, wx.ALL, 4)
		row1.Add(self.play_queue_button, 0, wx.ALL, 4)
		main_sizer.Add(row1, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
		row2 = wx.BoxSizer(wx.HORIZONTAL)
		self.dl_mp3_button = wx.Button(panel, label=_("Download MP3"))
		self.dl_mp4_button = wx.Button(panel, label=_("Download MP4"))
		self.close_button = wx.Button(panel, wx.ID_CLOSE, label="&" + _("Close"))
		row2.Add(self.dl_mp3_button, 0, wx.ALL, 4)
		row2.Add(self.dl_mp4_button, 0, wx.ALL, 4)
		row2.Add(self.close_button, 0, wx.ALL, 4)
		main_sizer.Add(row2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
		panel.SetSizer(main_sizer)
		self.search_button.Bind(wx.EVT_BUTTON, self.on_search)
		self.query_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_search)
		self.play_audio_button.Bind(wx.EVT_BUTTON, self.on_play_audio)
		self.play_video_button.Bind(wx.EVT_BUTTON, self.on_play_video)
		self.play_queue_button.Bind(wx.EVT_BUTTON, self.on_play_queue)
		self.dl_mp3_button.Bind(wx.EVT_BUTTON, lambda e: self.on_download("mp3"))
		self.dl_mp4_button.Bind(wx.EVT_BUTTON, lambda e: self.on_download("mp4"))
		self.close_button.Bind(wx.EVT_BUTTON, self.on_close)
		self.list_box.Bind(wx.EVT_LISTBOX_DCLICK, self.on_play_audio)
		self.Bind(wx.EVT_CLOSE, self.on_close)
		self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)
		self.query_ctrl.SetFocus()
		self.CentreOnParent()

	def on_key_down(self, event):
		key = event.GetKeyCode()
		alt_down = event.AltDown()
		if key == wx.WXK_ESCAPE:
			self.on_close(event)
			return
		if alt_down and key in (ord('A'), ord('a')):
			self.on_play_audio(event)
			return
		if alt_down and key in (ord('V'), ord('v')):
			self.on_play_video(event)
			return
		if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and self.list_box.HasFocus():
			self.on_play_audio(event)
			return
		event.Skip()

	def _selected(self):
		idx = self.list_box.GetSelection()
		if idx == wx.NOT_FOUND or idx < 0 or idx >= len(self.results):
			return None
		return self.results[idx]

	def _set_busy(self, busy, status=None):
		self._busy = busy
		self.search_button.Enable(not busy)
		self.play_audio_button.Enable(not busy)
		self.play_video_button.Enable(not busy)
		self.play_queue_button.Enable(not busy)
		self.dl_mp3_button.Enable(not busy)
		self.dl_mp4_button.Enable(not busy)
		if status is not None:
			self.status_label.SetLabel(status)

	def on_search(self, event):
		if self._busy:
			ui.message("A search is already running.")
			return
		query = self.query_ctrl.GetValue().strip()
		if not query:
			ui.message("Enter a search query or paste a YouTube URL.")
			return
		if is_youtube_playlist_url(query):
			if not (query.startswith("http://") or query.startswith("https://")):
				query = "https://" + query
			self._open_playlist_dialog(query)
			return
		self._set_busy(True, f"Searching YouTube for {query}. This window stays open.")
		ui.message(f"Searching YouTube for {query}")
		threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

	def _open_playlist_dialog(self, playlist_url):
		dlg = YouTubePlaylistActionDialog(self, playlist_url, self._handle_playlist_action)
		dlg.ShowModal()
		dlg.Destroy()

	def _handle_playlist_action(self, action, playlist_url):
		if self._closed:
			return
		if action == "audio":
			item = {"url": playlist_url, "title": "Playlist", "is_playlist": True}
			self._set_busy(True, "Loading playlist audio...")
			ui.message("Loading playlist as audio...")
			threading.Thread(target=self._load_playlist_and_play, args=(item,), daemon=True).start()
		elif action == "video":
			self._set_busy(True, "Loading playlist video...")
			ui.message("Loading playlist as video...")
			threading.Thread(target=self._load_playlist_and_play_video, args=(playlist_url,), daemon=True).start()
		elif action == "dl_mp3":
			self._download_playlist_url(playlist_url, kind="mp3")
		elif action == "dl_mp4":
			self._download_playlist_url(playlist_url, kind="mp4")

	def _search_worker(self, query):
		results, error = youtube_search(query, max_results=20)
		wx.CallAfter(self._search_done, results, error)

	def _search_done(self, results, error):
		if self._closed:
			return
		self._set_busy(False)
		if error:
			self.status_label.SetLabel(f"Error: {error}")
			handle_error(error)
			return
		self.results = results or []
		labels = []
		for r in self.results:
			dur = f" ({r['duration']}s)" if r.get("duration") else ""
			kind = " [Playlist]" if r.get("is_playlist") else ""
			labels.append(
				f"{r.get('title', 'Untitled')} — {r.get('uploader', '')}{dur}{kind}"
			)
		self.list_box.Set(labels)
		if labels:
			self.list_box.SetSelection(0)
			self.list_box.SetFocus()
		self.status_label.SetLabel(
			f"{len(self.results)} results. Play audio, play video, or download."
		)
		ui.message(f"Found {len(self.results)} YouTube results")

	def on_play_audio(self, event):
		if self._busy:
			ui.message("Already working.")
			return
		item = self._selected()
		if item is None:
			ui.message("Select a result first.")
			return
		self._set_busy(True, f"Preparing audio: {item.get('title', '')}")
		if item.get("is_playlist"):
			ui.message(f"Loading playlist: {item.get('title', '')}")
			threading.Thread(
				target=self._load_playlist_and_play, args=(item,), daemon=True
			).start()
		else:
			ui.message(f"Preparing audio: {item.get('title', '')}")
			threading.Thread(
				target=self._prepare_audio, args=([item],), daemon=True
			).start()

	def on_play_queue(self, event):
		if self._busy:
			ui.message("Already working.")
			return
		videos = [r for r in self.results if not r.get("is_playlist")]
		if not videos:
			ui.message("No individual videos to queue. Select a playlist instead.")
			return
		self._set_busy(True, f"Preparing audio queue of {len(videos)} tracks...")
		ui.message(f"Preparing audio queue of {len(videos)} tracks")
		threading.Thread(target=self._prepare_audio, args=(videos,), daemon=True).start()

	def _load_playlist_and_play(self, item):
		entries, error = youtube_expand_playlist(item.get("url") or "")
		if error:
			wx.CallAfter(self._fail, error)
			return
		if not entries:
			wx.CallAfter(self._fail, "Playlist is empty.")
			return
		self._prepare_audio(entries)

	def _prepare_audio(self, items):
		if not items:
			wx.CallAfter(self._fail, _("Could not prepare any audio."))
			return
		first = items[0]
		page_url = first.get("url") or ""
		title = first.get("title") or "YouTube track"
		media, error = youtube_prepare_audio(page_url)
		if not media:
			wx.CallAfter(
				self._fail,
				error or _("Could not prepare any audio."),
			)
			return
		stream_urls = [media]
		titles = [title]
		wx.CallAfter(self._start_audio_player, list(stream_urls), list(titles))
		for item in items[1:]:
			page_url = item.get("url") or ""
			if not page_url:
				continue
			more, err = youtube_prepare_audio(page_url)
			if more:
				stream_urls.append(more)
				titles.append(item.get("title") or "YouTube track")
		if len(stream_urls) > 1:
			wx.CallAfter(self._extend_player_queue, stream_urls, titles)

	def _extend_player_queue(self, stream_urls, titles):
		if self._closed or not self.plugin or not getattr(self.plugin, "_playerDialog", None):
			return
		try:
			self.plugin._playerDialog.replace_upcoming(stream_urls, titles)
		except Exception:
			pass

	def _start_audio_player(self, stream_urls, titles):
		if self._closed:
			return
		self._set_busy(False, _("Playing. Search window stays open."))
		_cancel_speech()
		if self.plugin:
			self.plugin._open_player(
				stream_urls, repeat_scope="playlist", titles=titles, quiet_open=True
			)

	def on_play_video(self, event):
		if self._busy:
			ui.message(_("Already working."))
			return
		item = self._selected()
		if item is None:
			ui.message(_("Select a result first."))
			return
		if item.get("is_playlist"):
			self._set_busy(True, "Loading playlist video...")
			ui.message("Loading playlist video...")
			threading.Thread(
				target=self._load_playlist_and_play_video,
				args=(item.get("url") or "",),
				daemon=True,
			).start()
			return
		self._set_busy(True, f"{_('Play video')}: {item.get('title', '')}")
		ui.message(f"{_('Play video')}: {item.get('title', '')}")
		threading.Thread(
			target=self._play_video_worker, args=(item,), daemon=True
		).start()

	def _load_playlist_and_play_video(self, playlist_url):
		entries, error = youtube_expand_playlist(playlist_url)
		if error:
			wx.CallAfter(self._fail, error)
			return
		if not entries:
			wx.CallAfter(self._fail, "Playlist is empty.")
			return
		self._prepare_video_queue(entries)

	def _prepare_video_queue(self, items):
		if not items:
			wx.CallAfter(self._fail, _("Could not prepare any video."))
			return
		first = items[0]
		page_url = first.get("url") or ""
		title = first.get("title") or "YouTube video"
		media, error = youtube_prepare_video(page_url)
		if not media:
			wx.CallAfter(self._fail, error or _("Could not prepare any video."))
			return
		stream_urls = [media]
		titles = [title]
		wx.CallAfter(self._start_video_player, media, title)
		for item in items[1:]:
			u = item.get("url") or ""
			if not u:
				continue
			more, _ = youtube_prepare_video(u)
			if more:
				stream_urls.append(more)
				titles.append(item.get("title") or "YouTube video")
		if len(stream_urls) > 1:
			wx.CallAfter(self._extend_player_queue, stream_urls, titles)

	def _play_video_worker(self, item):
		page_url = item.get("url") or ""
		title = item.get("title") or "YouTube video"
		media, error = youtube_prepare_video(page_url)
		if error or not media:
			wx.CallAfter(self._fail, error or _("Could not extract video."))
			return
		wx.CallAfter(self._start_video_player, media, title)

	def _start_video_player(self, media_path, title):
		if self._closed:
			return
		self._set_busy(False, _("Playing. Search window stays open."))
		_cancel_speech()
		if self.plugin:
			self.plugin._open_player(
				[media_path], repeat_scope="track", titles=[title], quiet_open=True
			)

	def on_download(self, kind):
		if self._busy:
			ui.message("Already working.")
			return
		item = self._selected()
		if item is None:
			ui.message("Select a result first.")
			return
		dest = get_download_folder()
		title = item.get("title", "") or "download"
		is_pl = bool(item.get("is_playlist"))
		label = f"playlist {title}" if is_pl else title
		self._set_busy(
			True,
			f"Downloading {kind.upper()}: {label}. This window stays open.",
		)
		ui.message(f"Downloading {kind.upper()} for {label}")
		_beep_progress(0)
		try:
			progress = wx.ProgressDialog(
				f"Downloading {kind.upper()}",
				f"Starting download of {label}",
				maximum=100,
				parent=self,
				style=wx.PD_AUTO_HIDE | wx.PD_ELAPSED_TIME | wx.PD_SMOOTH,
			)
			progress.Show()
		except Exception:
			progress = None
		self._dl_progress = progress
		threading.Thread(
			target=self._download_worker,
			args=(item, dest, kind, progress, is_pl),
			daemon=True,
		).start()

	def _download_playlist_url(self, playlist_url, kind="mp3"):
		dest = get_download_folder()
		label = f"Playlist {kind.upper()}"
		self._set_busy(True, f"Downloading {label}. This window stays open.")
		ui.message(f"Downloading {label} into Music\\NV-SoftPlayer")
		_beep_progress(0)
		try:
			progress = wx.ProgressDialog(
				f"Downloading {label}",
				f"Starting download of playlist...",
				maximum=100,
				parent=self,
				style=wx.PD_AUTO_HIDE | wx.PD_ELAPSED_TIME | wx.PD_SMOOTH,
			)
			progress.Show()
		except Exception:
			progress = None
		self._dl_progress = progress
		item = {"url": playlist_url, "title": "Playlist", "is_playlist": True}
		threading.Thread(
			target=self._download_worker,
			args=(item, dest, kind, progress, True),
			daemon=True,
		).start()

	def _download_progress(self, progress, percent, status):
		if self._closed:
			return
		try:
			if progress is not None:
				if percent is None:
					progress.Pulse(status or "Working…")
				else:
					progress.Update(max(0, min(100, int(percent))), status or "")
		except Exception:
			pass
		try:
			if percent is not None:
				_beep_progress(int(percent))
				if int(percent) in (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100):
					ui.message(status or f"{int(percent)} percent")
			else:
				_beep_progress(None)
				if status:
					ui.message(status)
		except Exception:
			pass

	def _download_worker(self, item, dest, kind, progress=None, is_playlist=False):
		def cb(percent, status):
			wx.CallAfter(self._download_progress, progress, percent, status)

		path, error = youtube_download(
			item.get("url") or "", dest, kind=kind, progress_callback=cb, is_playlist=is_playlist
		)
		def finish():
			try:
				if progress is not None:
					progress.Destroy()
			except Exception:
				pass
			self._dl_progress = None
			if error:
				self._fail(error)
				return
			label = "Playlist" if is_playlist else kind.upper()
			self._set_busy(False, f"{label} saved in {dest}")
			ui.message(f"{label} download finished in {dest}")

		wx.CallAfter(finish)

	def _fail(self, error):
		if self._closed:
			return
		self._set_busy(False, error)
		handle_error(error)

	def on_close(self, event=None):
		if self._closed:
			return
		self._closed = True
		try:
			gui.mainFrame.postPopup()
		except Exception:
			pass
		self.Destroy()


def show_youtube_dialog(parent, plugin):
	if not _find_ytdlp():
		handle_error(
			"yt-dlp was not found. Place the Windows x64 yt-dlp.exe "
			"(not arm64) in globalPlugins/NV-SoftPlayer/bin/ then restart NVDA. "
			"Download: https://github.com/yt-dlp/yt-dlp/releases/latest"
		)
		return None
	gui.mainFrame.prePopup()
	dlg = YouTubeDialog(parent, plugin)
	dlg.Show()
	dlg.Raise()
	dlg.query_ctrl.SetFocus()
	return dlg
