local license = [[
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
]]

-- ============================================================
local mp = require("mp")
local utils = require("mp.utils")

-- ============================================================
-- CONFIGURATION
-- ============================================================

local LOGO_ID = 7
local POSTER_ID = 8
local AUTO_HIDE_DELAY = 10 -- Detik sebelum logo menghilang setelah mouse berhenti

-- CLEAR LOGO CONFIG
local LOGO_LEFT = 0.02
local LOGO_TOP  = 0.03
local LOGO_MAX_WIDTH = 0.24
local LOGO_MAX_HEIGHT = 0.14
local GENRE_GAP = 12
local GENRE_FONT_SIZE = 36

-- CLOCK / END TIME CONFIG
local CLOCK_RIGHT_MARGIN = 40
local CLOCK_TOP_MARGIN = 10
local CLOCK_NOW_FONT_SIZE = 75
local CLOCK_END_FONT_SIZE = 36
local CLOCK_GAP_Y = 58

-- POSTER CONFIG
local POSTER_LEFT = 0.04
local POSTER_TOP  = 0.18
local POSTER_MAX_HEIGHT = 0.66

-- INFO TEXT CONFIG
local INFO_GAP = 35
local TITLE_FONT_SIZE = 56
local META_FONT_SIZE = 40
local GENRE_INFO_FONT_SIZE = 38
local OVERVIEW_FONT_SIZE = 37

-- DIRECTORY TEMP
local TEMP_DIR = os.getenv("XDG_RUNTIME_DIR") or os.getenv("TMPDIR") or os.getenv("TEMP") or "/tmp"

-- ============================================================
-- STATE & CACHE
-- ============================================================

local info_visible = false
local logo_visible = false
local poster_visible = false

local ass_overlay = mp.create_osd_overlay("ass-events")
local last_ass_data = ""

local logo_x, logo_y, logo_w, logo_h = 0, 0, 0, 0
local poster_x, poster_y, poster_w, poster_h = 0, 0, 0, 0

local ready_logo_cache = nil
local ready_poster_cache = nil

local cached_metadata = nil
local cached_metadata_path = nil

local auto_hide_timer = nil
local resize_debounce_timer = nil

local last_mouse_check = 0
local last_mouse_x, last_mouse_y = -1, -1

-- ============================================================
-- HELPER ESCAPE ASS
-- ============================================================

local function ass_escape(text)
    if not text then return "" end
    text = tostring(text)
    text = text:gsub("\\", "\\\\"):gsub("{", "\\{"):gsub("}", "\\}")
    return text
end

-- Generate hash unik dari path agar tidak ada bentrokan cache file bgra
local function simple_hash(str)
    local h = 5381
    for i = 1, #str do
        h = ((h * 32) + h + str:byte(i)) % 4294967296
    end
    return string.format("%x", h)
end

-- ============================================================
-- READ & LOAD METADATA
-- ============================================================

local function read_file(path)
    local file = io.open(path, "r")
    if not file then return nil end
    local data = file:read("*a")
    file:close()
    return data
end

local function get_movie_folder()
    local path = mp.get_property("path")
    if not path or path:find("^http") then return nil end
    return path:match("^(.*)/[^/]+$")
end

local function load_metadata()
    local folder = get_movie_folder()
    if not folder then return nil end

    if cached_metadata and cached_metadata_path == folder then
        return cached_metadata
    end

    local season_meta_path = folder .. "/season_metadata.json"
    local data = read_file(season_meta_path)
    local is_season = true

    if not data then
        local main_meta_path = folder .. "/metadata.json"
        data = read_file(main_meta_path)
        is_season = false
    end

    if not data then return nil end

    local metadata = utils.parse_json(data)
    if not metadata then return nil end

    if is_season then
        local show = metadata.show_title or metadata.title or "Unknown"
        local s_name = metadata.season_name or metadata.name or ("Season " .. tostring(metadata.season_number or ""))
        metadata.title = ass_escape(show) .. "\\N{\\fs36}" .. ass_escape(s_name)
        metadata.is_formatted_title = true
        metadata.year = metadata.air_date and metadata.air_date:sub(1, 4) or ""
    else
        metadata.title = ass_escape(metadata.title or "Unknown")
        metadata.is_formatted_title = true
        metadata.year = metadata.first_air_date and metadata.first_air_date:sub(1, 4) or metadata.year or ""
    end

    metadata.folder = folder
    cached_metadata = metadata
    cached_metadata_path = folder

    return metadata
end

-- ============================================================
-- LIGHTWEIGHT BGRA CREATOR
-- ============================================================

