# -*- coding: UTF-8 -*-
import os
import re
import json
import time
import shutil
import subprocess
import config
import api
import ui

try:
	import addonHandler
except ImportError:
	addonHandler = None

try:
	import globalVars
except ImportError:
	globalVars = None

try:
	import comtypes.client
	HAS_COMTYPES = True
except ImportError:
	HAS_COMTYPES = False

try:
	import winUser
	HAS_WINUSER = True
except ImportError:
	HAS_WINUSER = False

try:
	import languageHandler
except ImportError:
	languageHandler = None

try:
	import speech
	HAS_SPEECH = True
except ImportError:
	HAS_SPEECH = False
	speech = None

try:
	import tones
	HAS_TONES = True
except ImportError:
	HAS_TONES = False
	tones = None

import wx

ADDON_NAME = "NV-SoftPlayer"
USER_AGENT = "NV-SoftPlayer/2.5"

RTL_LANG_CODES = frozenset(("ar", "he", "fa", "ur", "ps", "ckb", "yi", "ku", "sd", "ug", "dv"))

NVDA_LANG_TO_NAME = {
	"ar": "Arabic", "en": "English", "fr": "French", "es": "Spanish",
	"de": "German", "it": "Italian", "tr": "Turkish", "ru": "Russian",
	"pt": "Portuguese", "pl": "Polish", "nl": "Dutch", "cs": "Czech",
	"da": "Danish", "fi": "Finnish", "el": "Greek", "he": "Hebrew",
	"hi": "Hindi", "hu": "Hungarian", "id": "Indonesian", "ja": "Japanese",
	"ko": "Korean", "nb": "Norwegian", "nn": "Norwegian", "fa": "Persian",
	"ro": "Romanian", "sv": "Swedish", "th": "Thai", "uk": "Ukrainian",
	"ur": "Urdu", "vi": "Vietnamese", "zh": "Chinese (Simplified)",
	"zh_CN": "Chinese (Simplified)", "zh_TW": "Chinese (Traditional)",
}

