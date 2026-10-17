import os
import io
import json
import time
import urllib.parse
import requests
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from datetime import datetime, timezone, timedelta

# -------------------- CONFIG --------------------
API_KEY = os.getenv("OPENWEATHER_API_KEY", "2b3d4cc3e4624937dd2c5f7f50e84aec")
CACHE_FILE = "cache.json"
HISTORY_FILE = "history.json"
BACKGROUND_IMAGE_PATH = "assets/bg.jpg" 
DEFAULT_UNITS = "metric"   
CACHE_TTL_SECONDS = 120

# -------------------- UTILITIES --------------------
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def kelvin_to_c(k):
    return k - 273.15

def get_local_time_from_offset(offset_seconds, dt_utc=None):
    if dt_utc is None:
        dt = datetime.now(timezone.utc)
    else:
        dt = datetime.fromtimestamp(dt_utc, tz=timezone.utc)
    return dt + timedelta(seconds=offset_seconds)

def icon_url(icon_code):
    return f"https://openweathermap.org/img/wn/{icon_code}@4x.png"

def fetch_image_bytes(url):
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.content

def c_f_toggle_text(units):
    return "°C" if units == "metric" else "°F"

# -------------------- MAIN APP --------------------
class WeatherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Weather App")
        self.geometry("700x520")
        self.minsize(640, 480)

        # Theme state
        self.themes = {
            "light": {
                "bg": "#EAF6FF",
                "fg": "#0B2545",
                "card": "#FFFFFF",
                "muted": "#375A7F",
                "button": "#1E90FF",
                "entry": "#FFFFFF",
            },
            "dark": {
                "bg": "#0F172A",
                "fg": "#E2E8F0",
                "card": "#111827",
                "muted": "#94A3B8",
                "button": "#3B82F6",
                "entry": "#1F2937",
            },
        }
        self.theme = "light"

        # Units state
        self.units = DEFAULT_UNITS

        # Cache/History/Favorites
        self.cache = load_json(CACHE_FILE, {})
        self.history = load_json(HISTORY_FILE, {"recent": [], "favorites": []})

        # Background
        self.bg_image_obj = None
        self._try_load_background()

        # Build UI
        self._build_header()
        self._build_controls()
        self._build_display()

        # Apply theme
        self.apply_theme()
        
        if self.history["recent"]:
            self.city_var.set(self.history["recent"][0])

    # ---------------- UI BUILDERS ----------------
    def _try_load_background(self):
        if os.path.exists(BACKGROUND_IMAGE_PATH):
            try:
                img = Image.open(BACKGROUND_IMAGE_PATH).resize((1600, 1000))
                self.bg_image_obj = ImageTk.PhotoImage(img)
                self.bg_label = tk.Label(self, image=self.bg_image_obj)
                self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
            except Exception:
                self.configure(bg=self.themes[self.theme]["bg"])
        else:
            self.configure(bg=self.themes[self.theme]["bg"])

    def _build_header(self):
        self.header_frame = tk.Frame(self, bd=0)
        self.header_frame.pack(fill="x", pady=(12, 8))
        self.header_title = tk.Label(
            self.header_frame,
            text="🌤  Weather App",
            font=("Segoe UI", 20, "bold"),
        )
        self.header_title.pack()

    def _build_controls(self):
        theme_cfg = self.themes[self.theme]

        self.control_card = tk.Frame(self, bd=0, highlightthickness=0)
        self.control_card.pack(fill="x", padx=16)

        # Entry + buttons row
        row = tk.Frame(self.control_card, bd=0)
        row.pack(fill="x")

        self.city_var = tk.StringVar()
        self.city_entry = tk.Entry(row, textvariable=self.city_var, font=("Segoe UI", 12), width=28)
        self.city_entry.pack(side="left", padx=(0, 8), pady=6)

        self.search_btn = tk.Button(row, text="Get Weather", font=("Segoe UI", 11, "bold"),
                                    command=self.on_search_click)
        self.search_btn.pack(side="left", padx=(0, 8), pady=6)

        self.unit_btn = tk.Button(row, text=f"Units: {c_f_toggle_text(self.units)}",
                                  font=("Segoe UI", 10),
                                  command=self.on_toggle_units)
        self.unit_btn.pack(side="left", padx=(0, 8))

        self.theme_btn = tk.Button(row, text="Toggle Theme", font=("Segoe UI", 10),
                                   command=self.on_toggle_theme)
        self.theme_btn.pack(side="left", padx=(0, 8))

        self.fav_btn = tk.Button(row, text="☆ Add to Favorites", font=("Segoe UI", 10),
                                 command=self.on_add_favorite)
        self.fav_btn.pack(side="left", padx=(0, 8))

        # History + Favorites row
        row2 = tk.Frame(self.control_card, bd=0)
        row2.pack(fill="x", pady=(6, 0))

        tk.Label(row2, text="Recent:", font=("Segoe UI", 10)).pack(side="left")
        self.recent_var = tk.StringVar()
        self.recent_combo = ttk.Combobox(row2, textvariable=self.recent_var, width=24, state="readonly")
        self.recent_combo.pack(side="left", padx=(4, 12))
        self.recent_combo.bind("<<ComboboxSelected>>", self.on_recent_selected)

        tk.Label(row2, text="Favorites:", font=("Segoe UI", 10)).pack(side="left")
        self.fav_var = tk.StringVar()
        self.fav_combo = ttk.Combobox(row2, textvariable=self.fav_var, width=24, state="readonly")
        self.fav_combo.pack(side="left", padx=(4, 0))
        self.fav_combo.bind("<<ComboboxSelected>>", self.on_favorite_selected)

        self.refresh_history_ui()

    def _build_display(self):
        self.display_card = tk.Frame(self, bd=0)
        self.display_card.pack(fill="both", expand=True, padx=16, pady=16)

        # Top: City/Time
        self.city_label = tk.Label(self.display_card, text="Enter a city and click Get Weather",
                                   font=("Segoe UI", 14, "bold"))
        self.city_label.pack(pady=(0, 6))

        self.time_label = tk.Label(self.display_card, text="", font=("Segoe UI", 10))
        self.time_label.pack()

        # Middle: Icon + Big Temp
        mid = tk.Frame(self.display_card, bd=0)
        mid.pack(pady=10)

        self.icon_label = tk.Label(mid)
        self.icon_label.pack(side="left", padx=10)

        self.temp_label = tk.Label(mid, text="", font=("Segoe UI", 36, "bold"))
        self.temp_label.pack(side="left", padx=10)

        # Bottom: Details grid
        grid = tk.Frame(self.display_card, bd=0)
        grid.pack(pady=8)

        self.desc_label = tk.Label(grid, text="", font=("Segoe UI", 12))
        self.desc_label.grid(row=0, column=0, columnspan=2, pady=(0, 6))

        self.detail_vars = {
            "feels": tk.StringVar(value=""),
            "hum": tk.StringVar(value=""),
            "wind": tk.StringVar(value=""),
            "minmax": tk.StringVar(value=""),
            "sun": tk.StringVar(value=""),
            "coord": tk.StringVar(value=""),
        }

        self._make_kv(grid, "Feels like:", "feels", 1, 0)
        self._make_kv(grid, "Humidity:", "hum", 1, 1)
        self._make_kv(grid, "Wind:", "wind", 2, 0)
        self._make_kv(grid, "Min / Max:", "minmax", 2, 1)
        self._make_kv(grid, "Sunrise / Sunset:", "sun", 3, 0)
        self._make_kv(grid, "Coordinates:", "coord", 3, 1)

    def _make_kv(self, parent, label, key, r, c):
        tk.Label(parent, text=label, font=("Segoe UI", 10, "bold")).grid(row=r, column=c*2, sticky="e", padx=(4, 4), pady=4)
        tk.Label(parent, textvariable=self.detail_vars[key], font=("Segoe UI", 10)).grid(row=r, column=c*2+1, sticky="w", padx=(0, 10), pady=4)

    # ---------------- ACTIONS ----------------
    def on_search_click(self):
        city = self.city_var.get().strip()
        if not city:
            messagebox.showwarning("Missing City", "Please enter a city name.")
            return
        self.get_and_display_city(city)

    def on_recent_selected(self, _e):
        city = self.recent_var.get()
        if city:
            self.city_var.set(city)
            self.get_and_display_city(city)

    def on_favorite_selected(self, _e):
        city = self.fav_var.get()
        if city:
            self.city_var.set(city)
            self.get_and_display_city(city)

    def on_toggle_units(self):
        self.units = "imperial" if self.units == "metric" else "metric"
        self.unit_btn.config(text=f"Units: {c_f_toggle_text(self.units)}")
        # Re-fetch current city in new units, if a city is shown
        current_city = self.city_label.cget("text")
        if current_city and "Enter a city" not in current_city:
            self.get_and_display_city(self.city_var.get().strip(), force_refresh=True)

    def on_toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.apply_theme()

    def on_add_favorite(self):
        city = self.city_var.get().strip()
        if not city:
            return
        if city not in self.history["favorites"]:
            self.history["favorites"].insert(0, city)
            self.history["favorites"] = self.history["favorites"][:20]
            save_json(HISTORY_FILE, self.history)
            self.refresh_history_ui()
            messagebox.showinfo("Added", f"Added '{city}' to favorites.")

    # ---------------- DATA FLOW ----------------
    def get_and_display_city(self, city, force_refresh=False):
        try:
            data = self.get_weather_data(city, force_refresh=force_refresh)
            if not data:
                return
            self.render_weather(data)
            self.update_history(city)
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Network Error", f"Failed to fetch weather.\n\n{e}")
        except Exception as e:
            messagebox.showerror("Error", f"Something went wrong.\n\n{e}")

    def get_weather_data(self, city, force_refresh=False):
        city_key = city.lower()
        now = time.time()
        # Cache lookup
        if not force_refresh and city_key in self.cache:
            entry = self.cache[city_key]
            if (now - entry.get("ts", 0)) < CACHE_TTL_SECONDS and entry.get("units") == self.units:
                return entry["data"]

        # API call
        q = urllib.parse.quote_plus(city)
        url = f"https://api.openweathermap.org/data/2.5/weather?q={q}&appid={API_KEY}&units={self.units}"
        r = requests.get(url, timeout=10)
        if r.status_code == 404:
            messagebox.showerror("Not Found", f"City '{city}' not found.")
            return None
        r.raise_for_status()
        data = r.json()

        # Write cache
        self.cache[city_key] = {"ts": now, "units": self.units, "data": data}
        save_json(CACHE_FILE, self.cache)
        return data

    def render_weather(self, data):
        # Basic fields
        name = data.get("name", "Unknown")
        sys = data.get("sys", {})
        country = sys.get("country", "")
        coord = data.get("coord", {})
        weather = data.get("weather", [{}])[0]
        main = data.get("main", {})
        wind = data.get("wind", {})
        tz_offset = data.get("timezone", 0)
        dt_utc = data.get("dt", None)
        sunrise = sys.get("sunrise")
        sunset = sys.get("sunset")

        # City label
        city_text = f"{name}, {country}" if country else name
        self.city_label.config(text=city_text)

        # Local time
        local_dt = get_local_time_from_offset(tz_offset)
        self.time_label.config(text=f"Local time: {local_dt.strftime('%A, %d %b %Y • %I:%M %p')}")

        # Icon
        icon_code = weather.get("icon", "")
        desc = weather.get("description", "—").capitalize()
        try:
            if icon_code:
                raw = fetch_image_bytes(icon_url(icon_code))
                img = Image.open(io.BytesIO(raw)).resize((120, 120))
                self.icon_img_ref = ImageTk.PhotoImage(img)
                self.icon_label.config(image=self.icon_img_ref)
            else:
                self.icon_label.config(image="", text="")
        except Exception:
            self.icon_label.config(image="", text="(no icon)")

        # Temperature block
        temp = main.get("temp")
        temp_unit = "°C" if self.units == "metric" else "°F"
        if temp is not None:
            self.temp_label.config(text=f"{round(temp)}{temp_unit}")
        else:
            self.temp_label.config(text="—")

        self.desc_label.config(text=f"{desc}")

        # Details
        feels = main.get("feels_like")
        hum = main.get("humidity")
        tmin = main.get("temp_min")
        tmax = main.get("temp_max")
        wind_speed = wind.get("speed")
        wind_unit = "m/s" if self.units == "metric" else "mph"

        self.detail_vars["feels"].set(f"{round(feels)}{temp_unit}" if feels is not None else "—")
        self.detail_vars["hum"].set(f"{hum}%" if hum is not None else "—")
        if wind_speed is not None:
            self.detail_vars["wind"].set(f"{wind_speed} {wind_unit}")
        else:
            self.detail_vars["wind"].set("—")
        if tmin is not None and tmax is not None:
            self.detail_vars["minmax"].set(f"{round(tmin)} / {round(tmax)} {temp_unit}")
        else:
            self.detail_vars["minmax"].set("—")

        # Sunrise/Sunset
        try:
            sr = get_local_time_from_offset(tz_offset, sunrise).strftime("%I:%M %p") if sunrise else "—"
            ss = get_local_time_from_offset(tz_offset, sunset).strftime("%I:%M %p") if sunset else "—"
            self.detail_vars["sun"].set(f"{sr} / {ss}")
        except Exception:
            self.detail_vars["sun"].set("—")

        # Coords
        self.detail_vars["coord"].set(f"{coord.get('lat', '—')}, {coord.get('lon', '—')}")

    def update_history(self, city):
        city = city.strip()
        if not city:
            return
        # Recent
        if city in self.history["recent"]:
            self.history["recent"].remove(city)
        self.history["recent"].insert(0, city)
        self.history["recent"] = self.history["recent"][:20]
        save_json(HISTORY_FILE, self.history)
        self.refresh_history_ui()

    def refresh_history_ui(self):
        self.recent_combo["values"] = self.history.get("recent", [])
        self.fav_combo["values"] = self.history.get("favorites", [])

    # ---------------- THEME ----------------
    def apply_theme(self):
        theme = self.themes[self.theme]
        # Root/bg
        self.configure(bg=theme["bg"])
        if hasattr(self, "bg_label") and self.bg_image_obj:
            # If background image used, don't recolor bg_label
            pass
        # Header
        self.header_frame.configure(bg=theme["bg"])
        self.header_title.configure(bg=theme["bg"], fg=theme["fg"])

        # Controls
        for w in (self.control_card,):
            w.configure(bg=theme["bg"])
        for w in self.control_card.winfo_children():
            try:
                if isinstance(w, tk.Entry):
                    w.configure(bg=theme["entry"], fg=theme["fg"], insertbackground=theme["fg"])
                elif isinstance(w, tk.Button) or isinstance(w, tk.Label) or isinstance(w, tk.Frame):
                    w.configure(bg=theme["bg"], fg=theme["fg"])
            except Exception:
                pass

        # Display
        for w in (self.display_card,):
            w.configure(bg=theme["bg"])
        for w in self.display_card.winfo_children():
            try:
                w.configure(bg=theme["bg"], fg=theme["fg"])
            except Exception:
                pass
        # Nested frames/labels
        def deep_set(widget):
            for child in widget.winfo_children():
                try:
                    if isinstance(child, tk.Label):
                        child.configure(bg=theme["bg"], fg=theme["fg"])
                    elif isinstance(child, tk.Frame):
                        child.configure(bg=theme["bg"])
                    elif isinstance(child, tk.Entry):
                        child.configure(bg=theme["entry"], fg=theme["fg"], insertbackground=theme["fg"])
                except Exception:
                    pass
                deep_set(child)
        deep_set(self.display_card)

# -------------------- RUN --------------------
if __name__ == "__main__":
    if not API_KEY:
        messagebox.showerror(
            "API Key Missing",
            "Please set your OpenWeather API key in the code (API_KEY) or as environment variable OPENWEATHER_API_KEY."
        )
    else:
        app = WeatherApp()
        app.mainloop()
