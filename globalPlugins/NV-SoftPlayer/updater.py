# -*- coding: UTF-8 -*-
"""
Automatic Update Checker for NV-SoftPlayer.
Checks GitHub Releases for new add-on versions and prompts the user.
"""

import os
import sys
import re
import json
import time
import threading
import urllib.request
import urllib.error
import wx
import config
import ui
import gui

try:
	import addonHandler
except ImportError:
	addonHandler = None

GITHUB_REPO = "AnasRayyan-it/NV-SoftPlayer"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = "NV-SoftPlayer-Updater/2.5"


def _parse_version(v_str):
	"""Parse version strings like '2.5.0' or 'v2.5.1' into comparable tuple of ints."""
	clean = re.sub(r"^[vV]", "", str(v_str or "").strip())
	parts = []
	for chunk in clean.split("."):
		num = re.sub(r"[^\d]", "", chunk)
		parts.append(int(num) if num else 0)
	while len(parts) < 3:
		parts.append(0)
	return tuple(parts)


def get_current_addon_version():
	"""Read the current version from manifest.ini."""
	try:
		if addonHandler is not None:
			addon = addonHandler.getCodeAddon()
			if addon and hasattr(addon, "manifest") and "version" in addon.manifest:
				return str(addon.manifest["version"]).strip()
	except Exception:
		pass
	# Fallback: parse manifest.ini directly from add-on directory
	try:
		here = os.path.dirname(os.path.abspath(__file__))
		root_dir = os.path.abspath(os.path.join(here, "..", ".."))
		manifest_path = os.path.join(root_dir, "manifest.ini")
		if os.path.isfile(manifest_path):
			with open(manifest_path, "r", encoding="utf-8") as f:
				for line in f:
					if line.strip().startswith("version"):
						return line.split("=", 1)[1].strip().strip('"').strip("'")
	except Exception:
		pass
	return "2.5.0"


class UpdatePromptDialog(wx.Dialog):
	"""Dialog shown when a new update is found."""
	def __init__(self, parent, latest_ver, release_info):
		self.latest_ver = latest_ver
		self.release_info = release_info
		super().__init__(
			parent,
			title="NV-SoftPlayer Update",
			size=(520, 240),
			style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP,
		)
		panel = wx.Panel(self)
		main_sizer = wx.BoxSizer(wx.VERTICAL)

		msg_text = (
			f"A new update for NV-SoftPlayer is available (version {latest_ver}).\n\n"
			f"Would you like to update now?"
		)
		static_msg = wx.StaticText(panel, label=msg_text)
		main_sizer.Add(static_msg, 0, wx.ALL | wx.EXPAND, 15)

		btn_sizer = wx.BoxSizer(wx.VERTICAL)
		self.btn_update = wx.Button(panel, label="&Yes / Update Now")
		self.btn_remind = wx.Button(panel, label="&Remind me in 10 days")
		self.btn_never = wx.Button(panel, label="&No thanks, do not remind me")

		btn_sizer.Add(self.btn_update, 0, wx.EXPAND | wx.BOTTOM, 6)
		btn_sizer.Add(self.btn_remind, 0, wx.EXPAND | wx.BOTTOM, 6)
		btn_sizer.Add(self.btn_never, 0, wx.EXPAND, 6)
		main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

		panel.SetSizer(main_sizer)

		self.btn_update.Bind(wx.EVT_BUTTON, self.on_update_now)
		self.btn_remind.Bind(wx.EVT_BUTTON, self.on_remind_later)
		self.btn_never.Bind(wx.EVT_BUTTON, self.on_never_remind)

		self.btn_update.SetDefault()
		self.btn_update.SetFocus()
		self.CentreOnScreen()

	def on_update_now(self, event):
		self.EndModal(wx.ID_OK)
		download_url = None
		# Find the .nvda-addon asset in the release
		assets = self.release_info.get("assets", [])
		for asset in assets:
			name = asset.get("name", "")
			if name.endswith(".nvda-addon"):
				download_url = asset.get("browser_download_url")
				break
		if not download_url:
			download_url = self.release_info.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/latest")

		threading.Thread(
			target=_download_and_install_update,
			args=(download_url, self.latest_ver),
			daemon=True,
		).start()

	def on_remind_later(self, event):
		self.EndModal(wx.ID_CANCEL)
		try:
			# Suppress for 10 days
			ten_days_later = time.time() + (10 * 86400)
			config.conf["nvSoftPlayer"]["remindAfter"] = float(ten_days_later)
			config.conf.save()
		except Exception:
			pass
		ui.message("You will be reminded about this update in 10 days.")

	def on_never_remind(self, event):
		self.EndModal(wx.ID_CANCEL)
		try:
			# Permanently suppress updates across restarts
			config.conf["nvSoftPlayer"]["suppressUpdates"] = True
			config.conf.save()
		except Exception:
			pass
		ui.message("Automatic update reminders permanently disabled for NV-SoftPlayer.")


def _download_and_install_update(url, version):
	"""Download the new .nvda-addon package and launch installation."""
	ui.message(f"Downloading NV-SoftPlayer version {version}...")
	temp_dir = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "nvSoftPlayer_update")
	os.makedirs(temp_dir, exist_ok=True)
	dest_file = os.path.join(temp_dir, f"NV-SoftPlayer-{version}.nvda-addon")

	try:
		req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
		with urllib.request.urlopen(req, timeout=60) as resp:
			with open(dest_file, "wb") as f:
				while True:
					chunk = resp.read(1024 * 64)
					if not chunk:
						break
					f.write(chunk)

		if os.path.isfile(dest_file) and os.path.getsize(dest_file) > 1024:
			ui.message("Download complete. Opening package installer...")
			# Launch the package using Windows default association (opens NVDA installer dialog)
			os.startfile(dest_file)
		else:
			ui.message("Update download failed: Empty file received.")
	except Exception as e:
		ui.message(f"Update failed: {e}")


def check_for_updates_async():
	"""Background worker to check for updates if enabled."""
	try:
		# Check if permanently suppressed
		conf_dict = config.conf.get("nvSoftPlayer", {})
		if conf_dict.get("suppressUpdates", False):
			return

		# Check if 10-day reminder period is still active
		remind_after = float(conf_dict.get("remindAfter", 0.0) or 0.0)
		if time.time() < remind_after:
			return

		# Fetch latest release from GitHub
		req = urllib.request.Request(
			LATEST_RELEASE_API,
			headers={
				"User-Agent": USER_AGENT,
				"Accept": "application/vnd.github.v3+json",
			},
		)
		with urllib.request.urlopen(req, timeout=12) as response:
			data = json.loads(response.read().decode("utf-8"))

		tag = data.get("tag_name", "")
		if not tag:
			return

		latest_ver = re.sub(r"^[vV]", "", tag).strip()
		current_ver = get_current_addon_version()

		if _parse_version(latest_ver) > _parse_version(current_ver):
			# Newer version exists! Prompt user in main GUI thread
			def _show():
				dlg = UpdatePromptDialog(gui.mainFrame, latest_ver, data)
				dlg.ShowModal()
				dlg.Destroy()

			wx.CallAfter(_show)
	except Exception:
		# Silently ignore network failures on startup
		pass
