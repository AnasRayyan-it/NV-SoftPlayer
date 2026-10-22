# -*- coding: UTF-8 -*-
import os
import re
import json
import time
import threading
import urllib.parse
import urllib.request
import urllib.error
import html
import wx
import api
import ui
import gui

from .common import (
	_,
	apply_ui_layout,
	handle_error,
	USER_AGENT,
	GEMINI_MODEL,
	GROQ_MODELS,
	AI_MAX_RETRIES,
	AI_RETRY_STATUS_CODES,
	TRANSLATION_LANGUAGES,
	get_ignore_words,
	get_active_api_key,
	get_preferred_languages,
	nvda_default_target_language,
)

ARABIC_LETTERS_RE = re.compile(r"[\u0600-\u06FF]")
ARABIC_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670\u0640]")
ARABIC_TRANSLATE = str.maketrans({
	"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
	"ء": "", "ؤ": "و", "ئ": "ي", "ة": "ه", "ى": "ي",
})


def normalize_arabic(text):
	if not text:
		return ""
	text = ARABIC_DIACRITICS_RE.sub("", str(text))
	text = text.translate(ARABIC_TRANSLATE)
	return text


def clean_query(text):
	if text is None:
		return ""
	text = str(text)
	emoji_pattern = re.compile(
		r"[\U0001F600-\U0001F64F"
		r"\U0001F300-\U0001F5FF"
		r"\U0001F680-\U0001F6FF"
		r"\U0001F1E0-\U0001F1FF"
		r"\U00002702-\U000027B0"
		r"\U000024C2-\U0001F251]",
		flags=re.UNICODE,
	)
	text = emoji_pattern.sub(" ", text)
	if ARABIC_LETTERS_RE.search(text):
		text = normalize_arabic(text)
	ignore_words = get_ignore_words()
	if ignore_words:
		pattern = r"\b(" + "|".join(re.escape(w) for w in ignore_words) + r")\b"
		text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
	return re.sub(r"\s+", " ", text).strip()


def _http_json(url, data=None, headers=None, timeout=45):
	request_headers = {"User-Agent": USER_AGENT}
	if headers:
		request_headers.update(headers)
	request = urllib.request.Request(
		url,
		data=data,
		headers=request_headers,
		method="POST" if data is not None else "GET",
	)
	with urllib.request.urlopen(request, timeout=timeout) as response:
		return response.read().decode("utf-8")


def _retry_wait(attempt, extra_seconds=0):
	wait_seconds = max(int(extra_seconds), 2 ** attempt)
	wx.CallAfter(
		ui.message,
		f"The AI service is busy. Retrying in {wait_seconds} seconds "
		f"(attempt {attempt} of {AI_MAX_RETRIES})."
	)
	time.sleep(wait_seconds)


def call_gemini_api(prompt, api_key):
	url = (
		"https://generativelanguage.googleapis.com/"
		f"v1beta/models/{GEMINI_MODEL}:generateContent"
		f"?key={urllib.parse.quote(api_key, safe='')}"
	)
	payload = json.dumps(
		{"contents": [{"parts": [{"text": prompt}]}]}
	).encode("utf-8")
	last_error = None
	for attempt in range(1, AI_MAX_RETRIES + 1):
		try:
			response_text = _http_json(
				url,
				data=payload,
				headers={"Content-Type": "application/json"},
				timeout=45,
			)
			result = json.loads(response_text)
			candidates = result.get("candidates", [])
			if not candidates:
				return None, "Gemini returned no candidates."
			parts = candidates[0].get("content", {}).get("parts", [])
			if not parts:
				return None, "Gemini returned no text."
			generated_text = parts[0].get("text", "")
			if not generated_text:
				return None, "Gemini returned empty text."
			return generated_text, None
		except urllib.error.HTTPError as e:
			error_message = ""
			retry_after = 0
			try:
				retry_after = int(float(e.headers.get("Retry-After") or 0))
			except Exception:
				retry_after = 0
			try:
				error_body = e.read().decode("utf-8")
				error_data = json.loads(error_body)
				error_message = error_data.get("error", {}).get("message", "")
			except Exception:
				pass
			last_error = (
				f"Gemini HTTP Error {e.code}: {error_message}"
				if error_message
				else f"Gemini HTTP Error {e.code}."
			)
			if e.code in AI_RETRY_STATUS_CODES and attempt < AI_MAX_RETRIES:
				_retry_wait(attempt, retry_after)
				continue
			return None, last_error
		except urllib.error.URLError as e:
			last_error = f"Network error while connecting to Gemini: {str(e)}"
			if attempt < AI_MAX_RETRIES:
				_retry_wait(attempt)
				continue
			return None, last_error
		except json.JSONDecodeError:
			return None, "Gemini returned invalid JSON."
		except Exception as e:
			return None, f"Gemini API Error: {str(e)}"
	return None, last_error or "Gemini request failed after retries."


def call_groq_api(prompt, api_key):
	url = "https://api.groq.com/openai/v1/chat/completions"
	last_error = None
	for model_name in GROQ_MODELS:
		for attempt in range(1, AI_MAX_RETRIES + 1):
			body = {
				"model": model_name,
				"messages": [
					{
						"role": "system",
						"content": (
							"You are a professional translator and music researcher. "
							"Support Arabic and English equally. "
							"Follow the user's instructions exactly. "
							"Do not add extra commentary outside the requested sections."
						),
					},
					{"role": "user", "content": prompt},
				],
				"temperature": 0.3,
			}
			if model_name.startswith("qwen/"):
				body["reasoning_effort"] = "none"
			payload = json.dumps(body).encode("utf-8")
			try:
				response_text = _http_json(
					url,
					data=payload,
					headers={
						"Content-Type": "application/json",
						"Authorization": f"Bearer {api_key}",
					},
					timeout=60,
				)
				result = json.loads(response_text)
				choices = result.get("choices", [])
				if not choices:
					last_error = "Groq returned no choices."
					break
				message = choices[0].get("message", {}) or {}
				generated_text = (message.get("content") or "").strip()
				if not generated_text:
					last_error = "Groq returned empty text."
					break
				return generated_text, None
			except urllib.error.HTTPError as e:
				error_message = ""
				retry_after = 0
				try:
					retry_after = int(float(e.headers.get("Retry-After") or 0))
				except Exception:
					retry_after = 0
				try:
					error_body = e.read().decode("utf-8")
					error_data = json.loads(error_body)
					error_obj = error_data.get("error", {})
					if isinstance(error_obj, dict):
						error_message = error_obj.get("message", "")
					else:
						error_message = str(error_obj)
				except Exception:
					pass
				last_error = (
					f"Groq HTTP Error {e.code}: {error_message}"
					if error_message
					else f"Groq HTTP Error {e.code}."
				)
				if e.code == 400 and "reasoning_effort" in (error_message or ""):
					try:
						body.pop("reasoning_effort", None)
						payload = json.dumps(body).encode("utf-8")
						response_text = _http_json(
							url,
							data=payload,
							headers={
								"Content-Type": "application/json",
								"Authorization": f"Bearer {api_key}",
							},
							timeout=60,
						)
						result = json.loads(response_text)
						generated_text = (
							result.get("choices", [{}])[0]
							.get("message", {})
							.get("content", "")
							or ""
						).strip()
						if generated_text:
							return generated_text, None
					except Exception:
						pass
				if e.code in (400, 404) and "model" in (error_message or "").lower():
					break
				if e.code in AI_RETRY_STATUS_CODES and attempt < AI_MAX_RETRIES:
					_retry_wait(attempt, retry_after)
					continue
				if e.code in (401, 403):
					return None, last_error
				if e.code not in (400, 404):
					return None, last_error
				break
			except urllib.error.URLError as e:
				last_error = f"Network error while connecting to Groq: {str(e)}"
				if attempt < AI_MAX_RETRIES:
					_retry_wait(attempt)
					continue
				return None, last_error
			except json.JSONDecodeError:
				return None, "Groq returned invalid JSON."
			except Exception as e:
				return None, f"Groq API Error: {str(e)}"
	return None, last_error or "Groq request failed after retries."


