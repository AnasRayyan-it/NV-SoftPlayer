# -*- coding: UTF-8 -*-
import os
import threading
import wx
import globalPluginHandler
import scriptHandler
import api
import ui
import gui
import config

from .common import (
	_,
	apply_ui_layout,
	handle_error,
	display_name,
	format_time,
	get_focused_audio_file,
	get_selected_audio_files,
	get_focused_folder,
	get_selected_folders,
	list_audio_in_folder,
	collect_audio_from_folders,
	get_audio_duration_seconds,
	load_addon_store,
	save_addon_store,
	_conf_get,
	get_ai_provider,
	get_groq_api_key,
	get_gemini_api_key,
	get_repeat_on,
	get_shuffle_on,
	get_preferred_languages,
	PROVIDER_LABELS,
	PROVIDER_VALUES,
	DEFAULT_IGNORE_WORDS,
	_find_ytdlp,
	cleanup_temp_files,
)

from .audioPlayer import (
	NVSoftPlayerDialog,
	open_player,
)

from .lyricsFetcher import (
	fetch_lyrics_online,
	ManualSearchDialog,
	LyricsDialog,
)

from .youtubePlayer import (
	YouTubeDialog,
	show_youtube_dialog,
)

config.conf.spec["nvSoftPlayer"] = {
	"ignoreWords": 'string(default="")',
	"geminiApiKey": 'string(default="")',
	"groqApiKey": 'string(default="")',
	"aiProvider": 'string(default="groq")',
	"preferredLanguages": 'string(default="Arabic,English")',
	"repeatOn": "boolean(default=False)",
	"shuffleOn": "boolean(default=False)",
}


