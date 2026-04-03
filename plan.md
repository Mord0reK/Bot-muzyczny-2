# Plan Projektowania Bota Muzycznego Discord

## Opis

Bot Discord do odtwarzania muzyki z YouTube, radia internetowego oraz konwertowania utworów ze Spotify na YouTube. Wszystkie komendy wykorzystują slash commands (`/`) z autocomplete.

---

## Struktura Projektu

```
Bot-muzyczny-2/
├── main.py                          # Entry point — inicjalizacja bota, ładowanie cogów
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── plan.md                          # Ten plik
│
├── config/
│   ├── __init__.py
│   └── settings.py                  # Stałe, ścieżki, konfiguracja bota
│
├── cogs/
│   ├── music/
│   │   ├── __init__.py
│   │   ├── player.py                # MusicPlayer — połączenie głosowe, kolejka, odtwarzanie
│   │   ├── youtube.py               # yt-dlp: wyszukiwanie, stream URL, metadane
│   │   └── commands.py              # /play, /skip, /queue, /pause, /resume, /stop, /loop, /volume, /shuffle
│   │
│   ├── radio/
│   │   ├── __init__.py
│   │   ├── stations.py              # Pobieranie stacji z https://api.radyjko.mordorek.dev/stations
│   │   └── commands.py              # /radio, /radio_list, /radio_favorite
│   │
│   ├── search/
│   │   ├── __init__.py
│   │   ├── cross_platform.py        # Spotify URL → parse → YouTube search
│   │   └── commands.py              # /spotify, /search
│   │
│   └── utility/
│       ├── __init__.py
│       ├── embeds.py                # Fabryka embedów (play, queue, error, now_playing)
│       ├── decorators.py            # @require_voice, @require_playing
│       └── commands.py              # /help, /ping, /now_playing
│
├── utils/
│   ├── __init__.py
│   ├── queue.py                     # TrackQueue — add, remove, skip, shuffle, loop, next
│   ├── audio_utils.py               # FFmpeg options, format validation
│   ├── api_client.py                # aiohttp client dla zewnętrznych API
│   ├── json_store.py                # Thread-safe JSON read/write
│   └── env_detector.py              # Wykrywanie VPS/Datacenter + walidacja cookies
│
└── data/
    ├── settings.json                # Ustawienia per guild (głośność, domyślny kanał)
    ├── favorites.json               # Ulubione stacje radiowe
    └── history.json                 # Historia odtwarzania
```

---

## Szczegółowy Opis Modułów

### 1. `main.py` — Główny skrypt bota

- Inicjalizacja `discord.ext.commands.Bot` z `intents`
- Ładowanie zmiennych środowiskowych (`python-dotenv`)
- Ładowanie wszystkich cogów z folderu `cogs/`
- Eventy:
  - `on_ready` — logowanie, rejestracja komend, sprawdzenie środowiska (VPS/datacenter)
  - `on_voice_state_update` — auto-opuszczenie kanału gdy pusty
- Przy starcie: uruchomienie `env_detector.check()` — jeśli VPS/datacenter i brak pliku cookies → ostrzeżenie w konsoli

### 2. `config/settings.py`

```python
# Stałe
BOT_PREFIX = "/"
COGS_FOLDER = "cogs"
DATA_FOLDER = "data"

# Ścieżki do plików JSON
SETTINGS_FILE = "data/settings.json"
FAVORITES_FILE = "data/favorites.json"
HISTORY_FILE = "data/history.json"

# API
RADIO_API_URL = "https://api.radyjko.mordorek.dev/stations"
RADIO_API_TIMEOUT = 10

# yt-dlp
YTDLP_FORMAT = "bestaudio/best"
YTDLP_MAX_DURATION = 7200  # 2 godziny max
```

### 3. `cogs/music/youtube.py`

**Odpowiedzialność:** Wyszukiwanie i pobieranie strumienia z YouTube przez `yt-dlp`.

