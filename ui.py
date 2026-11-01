"""tkinter interface for codetype (Python only).

Two sections share one typing view:
  free ground - ask any coding question; a local Ollama model answers with explained code
  tutorials   - fixed lessons, ordered by level
"""
import math
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import generator
import history
import samples
from engine import ASSIST, AUTO, CORRECT, PENDING, WRONG, TypingSession, key_name

# "Midnight" palette: deep navy with a mint accent.
C = {
    "bg": "#1b1e2b",
    "panel": "#232738",
    "main": "#7ee0c3",
    "text": "#e4e6f0",
    "sub": "#5c6382",
    "err": "#ff6b81",
    "err_bg": "#4a2433",
    "block": "#272c42",
    "assist": "#a594f9",  # autocompleted text and the autocomplete tracker
}

CODE_FONTS = ["JetBrains Mono", "Cascadia Code", "Cascadia Mono", "Consolas", "Menlo",
              "DejaVu Sans Mono", "Courier New"]
UI_FONTS = ["Segoe UI", "Inter", "Helvetica Neue", "Helvetica", "Arial"]

PLACEHOLDER = "ask a Python coding question, e.g. \"check if two strings are anagrams\""
HINT = "esc restart  |  ctrl+enter autocomplete line  |  tab spaces  |  ctrl+backspace word"
STATE_TAGS = {PENDING: "pending", CORRECT: "correct", WRONG: "wrong", AUTO: "auto",
              ASSIST: "assist"}
WELCOME = """# Welcome to the free ground.
#
# 1. Ask any coding question in the box above.
# 2. Pick a length and a model, then press solve.
# 3. Type the Python answer along. The panel on the right
#    explains each block of the code as you reach it.
#
# Answers come from Ollama running on your own computer.
# Want fixed lessons instead? Open the tutorials tab."""