class SoftPlayerSettingsPanel(gui.settingsDialogs.SettingsPanel):
	title = "NV-SoftPlayer"

	def makeSettings(self, settingsSizer):
		apply_ui_layout(self)
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		store = load_addon_store()
		current_provider = get_ai_provider()
		self.providerChoice = sHelper.addLabeledControl(
			_("AI provider for translation, song info, and artist details:"),
			wx.Choice,
			choices=PROVIDER_LABELS,
		)
		if current_provider in PROVIDER_VALUES:
			self.providerChoice.SetSelection(PROVIDER_VALUES.index(current_provider))
		else:
			self.providerChoice.SetSelection(0)
		self.groqKeyCtrl = sHelper.addLabeledControl(
			_("Groq API Key (recommended, free):"),
			wx.TextCtrl,
			value=get_groq_api_key(),
		)
		sHelper.addItem(wx.StaticText(
			self, label="Get a free Groq key: https://console.groq.com/keys"
		))
		self.geminiKeyCtrl = sHelper.addLabeledControl(
			"Gemini API Key (optional backup):",
			wx.TextCtrl,
			value=get_gemini_api_key(),
		)
		sHelper.addItem(wx.StaticText(
			self, label="Get a Gemini key: https://aistudio.google.com/apikey"
		))
		current_words = str(_conf_get("ignoreWords") or "")
		if not current_words:
			current_words = store.get("ignoreWords") or DEFAULT_IGNORE_WORDS
		self.ignoreWordsCtrl = sHelper.addLabeledControl(
			"Words to ignore during search (space or comma separated):",
			wx.TextCtrl,
			value=current_words,
		)
		pref_langs = ", ".join(get_preferred_languages())
		self.prefLangsCtrl = sHelper.addLabeledControl(
			_("Preferred translation languages (comma-separated, first is default):"),
			wx.TextCtrl,
			value=pref_langs,
		)
		sHelper.addItem(wx.StaticText(
			self,
			label="Example: Arabic, English, French. Used by context-menu Translate and as defaults.",
		))
		self.repeatCheck = sHelper.addItem(
			wx.CheckBox(self, label=_("Repeat on by default"))
		)
		self.repeatCheck.SetValue(get_repeat_on())
		self.shuffleCheck = sHelper.addItem(
			wx.CheckBox(self, label=_("Shuffle on by default"))
		)
		self.shuffleCheck.SetValue(get_shuffle_on())

	def onSave(self):
		selection = self.providerChoice.GetSelection()
		provider = "groq" if selection == wx.NOT_FOUND else PROVIDER_VALUES[selection]
		groq_key = self.groqKeyCtrl.GetValue().strip()
		gemini_key = self.geminiKeyCtrl.GetValue().strip()
		words = self.ignoreWordsCtrl.GetValue().strip()
		pref_langs = self.prefLangsCtrl.GetValue().strip() or "Arabic,English"
		repeat_on = self.repeatCheck.GetValue()
		shuffle_on = self.shuffleCheck.GetValue()
		config.conf["nvSoftPlayer"]["aiProvider"] = provider
		config.conf["nvSoftPlayer"]["groqApiKey"] = groq_key
		config.conf["nvSoftPlayer"]["geminiApiKey"] = gemini_key
		config.conf["nvSoftPlayer"]["ignoreWords"] = words
		config.conf["nvSoftPlayer"]["preferredLanguages"] = pref_langs
		config.conf["nvSoftPlayer"]["repeatOn"] = repeat_on
		config.conf["nvSoftPlayer"]["shuffleOn"] = shuffle_on
		save_addon_store(
			gemini_api_key=gemini_key,
			groq_api_key=groq_key,
			ai_provider=provider,
			ignore_words=words,
			repeat_on=repeat_on,
			shuffle_on=shuffle_on,
			preferred_languages=pref_langs,
		)
		try:
			config.conf.save()
		except Exception:
			pass


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		self._searchDialog = None
		self._lyricsDialog = None
		self._playerDialog = None
		self._youtubeDialog = None
		self._registerSettingsPanel()
		# Clean stale temporary files in the background whenever NVDA starts/restarts
		threading.Thread(
			target=cleanup_temp_files, daemon=True, name="NVSoftPlayer-AutoCleanup"
		).start()

	def terminate(self):
		self._unregisterSettingsPanel()
		for dlg in (
			self._searchDialog,
			self._lyricsDialog,
			self._playerDialog,
			self._youtubeDialog,
		):
			try:
				if dlg:
					dlg.Destroy()
			except Exception:
				pass
		# Also clean temporary files on shutdown/restart
		try:
			threading.Thread(
				target=cleanup_temp_files, daemon=True, name="NVSoftPlayer-ExitCleanup"
			).start()
		except Exception:
			pass
		super().terminate()

	def _registerSettingsPanel(self):
		try:
			classes = gui.settingsDialogs.NVDASettingsDialog.categoryClasses
			if SoftPlayerSettingsPanel not in classes:
				classes.append(SoftPlayerSettingsPanel)
		except Exception as e:
			handle_error(f"Could not register settings panel: {e}")

	def _unregisterSettingsPanel(self):
		try:
			classes = gui.settingsDialogs.NVDASettingsDialog.categoryClasses
			if SoftPlayerSettingsPanel in classes:
				classes.remove(SoftPlayerSettingsPanel)
		except Exception:
			pass

	def _open_player(self, paths, repeat_scope, titles=None, quiet_open=False):
		dialog = open_player(
			paths,
			repeat_scope=repeat_scope,
			titles=titles,
			quiet_open=quiet_open,
			existing_dialog=self._playerDialog,
		)
		if dialog:
			self._playerDialog = dialog

			def _clear(event=None):
				self._playerDialog = None

			dialog.Bind(wx.EVT_WINDOW_DESTROY, _clear)

	@scriptHandler.script(
		description="Open NV-SoftPlayer and play the focused audio file.",
		category="NV-SoftPlayer",
		gesture="kb:NVDA+control+1",
	)
	def script_playFocusedFile(self, gesture):
		path = get_focused_audio_file()
		if not path:
			handle_error("Select an audio file in File Explorer, then try again.")
			return
		ui.message(f"Opening NV-SoftPlayer for {display_name(path)}")
		self._open_player([path], repeat_scope="track")

	@scriptHandler.script(
		description="Play all selected audio files in NV-SoftPlayer.",
		category="NV-SoftPlayer",
		gesture="kb:NVDA+shift+control+1",
	)
	def script_playSelectedFiles(self, gesture):
		files = get_selected_audio_files()
		if not files:
			handle_error(
				"Select one or more audio files in a folder (for example with Control+A), "
				"then try again."
			)
			return
		ui.message(f"Playing {len(files)} selected files")
		self._open_player(files, repeat_scope="playlist")

	@scriptHandler.script(
		description="Play all audio files inside the focused folder.",
		category="NV-SoftPlayer",
		gesture="kb:NVDA+control+2",
	)
	def script_playFocusedFolder(self, gesture):
		folder = get_focused_folder()
		if not folder:
			handle_error(
				"Focus a folder in File Explorer without opening it, then try again."
			)
			return
		files = list_audio_in_folder(folder)
		if not files:
			handle_error(f"No audio files were found in {os.path.basename(folder)}.")
			return
		ui.message(f"Playing {len(files)} files from {os.path.basename(folder)}")
		self._open_player(files, repeat_scope="playlist")

	@scriptHandler.script(
		description="Play audio files from all selected folders.",
		category="NV-SoftPlayer",
		gesture="kb:NVDA+shift+control+2",
	)
	def script_playSelectedFolders(self, gesture):
		folders = get_selected_folders()
		if not folders:
			handle_error("Select one or more folders in File Explorer, then try again.")
			return
		files = collect_audio_from_folders(folders)
		if not files:
			handle_error("No audio files were found in the selected folders.")
			return
		ui.message(f"Playing {len(files)} files from {len(folders)} folders")
		self._open_player(files, repeat_scope="playlist")

	@scriptHandler.script(
		description="Fetch lyrics for the selected file in Explorer.",
		category="NV-SoftPlayer",
		gesture="kb:NVDA+control+3",
	)
	def script_fetchLyricsFromFile(self, gesture):
		focus_obj = api.getFocusObject()
		if not focus_obj:
			handle_error("No file is selected in File Explorer.")
			return
		file_name = getattr(focus_obj, "name", "")
		if not file_name:
			handle_error("No file name was found.")
			return
		song_name = os.path.splitext(file_name)[0]
		if not song_name.strip():
			handle_error("The selected file does not have a usable name.")
			return
		self._start_search(song_name)

	@scriptHandler.script(
		description="Manually search for song lyrics by typing a title.",
		category="NV-SoftPlayer",
		gesture="kb:NVDA+control+shift+3",
	)
	def script_manualSearch(self, gesture):
		wx.CallAfter(self._showManualSearchDialog)

	@scriptHandler.script(
		description="Search YouTube and play audio, video, or download MP3/MP4.",
		category="NV-SoftPlayer",
		gesture="kb:NVDA+control+4",
	)
	def script_youtubeSearch(self, gesture):
		ui.message("YouTube search")
		wx.CallAfter(self._showYouTubeDialog)

	@scriptHandler.script(
		description="Announce the duration of the focused audio file.",
		category="NV-SoftPlayer",
		gesture="kb:NVDA+control+l",
	)
	def script_announceFileLength(self, gesture):
		path = get_focused_audio_file()
		if not path and self._playerDialog and not getattr(self._playerDialog, "_closed", True):
			try:
				path = self._playerDialog._current_path()
			except Exception:
				path = None
		if not path:
			handle_error("Select an audio file in File Explorer, then try again.")
			return
		ui.message(f"Reading length of {display_name(path)}")

		def worker():
			duration = get_audio_duration_seconds(path)
			name = display_name(path)
			if duration <= 0:
				wx.CallAfter(ui.message, f"Could not read the length of {name}")
			else:
				wx.CallAfter(ui.message, f"{name}, {format_time(duration)}")

		threading.Thread(target=worker, daemon=True).start()

	def _start_search(self, query):
		ui.message(f"Searching lyrics for {query}")
		threading.Thread(target=self.search_worker, args=(query,), daemon=True).start()

	def search_worker(self, song_name):
		result, error = fetch_lyrics_online(song_name)
		wx.CallAfter(self.show_result, result, error)

	def show_result(self, result, error):
		if error:
			try:
				if self._searchDialog:
					self._searchDialog.reset_search()
			except Exception:
				pass
			handle_error(error)
			return
		if not result:
			try:
				if self._searchDialog:
					self._searchDialog.reset_search()
			except Exception:
				pass
			handle_error("No lyrics were found.")
			return
		ui.message(f"Lyrics found for {result.get('title', 'the selected song')}")
		try:
			if self._searchDialog:
				self._searchDialog.close_quietly()
		except Exception:
			pass
		try:
			if self._lyricsDialog:
				self._lyricsDialog.Destroy()
		except Exception:
			pass
		gui.mainFrame.prePopup()
		dialog = LyricsDialog(gui.mainFrame, result)
		self._lyricsDialog = dialog

		def _clear(event=None):
			self._lyricsDialog = None

		dialog.Bind(wx.EVT_WINDOW_DESTROY, _clear)
		dialog.Show()
		dialog.Raise()
		dialog.lyrics_ctrl.SetFocus()

	def _showManualSearchDialog(self):
		try:
			if self._searchDialog:
				self._searchDialog.Raise()
				self._searchDialog.query_ctrl.SetFocus()
				return
		except Exception:
			self._searchDialog = None
		gui.mainFrame.prePopup()
		dlg = ManualSearchDialog(gui.mainFrame, self._start_search)
		self._searchDialog = dlg

		def _clear(event=None):
			self._searchDialog = None

		dlg.Bind(wx.EVT_WINDOW_DESTROY, _clear)
		dlg.Show()
		dlg.Raise()
		dlg.query_ctrl.SetFocus()

	def _showYouTubeDialog(self):
		if not _find_ytdlp():
			handle_error(
				"yt-dlp was not found. Place the Windows x64 yt-dlp.exe "
				"(not arm64) in globalPlugins/NV-SoftPlayer/bin/ then restart NVDA. "
				"Download: https://github.com/yt-dlp/yt-dlp/releases/latest"
			)
			return
		try:
			if self._youtubeDialog:
				self._youtubeDialog.Raise()
				self._youtubeDialog.query_ctrl.SetFocus()
				return
		except Exception:
			self._youtubeDialog = None
		dlg = show_youtube_dialog(gui.mainFrame, self)
		if dlg:
			self._youtubeDialog = dlg

			def _clear(event=None):
				self._youtubeDialog = None

			dlg.Bind(wx.EVT_WINDOW_DESTROY, _clear)