**Funkcje:**
- `search_youtube(query, limit=10)` — zwraca listę dict `{title, url, duration, thumbnail, uploader}`
- `get_stream_url(url, cookies_file=None)` — zwraca bezpośredni URL strumienia audio
- `get_video_info(url)` — metadane pojedynczego filmu
- `extract_search_results(query)` — parsuje wyniki wyszukiwania yt-dlp

**Obsługa cookies:**
- Jeśli podano `cookies_file` (ścieżka do pliku cookies.txt/netscape) → yt-dlp użyje go do autoryzacji
- Jeśli nie podano i środowisko wykryte jako VPS/datacenter → rzuca wyjątek z komunikatem o konieczności dodania pliku cookies

### 4. `cogs/music/player.py`

**Odpowiedzialność:** Zarządzanie odtwarzaczem muzycznym.

**Klasa `MusicPlayer`:**
- `connect(channel)` — łączy z VoiceChannel
- `disconnect()` — rozłącza
- `play(track)` — odtwarza utwór (yt-dlp stream → FFmpeg → discord.PCMVolumeTransformer)
- `pause()`, `resume()`, `stop()` — kontrola
- `skip()` — przechodzi do następnego
- `set_volume(value)` — 0-200
- `set_loop(mode)` — off / track / queue
- `is_playing`, `is_paused`, `current_track`, `queue` — właściwości

**Eventy:**
- `after_play` — automatycznie odtwarza następny z kolejki
- `on_queue_empty` — opcjonalne opuszczenie kanału po timeout

### 5. `cogs/music/commands.py`

**Komendy slash:**

| Komenda | Parametry | Autocomplete | Opis |
|---------|-----------|-------------|------|
| `/play` | `query: str` | YouTube search suggestions | Szuka na YouTube i odtwarza |
| `/skip` | — | — | Następny utwór |
| `/queue` | — | — | Wyświetla kolejkę |
| `/pause` | — | — | Pauzuje |
| `/resume` | — | — | Wznawia |
| `/stop` | — | — | Zatrzymuje i czyści kolejkę |
| `/loop` | `mode: str` | off/track/queue | Ustawia pętlę |
| `/volume` | `value: int` | — | Głośność 0-200 |
| `/shuffle` | — | — | Tasuje kolejkę |

**Autocomplete dla `/play`:**
- Pobiera top 10 wyników z `youtube.search_youtube()`
- Zwraca `discord.app_commands.Choice(name=f"{title} ({duration})", value=url)`

### 6. `cogs/radio/stations.py`

**Odpowiedzialność:** Komunikacja z API stacji radiowych.

**Endpoint:** `https://api.radyjko.mordorek.dev/stations`

**Funkcje:**
- `get_all_stations()` — pobiera pełną listę stacji (cache w pamięci)
- `search_stations(query)` — filtruje po nazwie (case-insensitive)
- `get_station_by_id(station_id)` — zwraca pojedynczą stację
- `get_station_stream_url(station)` — zwraca URL strumienia audio

**Struktura odpowiedzi API (zakładana):**
```json
{
  "stations": [
    {
      "id": "...",
      "name": "Nazwa stacji",
      "stream_url": "https://...",
      "genre": "...",
      "description": "...",
      "logo": "https://..."
    }
  ]
}
```

### 7. `cogs/radio/commands.py`

| Komenda | Parametry | Autocomplete | Opis |
|---------|-----------|-------------|------|
| `/radio` | `station: str` | Nazwy stacji z API | Odtwarza wybraną stację |
| `/radio_list` | — | — | Lista wszystkich stacji |
| `/radio_favorite` | — | — | Ulubione stacje (zapis w favorites.json) |

**Autocomplete dla `/radio`:**
- Pobiera nazwy stacji z `stations.search_stations()`
- Limit 25 wyników (limit Discorda)

### 8. `cogs/search/cross_platform.py`