_UI = {
	"ar": {
		"Ready": "جاهز",
		"Playlist": "قائمة التشغيل",
		"Playing": "تشغيل",
		"Paused": "إيقاف مؤقت",
		"Stopped": "متوقف",
		"Search": "بحث",
		"Cancel": "إلغاء",
		"Close": "إغلاق",
		"Copy": "نسخ",
		"Back": "رجوع",
		"OK": "موافق",
		"Ask": "اسأل",
		"Play audio": "تشغيل الصوت",
		"Play video": "تشغيل الفيديو",
		"Play as queue": "تشغيل كقائمة",
		"Download MP3": "تنزيل MP3",
		"Download MP4": "تنزيل MP4",
		"Translate Lyrics": "ترجمة الكلمات",
		"Profound Translation": "ترجمة عميقة",
		"Artist details": "تفاصيل الفنان",
		"Latest Artist News": "آخر أخبار الفنان",
		"Copy Text": "نسخ النص",
		"Translate": "ترجمة",
		"YouTube — NV-SoftPlayer": "يوتيوب — NV-SoftPlayer",
		"Search YouTube, or paste a video / playlist URL:": "ابحث في يوتيوب، أو الصق رابط فيديو أو قائمة تشغيل:",
		"Type a search and press Enter. This window stays open.": "اكتب بحثاً ثم اضغط إدخال. تبقى هذه النافذة مفتوحة.",
		"Search Lyrics": "بحث عن الكلمات",
		"Enter song name or artist:": "أدخل اسم الأغنية أو الفنان:",
		"Choose target language:": "اختر لغة الهدف:",
		"Copied to clipboard.": "تم النسخ إلى الحافظة.",
		"Select a result first.": "حدد نتيجة أولاً.",
		"Already working.": "العمل جارٍ بالفعل.",
		"Playing. Search window stays open.": "جارٍ التشغيل. نافذة البحث تبقى مفتوحة.",
		"Video opened in Windows Media Player": "تم فتح الفيديو في Windows Media Player",
		"No audio files to play.": "لا توجد ملفات صوت للتشغيل.",
		"Ask about this song / artist / lyrics (music topics only):": "اسأل عن هذه الأغنية / الفنان / الكلمات (مواضيع موسيقية فقط):",
		"Preferred translation languages (comma-separated, first is default):": "لغات الترجمة المفضلة (مفصولة بفاصلة، الأولى هي الافتراضية):",
		"Repeat on by default": "التكرار مفعّل افتراضياً",
		"Shuffle on by default": "التبديل العشوائي مفعّل افتراضياً",
		"AI provider for translation, song info, and artist details:": "مزود الذكاء الاصطناعي للترجمة ومعلومات الأغنية وتفاصيل الفنان:",
		"Groq API Key (recommended, free):": "مفتاح Groq (موصى به، مجاني):",
		"Gemini API Key (optional backup):": "مفتاح Gemini (احتياطي اختياري):",
		"Words to ignore during search (space or comma separated):": "كلمات تُتجاهل أثناء البحث (مفصولة بمسافة أو فاصلة):",
		"Play / Pause": "تشغيل / إيقاف مؤقت",
		"Replay from start": "إعادة من البداية",
		"Stop": "إيقاف",
		"Previous track": "المقطع السابق",
		"Next track": "المقطع التالي",
		"Toggle repeat": "تبديل التكرار",
		"Toggle shuffle": "تبديل العشوائي",
		"Announce duration": "الإعلان عن المدة",
		"Keyboard shortcuts": "اختصارات لوحة المفاتيح",
		"This is the first track.": "هذا هو المقطع الأول.",
		"This is the last track.": "هذا هو المقطع الأخير.",
		"Playback finished.": "انتهى التشغيل.",
		"Empty search query.": "استعلام البحث فارغ.",
		"No YouTube results found.": "لا توجد نتائج على يوتيوب.",
		"Select a word or phrase in the lyrics first.": "حدد كلمة أو عبارة في الكلمات أولاً.",
		"Type a music-related question first.": "اكتب سؤالاً متعلقاً بالموسيقى أولاً.",
		"What do you want to do?": "ماذا تريد أن تفعل؟",
		"Play as audio": "تشغيل كصوت",
		"Play as video": "تشغيل كفيديو",
		"Download as MP3": "تنزيل كـ MP3",
		"Download as MP4": "تنزيل كـ MP4",
	},
	"he": {
		"Ready": "מוכן",
		"Playlist": "רשימת השמעה",
		"Playing": "מנגן",
		"Paused": "מושהה",
		"Stopped": "עצור",
		"Search": "חיפוש",
		"Cancel": "ביטול",
		"Close": "סגור",
		"Copy": "העתק",
		"Back": "חזרה",
		"Play audio": "נגן שמע",
		"Play video": "נגן וידאו",
		"Download MP3": "הורד MP3",
		"Download MP4": "הורד MP4",
	},
	"fa": {
		"Ready": "آماده",
		"Playlist": "فهرست پخش",
		"Playing": "در حال پخش",
		"Paused": "مکث",
		"Stopped": "متوقف",
		"Search": "جستجو",
		"Cancel": "لغو",
		"Close": "بستن",
		"Play audio": "پخش صدا",
		"Play video": "پخش ویدیو",
	},
	"ur": {
		"Ready": "تیار",
		"Playlist": "پلے لسٹ",
		"Playing": "چل رہا ہے",
		"Search": "تلاش",
		"Close": "بند کریں",
		"Play audio": "آڈیو چلائیں",
		"Play video": "ویڈیو چلائیں",
	},
	"fr": {
		"Ready": "Prêt",
		"Playlist": "Liste de lecture",
		"Playing": "Lecture",
		"Paused": "Pause",
		"Stopped": "Arrêté",
		"Search": "Rechercher",
		"Cancel": "Annuler",
		"Close": "Fermer",
		"Copy": "Copier",
		"Back": "Retour",
		"Play audio": "Lire l'audio",
		"Play video": "Lire la vidéo",
		"Play as queue": "Lire en file",
		"Download MP3": "Télécharger MP3",
		"Download MP4": "Télécharger MP4",
		"Translate Lyrics": "Traduire les paroles",
		"Artist details": "Détails de l'artiste",
		"Latest Artist News": "Dernières actualités de l'artiste",
	},
	"es": {
		"Ready": "Listo",
		"Playlist": "Lista de reproducción",
		"Playing": "Reproduciendo",
		"Paused": "Pausa",
		"Stopped": "Detenido",
		"Search": "Buscar",
		"Cancel": "Cancelar",
		"Close": "Cerrar",
		"Play audio": "Reproducir audio",
		"Play video": "Reproducir vídeo",
		"Download MP3": "Descargar MP3",
		"Download MP4": "Descargar MP4",
	},
	"de": {
		"Ready": "Bereit",
		"Playlist": "Wiedergabeliste",
		"Playing": "Wiedergabe",
		"Paused": "Pause",
		"Stopped": "Gestoppt",
		"Search": "Suchen",
		"Cancel": "Abbrechen",
		"Close": "Schließen",
		"Play audio": "Audio abspielen",
		"Play video": "Video abspielen",
	},
	"tr": {
		"Ready": "Hazır",
		"Playlist": "Çalma listesi",
		"Playing": "Çalıyor",
		"Paused": "Duraklatıldı",
		"Stopped": "Durduruldu",
		"Search": "Ara",
		"Close": "Kapat",
		"Play audio": "Sesi oynat",
		"Play video": "Videoyu oynat",
	},
	"ru": {
		"Ready": "Готово",
		"Playlist": "Список воспроизведения",
		"Playing": "Воспроизведение",
		"Paused": "Пауза",
		"Stopped": "Остановлено",
		"Search": "Поиск",
		"Close": "Закрыть",
		"Play audio": "Играть аудио",
		"Play video": "Играть видео",
	},
	"pt": {
		"Ready": "Pronto",
		"Playlist": "Lista de reprodução",
		"Playing": "Reproduzindo",
		"Search": "Pesquisar",
		"Close": "Fechar",
		"Play audio": "Reproduzir áudio",
		"Play video": "Reproduzir vídeo",
	},
	"it": {
		"Ready": "Pronto",
		"Playlist": "Playlist",
		"Playing": "In riproduzione",
		"Search": "Cerca",
		"Close": "Chiudi",
		"Play audio": "Riproduci audio",
		"Play video": "Riproduci video",
	},
}


