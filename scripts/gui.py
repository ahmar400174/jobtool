"""Job Finder — polished desktop UI launched by start.bat."""

from __future__ import annotations

import sys
import threading
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import Canvas, StringVar, BooleanVar, Tk, messagebox
from typing import Any

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from job_finder.source_catalog import SOURCES
from job_finder.countries import COUNTRIES, normalize_country, jobicy_geo

# ── Visual system ──────────────────────────────────────────────────────────
# Deep slate + electric teal — career/opportunity feel, not generic purple/AI.
C = {
    "bg": "#0c1220",
    "bg2": "#121a2b",
    "panel": "#162033",
    "panel2": "#1a2740",
    "border": "#243049",
    "border_hi": "#2f4060",
    "text": "#e8eef8",
    "muted": "#8b9bb8",
    "dim": "#5a6a86",
    "accent": "#1ec8a5",
    "accent2": "#14a88a",
    "accent_dim": "#0d3d36",
    "warn": "#f0b429",
    "danger": "#f07178",
    "ok": "#7ee787",
    "input_bg": "#0e1624",
    "chip": "#1e2d45",
}


class JobFinderApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Job Finder")
        self.root.configure(bg=C["bg"])
        self.root.minsize(720, 640)
        self.root.geometry("900x900")
        self.root.eval("tk::PlaceWindow . center")

        self.project_dir = Path(__file__).resolve().parent.parent
        self.settings_file = self.project_dir / "config" / "settings.yaml"
        self.settings = self.load_settings()
        self.running = False
        self.last_path: Path | None = None
        self._pulse_job: str | None = None
        self._pulse_phase = 0

        search = self.settings.get("search", {}) or {}
        sources = self.settings.get("sources", {}) or {}
        keywords = search.get("keywords") or ["QA Engineer"]
        default_prof = keywords[0] if keywords else "QA Engineer"
        default_start = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")

        self.prof_var = StringVar(value=default_prof)
        self.country_var = StringVar(value=normalize_country(search.get("location", "United States")))
        self.start_date_var = StringVar(value=search.get("start_date", default_start))
        self.end_date_var = StringVar(
            value=search.get("end_date", datetime.today().strftime("%Y-%m-%d"))
        )
        self.remote_var = BooleanVar(value=bool(search.get("remote_only", True)))
        self.exclude_pk_var = BooleanVar(value=bool(search.get("exclude_pakistan", True)))
        self.source_vars = {
            key: BooleanVar(value=bool((sources.get(key) or {}).get("enabled", default)))
            for key, label, default in SOURCES
        }

        self.status_var = StringVar(value="Ready to search")
        self.detail_var = StringVar(value="Set your role and location, then hit Search.")

        self._build()

    # ── Settings I/O ───────────────────────────────────────────────────────
    def load_settings(self) -> dict[str, Any]:
        try:
            with open(self.settings_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_settings(self) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.settings_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.settings, f, sort_keys=False)

    # ── UI construction ───────────────────────────────────────────────────
    def _build(self) -> None:
        # Ambient header band
        header = Canvas(self.root, height=118, bg=C["bg"], highlightthickness=0, bd=0)
        header.pack(fill="x")
        self._draw_header(header)

        body = Canvas(self.root, bg=C["bg"], highlightthickness=0, bd=0)
        body.pack(fill="both", expand=True, padx=28, pady=(8, 20))

        # Inner content frame via window embedding for layout simplicity
        from tkinter import Frame, Scrollbar

        body_scroll = Scrollbar(body, command=body.yview)
        body_scroll.pack(side="right", fill="y")
        body.configure(yscrollcommand=body_scroll.set)
        body.bind("<MouseWheel>", lambda e: body.yview_scroll(int(-e.delta / 120), "units"))

        content = Frame(body, bg=C["bg"])
        body.create_window(0, 0, anchor="nw", window=content, tags="content")

        def _sync(_event=None) -> None:
            body.configure(scrollregion=body.bbox("all"))
            body.itemconfigure("content", width=max(1, body.winfo_width() - body_scroll.winfo_width()))

        body.bind("<Configure>", _sync)
        content.bind("<Configure>", _sync)

        # Form panel
        panel = Frame(content, bg=C["panel"], highlightbackground=C["border"], highlightthickness=1)
        panel.pack(fill="x", pady=(0, 16))

        pad = Frame(panel, bg=C["panel"])
        pad.pack(fill="x", padx=22, pady=20)

        self._section_label(pad, "SEARCH CRITERIA").pack(anchor="w", pady=(0, 14))

        grid = Frame(pad, bg=C["panel"])
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self._field(grid, "Profession / role", self.prof_var, "e.g. QA Engineer, MERN stack").grid(
            row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 14)
        )
        self._country_dropdown(grid).grid(
            row=0, column=1, sticky="ew", padx=(10, 0), pady=(0, 14)
        )
        self._field(grid, "Start date", self.start_date_var, "YYYY-MM-DD").grid(
            row=1, column=0, sticky="ew", padx=(0, 10), pady=(0, 4)
        )
        self._field(grid, "End date", self.end_date_var, "YYYY-MM-DD").grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=(0, 4)
        )

        # Filters row
        filters = Frame(pad, bg=C["panel"])
        filters.pack(fill="x", pady=(16, 0))
        self._section_label(filters, "FILTERS").pack(anchor="w", pady=(0, 10))

        chips = Frame(filters, bg=C["panel"])
        chips.pack(fill="x")
        self._chip(chips, "Remote only", self.remote_var).pack(side="left", padx=(0, 8))
        self._chip(chips, "Exclude Pakistan", self.exclude_pk_var).pack(side="left", padx=(0, 8))

        # Sources
        src_wrap = Frame(pad, bg=C["panel"])
        src_wrap.pack(fill="x", pady=(18, 0))
        src_header = Frame(src_wrap, bg=C["panel"])
        src_header.pack(fill="x", pady=(0, 10))
        self._section_label(src_header, "SOURCES").pack(side="left")
        self._ghost_button(src_header, "Select all platforms", self.select_all_sources).pack(side="right")

        src_row = Frame(src_wrap, bg=C["panel"])
        src_row.pack(fill="x")
        for index, (key, label, default) in enumerate(SOURCES):
            self._chip(src_row, label, self.source_vars[key]).grid(
                row=index // 3, column=index % 3, sticky="w", padx=(0, 8), pady=(0, 6)
            )
        from tkinter import Label
        Label(src_wrap, text="Some job boards may require sign-in or limit public listing access.",
              bg=C["panel"], fg=C["muted"], font=("Segoe UI", 9), wraplength=680,
              justify="left").pack(anchor="w", pady=(4, 0))

        # CTA
        cta_row = Frame(content, bg=C["bg"])
        cta_row.pack(fill="x", pady=(0, 16))

        self.search_btn = self._primary_button(cta_row, "Search Jobs", self.on_search)
        self.search_btn.pack(side="left")

        self.open_btn = self._ghost_button(cta_row, "Open Excel", self.open_excel)
        self.open_btn.pack(side="left", padx=(12, 0))
        self.open_btn.configure(state="disabled")

        # Status panel
        status_panel = Frame(
            content, bg=C["panel2"], highlightbackground=C["border"], highlightthickness=1
        )
        status_panel.pack(fill="both", expand=True)

        status_inner = Frame(status_panel, bg=C["panel2"])
        status_inner.pack(fill="both", expand=True, padx=22, pady=18)

        top_status = Frame(status_inner, bg=C["panel2"])
        top_status.pack(fill="x", pady=(0, 10))

        self.pulse = Canvas(top_status, width=14, height=14, bg=C["panel2"], highlightthickness=0)
        self.pulse.pack(side="left", padx=(0, 10))
        self._draw_pulse(C["accent"])

        from tkinter import Label

        Label(
            top_status,
            textvariable=self.status_var,
            bg=C["panel2"],
            fg=C["text"],
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        Label(
            status_inner,
            textvariable=self.detail_var,
            bg=C["panel2"],
            fg=C["muted"],
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            wraplength=680,
        ).pack(fill="x", pady=(0, 12))

        # Log area
        log_frame = Frame(status_inner, bg=C["input_bg"], highlightbackground=C["border"], highlightthickness=1)
        log_frame.pack(fill="both", expand=True)

        from tkinter import Text, Scrollbar

        self.log = Text(
            log_frame,
            height=10,
            bg=C["input_bg"],
            fg=C["muted"],
            insertbackground=C["text"],
            font=("Cascadia Mono", 9) if self._font_exists("Cascadia Mono") else ("Consolas", 9),
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            wrap="word",
            state="disabled",
            highlightthickness=0,
        )
        scroll = Scrollbar(log_frame, command=self.log.yview, troughcolor=C["input_bg"], bg=C["border"])
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.log.tag_configure("info", foreground=C["muted"])
        self.log.tag_configure("ok", foreground=C["ok"])
        self.log.tag_configure("warn", foreground=C["warn"])
        self.log.tag_configure("err", foreground=C["danger"])
        self.log.tag_configure("accent", foreground=C["accent"])

        self._log("Job Finder ready. Configure search and click Search Jobs.", "accent")

    def _draw_header(self, canvas: Canvas) -> None:
        w = 900
        canvas.create_rectangle(0, 0, w, 118, fill=C["bg2"], outline="")
        # Teal glow band
        canvas.create_rectangle(0, 0, w, 3, fill=C["accent"], outline="")
        # Soft accent blob (left)
        canvas.create_oval(-40, 40, 120, 160, fill=C["accent_dim"], outline="")
        canvas.create_text(
            28,
            36,
            anchor="w",
            text="JOB FINDER",
            fill=C["accent"],
            font=("Segoe UI", 11, "bold"),
        )
        canvas.create_text(
            28,
            68,
            anchor="w",
            text="Find remote roles that fit.",
            fill=C["text"],
            font=("Segoe UI Semibold", 20),
        )
        canvas.create_text(
            28,
            96,
            anchor="w",
            text="Multi-source search · Excel export · one click",
            fill=C["dim"],
            font=("Segoe UI", 9),
        )

        def _resize(event) -> None:
            canvas.delete("all")
            canvas.create_rectangle(0, 0, event.width, 118, fill=C["bg2"], outline="")
            canvas.create_rectangle(0, 0, event.width, 3, fill=C["accent"], outline="")
            canvas.create_oval(-40, 40, 120, 160, fill=C["accent_dim"], outline="")
            canvas.create_text(
                28, 36, anchor="w", text="JOB FINDER", fill=C["accent"], font=("Segoe UI", 11, "bold")
            )
            canvas.create_text(
                28,
                68,
                anchor="w",
                text="Find remote roles that fit.",
                fill=C["text"],
                font=("Segoe UI Semibold", 20),
            )
            canvas.create_text(
                28,
                96,
                anchor="w",
                text="Multi-source search · Excel export · one click",
                fill=C["dim"],
                font=("Segoe UI", 9),
            )

        canvas.bind("<Configure>", _resize)

    def _section_label(self, parent, text: str):
        from tkinter import Label

        return Label(
            parent,
            text=text,
            bg=parent["bg"],
            fg=C["dim"],
            font=("Segoe UI", 8, "bold"),
        )

    def _field(self, parent, label: str, var: StringVar, placeholder: str = ""):
        from tkinter import Frame, Label, Entry

        wrap = Frame(parent, bg=C["panel"])
        Label(wrap, text=label.upper(), bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8, "bold")).pack(
            anchor="w", pady=(0, 6)
        )
        entry = Entry(
            wrap,
            textvariable=var,
            bg=C["input_bg"],
            fg=C["text"],
            insertbackground=C["accent"],
            relief="flat",
            font=("Segoe UI", 11),
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
        )
        entry.pack(fill="x", ipady=8, ipadx=8)
        if placeholder and not var.get():
            var.set(placeholder)
        return wrap

    def _country_dropdown(self, parent):
        from tkinter import Frame, Label, ttk

        wrap = Frame(parent, bg=C["panel"])
        Label(wrap, text="COUNTRY / REGION", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8, "bold")).pack(
            anchor="w", pady=(0, 6)
        )
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Country.TCombobox", fieldbackground=C["input_bg"], background=C["panel2"],
                        foreground=C["text"], arrowcolor=C["accent"], padding=8)
        style.map("Country.TCombobox", fieldbackground=[("readonly", C["input_bg"])],
                  foreground=[("readonly", C["text"])], selectbackground=[("readonly", C["input_bg"])],
                  selectforeground=[("readonly", C["text"])])
        self.root.option_add("*TCombobox*Listbox.background", C["input_bg"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["accent2"])
        choices = COUNTRIES
        # Preserve custom locations from older saved configurations.
        if self.country_var.get() not in choices:
            choices += (self.country_var.get(),)
        self.country_dropdown = ttk.Combobox(wrap, textvariable=self.country_var, values=choices,
                                            state="readonly", height=15, font=("Segoe UI", 11),
                                            style="Country.TCombobox", width=24)
        self.country_dropdown.pack(fill="x")
        return wrap

    def _chip(self, parent, text: str, var: BooleanVar):
        from tkinter import Frame, Checkbutton

        wrap = Frame(parent, bg=C["chip"], highlightbackground=C["border"], highlightthickness=1)
        cb = Checkbutton(
            wrap,
            text=text,
            variable=var,
            bg=C["chip"],
            fg=C["text"],
            activebackground=C["chip"],
            activeforeground=C["accent"],
            selectcolor=C["input_bg"],
            font=("Segoe UI", 9),
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            cursor="hand2",
        )
        cb.pack()
        return wrap

    def _primary_button(self, parent, text: str, command):
        from tkinter import Button

        btn = Button(
            parent,
            text=text,
            command=command,
            bg=C["accent"],
            fg=C["bg"],
            activebackground=C["accent2"],
            activeforeground=C["bg"],
            font=("Segoe UI Semibold", 11),
            relief="flat",
            bd=0,
            padx=28,
            pady=12,
            cursor="hand2",
        )
        return btn

    def _ghost_button(self, parent, text: str, command):
        from tkinter import Button

        btn = Button(
            parent,
            text=text,
            command=command,
            bg=C["panel"],
            fg=C["text"],
            activebackground=C["panel2"],
            activeforeground=C["accent"],
            disabledforeground=C["dim"],
            font=("Segoe UI", 10),
            relief="flat",
            bd=0,
            padx=18,
            pady=12,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=C["border"],
        )
        return btn

    def _font_exists(self, name: str) -> bool:
        try:
            from tkinter import font as tkfont

            return name in tkfont.families()
        except Exception:
            return False

    def _draw_pulse(self, color: str) -> None:
        self.pulse.delete("all")
        self.pulse.create_oval(2, 2, 12, 12, fill=color, outline="")

    def _start_pulse(self) -> None:
        self._pulse_phase = 0

        def tick() -> None:
            if not self.running:
                self._draw_pulse(C["ok"] if self.last_path else C["accent"])
                return
            colors = [C["accent"], C["accent2"], C["warn"], C["accent"]]
            self._draw_pulse(colors[self._pulse_phase % len(colors)])
            self._pulse_phase += 1
            self._pulse_job = self.root.after(400, tick)

        tick()

    def _stop_pulse(self, ok: bool = True) -> None:
        if self._pulse_job:
            self.root.after_cancel(self._pulse_job)
            self._pulse_job = None
        self._draw_pulse(C["ok"] if ok else C["danger"])

    def _log(self, message: str, tag: str = "info") -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] ", "dim" if False else "info")
        self.log.insert("end", message + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    # ── Actions ────────────────────────────────────────────────────────────
    def on_search(self) -> None:
        if self.running:
            return

        prof = self.prof_var.get().strip()
        country = self.country_var.get().strip()
        start = self.start_date_var.get().strip()
        end = self.end_date_var.get().strip()

        if not prof:
            messagebox.showerror("Missing profession", "Enter a profession or role to search for.")
            return

        try:
            datetime.strptime(start, "%Y-%m-%d")
            datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Invalid date", "Dates must be in YYYY-MM-DD format.")
            return

        if not any(var.get() for var in self.source_vars.values()):
            messagebox.showerror("No sources", "Enable at least one job source.")
            return

        if start > end:
            messagebox.showerror("Invalid date range", "Start date must be before or equal to end date.")
            return

        self._apply_settings(prof, country, start, end)
        self.save_settings()

        self.running = True
        self.last_path = None
        self.search_btn.configure(state="disabled", text="Searching…")
        self.open_btn.configure(state="disabled")
        self.status_var.set("Searching job boards…")
        enabled = sum(var.get() for var in self.source_vars.values())
        self.detail_var.set(f"Checking {enabled} platforms concurrently. Results appear as each platform finishes.")
        self._log(f"Starting search for “{prof}” in {country}", "accent")
        self._log(f"Date range {start} → {end}", "info")
        self._start_pulse()

        threading.Thread(target=self._run_fetch, daemon=True).start()

    def select_all_sources(self) -> None:
        for var in self.source_vars.values():
            var.set(True)

    def _source_progress(self, event: dict) -> None:
        self.status_var.set(f"Checked {event['completed']} of {event['total']} platforms")
        status = event["status"]
        tag = "err" if status == "failed" else "warn" if status == "partial" else "ok"
        self._log(f"{event['source']}: {event['count']} jobs, {status}, {event['seconds']:.1f}s", tag)

    def _apply_settings(self, prof: str, country: str, start: str, end: str) -> None:
        if "search" not in self.settings:
            self.settings["search"] = {}
        if "sources" not in self.settings:
            self.settings["sources"] = {}

        search = self.settings["search"]
        search["keywords"] = [prof]
        words = [w.strip() for w in prof.lower().split() if w.strip()]
        extra_terms = [
            "qa engineer",
            "quality assurance",
            "sdet",
            "test engineer",
            "automation engineer",
            "software engineer in test",
            "qa automation",
            "manual tester",
            "selenium",
            "playwright",
            "cypress",
        ]
        combined: list[str] = []
        for term in [prof.lower()] + words + extra_terms:
            if term not in combined:
                combined.append(term)
        search["profession_terms"] = combined
        search["location"] = normalize_country(country)
        search["start_date"] = start
        search["end_date"] = end
        search["remote_only"] = self.remote_var.get()
        search["exclude_pakistan"] = self.exclude_pk_var.get()

        sources = self.settings["sources"]
        for key, var in self.source_vars.items():
            sources.setdefault(key, {})
            sources[key]["enabled"] = var.get()

        jobicy = sources.setdefault("jobicy", {})
        jobicy["geo"] = jobicy_geo(country)
        jobicy["tags"] = [prof]

    def _run_fetch(self) -> None:
        try:
            from job_finder.aggregator import fetch_all
            from job_finder.config import load_settings
            from job_finder.export import export_excel
            from job_finder.report import save_search_report, summary_lines

            settings = load_settings()
            self._ui(lambda: self._log("Fetching from enabled sources…", "info"))

            jobs, source_counts = fetch_all(
                settings, on_progress=lambda event: self._ui(lambda e=event: self._source_progress(e))
            )
            report_path = save_search_report(settings, jobs, source_counts)
            self._ui(lambda: self._log(f"Search completed in {source_counts.elapsed_seconds:.1f}s. Report: {report_path.name}", "info"))

            for line in summary_lines(source_counts):
                self._ui(lambda message=line: self._log(message, "info"))

            failures = getattr(source_counts, "errors", {})
            for name, message in failures.items():
                self._ui(lambda n=name, m=message: self._log(f"{n}: {m}", "err"))
            if failures and not jobs:
                raise RuntimeError("No matching jobs; some sources failed: " + "; ".join(f"{n}: {m}" for n, m in failures.items()))

            total = len(jobs)
            self._ui(
                lambda: self._log(
                    f"After filters: {total} unique job{'s' if total != 1 else ''}",
                    "ok" if total else "warn",
                )
            )

            if not jobs:
                self._ui(self._on_empty)
                return

            self._ui(lambda: self._log(f"Writing {total} jobs to Excel...", "info"))
            try:
                path = export_excel(jobs, settings)
            except Exception as exc:
                save_search_report(settings, jobs, source_counts, export_error=str(exc))
                raise RuntimeError(f"Found {total} jobs, but Excel export failed: {exc}") from exc
            save_search_report(settings, jobs, source_counts, excel_path=path)
            self._ui(lambda: self._on_success(path, total, source_counts))
        except Exception as exc:
            self._ui(lambda message=str(exc): self._on_error(message))

    def _ui(self, fn) -> None:
        self.root.after(0, fn)

    def _on_empty(self) -> None:
        self.running = False
        self._stop_pulse(ok=False)
        self.search_btn.configure(state="normal", text="Search Jobs")
        self.status_var.set("No matches found")
        self.detail_var.set("Try a broader profession, different country, or widen the date range.")
        self._log("No jobs matched the current filters.", "warn")

    def _on_success(self, path: Path, total: int, source_counts: dict) -> None:
        self.running = False
        self.last_path = path
        self._stop_pulse(ok=True)
        self.search_btn.configure(state="normal", text="Search Jobs")
        self.open_btn.configure(state="normal")
        failed = len(source_counts.errors)
        self.status_var.set(f"Found {total} jobs" + (f" · {failed} platforms failed" if failed else ""))
        src_summary = " · ".join(f"{k} {v}" for k, v in source_counts.items())
        self.detail_var.set(f"Verified {total} Excel rows in {path.name}  ·  Raw: {src_summary}")
        self._log(f"Excel saved and verified: {total} job rows → {path}", "ok")
        try:
            import os

            os.startfile(path)  # type: ignore[attr-defined]
            self._log("Opened Excel workbook.", "accent")
        except Exception:
            pass

    def _on_error(self, message: str) -> None:
        self.running = False
        self._stop_pulse(ok=False)
        self.search_btn.configure(state="normal", text="Search Jobs")
        self.status_var.set("Search failed")
        self.detail_var.set(message)
        self._log(message, "err")
        messagebox.showerror("Search failed", message)

    def open_excel(self) -> None:
        if not self.last_path or not self.last_path.exists():
            messagebox.showinfo("No file", "Run a search first to generate the Excel file.")
            return
        try:
            import os

            os.startfile(self.last_path)  # type: ignore[attr-defined]
        except Exception:
            webbrowser.open(self.last_path.as_uri())


def main() -> None:
    root = Tk()
    try:
        root.iconbitmap(default="")
    except Exception:
        pass
    JobFinderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