**Odpowiedzialność:** Konwersja Spotify → YouTube.

**Funkcje:**
- `parse_spotify_url(url)` — parsuje URL Spotify, wyciąga typ (track/playlist/album) i ID
  - Format: `https://open.spotify.com/track/<id>`
- `build_search_query(track_name, artist)` — tworzy query `"track_name artist"`
- `spotify_to_youtube(url)` — pełny flow: parse → build query → search YouTube → zwraca najlepszy match

**Flow dla `/spotify`:**
1. Użytkownik podaje URL Spotify lub `nazwa utworu - artysta`
2. Jeśli URL → parsuj ID, zbuduj query
3. Jeśli tekst → użyj bezpośrednio jako query
4. Szukaj na YouTube przez `youtube.search_youtube()`
5. Zwróć najlepszy wynik do odtworzenia

### 9. `cogs/search/commands.py`

| Komenda | Parametry | Autocomplete | Opis |
|---------|-----------|-------------|------|
| `/spotify` | `query: str` | — | Konwertuje Spotify → YouTube i odtwarza |
| `/search` | `query: str` | YouTube suggestions | Szuka bez odtwarzania |

### 10. `cogs/utility/`

**`embeds.py`** — fabryka embedów:
- `now_playing_embed(track, requester)`
- `queue_embed(queue, page)`
- `error_embed(message)`
- `search_results_embed(results)`
- `radio_list_embed(stations)`
- `help_embed()`

**`decorators.py`**:
- `@require_voice_channel` — sprawdza czy użytkownik jest na kanale głosowym
- `@require_playing` — sprawdza czy bot aktualnie odtwarza
- `@require_same_channel` — sprawdza czy użytkownik i bot są na tym samym kanale

**`commands.py`**:
- `/help` — lista komend z opisami
- `/ping` — opóźnienie bota
- `/now_playing` — aktualnie odtwarzany utwór

### 11. `utils/queue.py`

**Klasa `TrackQueue`:**
- `add(track)` — dodaje na koniec
- `remove(index)` — usuwa po indeksie
- `next()` — zwraca i usuwa pierwszy element
- `peek()` — zwraca pierwszy bez usuwania
- `shuffle()` — tasuje
- `clear()` — czyści
- `is_empty`, `size`, `tracks` — właściwości
- `loop_mode` — off / track / queue
- `position` — aktualna pozycja w kolejce

### 12. `utils/json_store.py`

**Odpowiedzialność:** Bezpieczne operacje na plikach JSON.

**Funkcje:**
- `read_json(path, default=None)` — odczyt z obsługą błędów
- `write_json(path, data)` — zapis atomowy (write → rename)
- `async_read_json(path)` / `async_write_json(path)` — async wersje (via `asyncio.to_thread`)

### 13. `utils/env_detector.py` — Wykrywanie VPS/Datacenter

**Odpowiedzialność:** Detekcja środowiska uruchomieniowego i walidacja cookies.

**Metody detekcji:**

1. **Sprawdzenie IP przez API zewnętrzne:**
   - Zapytanie do `https://ipinfo.io/json` lub `https://api.ipify.org?format=json`
   - Sprawdzenie pola `org` / `asn` — jeśli zawiera słowa: `hosting`, `datacenter`, `cloud`, `vps`, `ovh`, `hetzner`, `aws`, `azure`, `digitalocean`, `google cloud` → środowisko serwerowe

2. **Sprawdzenie hostname:**
   - Hostname zawiera: `vps`, `server`, `cloud`, `instance`, `droplet`

3. **Sprawdzenie pliku `/proc/cpuinfo` lub `systemd-detect-virt`:**
   - Obecność flag wirtualizacji

