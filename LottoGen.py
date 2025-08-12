#!/usr/bin/env python3
# LottoGen v2.3.1
# - Help tab (How To + About)
# - Tooltips on key controls
# - Bonus (Top Prob) 4th line for Quick/Smart Pick (requires Update History)
# - Auto-fallback for history: WCLC → OLG → ALC
# - Frequency chart, copy/export, official sites dropdown

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import random, csv, os, threading, time, re, webbrowser
from datetime import datetime
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except Exception:
    requests = None
    BeautifulSoup = None

APP_NAME = "LottoGen"
APP_VER = "2.3.1"
PRIMARY_HEX = "#1172a1"
ACCENT = PRIMARY_HEX

OFFICIAL_SITES = {
    "OLG (Ontario)": "https://www.olg.ca/",
    "Loto‑Québec": "https://loteries.lotoquebec.com/fr/accueil",
    "ALC (Atlantic Lottery)": "https://www.alc.ca/",
    "BCLC (PlayNow)": "https://www.playnow.com/lottery/",
    "WCLC (Western Canada)": "https://www.wclc.com/winning-numbers.htm",
}

GAMES = {
    "Lotto 6/49": {
        "count": 6, "max_n": 49,
        "sources": [
            {"label":"WCLC", "urls":[
                "https://www.wclc.com/winning-numbers/lotto-649-extra.htm?channel=print",
                "https://www.wclc.com/winning-numbers/lotto-649-extra.htm?channel=print&printMode=true",
            ], "parser":"wclc"},
            {"label":"OLG", "urls":[
                "https://www.olg.ca/en/lottery/play-lotto-649-encore/past-results.html",
                "https://lottery.olg.ca/en-ca/winning-numbers/lotto-6-49",
            ], "parser":"generic"},
            {"label":"ALC", "urls":[
                "https://www.alc.ca/content/alc/en/winning-numbers.html",
            ], "parser":"generic"},
        ],
        "official_info": "https://www.olg.ca/en/lottery/play-lotto-649-encore/past-results.html",
    },
    "Lotto Max": {
        "count": 7, "max_n": 50,
        "sources": [
            {"label":"WCLC", "urls":[
                "https://www.wclc.com/winning-numbers/lotto-max-extra.htm?channel=print",
                "https://www.wclc.com/winning-numbers/lotto-max-extra.htm?channel=print&printMode=true",
            ], "parser":"wclc"},
            {"label":"OLG", "urls":[
                "https://www.olg.ca/en/lottery/play-lotto-max-encore/past-results.html",
                "https://lottery.olg.ca/en-ca/winning-numbers/lotto-max",
            ], "parser":"generic"},
            {"label":"ALC", "urls":[
                "https://www.alc.ca/content/alc/en/winning-numbers.html",
            ], "parser":"generic"},
        ],
        "official_info": "https://www.olg.ca/en/lottery/play-lotto-max-encore/past-results.html",
    },
}

DEFAULT_LINES = 3
SAVE_HISTORY_BY_DEFAULT = False

DATA_DIR = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")
os.makedirs(DATA_DIR, exist_ok=True)
HISTORY_CSV = os.path.join(DATA_DIR, "history.csv")

# ---------- Utils & parsing ----------
DATE_PATTERNS = ["%A %B %d %Y","%A, %B %d, %Y","%B %d, %Y"]

def try_parse_date(text):
    t = re.sub(r",", "", text).strip()
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except Exception:
            pass
    return None

def dedupe_by_date(draws):
    uniq = {}
    for d, main, bonus in draws:
        uniq[d] = (main, bonus)
    return [(d, *uniq[d]) for d in sorted(uniq.keys())]

def parse_wclc_print(soup, max_n, count):
    text = soup.get_text(" ", strip=True)
    month_re = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    parts = re.split(month_re, text)
    draws = []
    for i in range(1, len(parts), 2):
        month = parts[i]
        rest = parts[i+1] if i+1 < len(parts) else ""
        block = f"{month}{rest}"
        mdate = re.search(rf"{month}\s+\d{{1,2}},?\s+\d{{4}}", block)
        if not mdate: 
            continue
        date_iso = try_parse_date(mdate.group(0))
        nums = [int(n) for n in re.findall(r"\b\d{1,2}\b", block) if 1 <= int(n) <= max_n]
        if len(nums) >= count:
            main = nums[:count]
            bonus = nums[count] if len(nums) > count else None
            draws.append((date_iso, main, bonus))
    return dedupe_by_date(draws)

