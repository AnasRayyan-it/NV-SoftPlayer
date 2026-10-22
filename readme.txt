================================================================================
NV-SoftPlayer - Comprehensive Add-on User Guide & Reference
Author: Anas Rayyan
Add-on Name: NV-SoftPlayer
================================================================================

NV-SoftPlayer is a full-featured, accessible media player, YouTube streaming &
download suite, lyrics finder, and AI music assistant designed specifically for
NVDA (NonVisual Desktop Access) screen reader users.

It delivers seamless audio playback that never interferes with NVDA's speech
volume, robust YouTube streaming & downloading directly inside the add-on,
multi-lingual lyrics with standard and profound poetic translation, artist
biographies, and instant track duration announcements.


--------------------------------------------------------------------------------
TABLE OF CONTENTS
--------------------------------------------------------------------------------
1. Key Features Overview
2. Global Keyboard Shortcuts
3. Audio Player Window & Controls
4. YouTube Player & Downloader
5. Lyrics Fetcher & AI Music Assistant
6. Audio File Duration Announcement
7. Add-on Settings & AI Configuration
8. Supported Formats & Internal Architecture
9. Tips & Troubleshooting


--------------------------------------------------------------------------------
1. KEY FEATURES OVERVIEW
--------------------------------------------------------------------------------
* Independent Volume Architecture: Player audio runs out-of-process, ensuring
  adjusting player volume never affects NVDA speech synthesizer volume.
* Local Playback: Play single audio files, multiple selected tracks, entire
  folders, or multiple folders at once.
* YouTube Integration: Search YouTube directly from NVDA. Stream audio or
  video inside the add-on, queue multiple results, or download tracks.
* Playlist Auto-Detection: Pasting a YouTube playlist URL presents an instant
  dialog to Play as Audio, Play as Video, Download as MP3, or Download as MP4.
* Dedicated Music Folder: Downloads are automatically saved directly into
  "Music\NV-SoftPlayer", created once and reused without repetitive dialogs.
* Lyrics & Song Metadata: Searches LRCLIB with intelligent query cleaning and
  Arabic normalization.
* AI Music Assistant (Groq & Gemini): Fetches artist history, album tracklists,
  song meaning, latest artist news, and an interactive music Q&A box.
* Dual Translation Modes: Standard translation into 30+ languages, plus
  "Profound Translation" for poetic, metaphorical, and emotional nuances.
* Context-Menu Selection Translation: Select any line or phrase of lyrics and
  translate it instantly via the context menu.
* Instant File Duration Announcement: Press NVDA+Ctrl+L on any audio file in
  File Explorer or on the Desktop to hear its exact duration.
* Soft Audio Ducking on Seek: Smoothly ducks volume when rewinding or fast-
  forwarding, restoring it smoothly without audio clipping or harsh clicks.


--------------------------------------------------------------------------------
2. GLOBAL KEYBOARD SHORTCUTS
--------------------------------------------------------------------------------
The following shortcuts can be pressed anywhere in Windows:

Shortcut                   Action
-------------------------  -----------------------------------------------------
NVDA + Control + 1         Play the focused audio file in NV-SoftPlayer.
NVDA + Shift + Control + 1 Play all selected audio files as a playlist queue.
NVDA + Control + 2         Play all audio files inside the focused folder.
NVDA + Shift + Control + 2 Play all audio files from all selected folders.
NVDA + Control + 3         Search lyrics for the focused audio file in Explorer.
NVDA + Control + Shift + 3 Open Manual Lyrics Search to type a song or artist.
NVDA + Control + 4         Open YouTube Search, Streaming & Download dialog.
NVDA + Control + L         Announce the duration (length) of the focused file
                           (or the currently playing track).


--------------------------------------------------------------------------------
3. AUDIO PLAYER WINDOW & CONTROLS
--------------------------------------------------------------------------------
When playing local tracks or YouTube queues, the NV-SoftPlayer window opens.
All player functions can be operated using quick, single-key shortcuts:

Key                        Action
-------------------------  -----------------------------------------------------
Space                      Play / Pause playback.
Z                          Previous track in queue.
V                          Next track in queue.
X                          Replay current track from the beginning.
C                          Stop playback.
Left Arrow                 Rewind 5 seconds (with smooth audio ducking).
Right Arrow                Fast-forward 5 seconds (with smooth audio ducking).
Up Arrow                   Increase player volume by 5% (does not alter NVDA).
Down Arrow                 Decrease player volume by 5% (down to 0% smoothly).
M                          Toggle Mute / Unmute.
R                          Toggle Repeat (track / playlist mode for current session).
Ctrl + R                   Toggle Repeat and save preference as default.
S                          Toggle Shuffle (current session).
Ctrl + S                   Toggle Shuffle and save preference as default.
T                          Announce current track title and total duration.
H                          Announce the list of keyboard shortcuts.
Applications / Shift+F10   Open the Player Context Menu with all controls.
Ctrl + W or Alt + F4       Close the player window and stop playback.

Note on Volume:
Player volume is strictly separated from NVDA speech and is permanently
remembered across tracks, videos, and sessions. Even when set to 0% or muted,
your screen reader speech continues at full volume.


--------------------------------------------------------------------------------
4. YOUTUBE PLAYER & DOWNLOADER
--------------------------------------------------------------------------------
Press NVDA + Control + 4 to open the YouTube dialog. You can type keywords
(e.g., song title, artist) or paste a direct YouTube video or playlist link.

YouTube Dialog Controls & Shortcuts:
* Search Box: Type your search or paste a URL and press Enter.
* Result List: Navigate search results with Up/Down Arrow keys.
* Alt + A: Play selected item as audio inside the add-on.
* Alt + V: Play selected item as video inside the add-on.
* Play as queue: Load all search results into the player queue.
* Download MP3: Downloads the audio and converts it to MP3 with high quality.
* Download MP4: Downloads the video with audio in MP4 format.
* Double-Click / Enter on a result: Plays audio immediately.
* Escape: Closes the YouTube dialog.

Automatic Download Destination:
Downloads are automatically saved to your Windows "Music\NV-SoftPlayer" folder.
The add-on creates this folder once if it does not already exist, and saves all
future downloads directly without opening folder selection dialogs.

YouTube Playlist Auto-Detection:
When you paste a YouTube playlist URL and press Enter, NV-SoftPlayer detects the
playlist and displays the "YouTube Playlist" window with 4 buttons:
  1. Play as audio      - Streams all tracks sequentially as an audio queue.
  2. Play as video      - Streams the playlist with video inside the player.
  3. Download as MP3    - Downloads all playlist tracks as MP3s to your folder.
  4. Download as MP4    - Downloads all playlist tracks as MP4s to your folder.
  (Plus Cancel / Escape)


--------------------------------------------------------------------------------
5. LYRICS FETCHER & AI MUSIC ASSISTANT
--------------------------------------------------------------------------------
Press NVDA + Control + 3 on an audio file, or NVDA + Control + Shift + 3 to type
a title manually. The lyrics are fetched from LRCLIB and presented in an
accessible dialog.

Features in the Lyrics Dialog:
1. Lyrics Viewer: Multiline, accessible read-only text view with full lyrics.
2. AI Song Information (Groq / Gemini):
   - Singer / Artist name
   - Lyrics writer / composer
   - Album name & release year
   - Music producer / record label
   - Meaning and story behind the song
   - Full album tracklist
3. Translation Modes:
   - "Translate Lyrics": Standard grammatical translation into your chosen
     language (Arabic, English, French, Spanish, German, etc.).
   - "Profound Translation": In-depth literary translation that preserves
     poetic imagery, cultural metaphors, rhyme intent, and emotional weight.
4. Selection Context Menu:
   - Select any specific line or stanza with Shift + Arrow keys, then press
     the Applications key or Shift + F10.
   - Choose "Translate selection" or "Profound translation of selection" to
     analyze just that phrase without re-translating the whole song.