def _nvda_lang_code():
	try:
		if languageHandler is not None:
			raw = languageHandler.getLanguage() or "en"
			return str(raw).replace("-", "_")
	except Exception:
		pass
	return "en"


def _nvda_lang_base():
	return _nvda_lang_code().split("_")[0].lower()


def _is_rtl():
	return _nvda_lang_base() in RTL_LANG_CODES


def _(text):
	if not text:
		return text
	code = _nvda_lang_code()
	base = _nvda_lang_base()
	table = _UI.get(code) or _UI.get(base) or {}
	return table.get(text, text)


def apply_ui_layout(window):
	try:
		if _is_rtl():
			window.SetLayoutDirection(wx.Layout_RightToLeft)
		else:
			window.SetLayoutDirection(wx.Layout_LeftToRight)
	except Exception:
		pass


def nvda_default_target_language():
	code = _nvda_lang_code()
	if code in NVDA_LANG_TO_NAME:
		return NVDA_LANG_TO_NAME[code]
	base = _nvda_lang_base()
	return NVDA_LANG_TO_NAME.get(base, "English")


def _cancel_speech():
	if HAS_SPEECH and speech is not None:
		try:
			speech.cancelSpeech()
		except Exception:
			pass


def _beep_progress(pct=None):
	if not HAS_TONES or tones is None:
		return
	try:
		if pct is None:
			tones.beep(500, 40)
		else:
			freq = 400 + int(max(0, min(100, pct)) * 5)
			tones.beep(freq, 35)
	except Exception:
		pass