def _duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {seconds % 3600 // 60}m"


def pick_family(root, candidates, fallback):
    available = set(tkfont.families(root))
    return next((f for f in candidates if f in available), fallback)


class App:
    def __init__(self, root):
        self.root = root
        self.mode = None
        self.snippets = {"free": None, "tutorials": samples.TUTORIALS[0]}
        self.snippet = None
        self.session = None
        self.current_section = None
        self.current_line = None
        self.results_win = None
        self.models = []
        self.past = []
        self.generating = False
        self.gen_started = 0.0
        self.gen_model = ""
        self.jobs = queue.Queue()  # (kind, payload, error) from worker threads
        self._placeholder_on = False

        # Window sizes are in pixels, so scale them like the (point-sized) fonts.
        self.scale = max(1.0, float(root.tk.call("tk", "scaling")) / (96 / 72))
        root.title("codetype")
        self._place(root, 1320, 840)
        root.minsize(self.px(1000), self.px(640))
        root.configure(bg=C["bg"])

        code_family = pick_family(root, CODE_FONTS, "Courier")
        ui_family = pick_family(root, UI_FONTS, "TkDefaultFont")
        self.f_code = tkfont.Font(family=code_family, size=15)
        self.f_ui = tkfont.Font(family=ui_family, size=11)
        self.f_small = tkfont.Font(family=ui_family, size=10)
        self.f_bold = tkfont.Font(family=ui_family, size=12, weight="bold")
        self.f_title = tkfont.Font(family=ui_family, size=16, weight="bold")
        self.f_tab = tkfont.Font(family=ui_family, size=13)
        self.f_tab_on = tkfont.Font(family=ui_family, size=13, weight="bold")
        self.f_logo = tkfont.Font(family=code_family, size=22, weight="bold")
        self.f_stats = tkfont.Font(family=code_family, size=18)
        self.f_big = tkfont.Font(family=code_family, size=26, weight="bold")

        self._style()
        self._build_header()
        self._build_footer()
        self._build_body()

        self.refresh_models()
        self.set_mode("free")
        self._tick()

    def px(self, n):
        return int(n * self.scale)

    def _place(self, window, width, height):
        """Size a window (never bigger than 90% of the screen) and centre it."""
        sw, sh = window.winfo_screenwidth(), window.winfo_screenheight()
        w, h = min(self.px(width), int(sw * 0.9)), min(self.px(height), int(sh * 0.85))
        window.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - self.px(20))}")

    # ---- building the window ---------------------------------------------

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=C["panel"], background=C["panel"],
                        foreground=C["text"], arrowcolor=C["main"], bordercolor=C["panel"],
                        lightcolor=C["panel"], darkcolor=C["panel"], padding=5,
                        selectbackground=C["panel"], selectforeground=C["text"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", C["panel"])],
                  foreground=[("readonly", C["text"])],
                  background=[("active", C["block"])])
        self.root.option_add("*TCombobox*Listbox.background", C["panel"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["main"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", C["bg"])

    def _button(self, parent, text, command, accent=False):
        b = tk.Button(parent, text=text, command=command, font=self.f_ui, relief="flat", bd=0,
                      padx=14, pady=5, cursor="hand2",
                      bg=C["main"] if accent else C["panel"],
                      fg=C["bg"] if accent else C["text"],
                      activebackground=C["text"], activeforeground=C["bg"])
        b.pack(side="left", padx=(8, 0))
        return b

    def _label(self, parent, text="", fg="text", font=None, bg="bg", **kw):
        return tk.Label(parent, text=text, fg=C[fg], bg=C[bg], font=font or self.f_ui,
                        anchor="w", justify="left", **kw)

    def _combo(self, parent, var, values, width, readonly=True, font=None):
        box = ttk.Combobox(parent, textvariable=var, values=values, width=width,
                           state="readonly" if readonly else "normal", font=font or self.f_ui)
        box.pack(side="left", padx=(8, 0))
        return box

    def _build_header(self):
        bar = tk.Frame(self.root, bg=C["bg"])
        bar.pack(fill="x", padx=24, pady=(18, 10))
        self._label(bar, "code", "main", self.f_logo).pack(side="left")
        self._label(bar, "type", "text", self.f_logo).pack(side="left")

        self.tabs = {}
        tabs = tk.Frame(bar, bg=C["bg"])
        tabs.pack(side="left", padx=(36, 0))
        for key, text in (("free", "free ground"), ("tutorials", "tutorials"),
                          ("profile", "profile")):
            tab = tk.Label(tabs, text=text, font=self.f_tab, bg=C["bg"], fg=C["sub"],
                           cursor="hand2", padx=12, pady=4)
            tab.pack(side="left")
            tab.bind("<Button-1>", lambda e, k=key: self.set_mode(k))
            self.tabs[key] = tab
        self.status_lbl = self._label(bar, "", "sub", self.f_small)
        self.status_lbl.pack(side="right")

        # The typing view (free ground / tutorials) and the profile view swap places.
        self.typing_view = tk.Frame(self.root, bg=C["bg"])
        self.typing_view.pack(fill="both", expand=True)
        self.profile_view = tk.Frame(self.root, bg=C["bg"])
        self.view = "typing"

        mode_row = tk.Frame(self.typing_view, bg=C["bg"])
        mode_row.pack(fill="x", padx=24, pady=(0, 8))

        # free ground: question, length, model, solve
        self.free_row = tk.Frame(mode_row, bg=C["bg"])
        self.prompt_var = tk.StringVar()
        self.prompt_entry = tk.Entry(self.free_row, textvariable=self.prompt_var, font=self.f_ui,
                                     bg=C["panel"], fg=C["text"], insertbackground=C["main"],
                                     relief="flat", highlightthickness=1,
                                     highlightbackground=C["panel"], highlightcolor=C["main"])
        self.prompt_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.prompt_entry.bind("<Return>", lambda e: self.solve())
        self.prompt_entry.bind("<FocusIn>", self._clear_placeholder)
        self.prompt_entry.bind("<FocusOut>", lambda e: self._show_placeholder())
        self._show_placeholder()
        self.len_var = tk.StringVar(value="medium")
        self._combo(self.free_row, self.len_var, list(generator.LENGTHS), 7)
        self.model_var = tk.StringVar()
        self.model_box = self._combo(self.free_row, self.model_var, [], 18)
        self._button(self.free_row, "↻", self.refresh_models)
        self.solve_btn = self._button(self.free_row, "solve", self.solve, accent=True)

        # tutorials: lesson picker
        self.tut_row = tk.Frame(mode_row, bg=C["bg"])
        self._label(self.tut_row, "lesson", "sub", self.f_small).pack(side="left")
        self.lesson_var = tk.StringVar()
        self.lesson_box = self._combo(self.tut_row, self.lesson_var,
                                      [f"{t.level}  |  {t.title}" for t in samples.TUTORIALS], 44)
        self.lesson_box.bind("<<ComboboxSelected>>",
                             lambda e: self.load_snippet(samples.TUTORIALS[self.lesson_box.current()]))
        self._button(self.tut_row, "< prev", lambda: self.step_lesson(-1))
        self._button(self.tut_row, "next >", lambda: self.step_lesson(1))
        self.tut_info = self._label(self.tut_row, "", "sub", self.f_small)
        self.tut_info.pack(side="left", padx=(16, 0))

        opts = tk.Frame(self.typing_view, bg=C["bg"])
        opts.pack(fill="x", padx=24, pady=(0, 12))
        self.free_opts = tk.Frame(opts, bg=C["bg"])
        self._label(self.free_opts, "your questions", "sub", self.f_small).pack(side="left")
        self.past_var = tk.StringVar()
        self.past_box = self._combo(self.free_opts, self.past_var, [], 50, font=self.f_small)
        self.past_box.bind("<<ComboboxSelected>>",
                           lambda e: self.load_snippet(self.past[self.past_box.current()]))

        shared = tk.Frame(opts, bg=C["bg"])
        shared.pack(side="right")
        self.auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(shared, text="auto-indent", variable=self.auto_var, command=self.restart,
                       font=self.f_small, bg=C["bg"], fg=C["text"], selectcolor=C["panel"],
                       activebackground=C["bg"], activeforeground=C["main"],
                       highlightthickness=0, bd=0).pack(side="left")
        self.assist_btn = self._button(shared, "autocomplete line", self.autocomplete)
        self.assist_btn.configure(fg=C["assist"])
        self._button(shared, "restart", self.restart)

    def _build_footer(self):
        foot = tk.Frame(self.typing_view, bg=C["bg"])
        foot.pack(side="bottom", fill="x", padx=24, pady=(6, 16))
        self.stats_lbl = self._label(foot, "", "main", self.f_stats)
        self.stats_lbl.pack(side="left")
        self.assist_lbl = self._label(foot, "", "assist", self.f_ui)
        self.assist_lbl.pack(side="left", padx=(16, 0))
        self._label(foot, HINT, "sub", self.f_small).pack(side="right")

    def _build_body(self):
        body = tk.Frame(self.typing_view, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=24)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        code_box = tk.Frame(body, bg=C["bg"])
        code_box.grid(row=0, column=0, sticky="nsew")
        common = dict(font=self.f_code, bg=C["bg"], relief="flat", bd=0, highlightthickness=0,
                      pady=10, spacing1=3, spacing3=3, wrap="none")
        self.gutter = tk.Text(code_box, width=4, fg=C["sub"], cursor="arrow", takefocus=0,
                              padx=6, **common)
        self.gutter.pack(side="left", fill="y")
        self.gutter.tag_configure("num", justify="right")
        self.gutter.tag_configure("cur", foreground=C["main"])
        self.gutter.bind("<Button-1>", lambda e: "break")
        self.gutter.bind("<MouseWheel>", self._wheel)

        self.text = tk.Text(code_box, fg=C["sub"], insertwidth=0, insertofftime=0,
                            insertbackground=C["main"], padx=12, cursor="xterm",
                            selectbackground=C["bg"], inactiveselectbackground=C["bg"],
                            selectforeground=C["sub"], **common)
        self.text.pack(side="left", fill="both", expand=True)
        self.text.configure(yscrollcommand=lambda first, last: self.gutter.yview_moveto(first))
        # Tag order matters: later tags win, so the caret is drawn over everything.
        self.text.tag_configure("block", background=C["block"])
        self.text.tag_configure("pending", foreground=C["sub"])
        self.text.tag_configure("auto", foreground=C["sub"])
        self.text.tag_configure("correct", foreground=C["text"])
        self.text.tag_configure("assist", foreground=C["assist"])
        self.text.tag_configure("wrong", foreground=C["err"], background=C["err_bg"],
                                underline=True)
        self.text.tag_configure("caret", background=C["main"], foreground=C["bg"])
        self.text.bind("<Key>", self._on_key)
        self.text.bind("<Button-1>", lambda e: (self.text.focus_set(), "break")[1])
        self.text.bind("<B1-Motion>", lambda e: "break")
        self.text.bind("<Double-Button-1>", lambda e: "break")
        self.text.bind("<FocusIn>", lambda e: self._set_focus_look(True))
        self.text.bind("<FocusOut>", lambda e: self._set_focus_look(False))

        side = tk.Frame(body, bg=C["panel"], width=self.px(400))
        side.grid(row=0, column=1, sticky="ns", padx=(20, 0))
        side.pack_propagate(False)
        inner = tk.Frame(side, bg=C["panel"])
        inner.pack(fill="both", expand=True, padx=18, pady=16)

        self.title_lbl = self._label(inner, "", "main", self.f_title, bg="panel")
        self.title_lbl.pack(fill="x")
        self.meta_lbl = self._label(inner, "", "sub", self.f_small, bg="panel")
        self.meta_lbl.pack(fill="x")
        self.overview_lbl = self._label(inner, "", "text", self.f_small, bg="panel")
        self.overview_lbl.pack(fill="x", pady=(6, 0))

        self._caption(inner, "now typing")
        self.sec_title_lbl = self._label(inner, "", "text", self.f_bold, bg="panel")
        self.sec_title_lbl.pack(fill="x")
        self.sec_lines_lbl = self._label(inner, "", "sub", self.f_small, bg="panel")
        self.sec_lines_lbl.pack(fill="x")
        self.sec_expl_lbl = self._label(inner, "", "text", self.f_ui, bg="panel")
        self.sec_expl_lbl.pack(fill="x", pady=(6, 0))
        self.sec_concepts_lbl = self._label(inner, "", "main", self.f_small, bg="panel")
        self.sec_concepts_lbl.pack(fill="x", pady=(6, 0))

        self._caption(inner, "blocks")
        self.outline = tk.Text(inner, bg=C["panel"], fg=C["text"], font=self.f_small,
                               relief="flat", bd=0, highlightthickness=0, wrap="word",
                               cursor="arrow", height=8, spacing1=2, spacing3=2, takefocus=0)
        self.outline.pack(fill="both", expand=True)
        self.outline.tag_configure("done", foreground=C["sub"])
        self.outline.tag_configure("current", foreground=C["main"])
        self.outline.tag_configure("todo", foreground=C["text"])
        self.outline.tag_configure("lines", foreground=C["sub"])
        self.outline.bind("<Button-1>", lambda e: "break")

        self.wrap_labels = [self.title_lbl, self.meta_lbl, self.overview_lbl,
                            self.sec_title_lbl, self.sec_expl_lbl, self.sec_concepts_lbl]
        side.bind("<Configure>", lambda e: [l.configure(wraplength=e.width - self.px(40))
                                            for l in self.wrap_labels])

    def _caption(self, parent, text):
        tk.Frame(parent, bg=C["block"], height=1).pack(fill="x", pady=(16, 10))
        self._label(parent, text.upper(), "sub", self.f_small, bg="panel").pack(fill="x")

    def _wheel(self, event):
        self.text.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _set_focus_look(self, focused):
        color = C["main"] if focused else C["sub"]
        self.text.tag_configure("caret", background=color)
        self.text.configure(insertbackground=color)
        if self.generating:
            return
        if not focused and self.session and not self.session.finished:
            self._set_status("click the code to keep typing")
        elif focused:
            self._set_status("")

    # ---- prompt placeholder ----------------------------------------------

    def _show_placeholder(self):
        if not self.prompt_var.get():
            self._placeholder_on = True
            self.prompt_entry.configure(fg=C["sub"])
            self.prompt_var.set(PLACEHOLDER)

    def _clear_placeholder(self, _event=None):
        if self._placeholder_on:
            self._placeholder_on = False
            self.prompt_var.set("")
            self.prompt_entry.configure(fg=C["text"])

    # ---- sections (free ground / tutorials) --------------------------------

    def set_mode(self, mode):
        for key, tab in self.tabs.items():
            on = key == mode
            tab.configure(fg=C["main"] if on else C["sub"], font=self.f_tab_on if on else self.f_tab)
        if mode == "profile":
            if self.session:
                self.session.pause()  # the clock stops while you look at your stats
            self.view = "profile"
            self.typing_view.pack_forget()
            self.profile_view.pack(fill="both", expand=True)
            self.render_profile()
            return
        if self.view == "profile":
            self.view = "typing"
            self.profile_view.pack_forget()
            self.typing_view.pack(fill="both", expand=True)
            if self.session:
                self.session.resume()
        if mode == self.mode:
            if self.session:
                self.text.focus_set()
            return
        self.mode = mode
        for frame in (self.free_row, self.tut_row, self.free_opts):
            frame.pack_forget()
        if mode == "free":
            self.free_row.pack(fill="x")
            self.free_opts.pack(side="left")
            self.refresh_past()
        else:
            self.tut_row.pack(fill="x")
        self.load_snippet(self.snippets[mode])

    def step_lesson(self, delta):
        index = samples.TUTORIALS.index(self.snippets["tutorials"])
        self.load_snippet(samples.TUTORIALS[(index + delta) % len(samples.TUTORIALS)])

    def refresh_past(self):
        self.past = history.load_questions()
        self.past_box.configure(values=[s.question for s in self.past])
        self.past_var.set("pick one to practise again" if self.past else "none yet")

    # ---- loading code ----------------------------------------------------

    def load_snippet(self, snippet):
        self.snippets[self.mode] = snippet
        self.snippet = snippet
        if self.mode == "tutorials":
            index = samples.TUTORIALS.index(snippet)
            self.lesson_box.current(index)
            self.tut_info.configure(text=f"lesson {index + 1} of {len(samples.TUTORIALS)}")
        self.restart()

    def restart(self):
        self._close_results()
        snip = self.snippet
        if snip is None:
            self._show_welcome()
            return
        self.session = TypingSession(snip.code, snip.sections, auto_indent=self.auto_var.get())
        self.current_section = None
        self.current_line = None

        self.text.delete("1.0", "end")
        self.text.insert("1.0", snip.code, "pending")
        self._refresh(range(len(snip.code)))
        self._set_gutter(self.session.line_count)

        meta = [snip.level, snip.language, f"{self.session.line_count} lines",
                f"{len(snip.sections)} blocks", snip.model]
        self.title_lbl.configure(text=snip.title)
        self.meta_lbl.configure(text="  |  ".join(m for m in meta if m))
        overview = [f"Q: {snip.question}" if snip.question else "", snip.overview,
                    f"Complexity: {snip.complexity}" if snip.complexity else ""]
        self.overview_lbl.configure(text="\n\n".join(p for p in overview if p))
        self._move_caret()
        self.text.yview_moveto(0)
        self.text.focus_set()
        self._update_stats()

    def _show_welcome(self):
        self.session = None
        self.current_section = None
        self.text.delete("1.0", "end")
        self.text.insert("1.0", WELCOME, "pending")
        self.text.tag_remove("block", "1.0", "end")
        self._set_gutter(0)
        self.title_lbl.configure(text="Free ground")
        self.meta_lbl.configure(text="answers by Ollama, on your computer")
        self.overview_lbl.configure(text="Ask any coding question. The Python answer arrives as code "
                                         "you type along, with every block explained as you "
                                         "reach it, plus the time and space complexity.")
        for lbl in (self.sec_title_lbl, self.sec_lines_lbl, self.sec_expl_lbl,
                    self.sec_concepts_lbl):
            lbl.configure(text="")
        self._clear_outline()
        self.assist_lbl.configure(text="")
        self.stats_lbl.configure(text="ask a question to get started", fg=C["sub"],
                                 font=self.f_ui)

    def _set_gutter(self, line_count):
        self.gutter.configure(state="normal")
        self.gutter.delete("1.0", "end")
        self.gutter.insert("1.0", "\n".join(str(i) for i in range(1, line_count + 1)), "num")
        self.gutter.configure(state="disabled")

    # ---- typing ------------------------------------------------------------

    def _on_key(self, event):
        s = self.session
        if s is None:
            return "break"
        ks = event.keysym
        if ks == "Escape":
            self.restart()
            return "break"
        if s.finished:
            return "break"

        accepted = True
        ctrl = bool(event.state & 0x4)
        if ks == "BackSpace":
            changed = s.backspace(word=ctrl)
        elif ks in ("Return", "KP_Enter") and ctrl:
            changed = s.autocomplete_line()
        elif ks in ("Return", "KP_Enter"):
            changed, accepted = s.type_char("\n")
        elif ks == "Tab":
            changed, accepted = s.tab()
        elif len(event.char) == 1 and event.char.isprintable():
            # Checking the character (not Ctrl state) keeps AltGr layouts like { working.
            changed, accepted = s.type_char(event.char)
        else:
            return "break"  # shift, ctrl+v, arrows, etc.

        self._after_change(changed, accepted)
        return "break"

    def autocomplete(self):
        """Button version of ctrl+enter: fill the rest of the line for a tired typist."""
        s = self.session
        if s is None or s.finished:
            return
        self._after_change(s.autocomplete_line(), True)
        self.text.focus_set()

    def _after_change(self, changed, accepted):
        self._refresh(changed)
        self._move_caret()
        if not accepted:
            self._flash_caret()
        self._update_stats()
        if self.session.finished:
            self.root.after(150, self.show_results)

    def _refresh(self, positions):
        state = self.session.state
        for p in positions:
            a, b = f"1.0+{p}c", f"1.0+{p + 1}c"
            for tag in STATE_TAGS.values():
                self.text.tag_remove(tag, a, b)
            self.text.tag_add(STATE_TAGS[state[p]], a, b)

    def _move_caret(self):
        s = self.session
        self.text.tag_remove("caret", "1.0", "end")
        self.text.configure(insertwidth=0)
        if not s.finished:
            idx = f"1.0+{s.pos}c"
            if s.target[s.pos] == "\n":
                # A highlighted line break would paint the whole row, so show a thin
                # cursor at the end of the line instead of the block caret.
                self.text.mark_set("insert", idx)
                self.text.configure(insertwidth=self.px(3))
            else:
                self.text.tag_add("caret", idx, f"{idx}+1c")
            self.text.see(idx)

        line = s.current_line()
        if line != self.current_line:
            self.current_line = line
            self.gutter.tag_remove("cur", "1.0", "end")
            self.gutter.tag_add("cur", f"{line}.0", f"{line}.end")

        sec = s.section_at()
        if sec != self.current_section:
            self.current_section = sec
            self._show_section(sec)
        elif s.finished:
            self._render_outline()

    def _flash_caret(self):
        self.text.tag_configure("caret", background=C["err"])
        self.text.configure(insertbackground=C["err"])
        self.root.after(140, lambda: self._set_focus_look(self.root.focus_get() == self.text))

    def _show_section(self, index):
        self.text.tag_remove("block", "1.0", "end")
        if index is None:
            for lbl in (self.sec_title_lbl, self.sec_lines_lbl, self.sec_expl_lbl,
                        self.sec_concepts_lbl):
                lbl.configure(text="")
        else:
            sec = self.snippet.sections[index]
            self.text.tag_add("block", f"{sec.start_line}.0", f"{sec.end_line}.end+1c")
            self.sec_title_lbl.configure(text=sec.title)
            self.sec_lines_lbl.configure(text=sec.lines_label)
            self.sec_expl_lbl.configure(text=sec.explanation)
            self.sec_concepts_lbl.configure(text="   ".join(f"#{c}" for c in sec.concepts))
        self._render_outline()

    def _clear_outline(self):
        self.outline.configure(state="normal")
        self.outline.delete("1.0", "end")
        self.outline.configure(state="disabled")

    def _render_outline(self):
        self._clear_outline()
        o = self.outline
        o.configure(state="normal")
        for i, sec in enumerate(self.snippet.sections):
            if i == self.current_section and not self.session.finished:
                mark, tag = "▸", "current"
            elif self.session.section_done(i):
                mark, tag = "✓", "done"
            else:
                mark, tag = "·", "todo"
            o.insert("end", f"{mark}  {sec.title}", tag)
            o.insert("end", f"   {sec.start_line}-{sec.end_line}\n", "lines")
        o.configure(state="disabled")
        if self.current_section is not None:
            o.see(f"{self.current_section + 1}.0")

    # ---- live stats & background jobs --------------------------------------

    def _tick(self):
        if self.session and self.session.start_time and not self.session.finished:
            self._update_stats()
        if self.generating:
            waited = time.monotonic() - self.gen_started
            self._set_status(f"{self.gen_model} is writing your answer... {waited:.0f}s")
        try:
            while True:
                kind, payload, error = self.jobs.get_nowait()
                if kind == "models":
                    self._got_models(payload, error)
                else:
                    self._got_answer(payload, error)
        except queue.Empty:
            pass
        self.root.after(200, self._tick)

    def _update_stats(self):
        s = self.session
        self.assist_lbl.configure(text="")
        if s is None:
            return
        if s.start_time is None:
            self.stats_lbl.configure(text="start typing - the timer starts on your first key",
                                     fg=C["sub"], font=self.f_ui)
            return
        self.stats_lbl.configure(
            fg=C["main"], font=self.f_stats,
            text=f"{s.elapsed():4.0f}s   {s.wpm():3.0f} wpm   {s.accuracy():3.0f}% acc   "
                 f"{100 * s.progress():3.0f}%")
        self.assist_lbl.configure(
            text=f"autocomplete x{s.assist_uses} (not counted)" if s.assist_uses else "")

    def _set_status(self, text, error=False):
        self.status_lbl.configure(text=text, fg=C["err"] if error else C["sub"])

    # ---- asking Ollama -----------------------------------------------------

    def refresh_models(self):
        self.model_var.set("checking Ollama...")

        def work():
            try:
                self.jobs.put(("models", generator.list_models(), None))
            except generator.GenerationError as e:
                self.jobs.put(("models", [], str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _got_models(self, models, error):
        current = self.model_var.get()
        self.models = models
        self.model_box.configure(values=models)
        if error:
            self.model_var.set("Ollama not running")
            self._set_status("Ollama isn't running - start it, then press ↻", error=True)
        elif not models:
            self.model_var.set("no models installed")
            self._set_status(f"no models - run: ollama pull {generator.SUGGESTED_MODEL}",
                             error=True)
        else:
            self.model_var.set(current if current in models else models[0])
            if not self.generating:
                self._set_status("")

    def solve(self):
        if self.generating:
            return
        question = "" if self._placeholder_on else self.prompt_var.get().strip()
        if not question:
            self._set_status("type a question first", error=True)
            self.prompt_entry.focus_set()
            return
        model = self.model_var.get()
        if model not in self.models:
            messagebox.showinfo("codetype", (
                "No Ollama model is available.\n\n"
                "1. Install Ollama from https://ollama.com and open it.\n"
                f"2. In a terminal run:  ollama pull {generator.SUGGESTED_MODEL}\n"
                "3. Press the ↻ button next to the model list."), parent=self.root)
            return
        length = self.len_var.get()

        self.generating = True
        self.gen_started = time.monotonic()
        self.gen_model = model
        self.solve_btn.configure(text="solving...", state="disabled")

        def work():
            try:
                self.jobs.put(("answer", generator.solve(question, length, model), None))
            except generator.GenerationError as e:
                self.jobs.put(("answer", None, str(e)))
            except Exception as e:  # keep the UI alive whatever happens
                self.jobs.put(("answer", None, f"Unexpected error: {e}"))

        threading.Thread(target=work, daemon=True).start()

    def _got_answer(self, snippet, error):
        self.generating = False
        self.solve_btn.configure(text="solve", state="normal")
        if error:
            self._set_status("couldn't get an answer", error=True)
            messagebox.showerror("codetype", error, parent=self.root)
            return
        history.save_question(snippet)
        self.refresh_past()
        self.snippets["free"] = snippet
        if self.mode == "free":
            self._set_status("")
            self.load_snippet(snippet)
        else:
            self._set_status("your answer is ready in free ground")

    # ---- results -------------------------------------------------------------

    def _close_results(self):
        if self.results_win is not None:
            self.results_win.grab_release()
            self.results_win.destroy()
            self.results_win = None

    def show_results(self):
        if self.results_win is not None or not self.session.finished:
            return
        r = self.session.summary()
        history.save_run({
            "date": datetime.now().isoformat(timespec="seconds"),
            "mode": self.mode,
            "title": self.snippet.title,
            "language": self.snippet.language,
            "wpm": round(r.wpm, 1),
            "raw": round(r.raw, 1),
            "accuracy": round(r.accuracy, 1),
            "time": round(r.elapsed, 1),
            "chars": r.correct_chars,
            "missed": dict(r.missed),
            # Separate tracker: autocomplete never feeds the wpm/accuracy numbers above.
            "assist": {"uses": r.assist_uses, "chars": r.assist_chars,
                       "total": sum(1 for ch in self.session.target if ch != "\n")},
        })
        runs = history.load()

        win = tk.Toplevel(self.root)
        self.results_win = win
        win.title("codetype - results")
        win.configure(bg=C["bg"])
        self._place(win, 980, 720)
        win.transient(self.root)
        win.protocol("WM_DELETE_WINDOW", self._close_results)
        pad = tk.Frame(win, bg=C["bg"])
        pad.pack(fill="both", expand=True, padx=28, pady=22)

        self._label(pad, self.snippet.title, "text", self.f_title).pack(fill="x")

        row = tk.Frame(pad, bg=C["bg"])
        row.pack(fill="x", pady=(12, 8))
        stats = [("wpm", f"{r.wpm:.0f}"), ("acc", f"{r.accuracy:.0f}%"),
                 ("raw", f"{r.raw:.0f}"), ("time", f"{r.elapsed:.0f}s"),
                 ("correct/wrong", f"{r.correct_chars}/{r.wrong_chars}"),
                 ("mistakes", str(r.errors))]
        for name, value in stats:
            col = tk.Frame(row, bg=C["bg"])
            col.pack(side="left", padx=(0, self.px(28)))
            self._label(col, name, "sub", self.f_ui).pack(anchor="w")
            self._label(col, value, "main", self.f_big).pack(anchor="w")
        if r.assist_uses:
            total = sum(1 for ch in self.session.target if ch != "\n")
            self._label(pad, f"autocomplete used {r.assist_uses}x for {r.assist_chars} characters "
                             f"({100 * r.assist_chars / total:.0f}% of the code), tracked "
                             "separately and not counted in wpm or accuracy",
                        "assist", self.f_small).pack(fill="x")

        canvas = tk.Canvas(pad, height=self.px(200), bg=C["bg"], highlightthickness=0)
        canvas.pack(fill="x", pady=(4, 12))
        canvas.bind("<Configure>", lambda e: self._draw_graph(canvas, r.series))

        cols = tk.Frame(pad, bg=C["bg"])
        cols.pack(fill="both", expand=True)
        for i in range(3):
            cols.columnconfigure(i, weight=1, uniform="cols")

        def column(index, heading, lines):
            frame = tk.Frame(cols, bg=C["panel"])
            frame.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 10, 0))
            self._label(frame, heading.upper(), "sub", self.f_small, bg="panel").pack(
                fill="x", padx=12, pady=(10, 6))
            for text, color in lines or [("nothing here - nice!", "sub")]:
                self._label(frame, text, color, self.f_small, bg="panel",
                            wraplength=self.px(280)).pack(fill="x", padx=12)

        column(0, "keys missed this run",
               [(f"{key_name(ch):>6}   x{n}", "err") for ch, n in r.missed.most_common(8)])
        slow = sorted(r.sections, key=lambda s: s["time"], reverse=True)
        column(1, "time per block (slowest first)",
               [(f"{s['time']:4.1f}s  {s['accuracy']:3.0f}%  {s['title']}", "text")
                for s in slow[:8]])
        trouble = history.all_time_missed(runs).most_common(8)
        column(2, f"trouble keys over {len(runs)} runs",
               [(f"{key_name(ch):>6}   x{n}", "main") for ch, n in trouble])

        buttons = tk.Frame(pad, bg=C["bg"])
        buttons.pack(fill="x", pady=(14, 0))
        self._button(buttons, "retry (enter)", self.restart, accent=True)
        self._button(buttons, "close (esc)", self._close_results)

        if self.mode == "free":
            def ask_another():
                self._close_results()
                self.prompt_entry.focus_set()
            self._button(buttons, "ask another question", ask_another)
        else:
            self._button(buttons, "next lesson", lambda: self.step_lesson(1))
        win.bind("<Return>", lambda e: self.restart())
        win.bind("<Escape>", lambda e: self._close_results())
        win.focus_set()
        win.grab_set()

    # ---- profile ---------------------------------------------------------------

    def render_profile(self):
        """Rebuild the profile page from data/history.json."""
        for child in self.profile_view.winfo_children():
            child.destroy()
        runs = history.load()
        p = history.summarize(runs)
        pad = tk.Frame(self.profile_view, bg=C["bg"])
        pad.pack(fill="both", expand=True, padx=24, pady=(4, 16))
        self._label(pad, "your progress", "text", self.f_title).pack(fill="x")
        if not runs:
            self._label(pad, "No runs yet. Finish a tutorial or a free ground answer and your "
                             "progress will show up here.", "sub").pack(fill="x", pady=12)
            return

        tiles = tk.Frame(pad, bg=C["bg"])
        tiles.pack(fill="x", pady=(10, 4))
        trend = ""
        if p["previous_wpm"] is not None:
            trend = f"{p['recent_wpm'] - p['previous_wpm']:+.0f} vs the 10 before"
        for name, value, note in [
            ("runs", str(p["runs"]), ""),
            ("time typing", _duration(p["time"]), ""),
            ("best wpm", f"{p['best_wpm']:.0f}", p["best_title"]),
            ("wpm, last 10", f"{p['recent_wpm']:.0f}", trend),
            ("accuracy, last 10", f"{p['recent_accuracy']:.0f}%", ""),
            ("characters typed", f"{p['chars']:,}", ""),
        ]:
            col = tk.Frame(tiles, bg=C["bg"])
            col.pack(side="left", padx=(0, self.px(30)), anchor="n")
            self._label(col, name, "sub", self.f_ui).pack(anchor="w")
            self._label(col, value, "main", self.f_big).pack(anchor="w")
            self._label(col, note, "sub", self.f_small, wraplength=self.px(170)).pack(anchor="w")

        canvas = tk.Canvas(pad, height=self.px(220), bg=C["bg"], highlightthickness=0)
        canvas.pack(fill="x", pady=(8, 12))
        canvas.bind("<Configure>", lambda e: self._draw_progress(canvas, runs))

        grid = tk.Frame(pad, bg=C["bg"])
        grid.pack(fill="both", expand=True)
        for i in range(4):
            grid.columnconfigure(i, weight=1, uniform="cols")
        grid.rowconfigure(0, weight=1)

        def panel(index, heading, lines, heading_color="sub"):
            frame = tk.Frame(grid, bg=C["panel"])
            frame.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 10, 0))
            self._label(frame, heading.upper(), heading_color, self.f_small, bg="panel",
                        wraplength=self.px(260)).pack(fill="x", padx=12, pady=(10, 6))
            for text, color in lines:
                self._label(frame, text, color, self.f_small, bg="panel",
                            wraplength=self.px(260)).pack(fill="x", padx=12)

        panel(0, "trouble keys (all time)",
              [(f"{key_name(ch):>6}   x{n}", "err") for ch, n in p["missed"].most_common(10)]
              or [("no mistakes yet", "sub")])

        modes = []
        for mode, name in (("free", "free ground"), ("tutorials", "tutorials")):
            m = p["by_mode"][mode]
            if m["runs"]:
                modes.append((f"{name}: {m['runs']} runs, {m['wpm']:.0f} wpm, "
                              f"{m['accuracy']:.0f}% acc", "text"))
            else:
                modes.append((f"{name}: no runs yet", "sub"))
        modes.append((f"lessons finished: {len(p['lessons_done'])} of {len(samples.TUTORIALS)}",
                      "main"))
        panel(1, "by section", modes)

        a = p["assist"]
        panel(2, "autocomplete tracker", [
            ("kept separate: none of this counts in the stats on this page", "sub"),
            (f"used {a['uses']} times", "assist"),
            (f"{a['chars']:,} characters filled", "assist"),
            (f"{a['share']:.1f}% of all code you practised", "assist"),
            (f"in {a['runs']} of {p['runs']} runs", "assist"),
        ], heading_color="assist")

        recent = []
        for r in reversed(runs[-8:]):
            mark = "  +ac" if r.get("assist", {}).get("uses") else ""
            recent.append((f"{r.get('date', '')[5:10]}  {r.get('wpm', 0):3.0f} wpm  "
                           f"{r.get('accuracy', 0):3.0f}%  {r.get('title', '')}{mark}", "text"))
        panel(3, "recent runs", recent)

    def _draw_progress(self, canvas, runs):
        """wpm of every run (dots), a 5-run moving average (line) and accuracy (dashed)."""
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        left, right, top, bottom = self.px(44), self.px(44), self.px(22), self.px(26)
        wpms = [r.get("wpm", 0) for r in runs]
        accs = [r.get("accuracy", 0) for r in runs]
        max_y = max(10, math.ceil(max(wpms) * 1.15 / 10) * 10)
        n = len(runs)

        def x(i):
            return left + (i / (n - 1) if n > 1 else 0.5) * (w - left - right)

        def y(v, top_value=max_y):
            return h - bottom - v / top_value * (h - top - bottom)

        for i in range(5):
            v = max_y * i / 4
            canvas.create_line(left, y(v), w - right, y(v), fill=C["panel"])
            canvas.create_text(left - 8, y(v), text=f"{v:.0f}", anchor="e", fill=C["sub"],
                               font=self.f_small)
            canvas.create_text(w - right + 8, y(v), text=f"{25 * i}%", anchor="w",
                               fill=C["sub"], font=self.f_small)
        canvas.create_text(left, top - self.px(12), text="wpm", anchor="w", fill=C["main"],
                           font=self.f_small)
        canvas.create_text(w - right, top - self.px(12), text="accuracy", anchor="e",
                           fill=C["sub"], font=self.f_small)
        canvas.create_text((left + w - right) / 2, top - self.px(12),
                           text="each dot is a run   |   line: 5-run average   |   "
                                "dashed: accuracy", fill=C["sub"], font=self.f_small)
        canvas.create_text(left, h - self.px(8), text=runs[0].get("date", "")[:10], anchor="w",
                           fill=C["sub"], font=self.f_small)
        canvas.create_text(w - right, h - self.px(8), text=runs[-1].get("date", "")[:10],
                           anchor="e", fill=C["sub"], font=self.f_small)

        if n > 1:
            canvas.create_line(*[c for i, a in enumerate(accs) for c in (x(i), y(a, 100))],
                               fill=C["sub"], width=1, dash=(4, 3))
            average = [sum(wpms[max(0, i - 4):i + 1]) / len(wpms[max(0, i - 4):i + 1])
                       for i in range(n)]
            canvas.create_line(*[c for i, v in enumerate(average) for c in (x(i), y(v))],
                               fill=C["main"], width=3, smooth=True)
        r = self.px(4)
        for i, v in enumerate(wpms):
            color = C["assist"] if runs[i].get("assist", {}).get("uses") else C["main"]
            canvas.create_oval(x(i) - r, y(v) - r, x(i) + r, y(v) + r, fill=color, outline="")

    def _draw_graph(self, canvas, series):
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        left, right, top, bottom = self.px(44), self.px(12), self.px(10), self.px(26)
        if not series:
            return
        max_t = series[-1][0] or 1
        peak = max(max(p[1], p[2]) for p in series)
        max_y = max(10, math.ceil(peak * 1.1 / 10) * 10)

        def x(t):
            return left + t / max_t * (w - left - right)

        def y(v):
            return h - bottom - v / max_y * (h - top - bottom)

        for i in range(5):
            v = max_y * i / 4
            canvas.create_line(left, y(v), w - right, y(v), fill=C["panel"])
            canvas.create_text(left - 8, y(v), text=f"{v:.0f}", anchor="e", fill=C["sub"],
                               font=self.f_small)
        canvas.create_text(left, h - self.px(8), text="0s", anchor="w", fill=C["sub"],
                           font=self.f_small)
        canvas.create_text(w - right, h - self.px(8), text=f"{max_t:.0f}s", anchor="e",
                           fill=C["sub"], font=self.f_small)
        canvas.create_text(w - right, top, text="wpm (mint)   raw (grey)   mistakes (red x)",
                           anchor="ne", fill=C["sub"], font=self.f_small)

        if len(series) > 1:
            canvas.create_line(*[c for p in series for c in (x(p[0]), y(p[2]))],
                               fill=C["sub"], width=2, smooth=True)
            canvas.create_line(*[c for p in series for c in (x(p[0]), y(p[1]))],
                               fill=C["main"], width=3, smooth=True)
        for t, wpm, _raw, errs in series:
            if len(series) == 1:
                canvas.create_oval(x(t) - 4, y(wpm) - 4, x(t) + 4, y(wpm) + 4, fill=C["main"],
                                   outline="")
            if errs:
                cx, cy = x(t), h - bottom - self.px(10)
                canvas.create_text(cx, cy, text="x", fill=C["err"], font=self.f_bold)