local function get_image_dimensions_async(path, callback)
    mp.command_native_async({
        name = "subprocess",
        playback_only = false,
        capture_stdout = true,
        capture_stderr = false,
        args = {
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0", path
        }
    }, function(success, result)
        if success and result and result.stdout then
            local w, h = result.stdout:match("(%d+)x(%d+)")
            if w and h then
                callback(tonumber(w), tonumber(h))
                return
            end
        end
        callback(nil, nil)
    end)
end

local function create_bgra_async(source, width, height, name, force_crop, callback)
    local source_hash = simple_hash(source)
    local filename = string.format("%s/mpv_cache_%s_%s_%dx%d.bgra", TEMP_DIR, name, source_hash, width, height)

    local info = utils.file_info(filename)
    if info and info.size == (width * height * 4) then
        callback(filename)
        return
    end

    local vf_filter
    if force_crop then
        vf_filter = string.format("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d", width, height, width, height)
    else
        vf_filter = string.format("scale=%d:%d", width, height)
    end

    mp.command_native_async({
        name = "subprocess",
        playback_only = false,
        capture_stdout = false,
        capture_stderr = false,
        args = {
            "ffmpeg", "-y", "-threads", "1", "-hide_banner", "-loglevel", "quiet",
            "-i", source,
            "-vf", vf_filter,
            "-pix_fmt", "bgra", "-f", "rawvideo", filename
        }
    }, function(success, result)
        if success and result and result.status == 0 then
            local expected_bytes = width * height * 4
            local f_info = utils.file_info(filename)
            if f_info and f_info.size == expected_bytes then
                callback(filename)
                return
            end
        end
        callback(nil)
    end)
end

-- ============================================================
-- SMART RENDER ASS OVERLAY
-- ============================================================

local function render_ass_smart(data)
    if last_ass_data == data then return end
    ass_overlay.data = data
    ass_overlay:update()
    last_ass_data = data
end

-- ============================================================
-- REMOVE OVERLAYS & RESET STATE
-- ============================================================

local function remove_logo()
    mp.commandv("overlay-remove", tostring(LOGO_ID))
    logo_visible = false
end

local function remove_poster()
    mp.commandv("overlay-remove", tostring(POSTER_ID))
    poster_visible = false
end

local function reset_state()
    remove_logo()
    remove_poster()
    ass_overlay:remove()
    
    info_visible = false
    logo_visible = false
    poster_visible = false
    last_ass_data = ""
    
    -- Reset total cache agar gambar film sebelumnya hilang sama sekali
    ready_logo_cache = nil
    ready_poster_cache = nil
    cached_metadata = nil
    cached_metadata_path = nil

    if auto_hide_timer then
        auto_hide_timer:kill()
        auto_hide_timer = nil
    end
end

-- ============================================================
-- SEARCH LOGO & POSTER (STRICT CURRENT FOLDER)
-- ============================================================

local function find_clearlogo(folder)
    local extensions = { "png", "webp" }
    for _, ext in ipairs(extensions) do
        local path = folder .. "/clearlogo." .. ext
        if utils.file_info(path) then return path end
    end
    return nil
end

local function find_poster(folder)
    local filenames = { "poster.png", "poster.webp", "folder.png", "folder.webp", "cover.png", "cover.webp" }
    for _, name in ipairs(filenames) do
        local path = folder .. "/" .. name
        if utils.file_info(path) then return path end
    end
    return nil
end

local function preload_assets_async(metadata)
    if not metadata or not metadata.folder then return end
    local video_w, video_h = mp.get_osd_size()
    if not video_w or not video_h or video_w == 0 or video_h == 0 then return end
    
    local current_folder = metadata.folder

    -- 1. Preload Clear Logo
    local logo_path = find_clearlogo(current_folder)
    if logo_path then
        get_image_dimensions_async(logo_path, function(orig_w, orig_h)
            if get_movie_folder() ~= current_folder then return end
            local max_w = math.floor(video_w * LOGO_MAX_WIDTH)
            local max_h = math.floor(video_h * LOGO_MAX_HEIGHT)
            local target_w, target_h
            if orig_w and orig_h and orig_w > 0 and orig_h > 0 then
                local aspect = orig_w / orig_h
                target_h = max_h
                target_w = math.floor(target_h * aspect)
                if target_w > max_w then
                    target_w = max_w
                    target_h = math.floor(target_w / aspect)
                end
            else
                target_w = max_w
                target_h = max_h
            end

            local stride = target_w * 4
            local lx = math.floor(video_w * LOGO_LEFT)
            local ly = math.floor(video_h * LOGO_TOP)

            create_bgra_async(logo_path, target_w, target_h, "clearlogo", false, function(filepath)
                if get_movie_folder() ~= current_folder then return end
                if filepath then
                    ready_logo_cache = {
                        filepath = filepath, x = lx, y = ly, w = target_w, h = target_h,
                        raw_w = target_w, raw_h = target_h, stride = stride,
                        folder = current_folder
                    }
                end
            end)
        end)
    end

    -- 2. Preload Poster
    local poster_path = find_poster(current_folder)
    if poster_path then
        local px = math.floor(video_w * POSTER_LEFT)
        local py = math.floor(video_h * POSTER_TOP)
        local target_h = math.floor(video_h * POSTER_MAX_HEIGHT)
        local target_w = math.floor(target_h * (2 / 3))
        local stride = target_w * 4

        create_bgra_async(poster_path, target_w, target_h, "poster", true, function(filepath)
            if get_movie_folder() ~= current_folder then return end
            if filepath then
                ready_poster_cache = {
                    filepath = filepath, x = px, y = py, w = target_w, h = target_h,
                    raw_w = target_w, raw_h = target_h, stride = stride,
                    folder = current_folder
                }
            end
        end)
    end