DEFAULT_IGNORE_WORDS = (
	"remastered live official video audio lyrics "
	"feat ft remix version deluxe explicit "
	"hd hq 4k lyric visualizer"
)

AI_MAX_RETRIES = 3
AI_RETRY_STATUS_CODES = {429, 503}
GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODELS = [
	"qwen/qwen3-32b",
	"llama-3.3-70b-versatile",
	"openai/gpt-oss-120b",
]
PROVIDER_LABELS = [
	"Groq (recommended, free)",
	"Gemini",
]
PROVIDER_VALUES = ["groq", "gemini"]

TRANSLATION_LANGUAGES = [
	"Arabic", "Chinese (Simplified)", "Chinese (Traditional)", "Czech",
	"Danish", "Dutch", "English", "Finnish", "French", "German", "Greek",
	"Hebrew", "Hindi", "Hungarian", "Indonesian", "Italian", "Japanese",
	"Korean", "Norwegian", "Persian", "Polish", "Portuguese", "Romanian",
	"Russian", "Spanish", "Swedish", "Thai", "Turkish", "Ukrainian",
	"Urdu", "Vietnamese",
]

AUDIO_EXTENSIONS = {
	".mp3", ".wav", ".flac", ".m4a", ".aac", ".wma",
	".ogg", ".opus", ".mp4", ".m4b", ".aiff", ".aif",
	".ape", ".wv", ".mpc", ".ac3",
}

SEEK_SECONDS = 5
VOLUME_STEP = 5
SOFT_DUCK_RATIO = 0.22
SOFT_RESTORE_DELAY_MS = 220
SOFT_RESTORE_STEP_MS = 40

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _creation_flags():
	return CREATE_NO_WINDOW


def _config_dir():
	try:
		if globalVars and getattr(globalVars, "appArgs", None):
			path = getattr(globalVars.appArgs, "configPath", None)
			if path:
				return path
	except Exception:
		pass
	return os.path.expanduser("~")


def _store_file():
	return os.path.join(_config_dir(), "nvSoftPlayer.json")


def _legacy_store_file():
	return os.path.join(_config_dir(), "nvdaLyricsFetcher.json")


def load_addon_store():
	data = {
		"geminiApiKey": "",
		"groqApiKey": "",
		"aiProvider": "groq",
		"ignoreWords": "",
		"preferredLanguages": "",
		"repeatOn": False,
		"shuffleOn": False,
	}
	for path in (_store_file(), _legacy_store_file()):
		try:
			if os.path.isfile(path):
				with open(path, "r", encoding="utf-8") as f:
					loaded = json.load(f)
				if isinstance(loaded, dict):
					data.update(loaded)
				break
		except Exception:
			pass
	return data


def save_addon_store(
	gemini_api_key=None,
	groq_api_key=None,
	ai_provider=None,
	ignore_words=None,
	repeat_on=None,
	shuffle_on=None,
	preferred_languages=None,
):
	data = load_addon_store()
	if gemini_api_key is not None:
		data["geminiApiKey"] = gemini_api_key or ""
	if groq_api_key is not None:
		data["groqApiKey"] = groq_api_key or ""
	if ai_provider is not None:
		data["aiProvider"] = ai_provider or "groq"
	if ignore_words is not None:
		data["ignoreWords"] = ignore_words
	if repeat_on is not None:
		data["repeatOn"] = bool(repeat_on)
	if shuffle_on is not None:
		data["shuffleOn"] = bool(shuffle_on)
	if preferred_languages is not None:
		data["preferredLanguages"] = preferred_languages
	try:
		with open(_store_file(), "w", encoding="utf-8") as f:
			json.dump(data, f, ensure_ascii=False, indent=2)
	except Exception as e:
		handle_error(f"Could not save add-on settings to disk: {e}")


