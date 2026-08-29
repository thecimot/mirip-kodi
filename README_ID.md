# mirip-kodi (Media Library Scanner & MPV OSD Overlay)

Proyek ini adalah sistem otomasi pustaka media terintegrasi bergaya Kodi yang terdiri dari dua komponen utama:
1. **`scan_movies`**: Skrip otomatis berbasis Python untuk memindai direktori film/serial TV dan mengunduh metadata serta gambar dari TMDB.
2. **`movie-info.lua`**: Skrip Lua untuk pemutar video MPV yang membaca metadata hasil pemindaian dan menampilkannya sebagai antarmuka info interaktif (poster, sinopsis, genre, dan jam dinding digital).

## Fitur Utama

* **Pemindaian Otomatis**: Membaca folder Film dan Serial TV secara rekursif.
* **Integrasi TMDB**: Mengunduh informasi serta sinopsis otomatis berbahasa Indonesia (`id-ID`).
* **Pemberbersih Aset**: Mengunduh poster film serta mengompresi dan menajamkan logo jernih (`clearlogo.png`) menggunakan Pillow.
* **Antarmuka MPV Bergaya Kodi**: Menampilkan overlay poster, rating, daftar genre, sinopsis terbungkus rapi, jam waktu nyata, serta estimasi waktu film selesai.
* **Visibilitas Pintar**: Informasi otomatis muncul saat video dijeda (pause) atau kursor Mouse digerakkan, dan tersembunyi otomatis saat film dimainkan.

## Persyaratan Sistem

