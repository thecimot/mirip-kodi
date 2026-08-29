#!/usr/bin/env bash
set -e

# ============================================================
# Skrip Instalasi: mirip-kodi
# ============================================================

# Warna output
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m" # No Color

# Direktori sumber skrip dijalankan
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Standard direktori Linux (XDG Base Directory / User Home)
BIN_DIR="${HOME}/.local/bin"
SCANNER_TARGET_DIR="${BIN_DIR}/mirip-kodi-scanner"
SCANNER_EXEC="${SCANNER_TARGET_DIR}/scan_movies.py"
SYMLINK_PATH="${BIN_DIR}/scan_movies"

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
MPV_SCRIPTS_DIR="${CONFIG_DIR}/mpv/scripts"
MPV_TARGET_FILE="${MPV_SCRIPTS_DIR}/movie-info.lua"

echo -e "${BLUE}=== Memulai Instalasi mirip-kodi ===${NC}"

# 1. Validasi berkas sumber
if [ ! -d "${SOURCE_DIR}/mirip-kodi-scanner" ]; then
    echo -e "${RED}Error: Folder 'mirip-kodi-scanner' tidak ditemukan di ${SOURCE_DIR}${NC}"
    exit 1
fi

if [ ! -f "${SOURCE_DIR}/movie-info.lua" ]; then
    echo -e "${RED}Error: Berkas 'movie-info.lua' tidak ditemukan di ${SOURCE_DIR}${NC}"
    exit 1
fi

# 2. Buat direktori tujuan jika belum ada
echo -e "\n${BLUE}[1/4] Menyiapkan direktori tujuan...${NC}"
mkdir -p "${BIN_DIR}"
mkdir -p "${MPV_SCRIPTS_DIR}"
echo -e "  ${GREEN}✓${NC} Direktori bin: ${BIN_DIR}"
echo -e "  ${GREEN}✓${NC} Direktori mpv: ${MPV_SCRIPTS_DIR}"

# 3. Salin folder mirip-kodi-scanner ke ~/.local/bin/
echo -e "\n${BLUE}[2/4] Menyalin mirip-kodi-scanner ke ${BIN_DIR}...${NC}"
cp -r "${SOURCE_DIR}/mirip-kodi-scanner" "${BIN_DIR}/"
chmod +x "${SCANNER_EXEC}"
echo -e "  ${GREEN}✓${NC} Berhasil disalin ke: ${SCANNER_TARGET_DIR}"
echo -e "  ${GREEN}✓${NC} Izin eksekusi diberikan pada: ${SCANNER_EXEC}"

# 4. Buat symlink dari ~/.local/bin/mirip-kodi-scanner/scan_movies.py ke ~/.local/bin/scan_movies
echo -e "\n${BLUE}[3/4] Membuat symlink scan_movies...${NC}"
ln -sf "${SCANNER_EXEC}" "${SYMLINK_PATH}"
echo -e "  ${GREEN}✓${NC} Symlink dibuat: ${SYMLINK_PATH} -> ${SCANNER_EXEC}"

# 5. Salin movie-info.lua ke ~/.config/mpv/scripts/
echo -e "\n${BLUE}[4/4] Menyalin movie-info.lua ke ${MPV_SCRIPTS_DIR}...${NC}"
cp "${SOURCE_DIR}/movie-info.lua" "${MPV_TARGET_FILE}"
echo -e "  ${GREEN}✓${NC} Berkas disalin ke: ${MPV_TARGET_FILE}"

# 6. Pengecekan variabel PATH
echo -e "\n${GREEN}=== Instalasi Selesai! ===${NC}"
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    echo -e "\n${YELLOW}Catatan:${NC} Direktori ${BIN_DIR} belum ada di PATH terminal Anda."
    echo -e "Tambahkan baris berikut ke file ~/.bashrc atau ~/.zshrc jika perintah 'scan_movies' belum terbaca:"
    echo -e "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo -e "\nSekarang Anda dapat menjalankan perintah ${BLUE}scan_movies${NC} dari terminal."