def _conf_get(key, default=""):
	try:
		value = config.conf["nvSoftPlayer"][key]
		if value is not None and value != "":
			return value if not isinstance(value, str) else str(value).strip()
	except Exception:
		pass
	try:
		value = config.conf["nvdaLyricsFetcher"][key]
		if value is not None and value != "":
			return value if not isinstance(value, str) else str(value).strip()
	except Exception:
		pass
	return default


def get_ignore_words():
	try:
		value = _conf_get("ignoreWords")
		if not value:
			value = load_addon_store().get("ignoreWords") or DEFAULT_IGNORE_WORDS
		words = re.split(r"[,\s]+", str(value))
		return [w.lower().strip() for w in words if w.strip()]
	except Exception:
		words = re.split(r"[,\s]+", DEFAULT_IGNORE_WORDS)
		return [w.lower().strip() for w in words if w.strip()]


def get_gemini_api_key():
	store = load_addon_store()
	key = str(store.get("geminiApiKey") or "").strip()
	if key:
		return key
	return str(_conf_get("geminiApiKey") or "").strip()


def get_groq_api_key():
	store = load_addon_store()
	key = str(store.get("groqApiKey") or "").strip()
	if key:
		return key
	return str(_conf_get("groqApiKey") or "").strip()


def get_ai_provider():
	store = load_addon_store()
	value = str(store.get("aiProvider") or "").strip().lower()
	if value in ("groq", "gemini"):
		return value
	value = str(_conf_get("aiProvider", "groq") or "groq").lower()
	if value in ("groq", "gemini"):
		return value
	return "groq"


def get_repeat_on():
	store = load_addon_store()
	if "repeatOn" in store:
		return bool(store.get("repeatOn"))
	try:
		return bool(config.conf["nvSoftPlayer"]["repeatOn"])
	except Exception:
		return False


def get_shuffle_on():
	store = load_addon_store()
	if "shuffleOn" in store:
		return bool(store.get("shuffleOn"))
	try:
		return bool(config.conf["nvSoftPlayer"]["shuffleOn"])
	except Exception:
		return False


def get_preferred_languages():
	store = load_addon_store()
	raw = str(store.get("preferredLanguages") or "").strip()
	if not raw:
		raw = str(_conf_get("preferredLanguages", "Arabic,English") or "Arabic,English")
	langs = []
	seen = set()
	for part in re.split(r"[,;]+", raw):
		name = part.strip()
		if not name:
			continue
		key = name.lower()
		if key in seen:
			continue
		seen.add(key)
		matched = None
		for known in TRANSLATION_LANGUAGES:
			if known.lower() == key:
				matched = known
				break
		langs.append(matched or name)
	if not langs:
		langs = [nvda_default_target_language(), "English"]
		langs = list(dict.fromkeys(langs))
	return langs


def get_active_api_key():
	provider = get_ai_provider()
	if provider == "groq":
		key = get_groq_api_key()
		if key:
			return "groq", key
		gemini_key = get_gemini_api_key()
		if gemini_key:
			return "gemini", gemini_key
		return "groq", ""
	key = get_gemini_api_key()
	if key:
		return "gemini", key
	groq_key = get_groq_api_key()
	if groq_key:
		return "groq", groq_key
	return "gemini", ""


def handle_error(error_msg):
	formatted_msg = f"NV-SoftPlayer Error: {error_msg}"
	ui.message(formatted_msg)
	try:
		api.copyToClip(formatted_msg)
	except Exception:
		pass


class FocusPanel(wx.Panel):
	def AcceptsFocus(self):
		return True

	def AcceptsFocusFromKeyboard(self):
		return True


def _plugin_dir():
	return os.path.dirname(os.path.abspath(__file__))


def _addon_bin_dirs():
	dirs = []
	try:
		if addonHandler is not None:
			addon = addonHandler.getCodeAddon()
			dirs.append(os.path.join(addon.path, "globalPlugins", "NV-SoftPlayer", "bin"))
			dirs.append(os.path.join(addon.path, "globalPlugins", "nvSoftPlayer", "bin"))
			dirs.append(os.path.join(addon.path, "bin"))
	except Exception:
		pass
	here = _plugin_dir()
	dirs.append(os.path.join(here, "bin"))
	dirs.append(here)
	return dirs


