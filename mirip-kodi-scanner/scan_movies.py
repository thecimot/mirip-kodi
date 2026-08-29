#!/usr/bin/env python3
"""
MIT License

Copyright (c) 2026 Hartono

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO REGARDING THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import os
import re
import json
import time
import shutil
import urllib.parse
import urllib.request
import urllib.error
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image, ImageFilter, ImageOps

# Import modul penerjemah
try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False


# ============================================================
# COLOR CODES (ANSI)
# ============================================================
COLOR_RESET = "\033[0m"
COLOR_SUCCESS = "\033[94m"   # Biru
COLOR_ERROR = "\033[91m"     # Merah
COLOR_WARNING = "\033[93m"   # Kuning
COLOR_INFO = "\033[96m"      # Cyan / Biru Muda


# ============================================================
# LOAD DOTFILE (scan_movies.conf)
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / "scan_movies.conf" 

def load_env_file(env_path):
    """Membaca file konfigurasi tanpa ketergantungan paket eksternal."""
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip().strip("'\"")

load_env_file(ENV_FILE)

# ============================================================
# KONFIGURASI DARI DOTFILE / ENV
# ============================================================

MOVIES_DIR = Path(os.getenv("MOVIES_DIR", "/run/media/cimot/cimot/MOVIES"))
TV_DIR = Path(os.getenv("TV_DIR", "/run/media/cimot/cimot/TV SERIES"))

CACHE_FILE = SCRIPT_DIR / "tmdb_cache.json"
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "8"))

TMDB_READ_TOKEN = os.getenv("TMDB_READ_TOKEN", "").strip()
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()

PRIMARY_LANGUAGE = os.getenv("PRIMARY_LANGUAGE", "id-ID")
FALLBACK_LANGUAGE = os.getenv("FALLBACK_LANGUAGE", "en-US")
AUTO_TRANSLATE = os.getenv("AUTO_TRANSLATE", "true").lower() == "true"
POSTER_SIZE = os.getenv("POSTER_SIZE", "original")
LOGO_SIZE = os.getenv("LOGO_SIZE", "original")

SKIP_EXISTING = os.getenv("SKIP_EXISTING", "false").lower() == "true"
FORCE_RESCAN = os.getenv("FORCE_RESCAN", "true").lower() == "true"

# Thread Locks
print_lock = threading.Lock()
cache_lock = threading.Lock()


# ============================================================
# HELPER OUTPUT (THREAD-SAFE & COLORED)
# ============================================================

def line():
    with print_lock:
        print("=" * 70)

def print_msg(message):
    with print_lock:
        print(message)

def print_success(message):
    with print_lock:
        print(f"{COLOR_SUCCESS}{message}{COLOR_RESET}")

def print_error(message):
    with print_lock:
        print(f"{COLOR_ERROR}ERROR: {message}{COLOR_RESET}")

def print_warning(message):
    with print_lock:
        print(f"{COLOR_WARNING}WARNING: {message}{COLOR_RESET}")

def print_info(message):
    with print_lock:
        print(f"{COLOR_INFO}{message}{COLOR_RESET}")


# ============================================================
# HELPER TRANSLATION (SINGLE THREADED SAFE TRANSLATOR)
# ============================================================

def translate_text(text, target_lang_code):
    """Menerjemahkan teks via Google Translate."""
    if not text or not text.strip():
        return text

    if not HAS_TRANSLATOR:
        print_warning("  Modul 'deep_translator' tidak terpasang. Lewati terjemahan.")
        return text

    target_code = target_lang_code.split("-")[0].lower()

    try:
        translated = GoogleTranslator(source='auto', target=target_code).translate(text)
        
        if not translated or "Error 500" in translated or "That’s an error" in translated or "<html" in translated.lower():
            print_warning("  Google Translate membatasi akses (Rate Limit).")
            return text
            
        return translated

    except Exception as e:
        print_warning(f"  Gagal menerjemahkan ({e}). Menggunakan sinopsis asli.")
        return text


# ============================================================
# DISK CACHING MECHANISM
# ============================================================

def load_disk_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print_warning(f"Gagal membaca disk cache ({e}), membuat cache baru.")
    return {}


def save_disk_cache(cache_data):
    with cache_lock:
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print_warning(f"Gagal menyimpan disk cache: {e}")


DISK_CACHE = load_disk_cache()


def get_from_cache(key):
    with cache_lock:
        return DISK_CACHE.get(key)


def set_to_cache(key, value):
    with cache_lock:
        DISK_CACHE[key] = value
    save_disk_cache(DISK_CACHE)


# ============================================================
# IMAGE PROCESSING
# ============================================================

def process_poster(file_path):
    try:
        with Image.open(file_path) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")

            target_path = file_path.parent / "poster.webp"
            img.save(target_path, "WEBP", quality=95, method=6)

            if file_path != target_path and file_path.exists():
                file_path.unlink()

        return True
    except Exception as error:
        print_error(f"Gagal memproses poster {file_path.name}: {error}")
        return False


def process_clearlogo(file_path):
    try:
        with Image.open(file_path) as img:
            img = ImageOps.exif_transpose(img)

            if img.mode != "RGBA":
                img = img.convert("RGBA")

            clean_img = img.copy()
            width, height = clean_img.size
            if width > 3000 or height > 3000:
                new_size = (width // 2, height // 2)
                clean_img = clean_img.resize(new_size, Image.Resampling.LANCZOS)

            pixels = clean_img.load()
            total_r, total_g, total_b, count = 0, 0, 0, 0

            for y in range(clean_img.height):
                for x in range(clean_img.width):
                    r, g, b, a = pixels[x, y]
                    if a > 30:
                        total_r += r
                        total_g += g
                        total_b += b
                        count += 1

            if count > 0:
                avg_brightness = (0.299 * (total_r / count) + 
                                  0.587 * (total_g / count) + 
                                  0.114 * (total_b / count))

                if avg_brightness < 80:
                    for y in range(clean_img.height):
                        for x in range(clean_img.width):
                            r, g, b, a = pixels[x, y]
                            if a > 20:
                                pixels[x, y] = (255, 255, 255, a)

            sharpened_img = clean_img.filter(ImageFilter.SHARPEN)
            target_path = file_path.parent / "clearlogo.png"
            sharpened_img.save(target_path, "PNG", optimize=True)

            if file_path != target_path and file_path.exists():
                file_path.unlink()

        return True
    except Exception as error:
        print_error(f"Gagal memproses logo {file_path.name}: {error}")
        return False


# ============================================================
# TMDB REQUEST WITH RETRY
# ============================================================

def tmdb_request(endpoint, params=None, language=None, retries=4, backoff_factor=1.5):
    if params is None:
        params = {}

    if language:
        params["language"] = language

    headers = {
        "Accept": "application/json",
        "User-Agent": "MovieLibraryScanner/1.0",
    }

    if TMDB_READ_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_READ_TOKEN}"
    elif TMDB_API_KEY:
        params["api_key"] = TMDB_API_KEY
    else:
        print_error("TMDB_READ_TOKEN atau TMDB_API_KEY belum diatur di scan_movies.conf")
        return None

    query = urllib.parse.urlencode(params)
    url = f"https://api.themoviedb.org/3{endpoint}"
    if query:
        url += f"?{query}"

    for attempt in range(retries):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            if err.code == 429:
                retry_after = err.headers.get("Retry-After")
                sleep_time = float(retry_after) if retry_after else (backoff_factor ** attempt) + 1
                print_warning(f"TMDB Rate limit terdeteksi (429). Menunggu {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            elif err.code in [500, 502, 503, 504]:
                sleep_time = (backoff_factor ** attempt)
                print_warning(f"TMDB Server Error ({err.code}). Retry {attempt + 1}/{retries} dalam {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            else:
                print_error(f"TMDB request HTTP error {err.code} ({endpoint})")
                return None
        except Exception as error:
            sleep_time = (backoff_factor ** attempt)
            print_warning(f"TMDB network error: {error}. Retry {attempt + 1}/{retries} dalam {sleep_time:.1f}s...")
            time.sleep(sleep_time)

    print_error(f"Gagal menghubungi TMDB setelah {retries} percobaan ({endpoint})")
    return None


def fetch_details_with_append(endpoint):
    params = {"append_to_response": "images", "include_image_language": "id,en,null"}
    
    details_id = tmdb_request(endpoint, params=params, language=PRIMARY_LANGUAGE)
    if not details_id:
        details_id = tmdb_request(endpoint, params=params, language=FALLBACK_LANGUAGE)

    if not details_id:
        return None

    raw_overview = details_id.get("overview", "").strip()
    
    # Jika sinopsis Indonesia kosong, ambil sinopsis Inggris & tandai butuh terjemahan
    if not raw_overview:
        details_en = tmdb_request(endpoint, params=params, language=FALLBACK_LANGUAGE)
        if details_en and details_en.get("overview"):
            en_text = details_en.get("overview", "").strip()
            details_id["overview"] = en_text
            details_id["needs_translation"] = True
            details_id["raw_en_overview"] = en_text
        else:
            details_id["needs_translation"] = False
    else:
        details_id["needs_translation"] = False

    return details_id


def download_file(url, destination):
    destination = Path(destination)
    if SKIP_EXISTING and destination.exists() and not FORCE_RESCAN:
        print_msg(f"      File {destination.name} sudah ada, dilewati.")
        return True

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "MovieLibraryScanner/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            with open(destination, "wb") as output:
                shutil.copyfileobj(response, output)
        return True
    except Exception as error:
        print_error(f"Gagal download {destination.name}: {error}")
        return False


# ============================================================
# ADVANCED REGEX CLEANING & LOGO EXTRACTOR
# ============================================================

SCENE_JUNK_REGEX = re.compile(
    r"\b("
    r"1080p|720p|2160p|4k|bluray|blu-ray|webrip|web-dl|web|hdrip|dvdrip|brrip|"
    r"x265|x264|h264|h265|hevc|av1|10bit|8bit|aac|ddp\d?|ac3|dts|truehd|atmos|flac|"
    r"galaxyrg\d*|yts|asimov|tgx|rarbg|eztv|e-sub|subbed|multi|complete|remux|hybrid|"
    r"dv|dovi|hdr10\+?|hdr|nf|amzn|hbo|dsnp|hulu|apple tv\+?"
    r")\b",
    re.IGNORECASE
)


def normalize_name(text):
    text = str(text)
    text = re.sub(r"[._]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_movie_info(folder_name):
    text = normalize_name(folder_name)
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    year = year_match.group(1) if year_match else None
    
    if year_match:
        title = text[:year_match.start()].strip()
    else:
        title = SCENE_JUNK_REGEX.split(text)[0]
    
    title = re.sub(r"[\(\[\{\)\]\}]", "", title).strip(" -_.")
    return title, year


def extract_season_number(text):
    match = re.search(r"\bS(\d{1,2})\b|\bSeason\s*(\d{1,2})\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1) or match.group(2))
    return None


def clean_tv_title(raw_name):
    text = normalize_name(raw_name)
    text = re.split(r"\b(S\d{1,2}|Season\s*\d{1,2})\b", text, flags=re.IGNORECASE)[0]
    text = re.sub(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", " ", text)
    text = SCENE_JUNK_REGEX.split(text)[0]
    return text.strip(" -_.")


def search_movie(title, year=None):
    cache_key = f"search_movie_{title}_{year}"
    cached = get_from_cache(cache_key)
    if cached:
        return cached

    print_msg(f"Mencari Movie '{title}' ({year or 'Tahun N/A'}) di TMDB...")
    endpoint = "/search/movie"
    params = {"query": title, "include_adult": "false"}
    if year:
        params["year"] = year

    res = tmdb_request(endpoint, params=params, language=PRIMARY_LANGUAGE)
    if not (res and res.get("results")):
        res = tmdb_request(endpoint, params=params, language=FALLBACK_LANGUAGE)

    if res and res.get("results"):
        result = res["results"][0]
        set_to_cache(cache_key, result)
        return result

    return None


def search_tv_show(title):
    cache_key = f"search_tv_{title}"
    cached = get_from_cache(cache_key)
    if cached:
        return cached

    print_msg(f"Mencari TV Show '{title}' di TMDB...")
    endpoint = "/search/tv"

    res = tmdb_request(endpoint, params={"query": title, "include_adult": "false"}, language=PRIMARY_LANGUAGE)
    if not (res and res.get("results")):
        res = tmdb_request(endpoint, params={"query": title, "include_adult": "false"}, language=FALLBACK_LANGUAGE)

    if res and res.get("results"):
        result = res["results"][0]
        set_to_cache(cache_key, result)
        return result

    return None


def extract_logo_from_details(details_json):
    if not details_json:
        return None
    images = details_json.get("images", {})
    logos = images.get("logos", [])
    if not logos:
        return None

    valid_logos = [l for l in logos if not l.get("file_path", "").lower().endswith(".svg")]
    if not valid_logos:
        return None

    for lang in ["id", "en", None]:
        matching = [l for l in valid_logos if l.get("iso_639_1") == lang]
        if matching:
            matching.sort(key=lambda x: x.get("width", 0), reverse=True)
            return matching[0].get("file_path")

    valid_logos.sort(key=lambda x: x.get("width", 0), reverse=True)
    return valid_logos[0].get("file_path")


# ============================================================
# MODULE 1: SCAN MOVIES
# ============================================================

def process_movie_folder(movie_folder):
    print_info(f"Processing Movie Folder: {movie_folder.name}")

    meta_file = movie_folder / "metadata.json"
    poster_file = movie_folder / "poster.webp"
    logo_file = movie_folder / "clearlogo.png"

    if SKIP_EXISTING and meta_file.exists() and poster_file.exists() and logo_file.exists() and not FORCE_RESCAN:
        print_msg(f"  [{movie_folder.name}] Status: Metadata & gambar lengkap, dilewati.")
        return

    clean_title, year = extract_movie_info(movie_folder.name)
    search_result = search_movie(clean_title, year)

    if not search_result:
        print_error(f"  Movie '{clean_title}' tidak ditemukan di TMDB.")
        return

    tmdb_id = search_result.get("id")
    
    detail_cache_key = f"movie_detail_{tmdb_id}"
    details = get_from_cache(detail_cache_key)
    if not details:
        details = fetch_details_with_append(f"/movie/{tmdb_id}")
        if details:
            details["folder_path"] = str(movie_folder)
            set_to_cache(detail_cache_key, details)

    if not details:
        print_error(f"  Gagal mengambil detail Movie ID {tmdb_id}")
        return

    genres = [g.get("name") for g in details.get("genres", [])]

    if not (SKIP_EXISTING and meta_file.exists() and not FORCE_RESCAN):
        metadata = {
            "tmdb_id": tmdb_id,
            "media_type": "movie",
            "title": details.get("title") or clean_title,
            "original_title": details.get("original_title"),
            "year": details.get("release_date", "")[:4] if details.get("release_date") else year,
            "release_date": details.get("release_date"),
            "vote_average": details.get("vote_average", 0),
            "genres": genres,
            "overview": details.get("overview", ""),
            "runtime": details.get("runtime"),
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)
        print_success(f"  [{movie_folder.name}] metadata.json dibuat.")

    if details.get("poster_path") and not (SKIP_EXISTING and poster_file.exists() and not FORCE_RESCAN):
        ext = Path(details['poster_path']).suffix or ".jpg"
        temp_poster_file = movie_folder / f"temp_poster{ext}"
        poster_url = f"https://image.tmdb.org/t/p/{POSTER_SIZE}{details['poster_path']}"
        if download_file(poster_url, temp_poster_file):
            if process_poster(temp_poster_file):
                print_success(f"  [{movie_folder.name}] poster.webp berhasil dibuat.")

    if not (SKIP_EXISTING and logo_file.exists() and not FORCE_RESCAN):
        logo_path = extract_logo_from_details(details)
        if logo_path:
            ext = Path(logo_path).suffix or ".png"
            temp_logo_file = movie_folder / f"temp_clearlogo{ext}"
            logo_url = f"https://image.tmdb.org/t/p/{LOGO_SIZE}{logo_path}"
            if download_file(logo_url, temp_logo_file):
                if process_clearlogo(temp_logo_file):
                    print_success(f"  [{movie_folder.name}] clearlogo.png berhasil dibuat.")


def scan_movies(root_dir):
    line()
    print_info(f"SCANNING MOVIES DIRECTORY (PARALLEL): {root_dir}")
    line()

    if not root_dir.exists():
        print_error(f"Direktori MOVIES tidak ditemukan: {root_dir}")
        return

    movie_folders = [p for p in sorted(root_dir.iterdir()) if p.is_dir()]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_movie_folder, folder) for folder in movie_folders]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print_error(f"Error pada task movie thread: {e}")


# ============================================================
# MODULE 2: SCAN TV SERIES
# ============================================================

def process_tv_season(season_folder, tmdb_id, season_num, main_title, show_genres, main_overview="", show_vote_average=0, main_logo_path=None):
    print_info(f"  └── Processing Season Folder: {season_folder.name} (Season {season_num})")

    season_meta_file = season_folder / "season_metadata.json"
    poster_file = season_folder / "poster.webp"
    logo_file = season_folder / "clearlogo.png"

    if SKIP_EXISTING and season_meta_file.exists() and poster_file.exists() and logo_file.exists() and not FORCE_RESCAN:
        print_msg(f"      [{season_folder.name}] Status: Metadata & gambar season lengkap, dilewati.")
        return

    season_cache_key = f"tv_{tmdb_id}_s{season_num}"
    season_details = get_from_cache(season_cache_key)
    if not season_details:
        season_details = fetch_details_with_append(f"/tv/{tmdb_id}/season/{season_num}")
        if season_details:
            season_details["folder_path"] = str(season_folder)
            set_to_cache(season_cache_key, season_details)

    if not season_details:
        print_warning(f"      Gagal mengambil detail untuk Season {season_num}")
        return

    season_name_tmdb = season_details.get("name") or f"Season {season_num}"
    overview = season_details.get("overview", "").strip() or main_overview
    season_vote = season_details.get("vote_average") or show_vote_average

    if not (SKIP_EXISTING and season_meta_file.exists() and not FORCE_RESCAN):
        metadata = {
            "tmdb_id": tmdb_id,
            "show_title": main_title,
            "season_number": season_num,
            "season_name": season_name_tmdb,
            "title": main_title,
            "vote_average": season_vote,
            "genres": show_genres,
            "overview": overview,
            "air_date": season_details.get("air_date", ""),
            "poster_path": season_details.get("poster_path"),
            "episodes_count": len(season_details.get("episodes", [])),
        }
        with open(season_meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)
        print_success(f"      [{season_folder.name}] season_metadata.json dibuat.")

    poster_path = season_details.get("poster_path")
    if poster_path and not (SKIP_EXISTING and poster_file.exists() and not FORCE_RESCAN):
        ext = Path(poster_path).suffix or ".jpg"
        temp_poster_file = season_folder / f"temp_poster{ext}"
        poster_url = f"https://image.tmdb.org/t/p/{POSTER_SIZE}{poster_path}"
        if download_file(poster_url, temp_poster_file):
            if process_poster(temp_poster_file):
                print_success(f"      [{season_folder.name}] poster.webp berhasil dibuat.")

    if not (SKIP_EXISTING and logo_file.exists() and not FORCE_RESCAN):
        logo_path = extract_logo_from_details(season_details) or main_logo_path
        if logo_path:
            ext = Path(logo_path).suffix or ".png"
            temp_logo_file = season_folder / f"temp_clearlogo{ext}"
            logo_url = f"https://image.tmdb.org/t/p/{LOGO_SIZE}{logo_path}"
            if download_file(logo_url, temp_logo_file):
                if process_clearlogo(temp_logo_file):
                    print_success(f"      [{season_folder.name}] clearlogo.png berhasil dibuat.")


def process_tv_show_folder(path):
    clean_title = clean_tv_title(path.name)
    season_num_direct = extract_season_number(path.name)

    if not clean_title:
        return

    search_result = search_tv_show(clean_title)
    if not search_result:
        print_error(f"Serial '{clean_title}' tidak ditemukan di TMDB.")
        return

    tmdb_id = search_result.get("id")
    
    tv_detail_key = f"tv_detail_{tmdb_id}"
    details = get_from_cache(tv_detail_key)
    if not details:
        details = fetch_details_with_append(f"/tv/{tmdb_id}")
        if details:
            details["folder_path"] = str(path)
            set_to_cache(tv_detail_key, details)

    main_title = clean_title
    show_genres = []
    main_overview = ""
    vote_average = 0
    main_logo_path = None

    if details:
        main_title = details.get("name") or clean_title
        show_genres = [g.get("name") for g in details.get("genres", [])]
        main_overview = details.get("overview", "").strip()
        vote_average = details.get("vote_average", 0)
        main_logo_path = extract_logo_from_details(details)

    if season_num_direct is not None:
        print_info(f"Folder Season Langsung: {path.name}")
        process_tv_season(
            path, tmdb_id, season_num_direct, main_title, show_genres, main_overview, vote_average, main_logo_path
        )
    else:
        print_info(f"Folder Induk Serial: {path.name}")
        main_meta_file = path / "metadata.json"
        main_poster = path / "poster.webp"
        main_logo = path / "clearlogo.png"

        if details:
            if not (SKIP_EXISTING and main_meta_file.exists() and not FORCE_RESCAN):
                main_metadata = {
                    "tmdb_id": tmdb_id,
                    "media_type": "tv",
                    "title": main_title,
                    "original_title": details.get("original_name"),
                    "first_air_date": details.get("first_air_date"),
                    "vote_average": details.get("vote_average", 0),
                    "genres": show_genres,
                    "overview": main_overview,
                }
                with open(main_meta_file, "w", encoding="utf-8") as f:
                    json.dump(main_metadata, f, ensure_ascii=False, indent=4)
                print_success(f"  [{path.name}] metadata.json dibuat.")

            if details.get("poster_path") and not (SKIP_EXISTING and main_poster.exists() and not FORCE_RESCAN):
                ext = Path(details['poster_path']).suffix or ".jpg"
                temp_poster_file = path / f"temp_poster{ext}"
                if download_file(f"https://image.tmdb.org/t/p/{POSTER_SIZE}{details['poster_path']}", temp_poster_file):
                    if process_poster(temp_poster_file):
                        print_success(f"  [{path.name}] poster.webp berhasil dibuat.")

            if not (SKIP_EXISTING and main_logo.exists() and not FORCE_RESCAN):
                if main_logo_path:
                    ext = Path(main_logo_path).suffix or ".png"
                    temp_logo_file = path / f"temp_clearlogo{ext}"
                    if download_file(f"https://image.tmdb.org/t/p/{LOGO_SIZE}{main_logo_path}", temp_logo_file):
                        if process_clearlogo(temp_logo_file):
                            print_success(f"  [{path.name}] clearlogo.png berhasil dibuat.")

        for subfolder in path.iterdir():
            if subfolder.is_dir():
                s_num = extract_season_number(subfolder.name)
                if s_num is not None:
                    process_tv_season(
                        subfolder, tmdb_id, s_num, main_title, show_genres, main_overview, vote_average, main_logo_path
                    )


def scan_tv_series(root_dir):
    line()
    print_info(f"SCANNING TV SERIES (PARALLEL): {root_dir}")
    line()

    if not root_dir.exists():
        print_error(f"Direktori TV SERIES tidak ditemukan: {root_dir}")
        return

    tv_folders = [p for p in sorted(root_dir.iterdir()) if p.is_dir()]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_tv_show_folder, folder) for folder in tv_folders]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print_error(f"Error pada task TV thread: {e}")


# ============================================================
# BATCH TRANSLATION WITH INTERACTIVE PROMPT
# ============================================================

TRANSLATION_DELAY = 10.0  # Jeda aman (detik) antar-request ke Google Translate

def process_pending_translations():
    line()
    print_info("PEMERIKSAAN ANTREAN TERJEMAHAN (BATCH TRANSLATION)")
    line()

    pending_items = []
    
    with cache_lock:
        for key, data in DISK_CACHE.items():
            if isinstance(data, dict) and data.get("needs_translation") and AUTO_TRANSLATE:
                pending_items.append((key, data))

    if not pending_items:
        print_success("Semua sinopsis sudah berbahasa Indonesia / tidak ada antrean terjemahan.")
        return

    total_items = len(pending_items)
    
    # Hitung estimasi waktu berdasarkan TRANSLATION_DELAY
    estimated_seconds = int(total_items * TRANSLATION_DELAY)
    est_hours = estimated_seconds // 3600
    est_minutes = (estimated_seconds % 3600) // 60
    est_sec = estimated_seconds % 60

    if est_hours > 0:
        time_str = f"{est_hours}j {est_minutes}m {est_sec}s"
    elif est_minutes > 0:
        time_str = f"{est_minutes}m {est_sec}s"
    else:
        time_str = f"{est_sec}s"

    print_warning(f"Ditemukan {total_items} sinopsis yang membutuhkan terjemahan.")
    print_info(f"Estimasi waktu proses: ±{time_str} (jeda {TRANSLATION_DELAY}s anti-rate limit).")
    
    try:
        choice = input(f"\n{COLOR_WARNING}Apakah Anda ingin menerjemahkan sinopsis sekarang? [y/N]: {COLOR_RESET}").strip().lower()
    except (KeyboardInterrupt, EOFError):
        choice = "n"

    if choice not in ["y", "ya", "yes"]:
        print_msg("\nProses terjemahan dilewati. Status antrean tetap tersimpan di cache.")
        return

    print_msg("\nMemulai proses terjemahan batch...\n")

    for index, (cache_key, data) in enumerate(pending_items, 1):
        raw_text = data.get("raw_en_overview", "")
        title = data.get("title") or data.get("name") or cache_key
        
        print_info(f"[{index}/{total_items}] Menerjemahkan: {title}...")
        
        # Jeda aman sesuai variabel TRANSLATION_DELAY
        time.sleep(TRANSLATION_DELAY)
        
        translated_text = translate_text(raw_text, PRIMARY_LANGUAGE)
        
        if translated_text and translated_text != raw_text and "Error 500" not in translated_text:
            data["overview"] = translated_text
            data["needs_translation"] = False
            set_to_cache(cache_key, data)

            folder_path_str = data.get("folder_path")
            if folder_path_str:
                folder_path = Path(folder_path_str)
                for meta_name in ["metadata.json", "season_metadata.json"]:
                    meta_file = folder_path / meta_name
                    if meta_file.exists():
                        try:
                            with open(meta_file, "r+", encoding="utf-8") as f:
                                meta_data = json.load(f)
                                meta_data["overview"] = translated_text
                                f.seek(0)
                                json.dump(meta_data, f, ensure_ascii=False, indent=4)
                                f.truncate()
                        except Exception as e:
                            print_warning(f"  Gagal update file {meta_name}: {e}")

            print_success(f"  ✓ Berhasil diterjemahkan & metadata di-update.")
        else:
            print_warning(f"  ! Terjemahan gagal/dibatasi. Akan dicoba lagi pada scan berikutnya.")

    print_success("\nProses terjemahan batch selesai!")


# ============================================================
# MAIN SCANNER
# ============================================================

def main():
    line()
    print_info(f"             MEDIA LIBRARY SCANNER (OPTIMIZED & THREADED x{MAX_WORKERS})")
    line()

    if not TMDB_READ_TOKEN and not TMDB_API_KEY:
        print_error("TMDB_READ_TOKEN atau TMDB_API_KEY belum diatur di file scan_movies.conf")
        return

    # Phase 1: Scan & Download (Fast Parallel)
    scan_movies(MOVIES_DIR)
    scan_tv_series(TV_DIR)

    # Phase 2: Batch Translation (Interactive y/N)
    if AUTO_TRANSLATE:
        process_pending_translations()

    line()
    print_success("PROSES SCAN SELESAI!")
    line()


if __name__ == "__main__":
    main()