end

-- ============================================================
-- RENDER LOGO & HEADER INFO
-- ============================================================

local function get_header_ass_string(metadata)
    local w, h = mp.get_osd_size()
    if w == 0 or h == 0 then return "" end

    local ass_parts = {}

    if metadata and metadata.genres and not info_visible then
        local genres = ass_escape(table.concat(metadata.genres, " / "))
        if genres ~= "" and logo_visible then
            local genre_x = logo_x + logo_w + GENRE_GAP
            local genre_y = logo_y + math.floor(logo_h / 2)
            table.insert(ass_parts, string.format("{\\an4\\pos(%d,%d)\\fs%d\\bord1\\shad1}%s", genre_x, genre_y, GENRE_FONT_SIZE, genres))
        end
    end

    local now_time = os.date("%H:%M")
    local time_remaining = mp.get_property_number("time-remaining")

    local clock_x = w - CLOCK_RIGHT_MARGIN
    local clock_y = CLOCK_TOP_MARGIN

    local clock_str = string.format("{\\an9\\pos(%d,%d)\\bord1\\shad1}{\\fs%d\\b1}%s", clock_x, clock_y, CLOCK_NOW_FONT_SIZE, now_time)

    if time_remaining and time_remaining > 0 then
        local finish_timestamp = os.time() + math.floor(time_remaining)
        local finish_time = os.date("%H:%M", finish_timestamp)
        local end_y = clock_y + CLOCK_GAP_Y
        clock_str = clock_str .. string.format("\n{\\an9\\pos(%d,%d)\\bord1\\shad1}{\\fs%d\\b0\\a&H40&}Ends at : %s", clock_x, end_y, CLOCK_END_FONT_SIZE, finish_time)
    end

    table.insert(ass_parts, clock_str)
    return table.concat(ass_parts, "\n")
end

local function render_header_osd(metadata)
    local w, h = mp.get_osd_size()
    if w == 0 or h == 0 then return end

    ass_overlay.res_x = w
    ass_overlay.res_y = h

    local header_str = get_header_ass_string(metadata)
    render_ass_smart(header_str)
end

local function show_logo(metadata)
    if logo_visible or not metadata then return end

    local current_folder = get_movie_folder()
    if ready_logo_cache and ready_logo_cache.folder == current_folder then
        logo_x = ready_logo_cache.x
        logo_y = ready_logo_cache.y
        logo_w = ready_logo_cache.w
        logo_h = ready_logo_cache.h

        mp.commandv(
            "overlay-add", tostring(LOGO_ID), tostring(logo_x), tostring(logo_y),
            ready_logo_cache.filepath, "0", "bgra", tostring(ready_logo_cache.raw_w), tostring(ready_logo_cache.raw_h),
            tostring(ready_logo_cache.stride), tostring(logo_w), tostring(logo_h)
        )
        logo_visible = true
        if not info_visible then render_header_osd(metadata) end
    end
end

local function show_header()
    if info_visible then return end
    local metadata = load_metadata()
    if not metadata then return end
    show_logo(metadata)
end

local function hide_header()
    if info_visible then return end
    remove_logo()
    ass_overlay:remove()
    last_ass_data = ""
end

-- ============================================================
-- RENDER POSTER & FULL INFO
-- ============================================================

local function wrap_text(text, max_chars)
    if not text then return "" end
    local result, line = {}, ""
    for word in tostring(text):gmatch("%S+") do
        if #line == 0 then line = word
        elseif #line + #word + 1 <= max_chars then line = line .. " " .. word
        else table.insert(result, line); line = word end
    end
    if #line > 0 then table.insert(result, line) end
    return table.concat(result, "\\N")
end