def _find_powershell():
	root = os.environ.get("SystemRoot", r"C:\Windows")
	for path in (
		os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
		os.path.join(root, "Sysnative", "WindowsPowerShell", "v1.0", "powershell.exe"),
		os.path.join(root, "SysWOW64", "WindowsPowerShell", "v1.0", "powershell.exe"),
	):
		if os.path.isfile(path):
			return path
	return shutil.which("powershell.exe") or shutil.which("powershell")


def _find_ffmpeg():
	for folder in _addon_bin_dirs():
		for name in ("ffmpeg.exe", "affmpeg.exe", "ffmpeg"):
			path = os.path.join(folder, name)
			if os.path.isfile(path):
				return path
	return shutil.which("ffmpeg.exe") or shutil.which("ffmpeg")


def _find_ytdlp():
	exe_names = ("yt-dlp.exe", "yt-dlp")
	candidates = []
	for folder in _addon_bin_dirs():
		for name in exe_names:
			candidates.append(os.path.join(folder, name))
	for path in candidates:
		if path and os.path.isfile(path):
			return [path]
	for name in exe_names:
		found = shutil.which(name)
		if found:
			return [found]
	for py in ("py", "python"):
		found = shutil.which(py)
		if found:
			return [found, "-m", "yt_dlp"]
	return None


def _find_wmplayer():
	for base in (
		os.environ.get("ProgramFiles", r"C:\Program Files"),
		os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
	):
		path = os.path.join(base, "Windows Media Player", "wmplayer.exe")
		if os.path.isfile(path):
			return path
	return shutil.which("wmplayer.exe") or shutil.which("wmplayer")


def cleanup_temp_files():
	"""Silently clean up stale temporary media, partial downloads, and cache files created by NV-SoftPlayer."""
	try:
		temp_dir = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "nvSoftPlayer")
		if os.path.isdir(temp_dir):
			for entry in os.listdir(temp_dir):
				# Strictly preserve the bin folder containing executables and libraries
				if entry.lower() == "bin":
					continue
				full_path = os.path.join(temp_dir, entry)
				try:
					if os.path.isfile(full_path):
						os.remove(full_path)
					elif os.path.isdir(full_path):
						shutil.rmtree(full_path, ignore_errors=True)
				except Exception:
					pass
		# Also clean temporary player host script if present in TEMP
		host_tmp = os.path.join(
			os.environ.get("TEMP", os.path.expanduser("~")),
			"nvSoftPlayer_player_host.ps1",
		)
		if os.path.isfile(host_tmp):
			try:
				os.remove(host_tmp)
			except Exception:
				pass
	except Exception:
		pass


def get_download_folder():
	"""Return the NV-SoftPlayer folder inside the user's Music directory, creating it once if needed."""
	music_dir = os.path.join(os.path.expanduser("~"), "Music")
	if not os.path.isdir(music_dir):
		music_dir = os.path.join(os.path.expanduser("~"), "Downloads")
		if not os.path.isdir(music_dir):
			music_dir = os.path.expanduser("~")
	target = os.path.join(music_dir, "NV-SoftPlayer")
	try:
		if not os.path.exists(target):
			os.makedirs(target, exist_ok=True)
	except Exception as e:
		handle_error(f"Could not create NV-SoftPlayer folder in Music: {e}")
		return music_dir
	return target


def is_audio_file(path):
	if not path:
		return False
	ext = os.path.splitext(str(path))[1].lower()
	return ext in AUDIO_EXTENSIONS