def call_ai_api(prompt):
	provider, api_key = get_active_api_key()
	if not api_key:
		return (
			None,
			"No AI API key is set. Open NVDA Settings → NV-SoftPlayer "
			"and paste a Groq key (recommended) or a Gemini key. "
			"Lyrics search still works without a key."
		)
	if provider == "groq":
		return call_groq_api(prompt, api_key)
	return call_gemini_api(prompt, api_key)


def fetch_song_metadata(title, artist):
	_, api_key = get_active_api_key()
	if not api_key:
		return (
			"Song Information: Unavailable.\n"
			"Reason: No AI API key is set. Lyrics are still shown. "
			"Add a Groq or Gemini key in NVDA Settings → NV-SoftPlayer."
		), "Album tracklist: Unavailable (no AI API key)."
	prompt = (
		f"Research the song '{title}' by '{artist}'. "
		"The names may be in Arabic or English. Use the original language of the "
		"artist for names of albums and tracks when they are Arabic.\n\n"
		"Format the answer as plain text using exactly these labels:\n"
		"Singer/Artist:\n"
		"Lyricist:\n"
		"Album:\n"
		"Release Year:\n"
		"Producer/Label:\n"
		"Short summary of the song meaning:\n\n"
		"Then add this exact section:\n"
		"--- Album Tracklist ---\n"
		"Numbered list of every track on the same album as this song. "
		"If the album is unknown, write Unknown.\n"
	)
	result, error = call_ai_api(prompt)
	if error:
		return (
			f"Song Information: Unavailable.\nReason: {error}",
			f"Album tracklist: Unavailable.\nReason: {error}",
		)
	text = result.strip()
	marker = "--- Album Tracklist ---"
	if marker in text:
		info, tracklist = text.split(marker, 1)
		info = info.strip()
		tracklist = marker + "\n" + tracklist.strip()
	else:
		info = text
		tracklist = "--- Album Tracklist ---\nUnknown"
	return info, tracklist


def parse_metadata_dict(meta_text):
	d = {
		"singer": "",
		"lyricist": "",
		"album": "",
		"release_year": "",
		"producer": "",
		"summary": "",
	}
	if not meta_text:
		return d

	def find_field(patterns):
		for pat in patterns:
			m = re.search(rf"(?:{pat})\s*:\s*(.*?)(?=\n[A-Za-z\u0600-\u06FF\s]+:|\n---|\Z)", meta_text, re.DOTALL | re.IGNORECASE)
			if m:
				val = m.group(1).strip()
				if val:
					return val
		return ""

	d["singer"] = find_field([r"Singer/Artist", r"Singer", r"Artist", r"المغني/الفنان", r"المغني", r"الفنان"])
	d["lyricist"] = find_field([r"Lyricist", r"Lyrics Writer", r"Writer", r"الشاعر", r"كاتب الكلمات", r"المؤلف"])
	d["album"] = find_field([r"Album", r"الألبوم"])
	d["release_year"] = find_field([r"Release Year", r"Year", r"سنة الإصدار", r"سنة النشر", r"السنة"])
	d["producer"] = find_field([r"Producer/Label", r"Music Producer/Label", r"Producer", r"Label", r"المنتج/شركة الإنتاج", r"المنتج", r"شركة الإنتاج"])
	d["summary"] = find_field([r"Short summary of the song meaning", r"Meaning / Summary", r"Summary", r"Meaning", r"ملخص معنى الأغنية", r"المعنى / الملخص", r"الملخص", r"المعنى"])

	if not d["summary"]:
		m = re.search(r"(?:summary|meaning|ملخص|قصة الأغنية)[^\n]*\n+(.*?)(?=\n---|\Z)", meta_text, re.DOTALL | re.IGNORECASE)
		if m:
			d["summary"] = m.group(1).strip()
	return d


def build_structured_lyrics_html(title, artist, lyrics_body, song_info_dict, meaning_summary, tracklist_body):
	title_esc = html.escape(str(title or "").strip())
	artist_esc = html.escape(str(artist or "").strip())

	lyrics_lines = [html.escape(l) for l in str(lyrics_body or "").strip().splitlines()]
	lyrics_html = "<br>\n".join(lyrics_lines) if lyrics_lines else "<em>No lyrics available</em>"

	singer = html.escape(str(song_info_dict.get("singer") or artist or "Unknown").strip())
	lyricist = html.escape(str(song_info_dict.get("lyricist") or "Unknown").strip())
	album = html.escape(str(song_info_dict.get("album") or "Unknown").strip())
	release_year = html.escape(str(song_info_dict.get("release_year") or "Unknown").strip())
	producer = html.escape(str(song_info_dict.get("producer") or "Unknown").strip())

	summary_text = str(meaning_summary or "No summary available.").strip()
	summary_html = "<br>\n".join(html.escape(l) for l in summary_text.splitlines())

	tracklist_text = str(tracklist_body or "Unknown").strip()
	tracklist_text = re.sub(r"-{2,}\s*Album Tracklist\s*-{2,}", "", tracklist_text, flags=re.IGNORECASE).strip()
	tracklist_html = "<br>\n".join(html.escape(l) for l in tracklist_text.splitlines())

	doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
	font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
	font-size: 13pt;
	line-height: 1.6;
	padding: 12px;
	color: #111;
}}
h1 {{
	font-size: 18pt;
	margin-top: 0;
	margin-bottom: 14px;
	color: #000;
}}
h2 {{
	font-size: 14pt;
	margin-top: 22px;
	margin-bottom: 8px;
	border-bottom: 1px solid #ccc;
	padding-bottom: 4px;
	color: #111;
}}
p {{
	margin-top: 6px;
	margin-bottom: 10px;
}}
</style>
</head>
<body>
<h1>{title_esc} – {artist_esc}</h1>
<p>{lyrics_html}</p>

<h2>Song Info</h2>
<p>
<strong>Singer/Artist:</strong> {singer}<br>
<strong>Lyricist:</strong> {lyricist}<br>
<strong>Album:</strong> {album}<br>
<strong>Release Year:</strong> {release_year}<br>
<strong>Producer/Label:</strong> {producer}
</p>

<h2>Meaning / Summary</h2>
<p>{summary_html}</p>