5. Interactive Q&A Box:
   - Type any question about the song, artist, instruments, or lyrics in the
     question text box and press Enter (or click "Ask").
6. Artist Details:
   - Generates an in-depth biography, discography highlights, and musical style.
7. Latest Artist News:
   - Generates an AI summary of recent announcements, albums, and tours.
8. Copy Text:
   - Copies all current text to the Windows Clipboard with one click.


--------------------------------------------------------------------------------
6. AUDIO FILE DURATION ANNOUNCEMENT
--------------------------------------------------------------------------------
Shortcut: NVDA + Control + L

How it works:
1. Focus any audio file in File Explorer or on your Desktop (you do not even
   need to press Space to select it).
2. Press NVDA + Control + L.
3. NVDA immediately announces:
   "Reading length of [Title]" followed by "[Title], MM:SS" (e.g. "03:18").
4. If NV-SoftPlayer is currently open, pressing NVDA + Control + L announces the
   duration of the track currently playing in the add-on.

Technologies used:
Duration is extracted via sub-30ms bundled FFmpeg header inspection, Windows
Shell namespace metadata parsing (with Unicode directional-marker sanitization),
and Windows Media Player fallbacks.


--------------------------------------------------------------------------------
7. ADD-ON SETTINGS & AI CONFIGURATION
--------------------------------------------------------------------------------
To configure NV-SoftPlayer settings:
1. Open the NVDA Menu (NVDA + N).
2. Navigate to Preferences -> Settings.
3. Select "NV-SoftPlayer" from the categories list.

Configurable Options:
* AI Provider:
  - Groq (recommended, fast & free)
  - Google Gemini
* Groq API Key:
  - Paste your free Groq API key here (get one free at https://console.groq.com/keys).
* Gemini API Key:
  - Paste your Gemini API key here (get one at https://aistudio.google.com/apikey).
* Words to ignore during search:
  - Clean query filter that removes noise words like "remastered", "live",
    "official video", "lyrics", "feat", "4k", etc.
* Preferred translation languages:
  - Comma-separated list (e.g. "Arabic, English, French"). The first language
    is used as the default for instant translations.
* Repeat on by default:
  - Checkbox to enable track/playlist repeat automatically.
* Shuffle on by default:
  - Checkbox to shuffle queues automatically upon playback.

Note:
Lyrics lookup (LRCLIB), audio playback, duration reading, and YouTube playback
and downloading work completely free without any API keys. An API key is only
needed for AI translation, metadata analysis, and artist Q&A.


--------------------------------------------------------------------------------
8. SUPPORTED FORMATS & ARCHITECTURE
--------------------------------------------------------------------------------
Supported Audio Formats:
.mp3, .wav, .flac, .m4a, .aac, .wma, .ogg, .opus, .mp4, .m4b, .aiff, .aif,
.ape, .wv, .mpc, .ac3.

Architecture Highlights:
* player_host.ps1: Background PowerShell STA host using WMPlayer.OCX to ensure
  complete audio volume isolation from the NVDA screen reader process.
* yt-dlp & FFmpeg: Bundled in the add-on bin directory for high-speed YouTube
  extraction and high-quality audio/video conversion.


--------------------------------------------------------------------------------
9. TIPS & TROUBLESHOOTING
--------------------------------------------------------------------------------
* To restart NVDA after installing or modifying add-ons: Press NVDA + Q, then
  press Enter.
* If YouTube playback reports yt-dlp needs updating, place the latest 64-bit
  yt-dlp.exe in the add-on's "globalPlugins\NV-SoftPlayer\bin" directory.
* For keyboard shortcuts inside the player, press H anytime to hear NVDA read
  the available keys.
* All dialogs support standard navigation (Tab to cycle controls, Alt + underlined letter for shortcuts).
  To prevent accidental loss of progress, dialogs and player windows cannot be closed by pressing Escape alone;
  use Control + W or Alt + F4 to close.
================================================================================