def format_time(seconds):
	seconds = max(0, float(seconds or 0))
	m = int(seconds // 60)
	s = int(seconds % 60)
	return f"{m:02d}:{s:02d}"


def display_name(path):
	return os.path.splitext(os.path.basename(path))[0]


def list_audio_in_folder(folder):
	files = []
	try:
		for name in os.listdir(folder):
			path = os.path.join(folder, name)
			if os.path.isfile(path) and is_audio_file(path):
				files.append(os.path.normpath(path))
	except Exception:
		pass
	files.sort(key=lambda p: os.path.basename(p).lower())
	return files


def _focus_path_candidates():
	paths = []
	focus = api.getFocusObject()
	if not focus:
		return paths
	for attr in ("path", "value"):
		try:
			val = getattr(focus, attr, None)
			if val:
				paths.append(str(val))
		except Exception:
			pass
	try:
		parent = getattr(focus, "parent", None)
		if parent is not None:
			val = getattr(parent, "path", None)
			if val:
				paths.append(str(val))
	except Exception:
		pass
	try:
		name = getattr(focus, "name", None)
		if name:
			name_str = str(name).strip()
			desktop_dirs = [
				os.path.join(os.path.expanduser("~"), "Desktop"),
				os.path.join(os.environ.get("PUBLIC", "C:\\Users\\Public"), "Desktop"),
				os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
			]
			for ddir in desktop_dirs:
				if not os.path.isdir(ddir):
					continue
				cand = os.path.join(ddir, name_str)
				if os.path.isfile(cand):
					paths.append(cand)
				else:
					for ext in AUDIO_EXTENSIONS:
						cext = cand + ext
						if os.path.isfile(cext):
							paths.append(cext)
							break
	except Exception:
		pass
	return paths


def _shell_selected_paths():
	results = []
	if not HAS_COMTYPES:
		return results
	try:
		fg = winUser.getForegroundWindow() if HAS_WINUSER else None
		root_fg = fg
		if HAS_WINUSER and fg:
			try:
				root_fg = winUser.user32.GetAncestor(fg, 2)
			except Exception:
				root_fg = fg
		shell = comtypes.client.CreateObject("Shell.Application")
		fg_paths = []
		other_paths = []
		for window in shell.Windows():
			try:
				doc = window.Document
				if doc is None:
					continue
				selected = doc.SelectedItems()
				focused_item = getattr(doc, "FocusedItem", None)
				has_selected = (selected is not None and getattr(selected, "Count", 0) > 0)
				if not has_selected and focused_item is None:
					continue
				hwnd = None
				for attr in ("HWND", "hwnd", "HWnd"):
					try:
						hwnd = int(getattr(window, attr))
						break
					except Exception:
						continue
				is_fg = (hwnd is not None and (hwnd == fg or hwnd == root_fg))
				bucket = fg_paths if is_fg else other_paths
				if has_selected:
					for i in range(int(selected.Count)):
						try:
							item = selected.Item(i)
							path = item.Path
							if path:
								bucket.append(str(path))
						except Exception:
							continue
				if focused_item is not None:
					try:
						path = getattr(focused_item, "Path", None)
						if path and str(path) not in bucket:
							bucket.append(str(path))
					except Exception:
						pass
			except Exception:
				continue
		try:
			wins = shell.Windows()
			desk = wins.FindWindowSW(0, None, 8, 0, 1)
			if desk and getattr(desk, "Document", None):
				doc = desk.Document
				focused_item = getattr(doc, "FocusedItem", None)
				selected = getattr(doc, "SelectedItems", None)
				desk_hwnd = getattr(desk, "HWND", None)
				is_desk_fg = (desk_hwnd is not None and (desk_hwnd == fg or desk_hwnd == root_fg))
				bucket = fg_paths if is_desk_fg else other_paths
				if selected is not None and getattr(selected, "Count", 0) > 0:
					for i in range(int(selected.Count)):
						try:
							item = selected.Item(i)
							path = getattr(item, "Path", None)
							if path:
								bucket.append(str(path))
						except Exception:
							continue
				if focused_item is not None:
					try:
						path = getattr(focused_item, "Path", None)
						if path and str(path) not in bucket:
							bucket.append(str(path))
					except Exception:
						pass
		except Exception:
			pass
		results = fg_paths if fg_paths else other_paths
	except Exception:
		pass
	return results


def get_selected_paths():
	seen = set()
	ordered = []
	for path in _focus_path_candidates() + _shell_selected_paths():
		if not path:
			continue
		norm = os.path.normpath(path)
		if norm in seen:
			continue
		if os.path.isfile(norm) or os.path.isdir(norm):
			seen.add(norm)
			ordered.append(norm)
	return ordered


def get_focused_audio_file():
	for path in get_selected_paths():
		if os.path.isfile(path) and is_audio_file(path):
			return path
	return None


def get_selected_audio_files():
	files = [
		path for path in get_selected_paths()
		if os.path.isfile(path) and is_audio_file(path)
	]
	files.sort(key=lambda p: os.path.basename(p).lower())
	return files


def get_focused_folder():
	for path in get_selected_paths():
		if os.path.isdir(path):
			return path
	return None


def get_selected_folders():
	folders = [path for path in get_selected_paths() if os.path.isdir(path)]
	folders.sort(key=lambda p: os.path.basename(p).lower())
	return folders


def collect_audio_from_folders(folders):
	files = []
	seen = set()
	for folder in folders:
		for path in list_audio_in_folder(folder):
			norm = os.path.normpath(path)
			if norm in seen:
				continue
			seen.add(norm)
			files.append(norm)
	files.sort(key=lambda p: os.path.basename(p).lower())
	return files


def _duration_via_ffmpeg(path):
	ffmpeg = _find_ffmpeg()
	if not ffmpeg or not os.path.isfile(path):
		return 0.0
	try:
		proc = subprocess.run(
			[ffmpeg, "-i", path],
			capture_output=True,
			text=True,
			timeout=6,
			creationflags=_creation_flags(),
			encoding="utf-8",
			errors="replace",
		)
		err = proc.stderr or ""
		m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
		if m:
			hours = int(m.group(1))
			minutes = int(m.group(2))
			seconds = float(m.group(3))
			return hours * 3600 + minutes * 60 + seconds
	except Exception:
		pass
	return 0.0


def _duration_via_shell(path):
	if not HAS_COMTYPES or not os.path.isfile(path):
		return 0.0
	try:
		import comtypes
		comtypes.CoInitialize()
		shell = comtypes.client.CreateObject("Shell.Application")
		folder_path, file_name = os.path.split(os.path.abspath(path))
		folder = shell.NameSpace(folder_path)
		if folder:
			item = folder.ParseName(file_name)
			if item:
				for idx in (27, 28, 29, 30, 31):
					val = folder.GetDetailsOf(item, idx)
					if val and ":" in str(val):
						cleaned = re.sub(r"[^\d:]", "", str(val)).strip()
						parts = cleaned.split(":")
						if len(parts) == 3:
							h, m, s = parts
							return int(h) * 3600 + int(m) * 60 + float(s)
						elif len(parts) == 2:
							m, s = parts
							return int(m) * 60 + float(s)
	except Exception:
		pass
	return 0.0


def get_audio_duration_seconds(path):
	if not path or not os.path.isfile(path):
		return 0.0
	dur = _duration_via_ffmpeg(path)
	if dur > 0:
		return dur
	dur = _duration_via_shell(path)
	if dur > 0:
		return dur
	if HAS_COMTYPES:
		try:
			import comtypes
			comtypes.CoInitialize()
			wmp = comtypes.client.CreateObject("WMPlayer.OCX")
			try:
				media = wmp.newMedia(path)
				dur = float(media.duration or 0)
				if dur > 0:
					return dur
			except Exception:
				pass
			wmp.settings.autoStart = False
			wmp.URL = path
			for _ in range(15):
				time.sleep(0.06)
				dur = float(wmp.currentMedia.duration or 0)
				if dur > 0:
					return dur
			wmp.close()
		except Exception:
			pass
	return 0.0