def parse_generic_tables(soup, max_n, count):
    draws = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td","th"])]
            if not cells:
                continue
            date_iso = None
            for c in cells:
                date_iso = try_parse_date(c)
                if date_iso:
                    break
            if not date_iso:
                continue
            nums = []
            for c in cells:
                nums += [int(n) for n in re.findall(r"\b\d{1,2}\b", c) if 1 <= int(n) <= max_n]
            seen, cleaned = set(), []
            for v in nums:
                if v not in seen:
                    seen.add(v); cleaned.append(v)
            if len(cleaned) >= count:
                main = cleaned[:count]
                bonus = cleaned[count] if len(cleaned) > count else None
                draws.append((date_iso, main, bonus))
    return dedupe_by_date(draws)

def fetch_archives_with_fallback(game_key, progress_cb=None):
    cfg = GAMES[game_key]
    if requests is None or BeautifulSoup is None:
        return [], "offline"
    headers = {"User-Agent": f"{APP_NAME}/{APP_VER}"}
    for group in cfg["sources"]:
        label = group["label"]
        parser = group["parser"]
        all_draws = []
        for url in group["urls"]:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    if progress_cb: progress_cb(f"[{label}] Skip {url} (HTTP {resp.status_code})")
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                parsed = parse_wclc_print(soup, cfg["max_n"], cfg["count"]) if parser=="wclc" else parse_generic_tables(soup, cfg["max_n"], cfg["count"])
                if progress_cb: progress_cb(f"[{label}] Parsed {len(parsed)} draws from {urlparse(url).netloc}")
                all_draws.extend(parsed)
                time.sleep(0.2)
            except Exception as e:
                if progress_cb: progress_cb(f"[{label}] Error {url}: {e}")
        all_draws = dedupe_by_date(all_draws)
        if all_draws:
            return all_draws, label
    return [], "none"

# ---------- Stats & picks ----------
def compute_stats(draws, max_n, count, lookback=None):
    if not draws: return {}
    if lookback: draws = draws[-lookback:]
    freq = [0]*(max_n+1)
    last_seen = [None]*(max_n+1)
    i = 0
    for d, main, bonus in draws:
        i += 1
        for n in main:
            freq[n] += 1
            last_seen[n] = i
    cur = i + 1
    overdue = [(n, (cur - last_seen[n]) if last_seen[n] is not None else cur) for n in range(1, max_n+1)]
    overdue.sort(key=lambda x: x[1], reverse=True)
    hot = sorted([(n, freq[n]) for n in range(1, max_n+1)], key=lambda x: x[1], reverse=True)
    cold = sorted([(n, freq[n]) for n in range(1, max_n+1)], key=lambda x: x[1])
    return {"freq":freq, "last_seen":last_seen, "hot":hot, "cold":cold, "overdue":overdue, "sample_size":i}

def smart_weight(stats, max_n, flavor="balanced"):
    base = [1.0]*(max_n+1)
    hot_rank = {n:i+1 for i,(n,_) in enumerate(stats["hot"])}
    overdue_rank = {n:i+1 for i,(n,_) in enumerate(stats["overdue"])}
    for n in range(1, max_n+1):
        hr = (len(hot_rank)+1 - hot_rank[n]) / len(hot_rank)
        orank = (len(overdue_rank)+1 - overdue_rank[n]) / len(overdue_rank)
        if flavor == "hot":
            base[n] += 2.0*hr + 0.5*orank
        elif flavor == "overdue":
            base[n] += 2.0*orank + 0.5*hr
        else:
            base[n] += 1.0*hr + 1.0*orank
    return base

def smart_pick(stats, max_n, count, flavor="balanced"):
    base = smart_weight(stats, max_n, flavor)
    picks = set()
    while len(picks) < count:
        i = random.choices(range(1, max_n+1), weights=base[1:], k=1)[0]
        picks.add(i); base[i] = 0.0
    return sorted(picks)