**Flow walidacji:**
```
START
  │
  ├─ Czy środowisko = VPS/Datacenter?
  │    │
  │    ├─ TAK → Czy plik cookies istnieje i jest poprawny?
  │    │         │
  │    │         ├─ TAK → OK, YouTube będzie działać
  │    │         │
  │    │         └─ NIE → ❌ BŁĄD: Poinformuj użytkownika
  │    │                    "Wykryto środowisko serwerowe (VPS/Datacenter).
  │    │                     YouTube blokuje zapytania z serwerów.
  │    │                     Aby korzystać z funkcji YouTube, umieść plik
  │    │                     cookies.txt w folderze data/ i ustaw
  │    │                     YOUTUBE_COOKIES_PATH w .env.
  │    │                     Jak wyeksportować cookies: https://..."
  │    │
  │    └─ NIE → OK, YouTube powinien działać bez cookies
  │
END
```

**Konfiguracja w `.env`:**
```env
YOUTUBE_COOKIES_PATH=data/cookies.txt
```

**Jak wyeksportować cookies (instrukcja dla użytkownika):**
1. Zainstaluj rozszerzenie przeglądarki "Get cookies.txt LOCALLY"
2. Wejdź na YouTube.com i zaloguj się
3. Wyeksportuj cookies do pliku `cookies.txt`
4. Umieść plik w folderze `data/` bota

### 14. `utils/audio_utils.py`

- `get_ffmpeg_options(url, cookies_file=None)` — generuje opcje dla FFmpeg
- `validate_audio_url(url)` — sprawdza czy URL prowadzi do strumienia audio
- `format_duration(seconds)` — formatuje sekundy na `MM:SS` lub `HH:MM:SS`

### 15. `utils/api_client.py`

**Klasa `APIClient`:**
- Singleton z `aiohttp.ClientSession`
- `get(url, params=None, timeout=10)` — GET request
- `post(url, data=None, timeout=10)` — POST request
- Obsługa retry (3 próby z exponential backoff)

---

## Komendy — Podsumowanie

### Music (`/`)
| Komenda | Autocomplete | Opis |
|---------|-------------|------|
| `/play <query>` | YouTube search | Szuka i odtwarza z YouTube |
| `/skip` | — | Następny utwór |
| `/queue` | — | Wyświetla kolejkę |
| `/pause` | — | Pauzuje odtwarzanie |
| `/resume` | — | Wznawia odtwarzanie |
| `/stop` | — | Zatrzymuje i czyści |
| `/loop <mode>` | off/track/queue | Ustawia pętlę |
| `/volume <0-200>` | — | Ustawia głośność |
| `/shuffle` | — | Tasuje kolejkę |

### Radio
| Komenda | Autocomplete | Opis |
|---------|-------------|------|
| `/radio <station>` | Nazwy z API | Odtwarza stację radiową |
| `/radio_list` | — | Lista wszystkich stacji |
| `/radio_favorite` | — | Ulubione stacje |

### Search
| Komenda | Autocomplete | Opis |
|---------|-------------|------|
| `/spotify <query>` | — | Spotify → YouTube → odtwórz |
| `/search <query>` | YouTube search | Szuka bez odtwarzania |

### Utility
| Komenda | Autocomplete | Opis |
|---------|-------------|------|
| `/help` | — | Lista komend |
| `/ping` | — | Opóźnienie bota |
| `/now_playing` | — | Aktualny utwór |

---

## Zależności

### `requirements.txt`
```
discord.py[voice]==2.3.2
PyNaCl==1.5.0
yt-dlp
python-dotenv==1.0.0
aiohttp>=3.9.0
```

### Systemowe (Dockerfile)
- `ffmpeg` — konwersja audio
- `libopus0` — kodek Opus dla Discorda

---

## Zmienne środowiskowe (`.env`)

```env
# Wymagane
DISCORD_TOKEN=twoj_token_bota_tutaj

# Opcjonalne
YOUTUBE_COOKIES_PATH=data/cookies.txt   # Wymagane na VPS/Datacenter
ENVIRONMENT=development                  # development / production
```