<h2>Album Tracklist</h2>
<p>{tracklist_html}</p>
</body>
</html>"""
	return doc


def build_structured_lyrics_plain(title, artist, lyrics_body, song_info_dict, meaning_summary, tracklist_body):
	singer = str(song_info_dict.get("singer") or artist or "Unknown").strip()
	lyricist = str(song_info_dict.get("lyricist") or "Unknown").strip()
	album = str(song_info_dict.get("album") or "Unknown").strip()
	release_year = str(song_info_dict.get("release_year") or "Unknown").strip()
	producer = str(song_info_dict.get("producer") or "Unknown").strip()
	summary = str(meaning_summary or "Unknown").strip()
	tracklist = str(tracklist_body or "Unknown").strip()
	tracklist = re.sub(r"-{2,}\s*Album Tracklist\s*-{2,}", "", tracklist, flags=re.IGNORECASE).strip()
	lyrics_text = str(lyrics_body or "").strip() or "No lyrics available."

	return (
		f"{title} – {artist}\n\n"
		f"{lyrics_text}\n\n"
		f"Song Info\n"
		f"Singer/Artist: {singer}\n"
		f"Lyricist: {lyricist}\n"
		f"Album: {album}\n"
		f"Release Year: {release_year}\n"
		f"Producer/Label: {producer}\n\n"
		f"Meaning / Summary\n"
		f"{summary}\n\n"
		f"Album Tracklist\n"
		f"{tracklist}\n\n"
		f"By Anas Rayyan"
	)


def parse_translated_sections(raw_text, original_meta_dict=None, default_tracklist=""):
	if not raw_text:
		return "", dict(original_meta_dict or {}), "", default_tracklist or ""
	meta_dict = dict(original_meta_dict or {})
	lyrics = ""
	summary = ""
	tracklist = default_tracklist or ""

	sections = re.split(r"-{2,}\s*([^\n-]+?)\s*-{2,}", raw_text)
	if len(sections) >= 3:
		i = 1
		while i < len(sections):
			sec_title = sections[i].lower()
			sec_body = sections[i + 1].strip() if i + 1 < len(sections) else ""
			if any(k in sec_title for k in ["lyric", "parole", "كلمات"]):
				lyrics = sec_body
			elif any(k in sec_title for k in ["info", "معلومات"]):
				parsed_meta = parse_metadata_dict(sec_body)
				for k, v in parsed_meta.items():
					if v:
						meta_dict[k] = v
			elif any(k in sec_title for k in ["summary", "meaning", "ملخص", "معنى"]):
				summary = sec_body
			elif any(k in sec_title for k in ["tracklist", "album", "قائمة"]):
				tracklist = sec_body
			i += 2
	else:
		lyrics = raw_text.strip()

	if not summary:
		summary = meta_dict.get("summary", "")
	return lyrics, meta_dict, summary, tracklist


def fetch_artist_details(artist, target_language=None, profound=False):
	if target_language:
		lang_instruction = (
			f" Write the entire answer in {target_language} only. "
			"Do not leave English sentences except proper names."
		)
	else:
		lang_instruction = (
			"If this is an Arabic artist, write the answer in Arabic. "
			"Otherwise write in English."
		)
	style = ""
	if profound:
		style = (
			" Prefer a deep, nuanced and idiomatic rendering that captures "
			"cultural context, emotional undertones and figurative language "
			"rather than a purely literal translation."
		)
	prompt = (
		f"Provide detailed information about the music artist '{artist}'. "
		f"{lang_instruction}{style}\n\n"
		"Use exactly this structure:\n"
		"--- Biography ---\n"
		"Write the biography as clear readable paragraphs (2 to 5 short paragraphs). "
		"Use blank lines between paragraphs. Do NOT write the whole biography as one long line.\n\n"
		"--- Popular albums ---\n"
		"(Numbered list, one album per line)\n\n"
		"--- Popular songs ---\n"
		"(Numbered list, one song per line)\n"
	)
	return call_ai_api(prompt)


def fetch_artist_news(artist, years_back=2):
	prompt = (
		f"Provide the latest news and updates about the music artist '{artist}'. "
		"Prioritize the most recent and currently relevant items first "
		"(new releases, tours, awards, collaborations, industry announcements). "
		"Include approximate dates when known. "
		"Focus on verifiable public information. Ignore pure gossip.\n\n"
		"Use exactly this structure:\n"
		"--- Latest Artist News ---\n"
		"(Numbered list of the most recent notable news items, newest first. "
		"If little reliable news is available, say so clearly.)\n\n"
		"--- Summary ---\n"
		"(2–4 sentences summarizing what the artist has been doing recently.)\n"
	)
	return call_ai_api(prompt)


def translate_selection_with_context(
	selected_text, surrounding_line, song_title, artist, target_language, profound=False
):
	style = ""
	if profound:
		style = (
			" Prefer a deep, nuanced and idiomatic rendering that captures "
			"cultural context, emotional undertones and figurative language."
		)
	prompt = (
		f"You are a professional translator and language teacher specializing in song lyrics.\n"
		f"Translate and explain the selected text in the context of the song lyrics.\n"
		f"Write ALL explanatory text in {target_language} only (except the original "
		f"selected text and synonym list which stay in the source language).{style}\n\n"
		f"Song: {song_title}\n"
		f"Artist: {artist}\n"
		f"Surrounding lyric line: {surrounding_line}\n"
		f"Selected text: {selected_text}\n\n"
		f"Use exactly this structure:\n\n"
		f"--- Translation ---\n"
		f"(Accurate translation of the selected word/phrase into {target_language})\n\n"
		f"--- Why it appears here ---\n"
		f"(Brief contextual analysis: why this word/phrase is used in this lyric line, "
		f"its emotional or narrative role, any cultural or figurative meaning)\n\n"
		f"--- Useful synonyms (original language) ---\n"
		f"(Numbered list of 3–8 useful synonyms or near-synonyms in the ORIGINAL "
		f"language of the selected text, with a short gloss in {target_language} for each)\n"
	)
	return call_ai_api(prompt)


_MUSIC_QA_BLOCKED_PATTERNS = re.compile(
	r"\b("
	r"code|coding|program(?:ming)?|python|javascript|java\b|html|css|sql|"
	r"web\s*design|website|server|database|algorithm|function\s*\(|"
	r"class\s+\w+|import\s+\w+|def\s+\w+|console\.|print\s*\(|"
	r"math(?:ematics)?\s*problem|solve\s+equation|homework|"
	r"hack(?:ing)?|password|credit\s*card|"
	r"stock\s*market|crypto|bitcoin|"
	r"medical\s*advice|diagnose|prescribe"
	r")\b",
	re.IGNORECASE,
)

_MUSIC_QA_ALLOW_SIGNALS = re.compile(
	r"\b("
	r"singer|artist|musician|band|producer|lyricist|songwriter|composer|"
	r"album|song|track|lyrics?|meaning|theme|message|story|"
	r"vocabulary|word|phrase|idiom|metaphor|expression|slang|"
	r"language|translate|translation|synonym|grammar|usage|"
	r"daily\s*life|everyday|real\s*life|conversation|speak|say|"
	r"life|biography|bio|career|born|childhood|family|background|"
	r"release|label|genre|style|instrument|melody|harmony|rhythm|"
	r"performance|concert|tour|award|collaboration|who\s+is|about\s+her|"
	r"about\s+him|about\s+them|tell\s+me|explain|what\s+does|how\s+(can|do)|"
	r"can\s+i\s+use|is\s+it\s+(common|ok|okay|correct)"
	r")\b",
	re.IGNORECASE,
)


def is_music_related_question(question, song_title, artist):
	q = (question or "").strip()
	if not q or len(q) < 3:
		return False
	if _MUSIC_QA_BLOCKED_PATTERNS.search(q):
		return False
	lower = q.lower()
	if _MUSIC_QA_ALLOW_SIGNALS.search(lower):
		return True
	if song_title and any(part and part in lower for part in song_title.lower().split() if len(part) > 2):
		return True
	if artist and any(part and part in lower for part in artist.lower().split() if len(part) > 2):
		return True
	if len(q.split()) <= 12:
		return True
	return False


def answer_music_question(question, song_title, artist, raw_lyrics, song_info):
	if not is_music_related_question(question, song_title, artist):
		return (
			None,
			"This question looks unrelated to music, this song, the artist, or language learning. "
			"You can ask about the singer's life and career, the song or album, "
			"lyric meanings, vocabulary, or how to use a phrase from the song in daily life."
		)
	prompt = (
		"You are a helpful music educator and language teacher. "
		"The user is viewing lyrics for a specific song. Answer questions about:\n"
		"- The singer/artist (life, career, biography, background)\n"
		"- The song, album, producer, or music details\n"
		"- Lyrical meaning, themes, and analysis\n"
		"- Vocabulary, phrases from the lyrics, and how to use them in daily life / conversation\n"
		"Only refuse if the question is clearly about programming, web design, "
		"finance hacks, medical advice, or other non-music topics.\n\n"
		f"Song title: {song_title}\n"
		f"Artist: {artist}\n"
		f"Song info:\n{song_info}\n\n"
		f"Lyrics (for context):\n{(raw_lyrics or '')[:3000]}\n\n"
		f"User question: {question}\n\n"
		"Answer clearly in plain text. Use short paragraphs. Keep under 450 words."
	)
	return call_ai_api(prompt)


def fetch_lyrics_online(query):
	try:
		cleaned_query = clean_query(query)
		if not cleaned_query:
			return (
				None,
				"No valid song name remained after cleaning ignore words and emojis."
			)
		encoded_query = urllib.parse.quote(cleaned_query, safe="")
		url = f"https://lrclib.net/api/search?q={encoded_query}"
		request = urllib.request.Request(
			url,
			headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
			method="GET",
		)
		with urllib.request.urlopen(request, timeout=15) as response:
			response_text = response.read().decode("utf-8")
		data = json.loads(response_text)
		if not isinstance(data, list) or not data:
			return None, f"No lyrics were found for '{cleaned_query}'."
		chosen = None
		for item in data:
			if not isinstance(item, dict):
				continue
			if item.get("plainLyrics") or item.get("syncedLyrics"):
				chosen = item
				break
		if chosen is None:
			return None, "The song was found, but no lyrics were available."
		title = chosen.get("trackName", cleaned_query)
		artist = chosen.get("artistName", "Unknown artist")
		plain_lyrics = chosen.get("plainLyrics") or ""
		synced_lyrics = chosen.get("syncedLyrics") or ""
		if not plain_lyrics and synced_lyrics:
			plain_parts = []
			for raw in str(synced_lyrics).splitlines():
				line = re.sub(r"\[(\d{1,3}):(\d{1,2}(?:\.\d+)?)\]", "", raw).strip()
				if line:
					plain_parts.append(line)
			plain_lyrics = "\n".join(plain_parts)
		meta_info, tracklist = fetch_song_metadata(title, artist)
		meta_dict = parse_metadata_dict(meta_info)
		summary_text = meta_dict.get("summary") or "Song information retrieved from AI assistant."
		structured_html = build_structured_lyrics_html(title, artist, plain_lyrics, meta_dict, summary_text, tracklist)
		structured_plain = build_structured_lyrics_plain(title, artist, plain_lyrics, meta_dict, summary_text, tracklist)
		return (
			{
				"title": title,
				"artist": artist,
				"lyrics": structured_plain,
				"html": structured_html,
				"raw_lyrics": plain_lyrics,
				"song_info": meta_info,
				"tracklist": tracklist,
				"meta_dict": meta_dict,
			},
			None
		)
	except urllib.error.HTTPError as e:
		return None, f"LRCLIB HTTP Error {e.code}."
	except urllib.error.URLError as e:
		return None, f"Network error while contacting LRCLIB: {str(e)}"
	except json.JSONDecodeError:
		return None, "LRCLIB returned invalid JSON."
	except Exception as e:
		return None, f"Error while fetching lyrics: {str(e)}"


class LanguageSelectDialog(wx.Dialog):
	def __init__(self, parent, default_language=None):
		super().__init__(parent, title=_("Translate Lyrics"), size=(420, 180))
		apply_ui_layout(self)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		label = wx.StaticText(panel, label=_("Choose target language:"))
		sizer.Add(label, 0, wx.ALL, 10)
		pref = get_preferred_languages()
		ordered = []
		seen = set()
		for lang in pref + list(TRANSLATION_LANGUAGES):
			key = lang.lower()
			if key in seen:
				continue
			seen.add(key)
			ordered.append(lang)
		self.language_choice = wx.Choice(panel, choices=ordered)
		if not default_language:
			default_language = pref[0] if pref else nvda_default_target_language()
		if default_language in ordered:
			self.language_choice.SetStringSelection(default_language)
		else:
			self.language_choice.SetSelection(0)
		sizer.Add(self.language_choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
		button_sizer = wx.BoxSizer(wx.HORIZONTAL)
		ok_button = wx.Button(panel, wx.ID_OK, label="&OK")
		cancel_button = wx.Button(panel, wx.ID_ANY, label="&Cancel")
		button_sizer.Add(ok_button, 0, wx.ALL, 5)
		button_sizer.Add(cancel_button, 0, wx.ALL, 5)
		sizer.Add(button_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		panel.SetSizer(sizer)
		cancel_button.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))
		self.Bind(wx.EVT_CLOSE, lambda e: self.EndModal(wx.ID_CANCEL))
		self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)
		self.language_choice.SetFocus()
		self.CentreOnParent()

	def on_key_down(self, event):
		key = event.GetKeyCode()
		ctrl_down = event.ControlDown()
		alt_down = event.AltDown()
		if (ctrl_down and not alt_down and key in (ord('W'), ord('w'))) or (
			alt_down and not ctrl_down and key == wx.WXK_F4
		):
			self.EndModal(wx.ID_CANCEL)
			return
		if key == wx.WXK_ESCAPE:
			# Do not close on Escape key
			return
		event.Skip()

	def get_language(self):
		index = self.language_choice.GetSelection()
		if index == wx.NOT_FOUND:
			return ""
		return self.language_choice.GetString(index)


class ManualSearchDialog(wx.Dialog):
	def __init__(self, parent, on_search):
		super().__init__(parent, title=_("Search Lyrics"), size=(480, 200))
		apply_ui_layout(self)
		self.on_search = on_search
		self._closed = False
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		label = wx.StaticText(panel, label=_("Enter song name or artist:"))
		sizer.Add(label, 0, wx.ALL, 10)
		self.query_ctrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
		sizer.Add(self.query_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
		self.status_label = wx.StaticText(panel, label="")
		sizer.Add(self.status_label, 0, wx.EXPAND | wx.ALL, 8)
		button_sizer = wx.BoxSizer(wx.HORIZONTAL)
		self.search_button = wx.Button(panel, wx.ID_OK, label="&" + _("Search"))
		self.cancel_button = wx.Button(panel, wx.ID_ANY, label="&" + _("Cancel"))
		button_sizer.Add(self.search_button, 0, wx.ALL, 5)
		button_sizer.Add(self.cancel_button, 0, wx.ALL, 5)
		sizer.Add(button_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		panel.SetSizer(sizer)
		self.search_button.Bind(wx.EVT_BUTTON, self.on_ok)
		self.cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel)
		self.query_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_ok)
		self.Bind(wx.EVT_CLOSE, self.on_cancel)
		self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)
		self.query_ctrl.SetFocus()
		self.CentreOnParent()

	def set_searching(self):
		self.status_label.SetLabel("Searching, please wait. This window will stay open.")
		self.search_button.Disable()
		self.query_ctrl.Disable()

	def reset_search(self):
		if self._closed:
			return
		self.status_label.SetLabel("No results. Try another search.")
		self.search_button.Enable()
		self.query_ctrl.Enable()
		self.query_ctrl.SetFocus()

	def close_quietly(self):
		if self._closed:
			return
		self._closed = True
		try:
			gui.mainFrame.postPopup()
		except Exception:
			pass
		self.Destroy()

	def on_ok(self, event):
		query = self.query_ctrl.GetValue().strip()
		if not query:
			ui.message("Enter a search query.")
			return
		self.set_searching()
		if self.on_search:
			self.on_search(query)

	def on_cancel(self, event):
		self.close_quietly()

	def on_key_down(self, event):
		key = event.GetKeyCode()
		ctrl_down = event.ControlDown()
		alt_down = event.AltDown()
		if (ctrl_down and not alt_down and key in (ord('W'), ord('w'))) or (
			alt_down and not ctrl_down and key == wx.WXK_F4
		):
			self.close_quietly()
			return
		if key == wx.WXK_ESCAPE:
			# Do not close on Escape key
			return
		event.Skip()


class ResultTextDialog(wx.Dialog):
	def __init__(self, parent, title, text, size=(640, 480)):
		super().__init__(parent, title=title, size=size)
		apply_ui_layout(self)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.ctrl = wx.TextCtrl(
			panel, value=(text or "").strip(),
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
		)
		sizer.Add(self.ctrl, 1, wx.EXPAND | wx.ALL, 10)
		btn_row = wx.BoxSizer(wx.HORIZONTAL)
		copy_btn = wx.Button(panel, label="&" + _("Copy"))
		close_btn = wx.Button(panel, wx.ID_ANY, label="&" + _("Close"))
		btn_row.Add(copy_btn, 0, wx.ALL, 5)
		btn_row.Add(close_btn, 0, wx.ALL, 5)
		sizer.Add(btn_row, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		panel.SetSizer(sizer)

		copy_btn.Bind(wx.EVT_BUTTON, self.on_copy)
		close_btn.Bind(wx.EVT_BUTTON, lambda e: self.Destroy())
		self.Bind(wx.EVT_CLOSE, lambda e: self.Destroy())
		self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)

	def on_copy(self, evt=None):
		try:
			api.copyToClip(self.ctrl.GetValue())
			ui.message(_("Copied to clipboard."))
		except Exception as e:
			handle_error(str(e))

	def on_key_down(self, event):
		key = event.GetKeyCode()
		ctrl_down = event.ControlDown()
		alt_down = event.AltDown()
		if (ctrl_down and not alt_down and key in (ord('W'), ord('w'))) or (
			alt_down and not ctrl_down and key == wx.WXK_F4
		):
			self.Destroy()
			return
		if key == wx.WXK_ESCAPE:
			# Do not close on Escape key
			return
		event.Skip()


class ArtistDetailsDialog(wx.Dialog):
	def __init__(self, parent, artist, initial_text, target_language=None, already_translated=False):
		self.artist = artist
		self._closed = False
		self._translating = False
		self._last_language = target_language or nvda_default_target_language()
		self._is_translated = already_translated
		self._current_text = initial_text
		super().__init__(parent, title=f"{_('Artist details')} - {artist}", size=(700, 560))
		apply_ui_layout(self)
		panel = wx.Panel(self)
		main_sizer = wx.BoxSizer(wx.VERTICAL)
		heading = wx.StaticText(panel, label=f"Artist: {artist}")
		heading.SetFont(
			wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
		)
		main_sizer.Add(heading, 0, wx.EXPAND | wx.ALL, 10)
		self.text_ctrl = wx.TextCtrl(
			panel, value=initial_text,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
		)
		main_sizer.Add(self.text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
		button_sizer = wx.BoxSizer(wx.HORIZONTAL)
		self.back_button = wx.Button(panel, label="&" + _("Back"))
		self.translate_button = wx.Button(panel, label="&" + _("Translate"))
		self.profound_button = wx.Button(panel, label=_("Profound Translation"))
		self.copy_button = wx.Button(panel, label=_("Copy Text"))
		self.close_button = wx.Button(panel, wx.ID_CLOSE, label="&" + _("Close"))
		button_sizer.Add(self.back_button, 0, wx.ALL, 5)
		button_sizer.Add(self.translate_button, 0, wx.ALL, 5)
		button_sizer.Add(self.profound_button, 0, wx.ALL, 5)
		button_sizer.Add(self.copy_button, 0, wx.ALL, 5)
		button_sizer.Add(self.close_button, 0, wx.ALL, 5)
		main_sizer.Add(button_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		panel.SetSizer(main_sizer)
		self.back_button.Bind(wx.EVT_BUTTON, self.on_back)
		self.translate_button.Bind(wx.EVT_BUTTON, lambda e: self.on_translate(profound=False))
		self.profound_button.Bind(wx.EVT_BUTTON, lambda e: self.on_translate(profound=True))
		self.copy_button.Bind(wx.EVT_BUTTON, self.on_copy)
		self.close_button.Bind(wx.EVT_BUTTON, self.on_close)
		self.Bind(wx.EVT_CLOSE, self.on_close)
		self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)
		self.text_ctrl.SetFocus()
		self.CentreOnParent()

	def on_back(self, event):
		self.on_close(event)
		try:
			parent = self.GetParent()
			if parent:
				parent.Raise()
				parent.SetFocus()
		except Exception:
			pass

	def on_copy(self, event):
		try:
			api.copyToClip(self.text_ctrl.GetValue())
			ui.message("Copied to clipboard.")
		except Exception as e:
			handle_error(f"Failed to copy text: {e}")

	def on_translate(self, profound=False):
		if self._translating:
			ui.message("Translation is already in progress.")
			return
		_, api_key = get_active_api_key()
		if not api_key:
			handle_error(
				"No AI API key is set. Open NVDA Settings → NV-SoftPlayer "
				"and paste a Groq key (recommended) or a Gemini key."
			)
			return
		if self._is_translated and self._last_language:
			target_lang = self._last_language
		else:
			lang_dlg = LanguageSelectDialog(self, self._last_language)
			if lang_dlg.ShowModal() != wx.ID_OK:
				lang_dlg.Destroy()
				return
			target_lang = lang_dlg.get_language()
			lang_dlg.Destroy()
			if not target_lang:
				ui.message("No language selected.")
				return
		self._last_language = target_lang
		self._translating = True
		self.translate_button.Disable()
		self.profound_button.Disable()
		mode = "profound" if profound else "standard"
		provider, _ = get_active_api_key()
		provider_name = "Groq" if provider == "groq" else "Gemini"
		ui.message(
			f"Translating artist details to {target_lang} "
			f"({mode} mode) using {provider_name}..."
		)
		artist = self.artist

		def worker():
			text, error = fetch_artist_details(
				artist, target_language=target_lang, profound=profound
			)
			wx.CallAfter(self._translation_done, text, error)

		threading.Thread(target=worker, daemon=True).start()

	def _translation_done(self, text, error):
		self._translating = False
		if not self._closed:
			self.translate_button.Enable()
			self.profound_button.Enable()
		if error:
			handle_error(error)
			return
		self._is_translated = True
		self._current_text = text.strip()
		self.text_ctrl.SetValue(self._current_text)
		self.text_ctrl.SetFocus()
		ui.message("Artist details translation completed.")

	def on_key_down(self, event):
		key = event.GetKeyCode()
		ctrl_down = event.ControlDown()
		alt_down = event.AltDown()
		if (ctrl_down and not alt_down and key in (ord('W'), ord('w'))) or (
			alt_down and not ctrl_down and key == wx.WXK_F4
		):
			self.on_close(event)
			return
		if key == wx.WXK_ESCAPE:
			# Do not close on Escape key
			return
		event.Skip()

	def on_close(self, event):
		if self._closed:
			return
		self._closed = True
		try:
			gui.mainFrame.postPopup()
		except Exception:
			pass
		self.Destroy()


class LyricsDialog(wx.Dialog):
	def __init__(self, parent, result):
		self.song_title = result.get("title", "Unknown title")
		self.artist = result.get("artist", "Unknown artist")
		self.raw_lyrics = result.get("raw_lyrics", "")
		self.song_info = result.get("song_info", "")
		self.meta_dict = result.get("meta_dict") or parse_metadata_dict(self.song_info)
		self.tracklist = result.get("tracklist", "")
		self.original_html = result.get("html") or build_structured_lyrics_html(
			self.song_title, self.artist, self.raw_lyrics,
			self.meta_dict, self.meta_dict.get("summary", ""), self.tracklist
		)
		self.original_plain = result.get("lyrics") or build_structured_lyrics_plain(
			self.song_title, self.artist, self.raw_lyrics,
			self.meta_dict, self.meta_dict.get("summary", ""), self.tracklist
		)
		self.current_html = self.original_html
		self.current_plain = self.original_plain
		self.full_text = self.current_plain
		self._closed = False
		self._translating = False
		self._artist_loading = False
		self._news_loading = False
		self._qa_busy = False
		self._selection_busy = False
		pref = get_preferred_languages()
		self._last_language = pref[0] if pref else nvda_default_target_language()
		self._is_translated = False
		self._artist_dialog = None
		self._result_dialog = None
		super().__init__(parent, title=f"{self.song_title} - {self.artist}", size=(760, 680))
		apply_ui_layout(self)
		self.panel = wx.Panel(self)
		main_sizer = wx.BoxSizer(wx.VERTICAL)
		heading = wx.StaticText(self.panel, label=f"{self.song_title} — {self.artist}")
		heading.SetFont(
			wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
		)
		main_sizer.Add(heading, 0, wx.EXPAND | wx.ALL, 10)
		self.lyrics_ctrl = wx.TextCtrl(
			self.panel,
			value=self.current_plain,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
		)
		self.html_ctrl = self.lyrics_ctrl
		main_sizer.Add(self.lyrics_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

		qa_label = wx.StaticText(
			self.panel,
			label=_("Ask about this song / artist / lyrics (music topics only):"),
		)
		main_sizer.Add(qa_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)
		qa_row = wx.BoxSizer(wx.HORIZONTAL)
		self.qa_ctrl = wx.TextCtrl(self.panel, style=wx.TE_PROCESS_ENTER)
		qa_row.Add(self.qa_ctrl, 1, wx.EXPAND | wx.RIGHT, 6)
		self.qa_button = wx.Button(self.panel, label="&" + _("Ask"))
		qa_row.Add(self.qa_button, 0)
		main_sizer.Add(qa_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

		self.button_sizer = wx.BoxSizer(wx.HORIZONTAL)
		self.back_button = wx.Button(self.panel, label=_("Back to Original Lyrics"))
		self.back_button.Hide()
		self.translate_button = wx.Button(self.panel, label=_("Translate Lyrics"))
		self.profound_button = wx.Button(self.panel, label=_("Profound Translation"))
		self.artist_button = wx.Button(self.panel, label=_("Artist details"))
		self.news_button = wx.Button(self.panel, label=_("Latest Artist News"))
		self.html_button = wx.Button(self.panel, label=_("HTML View (Browse Mode)"))
		self.copy_button = wx.Button(self.panel, label=_("Copy Text"))
		self.close_button = wx.Button(self.panel, wx.ID_CLOSE, label="&Close")
		self.button_sizer.Add(self.back_button, 0, wx.ALL, 4)
		self.button_sizer.Add(self.translate_button, 0, wx.ALL, 4)
		self.button_sizer.Add(self.profound_button, 0, wx.ALL, 4)
		self.button_sizer.Add(self.artist_button, 0, wx.ALL, 4)
		self.button_sizer.Add(self.news_button, 0, wx.ALL, 4)
		self.button_sizer.Add(self.html_button, 0, wx.ALL, 4)
		self.button_sizer.Add(self.copy_button, 0, wx.ALL, 4)
		self.button_sizer.Add(self.close_button, 0, wx.ALL, 4)
		main_sizer.Add(self.button_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.panel.SetSizer(main_sizer)

		self.back_button.Bind(wx.EVT_BUTTON, self.on_back_to_original)
		self.translate_button.Bind(wx.EVT_BUTTON, lambda e: self.on_translate(profound=False))
		self.profound_button.Bind(wx.EVT_BUTTON, lambda e: self.on_translate(profound=True))
		self.artist_button.Bind(wx.EVT_BUTTON, self.on_artist_details)
		self.news_button.Bind(wx.EVT_BUTTON, self.on_artist_news)
		self.html_button.Bind(wx.EVT_BUTTON, self.on_browse_html)
		self.copy_button.Bind(wx.EVT_BUTTON, self.on_copy)
		self.close_button.Bind(wx.EVT_BUTTON, self.on_close)
		self.qa_button.Bind(wx.EVT_BUTTON, self.on_ask)
		self.qa_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_ask)
		self.lyrics_ctrl.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
		self.Bind(wx.EVT_CLOSE, self.on_close)
		self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)
		self.lyrics_ctrl.SetInsertionPoint(0)
		self.lyrics_ctrl.SetFocus()
		self.CentreOnParent()

	def on_back_to_original(self, event=None):
		self.current_html = self.original_html
		self.current_plain = self.original_plain
		self.full_text = self.current_plain
		self.lyrics_ctrl.SetValue(self.current_plain)
		self.lyrics_ctrl.SetInsertionPoint(0)
		self.SetTitle(f"{self.song_title} - {self.artist}")
		self._is_translated = False
		self.back_button.Hide()
		self.panel.Layout()
		self.Layout()
		self.lyrics_ctrl.SetFocus()
		ui.message(_("Showing original lyrics."))

	def on_browse_html(self, event=None):
		try:
			title = f"{self.song_title} - {self.artist}"
			if self._is_translated:
				title += f" ({_('Translated')})"
			ui.browseableMessage(self.current_html, title=title, isHtml=True)
		except Exception as e:
			handle_error(f"Failed to open HTML view: {str(e)}")

	def _get_selected_text_and_line(self):
		try:
			if hasattr(self, "lyrics_ctrl") and hasattr(self.lyrics_ctrl, "GetSelection"):
				start, end = self.lyrics_ctrl.GetSelection()
				full = self.lyrics_ctrl.GetValue()
				if start != end and start >= 0:
					selected = full[start:end].strip()
					if selected:
						line_start = full.rfind("\n", 0, start) + 1
						line_end = full.find("\n", end)
						if line_end < 0:
							line_end = len(full)
						line = full[line_start:line_end].strip()
						return selected, line
			return "", ""
		except Exception:
			return "", ""

	def on_context_menu(self, event=None):
		selected, line = self._get_selected_text_and_line()
		menu = wx.Menu()
		id_translate = wx.NewIdRef()
		id_profound = wx.NewIdRef()
		id_full_translate = wx.NewIdRef()
		id_full_profound = wx.NewIdRef()
		id_browse_html = wx.NewIdRef()
		id_copy = wx.NewIdRef()

		if selected:
			label = (
				f"Translate selection ({selected[:40]}…)"
				if len(selected) > 40
				else f"Translate selection: {selected}"
			)
			menu.Append(id_translate, label)
			menu.Append(id_profound, "Profound translation of selection")
			menu.AppendSeparator()
		menu.Append(id_full_translate, "Translate full lyrics")
		menu.Append(id_full_profound, "Profound translation of full lyrics")
		menu.AppendSeparator()
		menu.Append(id_browse_html, _("HTML View (Browse Mode)"))
		menu.Append(id_copy, _("Copy Text"))

		if selected:
			self.Bind(wx.EVT_MENU, lambda e: self.on_translate_selection(selected, line, profound=False), id=id_translate)
			self.Bind(wx.EVT_MENU, lambda e: self.on_translate_selection(selected, line, profound=True), id=id_profound)
		self.Bind(wx.EVT_MENU, lambda e: self.on_translate(profound=False), id=id_full_translate)
		self.Bind(wx.EVT_MENU, lambda e: self.on_translate(profound=True), id=id_full_profound)
		self.Bind(wx.EVT_MENU, self.on_browse_html, id=id_browse_html)
		self.Bind(wx.EVT_MENU, self.on_copy, id=id_copy)

		try:
			self.PopupMenu(menu)
		finally:
			menu.Destroy()

	def on_translate_selection(self, selected, line, profound=False):
		if not selected:
			ui.message("Select a word or phrase in the lyrics first.")
			return
		if self._selection_busy:
			ui.message("A selection is already being translated.")
			return
		_, api_key = get_active_api_key()
		if not api_key:
			handle_error(
				"No AI API key is set. Open NVDA Settings → NV-SoftPlayer "
				"and paste a Groq key (recommended) or a Gemini key."
			)
			return
		lang_dlg = LanguageSelectDialog(self, self._last_language)
		if lang_dlg.ShowModal() != wx.ID_OK:
			lang_dlg.Destroy()
			return
		target_lang = lang_dlg.get_language()
		lang_dlg.Destroy()
		if not target_lang:
			ui.message("No language selected.")
			return
		self._last_language = target_lang
		self._selection_busy = True
		mode = "profound" if profound else "standard"
		provider, _ = get_active_api_key()
		provider_name = "Groq" if provider == "groq" else "Gemini"
		ui.message(
			f"Translating selection to {target_lang} ({mode}) using {provider_name}..."
		)
		title = self.song_title
		artist = self.artist

		def worker():
			text, error = translate_selection_with_context(
				selected, line, title, artist, target_lang, profound=profound
			)
			wx.CallAfter(self._show_selection_result, text, error, selected)

		threading.Thread(target=worker, daemon=True).start()

	def _show_selection_result(self, text, error, selected):
		self._selection_busy = False
		if error:
			handle_error(error)
			return
		try:
			if self._result_dialog:
				self._result_dialog.Destroy()
		except Exception:
			pass
		dlg = ResultTextDialog(self, title=f"Selection: {selected[:50]}", text=text, size=(640, 480))
		self._result_dialog = dlg

		def _clear(evt=None):
			self._result_dialog = None

		dlg.Bind(wx.EVT_WINDOW_DESTROY, _clear)
		dlg.Show()
		dlg.Raise()
		dlg.ctrl.SetFocus()
		ui.message("Selection translation ready.")

	def on_artist_news(self, event):
		if self._news_loading:
			ui.message("Artist news is already loading.")
			return
		_, api_key = get_active_api_key()
		if not api_key:
			handle_error(
				"No AI API key is set. Open NVDA Settings → NV-SoftPlayer "
				"and paste a Groq key (recommended) or a Gemini key."
			)
			return
		self._news_loading = True
		self.news_button.Disable()
		provider, _ = get_active_api_key()
		provider_name = "Groq" if provider == "groq" else "Gemini"
		ui.message(f"Loading latest news for {self.artist} using {provider_name}...")
		artist = self.artist

		def worker():
			text, error = fetch_artist_news(artist, years_back=2)
			wx.CallAfter(self._show_news_result, text, error)

		threading.Thread(target=worker, daemon=True).start()

	def _show_news_result(self, text, error):
		self._news_loading = False
		if not self._closed:
			self.news_button.Enable()
		if error:
			handle_error(error)
			return
		try:
			if self._result_dialog:
				self._result_dialog.Destroy()
		except Exception:
			pass
		dlg = ResultTextDialog(self, title=f"Latest news — {self.artist}", text=text, size=(700, 520))
		self._result_dialog = dlg

		def _clear(evt=None):
			self._result_dialog = None

		dlg.Bind(wx.EVT_WINDOW_DESTROY, _clear)
		dlg.Show()
		dlg.Raise()
		dlg.ctrl.SetFocus()
		ui.message("Artist news loaded.")

	def on_ask(self, event):
		if self._qa_busy:
			ui.message("A question is already being answered.")
			return
		question = self.qa_ctrl.GetValue().strip()
		if not question:
			ui.message("Type a music-related question first.")
			return
		if not is_music_related_question(question, self.song_title, self.artist):
			handle_error(
				"This question looks unrelated to music, this song, the artist, or language learning. "
				"You can ask about the singer's life and career, the song or album, "
				"lyric meanings, vocabulary, or how to use a phrase from the song in daily life."
			)
			return
		_, api_key = get_active_api_key()
		if not api_key:
			handle_error(
				"No AI API key is set. Open NVDA Settings → NV-SoftPlayer "
				"and paste a Groq key (recommended) or a Gemini key."
			)
			return
		self._qa_busy = True
		self.qa_button.Disable()
		self.qa_ctrl.Disable()
		provider, _ = get_active_api_key()
		provider_name = "Groq" if provider == "groq" else "Gemini"
		ui.message(f"Answering with {provider_name}...")
		q = question
		title = self.song_title
		artist = self.artist
		lyrics = self.raw_lyrics
		info = self.song_info

		def worker():
			text, error = answer_music_question(q, title, artist, lyrics, info)
			wx.CallAfter(self._show_qa_result, text, error)

		threading.Thread(target=worker, daemon=True).start()

	def _show_qa_result(self, text, error):
		self._qa_busy = False
		if not self._closed:
			self.qa_button.Enable()
			self.qa_ctrl.Enable()
		if error:
			handle_error(error)
			return
		try:
			if self._result_dialog:
				self._result_dialog.Destroy()
		except Exception:
			pass
		dlg = ResultTextDialog(self, title="Music Q&A answer", text=text, size=(640, 420))
		self._result_dialog = dlg

		def _clear(evt=None):
			self._result_dialog = None

		dlg.Bind(wx.EVT_WINDOW_DESTROY, _clear)
		dlg.Show()
		dlg.Raise()
		dlg.ctrl.SetFocus()
		ui.message("Answer ready.")

	def on_artist_details(self, event):
		if self._artist_loading:
			ui.message("Artist details are already loading.")
			return
		_, api_key = get_active_api_key()
		if not api_key:
			handle_error(
				"No AI API key is set. Open NVDA Settings → NV-SoftPlayer "
				"and paste a Groq key (recommended) or a Gemini key."
			)
			return
		self._artist_loading = True
		self.artist_button.Disable()
		provider, _ = get_active_api_key()
		provider_name = "Groq" if provider == "groq" else "Gemini"
		ui.message(f"Loading artist details for {self.artist} using {provider_name}...")
		artist = self.artist
		target_lang = self._last_language if self._is_translated else None
		already = self._is_translated

		def worker():
			text, error = fetch_artist_details(
				artist, target_language=target_lang, profound=False
			)
			wx.CallAfter(self._show_artist_details, text, error, target_lang, already)

		threading.Thread(target=worker, daemon=True).start()

	def _show_artist_details(self, text, error, target_lang, already_translated):
		self._artist_loading = False
		if not self._closed:
			self.artist_button.Enable()
		if error:
			handle_error(error)
			return
		try:
			if self._artist_dialog:
				self._artist_dialog.Destroy()
		except Exception:
			pass
		dlg = ArtistDetailsDialog(
			self, self.artist, text.strip(),
			target_language=target_lang,
			already_translated=already_translated,
		)
		self._artist_dialog = dlg

		def _clear(evt=None):
			self._artist_dialog = None

		dlg.Bind(wx.EVT_WINDOW_DESTROY, _clear)
		dlg.Show()
		dlg.Raise()
		ui.message("Artist details loaded.")

	def on_translate(self, profound=False):
		if self._translating:
			ui.message("Translation is already in progress.")
			return
		_, api_key = get_active_api_key()
		if not api_key:
			handle_error(
				"No AI API key is set. Open NVDA Settings → NV-SoftPlayer "
				"and paste a Groq key (recommended) or a Gemini key."
			)
			return
		lang_dlg = LanguageSelectDialog(self, self._last_language)
		if lang_dlg.ShowModal() != wx.ID_OK:
			lang_dlg.Destroy()
			return
		target_lang = lang_dlg.get_language()
		lang_dlg.Destroy()
		if not target_lang:
			ui.message("No language selected.")
			return
		self._last_language = target_lang
		self._translating = True
		self.translate_button.Disable()
		self.profound_button.Disable()
		mode = "profound / deep" if profound else "standard"
		provider, _ = get_active_api_key()
		provider_name = "Groq" if provider == "groq" else "Gemini"
		ui.message(
			f"Translating lyrics and song info to {target_lang} "
			f"({mode} mode) using {provider_name}..."
		)
		lyrics = self.raw_lyrics
		song_info = self.song_info
		tracklist = self.tracklist
		title = self.song_title
		artist = self.artist

		def translate_worker():
			style = ""
			if profound:
				style = (
					" Prefer a deep, nuanced and idiomatic translation that "
					"captures cultural context, emotional undertones, metaphors "
					"and figurative language rather than a purely literal "
					"line-by-line rendering."
				)
			prompt = (
				f"You are a professional translator and music researcher. Translate EVERYTHING into {target_lang}.\n"
				f"Write ALL output in {target_lang} only (except proper names that are normally kept).{style}\n\n"
				f"Song: {title} - {artist}\n\n"
				f"Use exactly this structure:\n\n"
				f"--- Translated Lyrics ---\n"
				f"(Translate the song lyrics here line-by-line)\n\n"
				f"--- Song Info ---\n"
				f"Singer/Artist: (translated/kept artist name)\n"
				f"Lyricist: (translated/kept lyricist)\n"
				f"Album: (translated/kept album name)\n"
				f"Release Year: (year)\n"
				f"Producer/Label: (producer or label)\n\n"
				f"--- Summary ---\n"
				f"(A clear summary of the song's story, emotion, and meaning, "
				f"written entirely in {target_lang}. This section is required.)\n\n"
				f"--- Album Tracklist ---\n"
				f"(Album tracklist if known, or write Unknown)\n\n"
				f"Original lyrics:\n{lyrics}\n\n"
				f"Original song info:\n{song_info}\n\n"
				f"Original tracklist:\n{tracklist}\n"
			)
			translated_result, error = call_ai_api(prompt)
			if error:
				wx.CallAfter(self._translation_failed, error)
				return
			trans_lyrics, trans_meta, trans_summary, trans_tracklist = parse_translated_sections(
				translated_result, self.meta_dict, self.tracklist
			)
			if not trans_lyrics:
				trans_lyrics = translated_result.strip()
			trans_html = build_structured_lyrics_html(
				title, artist, trans_lyrics, trans_meta, trans_summary, trans_tracklist
			)
			trans_plain = build_structured_lyrics_plain(
				title, artist, trans_lyrics, trans_meta, trans_summary, trans_tracklist
			)
			wx.CallAfter(self.update_lyrics_text, trans_html, trans_plain)

		threading.Thread(target=translate_worker, daemon=True).start()

	def _translation_failed(self, error):
		self._translating = False
		if not self._closed:
			self.translate_button.Enable()
			self.profound_button.Enable()
		handle_error(error)

	def update_lyrics_text(self, trans_html, trans_plain):
		self._translating = False
		self._is_translated = True
		if self._closed:
			return
		self.translate_button.Enable()
		self.profound_button.Enable()
		self.current_html = trans_html
		self.current_plain = trans_plain
		self.full_text = trans_plain
		self.lyrics_ctrl.SetValue(self.current_plain)
		self.lyrics_ctrl.SetInsertionPoint(0)
		self.SetTitle(f"{self.song_title} - {self.artist} ({_('Translated')})")
		self.back_button.Show()
		self.panel.Layout()
		self.Layout()
		self.lyrics_ctrl.SetFocus()
		ui.message(_("Translation completed."))

	def on_key_down(self, event):
		key = event.GetKeyCode()
		ctrl_down = event.ControlDown()
		alt_down = event.AltDown()
		if (ctrl_down and not alt_down and key in (ord('W'), ord('w'))) or (
			alt_down and not ctrl_down and key == wx.WXK_F4
		):
			self.on_close(event)
			return
		if key == wx.WXK_WINDOWS_MENU or (
			key == wx.WXK_F10 and event.ShiftDown()
		):
			self.on_context_menu(event)
			return
		if key == wx.WXK_ESCAPE:
			# Do not close on Escape key
			return
		if (alt_down and key in (ord('H'), ord('h'), ord('B'), ord('b'))) or (ctrl_down and key in (ord('H'), ord('h'))):
			self.on_browse_html(event)
			return
		event.Skip()

	def on_copy(self, event=None):
		try:
			api.copyToClip(self.current_plain)
			ui.message(_("Copied to clipboard."))
		except Exception as e:
			handle_error(f"Failed to copy lyrics: {str(e)}")

	def on_close(self, event=None):
		if self._closed:
			return
		self._closed = True
		try:
			if self._artist_dialog:
				self._artist_dialog.Destroy()
		except Exception:
			pass
		try:
			if self._result_dialog:
				self._result_dialog.Destroy()
		except Exception:
			pass
		try:
			gui.mainFrame.postPopup()
		except Exception:
			pass
		self.Destroy()