def top_probability_line(stats, max_n, count, flavor="balanced"):
    base = smart_weight(stats, max_n, flavor)
    ranking = sorted(range(1, max_n+1), key=lambda n: base[n], reverse=True)
    line = sorted(ranking[:count])
    return line

# ---------- ToolTip ----------
class ToolTip:
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tw = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._unschedule)
        widget.bind("<ButtonPress>", self._unschedule)
    def _schedule(self, _=None):
        self._unschedule()
        self.after_id = self.widget.after(self.delay, self._show)
    def _unschedule(self, _=None):
        if self.after_id: self.widget.after_cancel(self.after_id); self.after_id=None
        if self.tw: self.tw.destroy(); self.tw=None
    def _show(self):
        if self.tw or not self.text: return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tw, text=self.text, bg="#ffffe0", relief="solid", borderwidth=1, font=("Segoe UI",9)).pack(ipadx=6, ipady=4)

# ---------- GUI ----------
class LottoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VER}")
        self.geometry("1000x740"); self.minsize(900, 640); self.configure(bg="white")

        self.save_history = tk.BooleanVar(value=SAVE_HISTORY_BY_DEFAULT)
        self.lookback_var = tk.StringVar(value="All")
        self.flavor_var = tk.StringVar(value="balanced")
        self.site_var = tk.StringVar(value=list(OFFICIAL_SITES.keys())[0])

        self.draw_cache = {k: [] for k in GAMES.keys()}
        self.stats_cache = {k: None for k in GAMES.keys()}

        self.style = ttk.Style(self); self._setup_theme(); self._build_ui()

    def _setup_theme(self):
        try: self.style.theme_use("clam")
        except tk.TclError: pass
        self.style.configure("TNotebook.Tab", padding=[16,8])
        self.style.configure("Accent.TButton", background=ACCENT, foreground="white")
        self.style.map("Accent.TButton", background=[("active", ACCENT), ("pressed", ACCENT)], foreground=[("active","white"),("pressed","white")])

    def _build_ui(self):
        header = tk.Frame(self, bg=ACCENT, height=64); header.pack(fill="x", side="top")
        tk.Label(header, text="LottoGen", fg="white", bg=ACCENT, font=("Segoe UI", 18, "bold")).pack(side="left", padx=16, pady=12)
        tk.Label(header, text="Lotto 6/49 & Lotto Max number generator with smart picks", fg="white", bg=ACCENT, font=("Segoe UI", 10)).pack(side="left", padx=6, pady=12)

        links = tk.Frame(self, bg="#eef6fb"); links.pack(fill="x", padx=0, pady=(0,6))
        tk.Label(links, text="Official sites:", bg="#eef6fb").pack(side="left", padx=(12,6), pady=6)
        cbo = ttk.Combobox(links, textvariable=self.site_var, values=list(OFFICIAL_SITES.keys()), width=32, state="readonly"); cbo.pack(side="left", padx=4, pady=6)
        btn_open = ttk.Button(links, text="Open", command=self.open_selected_site); btn_open.pack(side="left", padx=4, pady=6)
        ToolTip(cbo, "Choose an official site to open in your browser."); ToolTip(btn_open, "Open the selected official site.")

        controls = tk.Frame(self, bg="white"); controls.pack(fill="x", padx=16, pady=8)
        tk.Label(controls, text="Smart pick style:").pack(side="left")
        style_cbo = ttk.Combobox(controls, textvariable=self.flavor_var, width=12, values=["balanced","hot","overdue"], state="readonly"); style_cbo.pack(side="left", padx=6)
        ToolTip(style_cbo, "Balanced blends hot and overdue; Hot favors frequent; Overdue favors gaps.")
        tk.Label(controls, text="Lookback:").pack(side="left", padx=(16,0))
        look_cbo = ttk.Combobox(controls, textvariable=self.lookback_var, width=10, values=["All","100","250","500","1000"], state="readonly"); look_cbo.pack(side="left", padx=6)
        ToolTip(look_cbo, "Analyze only the most recent N draws, or All.")
        chk = ttk.Checkbutton(controls, text="Save generations to CSV", variable=self.save_history); chk.pack(side="left", padx=(16,0))
        ToolTip(chk, "If enabled, every generated line is saved to %USERPROFILE%\\.lottogen\\history.csv")
        btn_update = ttk.Button(controls, text="Update History", command=self.update_history, style="Accent.TButton"); btn_update.pack(side="right")
        ToolTip(btn_update, "Fetch past results (WCLC → OLG → ALC) and compute stats.")
        btn_odds = ttk.Button(controls, text="About Odds", command=self.show_odds); btn_odds.pack(side="right", padx=8)
        ToolTip(btn_odds, "Show jackpot/overall odds (reminder: play for fun).")

        self.tabs = ttk.Notebook(self); self.tabs.pack(fill="both", expand=True, padx=12, pady=8)
        for game in GAMES.keys():
            frm = tk.Frame(self.tabs, bg="white"); self.tabs.add(frm, text=game); self._build_game_tab(frm, game)

        self.analysis_tab = tk.Frame(self.tabs, bg="white"); self.tabs.add(self.analysis_tab, text="Analysis"); self._build_analysis_tab(self.analysis_tab)
        self.help_tab = tk.Frame(self.tabs, bg="white"); self.tabs.add(self.help_tab, text="Help"); self._build_help_tab(self.help_tab)
        self.history_tab = tk.Frame(self.tabs, bg="white"); self.tabs.add(self.history_tab, text="Saved History"); self._build_history_tab(self.history_tab)

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self.status_var, anchor="w", bg="#f4f6f8").pack(fill="x", side="bottom")

    def open_selected_site(self):
        site = self.site_var.get(); url = OFFICIAL_SITES.get(site)
        if url: webbrowser.open(url)

    def _build_game_tab(self, root, game):
        top = tk.Frame(root, bg="white"); top.pack(fill="x", padx=12, pady=10)
        btn_quick = ttk.Button(top, text="Quick Pick (3+Bonus)", command=lambda g=game: self.generate_quick_with_bonus(g), style="Accent.TButton"); btn_quick.pack(side="left")
        ToolTip(btn_quick, "Generate 3 random lines + a Bonus (Top Prob) line (needs Update History).")
        btn_smart = ttk.Button(top, text="Smart Pick (3+Bonus)", command=lambda g=game: self.generate_smart_with_bonus(g), style="Accent.TButton"); btn_smart.pack(side="left", padx=10)
        ToolTip(btn_smart, "Generate 3 stat-weighted lines + a Bonus (Top Prob) line (needs Update History).")
        btn_copy = ttk.Button(top, text="Copy All", command=lambda g=game: self.copy_all(g)); btn_copy.pack(side="left"); ToolTip(btn_copy, "Copy all lines to clipboard.")
        btn_export = ttk.Button(top, text="Export CSV", command=lambda g=game: self.export_csv(g)); btn_export.pack(side="left", padx=6); ToolTip(btn_export, "Save lines to CSV.")
        btn_open_game = ttk.Button(top, text="Open game page", command=lambda g=game: webbrowser.open(GAMES[g]['official_info'])); btn_open_game.pack(side="right")

        cols = ("Row", "Numbers")
        tree = ttk.Treeview(root, columns=cols, show="headings", height=14, selectmode="extended")
        tree.heading("#1", text="Row"); tree.heading("#2", text="Numbers")
        tree.column("#1", width=120, anchor="center"); tree.column("#2", width=640, anchor="w")
        tree.pack(fill="both", expand=True, padx=12, pady=8)
        tree.bind("<Double-1>", lambda e, g=game: self.copy_selected(g, silent=True))
        tree.bind("<Button-3>", lambda e, g=game: self._show_context_menu(e, g))
        setattr(self, f"tree_{game}", tree)

    def _show_context_menu(self, event, game):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Copy Selected", command=lambda g=game: self.copy_selected(g))
        menu.add_command(label="Copy All", command=lambda g=game: self.copy_all(g))
        menu.tk_popup(event.x_root, event.y_root)

    def _build_analysis_tab(self, root):
        info = tk.Frame(root, bg="white"); info.pack(fill="x", padx=12, pady=10)
        ttk.Label(info, text="Update history, then view stats below.").pack(side="left")
        chart_controls = tk.Frame(root, bg="white"); chart_controls.pack(fill="x", padx=12, pady=(0,6))
        ttk.Label(chart_controls, text="Chart game:").pack(side="left")
        self.chart_game_var = tk.StringVar(value=list(GAMES.keys())[0])
        cbo_chart = ttk.Combobox(chart_controls, textvariable=self.chart_game_var, values=list(GAMES.keys()), width=14, state="readonly"); cbo_chart.pack(side="left", padx=6)
        ToolTip(cbo_chart, "Choose which game’s frequency to visualize.")
        btn_chart = ttk.Button(chart_controls, text="Show Frequency Chart", command=self.draw_chart, style="Accent.TButton"); btn_chart.pack(side="left", padx=8)
        ToolTip(btn_chart, "Draw a bar chart of number frequencies from Update History.")
        self.analysis_text = tk.Text(root, height=12, bg="#fbfdff"); self.analysis_text.pack(fill="x", expand=False, padx=12, pady=8); self.analysis_text.insert("end", "No data yet.\n")
        chart_frame = tk.Frame(root, bg="white"); chart_frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.chart_canvas = tk.Canvas(chart_frame, bg="#ffffff", height=240, highlightthickness=1, highlightbackground="#e0e0e0"); self.chart_canvas.pack(fill="both", expand=True)

    def _build_help_tab(self, root):
        wrapper = ttk.Notebook(root); wrapper.pack(fill="both", expand=True, padx=12, pady=12)
        howto = tk.Frame(wrapper, bg="white"); wrapper.add(howto, text="How To")
        txt = tk.Text(howto, wrap="word", bg="#fbfdff"); txt.pack(fill="both", expand=True, padx=8, pady=8)
        howto_steps = (
            "HOW TO USE LOTTOGEN\n\n"
            "1) Pick Lotto 6/49 or Lotto Max.\n"
            "2) Click Quick Pick (3+Bonus) for 3 random lines + a Bonus (Top Prob) line.\n"
            "   • Or Smart Pick (3+Bonus) to use stats (Balanced/Hot/Overdue).\n"
            "3) Click Update History to fetch past results. The app tries WCLC → OLG → ALC.\n"
            "   • Use Lookback to limit analysis to recent draws.\n"
            "4) View the Frequency Chart on the Analysis tab.\n"
            "5) Copy or Export your lines. Enable 'Save generations to CSV' if you want logging.\n"
            "Note: Bonus (Top Prob) is based on current stats; run Update History first.\n"
        ); txt.insert("end", howto_steps); txt.configure(state="disabled")
        about = tk.Frame(wrapper, bg="white"); wrapper.add(about, text="About")
        tk.Label(about, text="Copyright © 2025 SERC Professional Services\nBuilt with ChatGPT-5", bg="white", font=("Segoe UI", 11)).pack(pady=12)

    def _build_history_tab(self, root):
        top = tk.Frame(root, bg="white"); top.pack(fill="x", padx=12, pady=10)
        ttk.Button(top, text="Open history.csv", command=self.open_history).pack(side="left")
        ttk.Button(top, text="Import CSV...", command=self.import_csv).pack(side="left", padx=6)
        cols = ("timestamp","game","method","line")
        tree = ttk.Treeview(root, columns=cols, show="headings", height=14)
        for i, c in enumerate(cols, start=1):
            tree.heading(f"#{i}", text=c); tree.column(f"#{i}", width=180 if i==1 else 120 if i<4 else 460, anchor="w")
        tree.pack(fill="both", expand=True, padx=12, pady=8); self.history_tree = tree; self.refresh_history_view()

    # -------- Actions --------
    def generate_quick_with_bonus(self, game):
        cfg = GAMES[game]
        rnd = random.Random()
        lines = [sorted(rnd.sample(range(1, cfg['max_n']+1), cfg['count'])) for _ in range(3)]
        bonus_line = None
        stats = self.stats_cache.get(game)
        if stats:
            bonus_line = top_probability_line(stats, cfg["max_n"], cfg["count"], flavor="balanced")
        self._display_lines_with_bonus(game, lines, bonus_line, method="Quick Pick")
        if not stats:
            self.set_status("Generated 3 lines. Bonus requires Update History.")

    def generate_smart_with_bonus(self, game):
        cfg = GAMES[game]
        stats = self.stats_cache.get(game)
        if not stats:
            messagebox.showwarning("No data", "Please click Update History first to compute stats."); return
        flavor = self.flavor_var.get()
        lines = [smart_pick(stats, cfg["max_n"], cfg["count"], flavor=flavor) for _ in range(3)]
        bonus_line = top_probability_line(stats, cfg["max_n"], cfg["count"], flavor=flavor)
        self._display_lines_with_bonus(game, lines, bonus_line, method=f"Smart:{flavor}")

    def _display_lines_with_bonus(self, game, lines, bonus_line, method):
        tree = getattr(self, f"tree_{game}")
        for i in tree.get_children(): tree.delete(i)
        for idx, line in enumerate(lines, start=1):
            tree.insert("", "end", values=(f"Line {idx}", " ".join(f"{n:02d}" for n in line)))
        if bonus_line:
            tree.insert("", "end", values=("Bonus (Top Prob)", " ".join(f"{n:02d}" for n in bonus_line)))
        if self.save_history.get():
            all_lines = lines + ([bonus_line] if bonus_line else [])
            self._append_history(game, all_lines, method)
            self.refresh_history_view()
        self.set_status(f"Generated {len(lines)} line(s){' + Bonus' if bonus_line else ''} for {game} — {method}")

    def _append_history(self, game, picks_list, method):
        newfile = not os.path.exists(HISTORY_CSV)
        with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if newfile: w.writerow(["timestamp","app_ver","game","method","seed","line"])
            ts = datetime.now().isoformat(timespec="seconds")
            for line in picks_list:
                w.writerow([ts, APP_VER, game, method, "", " ".join(map(str, line))])

    def copy_selected(self, game, silent=False):
        txt = self._collect_selected(game)
        if not txt: return
        self.clipboard_clear(); self.clipboard_append(txt)
        if not silent: self.set_status("Copied selected line(s) to clipboard")

    def copy_all(self, game):
        tree = getattr(self, f"tree_{game}")
        out = []
        for it in tree.get_children():
            _, nums = tree.item(it, "values"); out.append(str(nums))
        if not out: return
        self.clipboard_clear(); self.clipboard_append("\n".join(out)); self.set_status("Copied all lines to clipboard")

    def _collect_selected(self, game):
        tree = getattr(self, f"tree_{game}")
        items = tree.selection() or tree.get_children()
        out = []
        for it in items:
            _, nums = tree.item(it, "values"); out.append(str(nums))
        return "\n".join(out)

    def export_csv(self, game):
        tree = getattr(self, f"tree_{game}"); rows = []
        for item in tree.get_children():
            row, nums = tree.item(item, "values"); rows.append((row, nums))
        if not rows: messagebox.showinfo("Nothing to export", "Generate some numbers first."); return
        fp = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if not fp: return
        with open(fp, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["row","numbers"])
            for row, nums in rows: w.writerow([row, nums])
        self.set_status(f"Exported {len(rows)} rows to {os.path.basename(fp)}")

    def show_odds(self):
        msg = (
            "Lotto 6/49: selects 6 numbers from 1–49.\n"
            "Jackpot odds: 1 in 13,983,816; overall odds ~1 in 6.6.\n\n"
            "Lotto Max: selects 7 numbers from 1–50 (+bonus for secondary prizes).\n"
            "Jackpot odds per line: about 1 in 33,294,800.\n\n"
            "Smart Picks use historical frequencies and 'overdue' gaps to weight numbers.\n"
            "This does NOT change true odds. Play responsibly."
        )
        messagebox.showinfo("Odds & Info", msg)

    def open_history(self):
        if not os.path.exists(HISTORY_CSV): messagebox.showinfo("History", "No history yet."); return
        try: os.startfile(HISTORY_CSV)
        except Exception: webbrowser.open("file://" + HISTORY_CSV.replace("\\","/"))

    def import_csv(self):
        fp = filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
        if not fp: return
        messagebox.showinfo("Import", "Import complete (placeholder).")

    def refresh_history_view(self):
        tree = self.history_tree
        for item in tree.get_children(): tree.delete(item)
        if not os.path.exists(HISTORY_CSV): return
        with open(HISTORY_CSV, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f); rows = list(r)[-200:]
        for row in rows: tree.insert("", "end", values=(row["timestamp"], row["game"], row["method"], row["line"]))

    def update_history(self):
        self.set_status("Fetching past results (WCLC → OLG → ALC)...")
        self.analysis_text.delete("1.0","end"); self.analysis_text.insert("end", "Updating...\n")
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self):
        try:
            for game in GAMES.keys():
                self._log(f"--- {game} ---")
                draws, source_label = fetch_archives_with_fallback(game, progress_cb=lambda m: self._log(m))
                self.draw_cache[game] = draws
                if source_label == "none" or not draws:
                    self._log(f"No draws found from any source for {game}.")
                    self.stats_cache[game] = None
                    continue
                self._log(f"Using source: {source_label} — {len(draws)} draws total after dedupe.")
                stats = compute_stats(draws, GAMES[game]["max_n"], GAMES[game]["count"], lookback=self._get_lookback())
                self.stats_cache[game] = stats; self._log_stats(game, stats)
            self.set_status("Update complete.")
        except Exception as e:
            self.set_status(f"Update failed: {e}")

    def _get_lookback(self):
        v = self.lookback_var.get(); return None if v == "All" else int(v)

    def _log(self, line): self.analysis_text.insert("end", line + "\n"); self.analysis_text.see("end")

    def _log_stats(self, game, stats):
        if not stats: self._log(f"{game}: no stats available."); return
        self._log(f"{game}: sample size = {stats['sample_size']} draws.")
        hot10 = ", ".join(f"{n}({c})" for n,c in stats["hot"][:10])
        cold10 = ", ".join(f"{n}({c})" for n,c in stats["cold"][:10])
        over10 = ", ".join(f"{n}" for n,_ in stats["overdue"][:10])
        self._log(f"{game} HOT (top10): {hot10}")
        self._log(f"{game} COLD (bottom10): {cold10}")
        self._log(f"{game} OVERDUE (top10): {over10}")

    def draw_chart(self):
        game = self.chart_game_var.get(); stats = self.stats_cache.get(game)
        if not stats: messagebox.showwarning("No data", "Please click Update History first."); return
        freq = stats["freq"]; max_n = GAMES[game]["max_n"]; c = self.chart_canvas
        c.delete("all"); w = c.winfo_width() or 800; h = c.winfo_height() or 240
        padding = 40; chart_w = w - padding*2; chart_h = h - padding*2
        max_f = max(freq[1:max_n+1]) or 1; bar_w = chart_w / max_n
        c.create_line(padding, h-padding, w-padding, h-padding, fill="#666"); c.create_line(padding, padding, padding, h-padding, fill="#666")
        for i in range(1, max_n+1):
            x0 = padding + (i-1)*bar_w + 1; x1 = padding + i*bar_w - 1
            bh = (freq[i]/max_f) * chart_h; y0 = h - padding - bh; y1 = h - padding
            c.create_rectangle(x0, y0, x1, y1, fill=ACCENT, outline="")
            if i % 5 == 0 or i == 1 or i == max_n: c.create_text((x0+x1)/2, h-padding+12, text=str(i), font=("Segoe UI", 8))
        c.create_text(w/2, 14, text=f"{game} Frequency (lookback={self.lookback_var.get()})", font=("Segoe UI", 10, "bold"))
        c.create_text(padding-16, h-padding, text="0", font=("Segoe UI", 8)); c.create_text(padding-16, padding, text=str(max_f), font=("Segoe UI", 8))

    def set_status(self, txt):
        self.status_var.set(txt); self.title(f"{APP_NAME} {APP_VER} — {txt}")

def main():
    app = LottoApp(); app.mainloop()

if __name__ == "__main__":
    main()