---

## Flow Uruchomienia

```
1. main.py start
   │
   ├─ Load .env
   ├─ Create Bot instance
   ├─ env_detector.check()
   │    ├─ Wykryj środowisko
   │    └─ Jeśli VPS + brak cookies → WARNING w konsoli
   ├─ Load cogs (cogs/*/*.py)
   ├─ Setup slash commands
   └─ Bot.login()
        │
        └─ on_ready
             ├─ Sync commands
             ├─ Load JSON data files
             └─ Bot ready!
```

---

## Flow Odtwarzania YouTube

```
/play "Never Gonna Give You Up"
   │
   ├─ Autocomplete: search_youtube("Never Gonna...") → sugestie
   │
   ├─ env_detector.is_server_environment()
   │    ├─ TAK → Sprawdź cookies_file → Jeśli brak → BŁĄD
   │    └─ NIE → Kontynuuj
   │
   ├─ youtube.search_youtube(query) → najlepszy wynik
   ├─ queue.add(track)
   ├─ player.play(track)
   │    ├─ youtube.get_stream_url(url, cookies_file)
   │    ├─ discord.VoiceClient.play(FFmpegPCMAudio)
   │    └─ after_play → queue.next() → play(next)
   │
   └─ Embed: "Teraz odtwarzano: Never Gonna Give You Up"
```

---

## Flow Odtwarzania Radia

```
/radio "RMF FM"
   │
   ├─ Autocomplete: stations.search_stations("RMF FM") → sugestie
   │
   ├─ stations.get_station_by_name("RMF FM")
   ├─ player.play_radio(station.stream_url)
   │    ├─ discord.VoiceClient.play(FFmpegPCMAudio(stream_url))
   │    └─ after_play → NIE przechodzi do kolejki (radio = ciągłe)
   │
   └─ Embed: "Teraz odtwarzano: RMF FM"
```

---

## Flow Spotify → YouTube

```
/spotify "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
   │
   ├─ cross_platform.parse_spotify_url(url)
   │    └─ Typ: track, ID: 4cOdK2wGLETKBW3PvgPWqT
   │
   ├─ cross_platform.build_search_query(...)
   │    └─ "Rick Astley - Never Gonna Give You Up"
   │
   ├─ youtube.search_youtube(query) → najlepszy match
   ├─ queue.add(track)
   ├─ player.play(track)
   └─ Embed: "Znaleziono na YouTube: Never Gonna Give You Up"
```

---

## Kroki Implementacji (zalecana kolejność)

| Krok | Moduł | Opis |
|------|-------|------|
| 1 | `config/`, `.env` | Konfiguracja i stałe |
| 2 | `utils/json_store.py`, `utils/api_client.py` | Narzędzia bazowe |
| 3 | `utils/env_detector.py` | Detekcja VPS + walidacja cookies |
| 4 | `utils/queue.py`, `utils/audio_utils.py` | Kolejka i audio |
| 5 | `cogs/utility/embeds.py`, `decorators.py` | Embedy i dekoratory |
| 6 | `cogs/music/youtube.py` | Integracja z YouTube (yt-dlp) |
| 7 | `cogs/music/player.py` | Odtwarzacz |
| 8 | `cogs/music/commands.py` | Komendy muzyczne z autocomplete |
| 9 | `cogs/radio/stations.py` | Integracja z API radyjko |
| 10 | `cogs/radio/commands.py` | Komendy radiowe z autocomplete |
| 11 | `cogs/search/cross_platform.py` | Spotify → YouTube converter |
| 12 | `cogs/search/commands.py` | Komendy search |
| 13 | `cogs/utility/commands.py` | /help, /ping, /now_playing |
| 14 | `main.py` | Integracja wszystkiego |
| 15 | `data/*.json` | Pliki danych (puste szablony) |
| 16 | Testy i Docker | Weryfikacja w kontenerze |