local function render_info_panel(metadata)
    local width, height = mp.get_osd_size()
    ass_overlay.res_x, ass_overlay.res_y = width, height

    local text_x = poster_visible and (poster_x + poster_w + INFO_GAP) or math.floor(width * 0.08)
    local text_y = poster_visible and poster_y or math.floor(height * POSTER_TOP)

    local title = metadata.is_formatted_title and metadata.title or ass_escape(metadata.title or "Unknown")
    local year = tostring(metadata.year or "")
    local rating = tonumber(metadata.vote_average) or 0
    local genres = ass_escape(metadata.genres and table.concat(metadata.genres, " • ") or "")
    local overview = ass_escape(metadata.overview or "")

    local available_width = width - text_x - math.floor(width * 0.05)
    local max_chars = math.max(35, math.floor(available_width / (OVERVIEW_FONT_SIZE * 0.55)))
    overview = wrap_text(overview, max_chars)

    local panel_str = string.format(
        "{\\an7\\pos(%d,%d)}{\\fs%d\\b1\\bord2\\shad2}%s\\N{\\fs%d\\b0\\bord1\\shad1}%s  •  ⭐ %.1f/10\\N{\\fs%d}%s\\N\\N{\\fs%d\\q2\\bord1\\shad1}%s",
        text_x, text_y, TITLE_FONT_SIZE, title, META_FONT_SIZE, year, rating, GENRE_INFO_FONT_SIZE, genres, OVERVIEW_FONT_SIZE, overview
    )

    local header_str = get_header_ass_string(metadata)
    local full_ass = header_str ~= "" and (panel_str .. "\n" .. header_str) or panel_str

    render_ass_smart(full_ass)
    info_visible = true
end

local function show_info()
    local metadata = load_metadata()
    if not metadata then
        mp.osd_message("Metadata JSON tidak ditemukan", 2)
        return
    end

    show_logo(metadata)

    local current_folder = get_movie_folder()
    if ready_poster_cache and ready_poster_cache.folder == current_folder then
        poster_x = ready_poster_cache.x
        poster_y = ready_poster_cache.y
        poster_w = ready_poster_cache.w
        poster_h = ready_poster_cache.h

        mp.commandv(
            "overlay-add", tostring(POSTER_ID), 
            tostring(poster_x), tostring(poster_y),
            ready_poster_cache.filepath, "0", "bgra", 
            tostring(ready_poster_cache.raw_w), tostring(ready_poster_cache.raw_h),
            tostring(ready_poster_cache.stride), 
            tostring(poster_w), tostring(poster_h)
        )
        poster_visible = true
    end
    render_info_panel(metadata)
end

local function hide_info()
    remove_poster()
    remove_logo()
    ass_overlay:remove()
    last_ass_data = ""
    info_visible = false
end

local function toggle_info()
    if info_visible then hide_info() else show_info() end
end

mp.add_key_binding("=", "movie-info-key", toggle_info)
mp.add_forced_key_binding("MBTN_RIGHT", "movie-info-mouse", toggle_info)

-- ============================================================
-- MOUSE & RESIZE HANDLERS
-- ============================================================

local function request_show_header()
    if info_visible then return end
    show_header()

    if auto_hide_timer then auto_hide_timer:kill() end

    local paused = mp.get_property_native("pause")
    if not paused then
        auto_hide_timer = mp.add_timeout(AUTO_HIDE_DELAY, function()
            if not info_visible then hide_header() end
        end)
    end
end

mp.observe_property("mouse-pos", "native", function(_, mouse)
    if not mouse then return end

    local now = mp.get_time()
    if now - last_mouse_check < 0.1 then return end
    last_mouse_check = now

    if math.abs(mouse.x - last_mouse_x) > 3 or math.abs(mouse.y - last_mouse_y) > 3 then
        last_mouse_x = mouse.x
        last_mouse_y = mouse.y
        request_show_header()
    end
end)

mp.observe_property("pause", "bool", function() request_show_header() end)

mp.observe_property("osd-dimensions", "native", function()
    if resize_debounce_timer then resize_debounce_timer:kill() end
    resize_debounce_timer = mp.add_timeout(0.15, function()
        ready_logo_cache = nil
        ready_poster_cache = nil
        local metadata = load_metadata()
        if metadata then
            preload_assets_async(metadata)
        end
    end)
end)

-- ============================================================
-- EVENT HANDLERS (STRICT CLEANUP)
-- ============================================================

mp.register_event("start-file", function()
    reset_state()
end)

mp.register_event("file-loaded", function()
    reset_state()
    local metadata = load_metadata()
    if metadata then
        preload_assets_async(metadata)
    end
end)

mp.register_event("end-file", function()
    reset_state()
end)

mp.register_event("shutdown", function()
    reset_state()
end)

mp.msg.info("movie-info.lua (v4.4.7 - strict single-folder match) loaded")