Sebelum memulai instalasi, pastikan sistem Linux Anda memenuhi kebutuhan berikut:
* **Sistem Operasi**: Linux / Unix-based (Skrip membaca path direktori media eksternal `/run/media/...`).
* **Python**: Versi 3.x atau yang terbaru.
* **Aplikasi Pemutar**: [MPV Player](https://mpv.io) terinstal di sistem.
* **Alat Pendukung**: `ffmpeg` dan `ffprobe` (Bawaan sistem Linux, diperlukan oleh skrip MPV untuk memproses gambar).

### Dependensi Python

Skrip pemindai memerlukan library pihak ketiga **Pillow** untuk memproses gambar. Instal melalui terminal Anda:

```bash
pip install Pillow
```

## Konfigurasi Lingkungan (.bashrc)

Skrip ini memerlukan otentikasi ke API TMDB agar dapat berfungsi. Disarankan menggunakan **TMDB Read Access Token (v4 auth)** yang dimasukkan ke dalam file `.bashrc` Anda.

### Cara Mendapatkan Token TMDB (Gratis):
1. Buka situs resmi [The Movie Database (TMDB)](https://themoviedb.org) dan masuk ke akun Anda.
2. Klik ikon profil Anda di pojok kanan atas, lalu pilih **Settings**.
3. Pada menu sebelah kiri, klik tab **API**.
4. Klik tautan **Create** di bawah bagian "Request an API Key", lalu pilih jenis aplikasi **Developer**.
5. Isi formulir informasi aplikasi yang diminta (Anda bisa mengisi nama proyek dengan `mirip-kodi` dan URL dengan tautan GitHub Anda).
6. Setelah menyetujui persyaratan, cari bagian **API Read Access Token (v4 auth)** yang berupa teks kode sangat panjang, lalu salin (copy) seluruh kode tersebut.

### Memasukkan Token ke Sistem:
Jalankan perintah berikut di terminal untuk memasukkan token Anda secara otomatis ke dalam konfigurasi sistem Linux:

```bash
# Tambahkan Token TMDB ke .bashrc
echo 'export TMDB_TOKEN="isi_read_access_token_v4_anda_di_sini"' >> ~/.bashrc

# Muat ulang konfigurasi terminal agar langsung aktif
source ~/.bashrc
```

*Catatan: Pastikan Anda mengganti `"isi_read_access_token_v4_anda_di_sini"` dengan kode token panjang yang sudah Anda salin dari dasbor TMDB sebelum menekan Enter [1].*

## Langkah Instalasi Components

Ikuti langkah-langkah pemasangan berikut di terminal untuk memasang pemindai global dan pemutar MPV secara berdampingan:

### 1. Unduh (Clone) Repositori
```bash
git clone https://github.com/thecimot/mirip-kodi
cd mirip-kodi
```

### 2. Pasang Pemindai Media (`scan_movies`) ke Sistem
Agar skrip dapat dipanggil langsung dari mana saja di terminal tanpa mengetik ekstensi `.py`:
```bash
# Buat folder bin lokal jika belum ada
mkdir -p ~/.local/bin

# Salin berkas pemindai utama
cp scan_movies ~/.local/bin/

# Berikan hak akses eksekusi ke berkas
chmod +x ~/.local/bin/scan_movies
```
*Pastikan folder `~/.local/bin` sudah terdaftar di variabel `$PATH` sistem Anda di dalam file `.bashrc`.*

## 3. Kustomisasi Pengaturan Skrip (`scan_movies`)

Anda dapat menyesuaikan folder tujuan media serta bahasa pencarian utama langsung di dalam skrip `scan_movies`. Buka file menggunakan teks editor pilihan Anda (misalnya Nano):

```bash
nano ~/.local/bin/scan_movies
```

  Cari blok kode konfigurasi di baris-baris awal file dan sesuaikan parameternya:

  ### a. Menentukan Folder Media Tujuan
  Ubah isi di dalam tanda kurung `Path("...")` sesuai dengan lokasi folder Film dan Serial TV di harddisk/media eksternal Anda:
  ```python
  # ============================================================
  # KONFIGURASI DIREKTORI
  # ============================================================

  MOVIES_DIR = Path("/run/media/cimot/cimot/MOVIES")
  TV_DIR = Path("/run/media/cimot/cimot/TV SERIES")
  ```

  ### b. Mengubah Preferensi Bahasa (Language)
  Secara bawaan, skrip diatur untuk mengutamakan sinopsis berbahasa Indonesia. Jika metadata tidak tersedia, skrip akan otomatis menggunakan bahasa Inggris       sebagai cadangan (fallback). Anda dapat mengganti kode bahasa standar ISO 639-1 jika diperlukan:
  ```python
  PRIMARY_LANGUAGE = "id-ID"      # Bahasa utama pencarian metadata (Indonesia)
  FALLBACK_LANGUAGE = "en-US"     # Bahasa cadangan jika bahasa utama kosong (Inggris)
  ```

  Setelah melakukan pengeditan, simpan perubahan file dengan menekan tombol kombinasi `Ctrl + O`, lalu `Enter`, dan tekan `Ctrl + X` untuk keluar dari editor Nano.

### 4. Pasang Antarmuka MPV (`movie-info.lua`)
Salin berkas skrip Lua langsung ke dalam direktori konfigurasi bawaan milik aplikasi MPV Anda:
```bash
# Buat direktori scripts MPV jika belum ada
mkdir -p ~/.config/mpv/scripts

# Salin skrip antarmuka OSD
cp movie-info.lua ~/.config/mpv/scripts/
```

## 5. Cara Penggunaan

### Memindai Berkas Media
Buka terminal Anda, masuk ke sistem, lalu cukup ketik perintah global berikut untuk memperbarui seluruh aset gambar serta metadata json secara otomatis:
```bash
scan_movies
```

### 6. Menampilkan Informasi di MPV
Putar video film atau serial TV Anda menggunakan MPV. Antarmuka informasi pintar akan muncul otomatis saat Anda menggerakkan Mouse atau menjeda video. Untuk memunculkan panel informasi lengkap (Poster dan Sinopsis), tekan tombol hotkey berikut pada papan ketik Anda:
* Tombol **`=`** (Sama Dengan) [2]
* Klik **Tombol Kanan Mouse (Right-Click)** di jendela pemutar MPV [2]

### 7. Screenshoot
a. Clear Logo, Genre dan Jam akan muncul saat Mouse Bergerak dan akan menghilang dengan sendirinya. Default = 10 Detik.
![Spring Clear Logo](Screenshoot/Spring_Clear_Logo.webp)

b. Poster Rating dan Sinopsis akan muncul saat Right Clik (Klik Kanan Pada Mouse) dan akan hilang jika Klik Kanan Kedua Kalinya.
![Spring Poster](Screenshoot/Spring_Poster.webp)

### 8. Terdapat Folder Contoh Film Beserta Metatada,Poster,dll jika anda clone repositori inI. Untuk mengecek apakah plugin movie-info.lua bekerja di Player MPV.

### SELAMAT MENONTON!!
## Lisensi

Proyek ini dilisensikan di bawah **MIT License** - Lihat isi file kode untuk detail hak cipta oleh Hartono (2026).
