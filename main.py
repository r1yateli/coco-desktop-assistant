import ctypes
import os
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import Canvas, Scrollbar, simpledialog, messagebox

from PIL import Image, ImageTk

import main

_BASE_DIR = main._BASE_DIR
FONT = "Segoe UI"
INK = "#2C1A1D"
_SIDE_POPUPS = ("history_popup", "theme_popup", "notes_popup", "todo_popup", "contacts_popup")
_POPUPS = _SIDE_POPUPS + ("alarm_popup",)

THEMES = {
    "Butter Yellow": dict(BG_CHAT="#FFFDD0", HEADER_BG="#4A2E1B", HEADER_FG="#FFF8DC", BORDER_BROWN="#5C3A21",
                          BUBBLE_BOT="#FFFFFF", BUBBLE_USER="#FFE0B2", TEXT_BROWN="#2C1A1D", ACCENT_BUTTON="#5C3A21"),
    "Midnight Dark": dict(BG_CHAT="#1E1E2E", HEADER_BG="#11111B", HEADER_FG="#CDD6F4", BORDER_BROWN="#313244",
                          BUBBLE_BOT="#313244", BUBBLE_USER="#45475A", TEXT_BROWN="#CDD6F4", ACCENT_BUTTON="#45475A"),
    "Pastel Pink": dict(BG_CHAT="#FFF0F5", HEADER_BG="#D46A9F", HEADER_FG="#FFF8FB", BORDER_BROWN="#C2185B",
                        BUBBLE_BOT="#FFFFFF", BUBBLE_USER="#FFD1E8", TEXT_BROWN="#5A2A3A", ACCENT_BUTTON="#D46A9F"),
    "Ocean Blue": dict(BG_CHAT="#E8F4F8", HEADER_BG="#1B4F72", HEADER_FG="#EAF2F8", BORDER_BROWN="#154360",
                       BUBBLE_BOT="#FFFFFF", BUBBLE_USER="#AED6F1", TEXT_BROWN="#1B2631", ACCENT_BUTTON="#1B4F72"),
}


def _resource(name):
    for base in (_BASE_DIR, getattr(sys, "_MEIPASS", _BASE_DIR)):
        path = os.path.join(base, name)
        if os.path.exists(path):
            return path
    return os.path.join(_BASE_DIR, name)


def _win_focus(widget):
    if sys.platform != "win32":
        return
    try:
        widget.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(widget.winfo_id())
        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


class CocoGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Coco Chat")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.TRANS_COLOR = "#000000"
        self.root.config(bg=self.TRANS_COLOR)
        self.root.wm_attributes("-transparentcolor", self.TRANS_COLOR)
        self.root.geometry("460x360+100+100")
        self._set_colors("Butter Yellow")

        self.avatar_size = (120, 120)
        self.chat_visible = True
        self.single_click_timer = None
        self.is_dragging = False
        self.mic_listening = False
        self._menu_open = False
        self.message_widgets = []
        self.history_listbox = None
        for name in _POPUPS:
            setattr(self, name, None)

        container = tk.Frame(self.root, bg=self.TRANS_COLOR)
        container.pack(fill="both", expand=True)
        self.container = container

        self.avatar_img = None
        self.load_avatar_image()
        self.avatar_label = tk.Label(container, image=self.avatar_img, bg=self.TRANS_COLOR, bd=0, cursor="hand2")
        self.avatar_label.place(x=5, y=110)

        self.chat_container = tk.Frame(container, bg=self.BG_CHAT, highlightbackground=self.BORDER_BROWN,
                                       highlightthickness=2, bd=0)
        self.chat_container.place(x=135, y=10, width=310, height=335)
        self.chat_container.rowconfigure(1, weight=1)
        self.chat_container.columnconfigure(0, weight=1)

        self.header_frame = tk.Frame(self.chat_container, bg=self.HEADER_BG, bd=0)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 2))
        self.title_label = tk.Label(self.header_frame, text="coco chat", font=(FONT, 10, "bold"),
                                    fg=self.HEADER_FG, bg=self.HEADER_BG, padx=8, pady=4)
        self.title_label.pack(side="left")
        self.close_btn = self._btn(self.header_frame, "✕", self.hide_chat, bg="#3D2314", fg="#FFF8DC",
                                   activebackground="#5C3A21", width=3)
        self.close_btn.pack(side="right", padx=6, pady=4)
        self.menu_btn = self._btn(self.header_frame, "⋮", self.show_options_menu, bg="#3D2314", fg="#FFF8DC",
                                  activebackground="#5C3A21", font=(FONT, 10, "bold"), width=3)
        self.menu_btn.pack(side="right", padx=(6, 0), pady=4)

        self.chat_frame = tk.Frame(self.chat_container, bg=self.BG_CHAT)
        self.chat_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=2)
        self.chat_canvas = Canvas(self.chat_frame, bg=self.BG_CHAT, highlightthickness=0)
        self.scrollbar = Scrollbar(self.chat_frame, orient="vertical", command=self.chat_canvas.yview)
        self.scroll_frame = tk.Frame(self.chat_canvas, bg=self.BG_CHAT)
        self.canvas_window = self.chat_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.chat_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.chat_canvas.pack(side="left", fill="both", expand=True)
        self.scroll_frame.bind("<Configure>", lambda e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all")))
        self.chat_canvas.bind("<Configure>", lambda e: self.chat_canvas.itemconfig(self.canvas_window, width=e.width))
        self.chat_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self.input_frame = tk.Frame(self.chat_container, bg=self.BG_CHAT)
        self.input_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=(2, 6))
        self.mic_btn = self._btn(self.input_frame, "🎤", self.toggle_mic_listen, font=(FONT, 9, "bold"), width=3)
        self.mic_btn.pack(side="left", padx=(0, 4))
        self.entry_box = tk.Entry(self.input_frame, bg="#FFFFFF", fg=self.TEXT_BROWN, font=(FONT, 9), bd=1,
                                  relief="solid", insertbackground=self.TEXT_BROWN)
        self.entry_box.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 4))
        self.entry_box.bind("<Return>", lambda e: self.send_message())
        self._force_focus_on_click(self.entry_box)
        self.send_btn = self._btn(self.input_frame, "Send", self.send_message, font=(FONT, 9, "bold"), padx=10)
        self.send_btn.pack(side="right")

        for widget in (self.title_label, self.header_frame):
            widget.bind("<Button-1>", self.start_drag)
            widget.bind("<B1-Motion>", self.on_drag)
        self.avatar_label.bind("<Button-1>", self.on_avatar_click)
        self.avatar_label.bind("<Double-Button-1>", self.on_avatar_double_click)
        self.avatar_label.bind("<B1-Motion>", self.on_avatar_drag)
        self.avatar_label.bind("<Button-3>", self.show_avatar_menu)

        self.tray = None
        self._start_tray()
        self._keep_on_top()

    def setup_first_run(self):
        """Ask for the user's name first, then the Groq key if it is missing."""
        # Bring Coco forward so the first-run dialog doesn't hide behind the chat window.
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.update_idletasks()
        except Exception:
            pass

        if not main._user_name():
            name = simpledialog.askstring(
                "What's your name?",
                "What's your name?",
                parent=self.root
            )
            if name and name.strip():
                main.DATA["profile_name"] = name.strip()
                main._save_data()

        if not main._groq_key():
            key = simpledialog.askstring(
                "Set up Coco",
                "Enter your Groq API key. Get one at console.groq.com. "
                "Your key will be saved locally on this computer.",
                show="*",
                parent=self.root
            )
            if key and key.strip():
                try:
                    main._save_groq_key(key.strip())
                except OSError as exc:
                    messagebox.showerror(
                        "Could not save API key",
                        f"Coco couldn't save groq_key.txt beside the app.\\n\\n{exc}",
                        parent=self.root
                    )
            else:
                messagebox.showinfo(
                    "Groq key not set",
                    "Coco can still open, but AI features need a Groq API key. "
                    "You can add groq_key.txt beside Coco.exe later.",
                    parent=self.root
                )

        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass

    def _set_colors(self, name):
        self.current_theme_name = name
        for key, value in THEMES[name].items():
            setattr(self, key, value)

    def _btn(self, parent, text, command, bg=None, fg="#FFFFFF", font=(FONT, 8, "bold"), **kw):
        kw.setdefault("activebackground", "#3D2314")
        return tk.Button(parent, text=text, command=command, bg=bg or self.ACCENT_BUTTON, fg=fg,
                         activeforeground="#FFFFFF", bd=0, cursor="hand2", font=font, **kw)

    def _small_button(self, parent, text, command, side="left"):
        btn = self._btn(parent, text, command, activebackground=self.HEADER_BG, padx=8, pady=2)
        btn.pack(side=side, padx=(0, 4))
        return btn

    def _alive(self, attr):
        popup = getattr(self, attr, None)
        try:
            return popup is not None and popup.winfo_exists()
        except tk.TclError:
            return False

    def _show_menu(self, menu, x, y):
        self._menu_open = True
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()
            self._menu_open = False

    def _start_tray(self):
        try:
            import pystray
        except ImportError:
            return
        try:
            path = _resource("avatar.png")
            img = (Image.open(path).convert("RGBA").resize((64, 64)) if os.path.exists(path)
                   else Image.new("RGBA", (64, 64), (74, 46, 27, 255)))
            menu = pystray.Menu(
                pystray.MenuItem("Show Coco", lambda icon, item: self.root.after(0, self.show_coco), default=True),
                pystray.MenuItem("Quit Coco", lambda icon, item: self.root.after(0, self.close_app)))
            self.tray = pystray.Icon("Coco", img, "Coco", menu)
            self.tray.run_detached()
        except Exception as e:
            print(f"Tray icon failed: {e}")
            self.tray = None

    def hide_to_tray(self):
        if self.tray is None:
            self.hide_chat()
            self.append_message("Coco", "Tray needs: pip install pystray. I only hid the chat for now.")
            return
        self._close_popups()
        self.root.withdraw()

    def show_coco(self):
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        if not self.chat_visible:
            self.toggle_chat_window()

    def _keep_on_top(self):
        try:
            if not self._menu_open and not any(self._alive(a) for a in _POPUPS):
                self.root.attributes("-topmost", True)
        except tk.TclError:
            return
        self.root.after(3000, self._keep_on_top)

    def _raise_popups(self):
        for attr in _POPUPS:
            if self._alive(attr):
                getattr(self, attr).lift()

    def _close_popups(self):
        for attr in _SIDE_POPUPS:
            if self._alive(attr):
                getattr(self, attr).destroy()
            setattr(self, attr, None)
        self.history_listbox = None

    def _open_exclusive(self, opener):
        self._close_popups()
        opener()
        self.root.lift()
        self._raise_popups()
        self.root.after(100, self._raise_popups)

    def hide_chat(self):
        self._close_popups()
        if self.chat_visible:
            self.toggle_chat_window()

    def show_avatar_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Show / hide chat", command=self.toggle_chat_window)
        menu.add_command(label="Stop listening" if main.is_listening else "Start listening",
                         command=lambda: self.set_listening(not main.is_listening))
        menu.add_command(label="Hide to tray", command=self.hide_to_tray)
        menu.add_separator()
        menu.add_command(label="Quit Coco", command=self.close_app)
        self._show_menu(menu, event.x_root, event.y_root)

    def _on_mousewheel(self, event):
        if self.chat_visible:
            self.chat_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def load_avatar_image(self):
        path = _resource("avatar.png")
        if not os.path.exists(path):
            path = _resource("avatar.jpg")
        if os.path.exists(path):
            img = Image.open(path).convert("RGBA").resize(self.avatar_size, Image.Resampling.LANCZOS)
        else:
            img = Image.new("RGBA", self.avatar_size, color=(74, 46, 27, 255))
        self.avatar_img = ImageTk.PhotoImage(img)

    def append_message(self, sender, message):
        def update():
            bg = self.BUBBLE_BOT if sender == "Coco" else self.BUBBLE_USER
            frame = tk.Frame(self.scroll_frame, bg=bg, highlightbackground=self.BORDER_BROWN,
                             highlightthickness=1, bd=0, padx=8, pady=6)
            label = tk.Label(frame, text=message, font=(FONT, 9), bg=bg, fg=self.TEXT_BROWN,
                             wraplength=170, justify="left")
            label.pack()
            frame.pack(anchor="w" if sender == "Coco" else "e", pady=3, padx=4)
            self.message_widgets.append((frame, label, sender))
            self.root.update_idletasks()
            self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
            self.chat_canvas.yview_moveto(1.0)
        self.root.after(0, update)

    def _submit(self, text):
        self.append_message("You", text)
        threading.Thread(target=main.handle_command, args=(text,), daemon=True).start()

    def send_message(self):
        text = self.entry_box.get().strip()
        if text:
            self.entry_box.delete(0, tk.END)
            self._submit(text)

    def _say(self, msg):
        self.root.after(0, lambda: self.append_message("Coco", msg))

    def _set_listen_ui(self, on):
        self.title_label.config(text="coco chat  🔴 listening" if on else "coco chat")
        self.mic_btn.config(text="🔴" if on else "🎤")

    def _recognizer(self):
        try:
            import speech_recognition as sr
        except ImportError:
            self._say("Voice input needs two extra packages - run: pip install SpeechRecognition pyaudio")
            return None, None
        recognizer = sr.Recognizer()
        recognizer.pause_threshold = 1.5
        return sr, recognizer

    def toggle_mic_listen(self):
        if main.is_listening:
            self.set_listening(False)
            return
        if self.mic_listening:
            return
        self.mic_listening = True
        self._set_listen_ui(True)
        self.mic_btn.config(state="disabled")
        threading.Thread(target=self._mic_listen_worker, daemon=True).start()

    def _mic_listen_worker(self):
        sr, recognizer = self._recognizer()
        if not sr:
            self.root.after(0, self._reset_mic_button)
            return
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=60)
            text = recognizer.recognize_google(audio, language="en-IN")
            self.root.after(0, lambda: self._submit(text))
        except sr.WaitTimeoutError:
            self._say("Didn't hear anything - try again.")
        except sr.UnknownValueError:
            self._say("Sorry, I couldn't make that out.")
        except OSError:
            self._say("No microphone found. Check your input device.")
        except Exception as e:
            self._say(f"Voice error: {e}")
        finally:
            self.root.after(0, self._reset_mic_button)

    def _reset_mic_button(self):
        self.mic_listening = False
        self.mic_btn.config(state="normal")
        self._set_listen_ui(main.is_listening)

    def set_listening(self, on):
        if on == main.is_listening:
            return
        main.is_listening = on
        self._set_listen_ui(on)
        if on:
            threading.Thread(target=self._continuous_listen_worker, daemon=True).start()

    def _listening_ended(self):
        main.is_listening = False
        self._set_listen_ui(False)

    def _continuous_listen_worker(self):
        sr, recognizer = self._recognizer()
        if not sr:
            self.root.after(0, self._listening_ended)
            return
        recognizer.dynamic_energy_threshold = True
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
                self._say("I'm listening - just talk. Double-click me to stop.")
                while main.is_listening and main.running:
                    if main.is_speaking():
                        source.stream.read(source.CHUNK)
                        continue
                    try:
                        audio = recognizer.listen(source, timeout=1, phrase_time_limit=60)
                    except sr.WaitTimeoutError:
                        continue
                    if main.is_speaking():
                        continue
                    try:
                        text = recognizer.recognize_google(audio, language="en-IN")
                    except sr.UnknownValueError:
                        continue
                    except sr.RequestError:
                        self._say("I can't reach the speech service. Check your internet.")
                        time.sleep(3)
                        continue
                    self.root.after(0, lambda t=text: self._submit(t))
        except OSError:
            self._say("No microphone found. Check your input device.")
        except Exception as e:
            self._say(f"Voice error: {e}")
        finally:
            self.root.after(0, self._listening_ended)

    def start_drag(self, event):
        self.x, self.y = event.x, event.y

    def on_drag(self, event):
        x = self.root.winfo_x() + event.x - self.x
        y = self.root.winfo_y() + event.y - self.y
        self.root.geometry(f"+{x}+{y}")

    def on_avatar_drag(self, event):
        if self.single_click_timer:
            self.root.after_cancel(self.single_click_timer)
            self.single_click_timer = None
        self.is_dragging = True
        self.on_drag(event)

    def toggle_chat_window(self):
        if self.chat_visible:
            self.chat_container.place_forget()
        else:
            self.chat_container.place(x=135, y=10, width=310, height=335)
        self.chat_visible = not self.chat_visible

    def _execute_click_toggle(self):
        if not self.is_dragging:
            self.toggle_chat_window()
        self.single_click_timer = None

    def on_avatar_click(self, event):
        self.start_drag(event)
        self.is_dragging = False
        if self.single_click_timer:
            self.root.after_cancel(self.single_click_timer)
        self.single_click_timer = self.root.after(200, self._execute_click_toggle)

    def on_avatar_double_click(self, event):
        if self.single_click_timer:
            self.root.after_cancel(self.single_click_timer)
            self.single_click_timer = None
        self.set_listening(not main.is_listening)

    def _toggle_autostart(self):
        want = self._auto_var.get()
        if main.set_autostart(want):
            self.append_message("Coco", "Done! I'll open automatically when you log in to Windows."
                                if want else "Okay, I won't start automatically anymore.")
        else:
            self._auto_var.set(not want)
            self.append_message("Coco", "Sorry, I couldn't change the startup setting.")

    def show_options_menu(self):
        menu = tk.Menu(self.root, tearoff=0, bg=self.HEADER_BG, fg=self.HEADER_FG,
                       activebackground=self.ACCENT_BUTTON, activeforeground="#FFFFFF",
                       selectcolor=self.HEADER_FG, font=(FONT, 9))
        for label, opener in (("✅  To-Do List", self.open_todo_popup), ("📝  Notes", self.open_notes_popup),
                              ("👥  Contacts", self.open_contacts_popup)):
            menu.add_command(label=label, command=lambda o=opener: self._open_exclusive(o))
        menu.add_separator()
        menu.add_command(label="📜  Command History", command=lambda: self._open_exclusive(self.open_history_popup))
        menu.add_command(label="🎨  Change Theme", command=lambda: self._open_exclusive(self.open_theme_popup))
        menu.add_separator()
        self._auto_var = tk.BooleanVar(value=main.is_autostart())
        menu.add_checkbutton(label="🚀  Start with Windows", variable=self._auto_var, command=self._toggle_autostart)
        menu.add_separator()
        menu.add_command(label="🚪  Quit Coco", command=self.close_app)
        self._show_menu(menu, self.menu_btn.winfo_rootx(), self.menu_btn.winfo_rooty() + self.menu_btn.winfo_height())

    def _build_popup(self, title, width, height, attr_name):
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.transient(self.root)
        popup.geometry(f"{width}x{height}+{self.root.winfo_x() + 135}+{self.root.winfo_y() + 45}")
        popup.focus_force()
        popup.after(60, lambda: _win_focus(popup))

        frame = tk.Frame(popup, bg=self.BG_CHAT, highlightbackground=self.BORDER_BROWN, highlightthickness=2)
        frame.pack(fill="both", expand=True)
        header = tk.Frame(frame, bg=self.HEADER_BG)
        header.pack(fill="x")
        tk.Label(header, text=title, font=(FONT, 9, "bold"), fg=self.HEADER_FG, bg=self.HEADER_BG,
                 padx=6, pady=4).pack(side="left")

        def close():
            if popup.winfo_exists():
                popup.destroy()
            setattr(self, attr_name, None)
            try:
                _win_focus(self.root)
                self.entry_box.focus_force()
            except Exception:
                pass

        self._btn(header, "✕", close, bg=self.HEADER_BG, fg=self.HEADER_FG, width=3).pack(side="right", padx=4)
        setattr(self, attr_name, popup)
        return frame

    def _make_listbox(self, parent):
        holder = tk.Frame(parent, bg=self.BG_CHAT)
        holder.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        scrollbar = Scrollbar(holder)
        scrollbar.pack(side="right", fill="y")
        listbox = tk.Listbox(holder, bg="#FFFFFF", fg=INK, font=(FONT, 9), bd=0, highlightthickness=0,
                             selectbackground=self.BUBBLE_USER, selectforeground=INK, activestyle="none",
                             yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)
        return listbox

    @staticmethod
    def _force_focus_on_click(entry):
        def grab_focus(_event=None):
            _win_focus(entry)
            entry.focus_force()
        entry.bind("<Button-1>", grab_focus)

    def open_theme_popup(self):
        if self._alive("theme_popup"):
            self.theme_popup.lift()
            return
        frame = self._build_popup("Choose a theme", 200, 40 + 34 * len(THEMES), "theme_popup")
        for name, colors in THEMES.items():
            active = name == self.current_theme_name
            tk.Button(frame, text=("✓ " if active else "   ") + name,
                      font=(FONT, 9, "bold" if active else "normal"),
                      bg=colors["HEADER_BG"], fg=colors["HEADER_FG"],
                      activebackground=colors["ACCENT_BUTTON"], activeforeground="#FFFFFF",
                      bd=0, anchor="w", padx=10, pady=6, cursor="hand2",
                      command=lambda n=name: self._select_theme(n)).pack(fill="x", padx=4, pady=(4, 0))

    def _select_theme(self, name):
        self.apply_theme(name)
        if self._alive("theme_popup"):
            self.theme_popup.destroy()
        self.theme_popup = None

    def apply_theme(self, name):
        if name not in THEMES:
            return
        self._set_colors(name)
        self.chat_container.config(bg=self.BG_CHAT, highlightbackground=self.BORDER_BROWN)
        self.header_frame.config(bg=self.HEADER_BG)
        self.title_label.config(bg=self.HEADER_BG, fg=self.HEADER_FG)
        for btn in (self.close_btn, self.menu_btn):
            btn.config(bg=self.HEADER_BG, fg=self.HEADER_FG, activebackground=self.ACCENT_BUTTON)
        for widget in (self.chat_frame, self.chat_canvas, self.scroll_frame, self.input_frame):
            widget.config(bg=self.BG_CHAT)
        self.entry_box.config(bg="#313244" if name == "Midnight Dark" else "#FFFFFF",
                              fg=self.TEXT_BROWN, insertbackground=self.TEXT_BROWN)
        for btn in (self.send_btn, self.mic_btn):
            btn.config(bg=self.ACCENT_BUTTON, fg="#FFFFFF")
        for frame, label, sender in self.message_widgets:
            bg = self.BUBBLE_BOT if sender == "Coco" else self.BUBBLE_USER
            frame.config(bg=bg, highlightbackground=self.BORDER_BROWN)
            label.config(bg=bg, fg=self.TEXT_BROWN)

    def open_history_popup(self):
        if self._alive("history_popup"):
            self.history_popup.lift()
            return
        frame = self._build_popup("Command History (stack)", 260, 260, "history_popup")
        self.history_listbox = self._make_listbox(frame)
        self.history_listbox.bind("<Double-Button-1>", self._rerun_history_item)
        row = tk.Frame(frame, bg=self.BG_CHAT)
        row.pack(fill="x", padx=4, pady=4)
        self._small_button(row, "Clear History", self._clear_history)
        tk.Label(row, text="Double-click to repeat", font=(FONT, 7), bg=self.BG_CHAT, fg=self.TEXT_BROWN).pack(side="right")
        self._populate_history_listbox()

    def _populate_history_listbox(self):
        if self.history_listbox is None:
            return
        self.history_listbox.delete(0, tk.END)
        entries = main.command_history.get_all_most_recent_first()
        if not entries:
            self.history_listbox.insert(tk.END, "(no commands yet)")
        for entry in entries:
            self.history_listbox.insert(tk.END, f"[{entry['time']}]  {entry['command']}")

    def refresh_history_if_open(self):
        if self._alive("history_popup"):
            self._populate_history_listbox()

    def _clear_history(self):
        main.command_history.clear()
        self._populate_history_listbox()

    def _rerun_history_item(self, event):
        selection = self.history_listbox.curselection() if self.history_listbox else None
        entries = main.command_history.get_all_most_recent_first()
        if selection and selection[0] < len(entries):
            self._submit(entries[selection[0]]["command"])

    def open_notes_popup(self):
        frame = self._build_popup("Notes", 280, 300, "notes_popup")
        self.notes_listbox = self._make_listbox(frame)
        row = tk.Frame(frame, bg=self.BG_CHAT)
        row.pack(fill="x", padx=4, pady=(4, 0))
        self.note_entry = tk.Entry(row, font=(FONT, 9), bd=1, relief="solid")
        self.note_entry.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 4))
        self.note_entry.bind("<Return>", lambda e: self._add_note())
        self._force_focus_on_click(self.note_entry)
        self._small_button(row, "Add", self._add_note, side="right")
        bottom = tk.Frame(frame, bg=self.BG_CHAT)
        bottom.pack(fill="x", padx=4, pady=4)
        self._small_button(bottom, "Delete selected", self._delete_note)
        self._refresh_notes()
        self.note_entry.focus_force()

    def _refresh_notes(self):
        if not self._alive("notes_popup"):
            return
        self.notes_listbox.delete(0, tk.END)
        if not main.DATA["notes"]:
            self.notes_listbox.insert(tk.END, "(no notes yet)")
        for i, note in enumerate(main.DATA["notes"], 1):
            self.notes_listbox.insert(tk.END, f"{i}. {note}")

    def _add_note(self):
        text = self.note_entry.get().strip()
        if text:
            main.add_note(text)
            self.note_entry.delete(0, tk.END)
            self._refresh_notes()

    def _delete_note(self):
        selection = self.notes_listbox.curselection()
        if selection and main.DATA["notes"]:
            main.delete_note(selection[0])
            self._refresh_notes()

    def open_todo_popup(self):
        frame = self._build_popup("To-Do List", 300, 340, "todo_popup")

        row = tk.Frame(frame, bg=self.BG_CHAT)
        row.pack(fill="x", padx=6, pady=(6, 2))
        self.todo_entry = tk.Entry(row, font=(FONT, 9), bd=1, relief="solid")
        self.todo_entry.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 4))
        self.todo_entry.bind("<Return>", lambda e: self._add_todo())
        self._force_focus_on_click(self.todo_entry)
        self._small_button(row, "Add", self._add_todo, side="right")

        remind = tk.Frame(frame, bg=self.BG_CHAT)
        remind.pack(fill="x", padx=6, pady=(0, 2))
        tk.Label(remind, text="Alarm me in", font=(FONT, 8), bg=self.BG_CHAT, fg=INK).pack(side="left")
        self.todo_minutes = tk.Entry(remind, width=4, font=(FONT, 9), bd=1, relief="solid")
        self.todo_minutes.pack(side="left", padx=4, ipady=2)
        self._force_focus_on_click(self.todo_minutes)
        tk.Label(remind, text="min (optional)", font=(FONT, 8), bg=self.BG_CHAT, fg=INK).pack(side="left")

        tk.Label(frame, text="Tick the box when done  -  press \u2715 to delete", font=(FONT, 7),
                 bg=self.BG_CHAT, fg=INK).pack(anchor="w", padx=8)

        bottom = tk.Frame(frame, bg=self.BG_CHAT)
        bottom.pack(side="bottom", fill="x", padx=6, pady=6)
        self.todo_clear_btn = self._small_button(bottom, "Clear finished tasks", self._clear_done_todos)

        holder = tk.Frame(frame, bg=self.BG_CHAT)
        holder.pack(fill="both", expand=True, padx=6, pady=(2, 0))
        canvas = Canvas(holder, bg="#FFFFFF", highlightthickness=0)
        scrollbar = Scrollbar(holder, orient="vertical", command=canvas.yview)
        self.todo_list_frame = tk.Frame(canvas, bg="#FFFFFF")
        window = canvas.create_window((0, 0), window=self.todo_list_frame, anchor="nw")
        self.todo_list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._refresh_todos()
        self.todo_entry.focus_force()

    def _refresh_todos(self):
        if not self._alive("todo_popup"):
            return
        for w in self.todo_list_frame.winfo_children():
            w.destroy()
        todos = main.DATA["todos"]
        if not todos:
            tk.Label(self.todo_list_frame, text="Nothing to do - nice!", font=(FONT, 9),
                     bg="#FFFFFF", fg=INK).pack(pady=20)
        for i, t in enumerate(todos):
            row = tk.Frame(self.todo_list_frame, bg="#FFFFFF")
            row.pack(fill="x", padx=4, pady=1)
            font = (FONT, 9, "overstrike") if t["done"] else (FONT, 9)
            fg = "#999999" if t["done"] else INK
            tk.Checkbutton(row, text=t["text"], variable=tk.BooleanVar(value=t["done"]), anchor="w",
                           justify="left", wraplength=190, font=font, fg=fg, bg="#FFFFFF",
                           activebackground="#FFFFFF", activeforeground=fg, selectcolor="#FFFFFF",
                           bd=0, highlightthickness=0, cursor="hand2",
                           command=lambda i=i: self._todo_action(main.toggle_todo, i)).pack(side="left", fill="x", expand=True)
            tk.Button(row, text="\u2715", font=(FONT, 8, "bold"), fg="#B00020", bg="#FFFFFF",
                      activebackground="#FFE0E0", bd=0, cursor="hand2",
                      command=lambda i=i: self._todo_action(main.delete_todo, i)).pack(side="right")
        if any(t["done"] for t in todos):
            self.todo_clear_btn.pack(side="left", padx=(0, 4))
        else:
            self.todo_clear_btn.pack_forget()

    def _todo_action(self, action, *args):
        action(*args)
        self._refresh_todos()

    def _clear_done_todos(self):
        self._todo_action(main.clear_done_todos)

    def _add_todo(self):
        text = self.todo_entry.get().strip()
        if not text:
            return
        raw = self.todo_minutes.get().strip()
        try:
            minutes = float(raw) if raw else None
        except ValueError:
            minutes = None
        main.add_todo(text, remind_minutes=minutes)
        self.todo_entry.delete(0, tk.END)
        self.todo_minutes.delete(0, tk.END)
        self._refresh_todos()
        if minutes:
            self.append_message("Coco", f"Okay, I'll sound an alarm for '{text}' in {raw} minute(s).")

    def show_alarm_popup(self, message):
        if self._alive("alarm_popup"):
            self.alarm_popup.destroy()
        popup = tk.Toplevel(self.root)
        popup.title("Coco Reminder")
        popup.attributes("-topmost", True)
        popup.configure(bg=self.BG_CHAT)
        sw, sh = popup.winfo_screenwidth(), popup.winfo_screenheight()
        popup.geometry(f"360x190+{(sw - 360) // 2}+{(sh - 190) // 3}")

        tk.Label(popup, text="⏰  Reminder", font=(FONT, 14, "bold"), bg=self.BG_CHAT,
                 fg=self.HEADER_BG).pack(pady=(14, 4))
        tk.Label(popup, text=message, font=(FONT, 11), wraplength=320, justify="center",
                 bg=self.BG_CHAT, fg=INK).pack(pady=4, padx=12)

        def dismiss():
            main.stop_alarm()
            if popup.winfo_exists():
                popup.destroy()
            self.alarm_popup = None

        def snooze():
            main.snooze(message, 5)
            dismiss()
            self.append_message("Coco", "Snoozed for 5 minutes.")

        row = tk.Frame(popup, bg=self.BG_CHAT)
        row.pack(pady=12)
        self._btn(row, "Dismiss", dismiss, font=(FONT, 10, "bold"), padx=16, pady=4).pack(side="left", padx=6)
        self._btn(row, "Snooze 5 min", snooze, bg=self.HEADER_BG, fg=self.HEADER_FG,
                  font=(FONT, 10, "bold"), padx=16, pady=4).pack(side="left", padx=6)

        popup.protocol("WM_DELETE_WINDOW", dismiss)
        popup.lift()
        popup.focus_force()
        self.alarm_popup = popup

    def _contact_names(self):
        contacts, phones = main.DATA["contacts"], main.DATA["phones"]
        have = {c.lower() for c in contacts}
        return list(contacts) + [n for n in phones if n.lower() not in have]

    def open_contacts_popup(self):
        frame = self._build_popup("Contacts", 300, 370, "contacts_popup")
        self.contacts_listbox = self._make_listbox(frame)
        self.contacts_listbox.config(height=8)

        form = tk.Frame(frame, bg=self.BG_CHAT)
        form.pack(fill="x", padx=6, pady=(4, 0))
        self.contact_entries = {}
        for label in ("Name", "Email", "Phone (optional)"):
            row = tk.Frame(form, bg=self.BG_CHAT)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, width=14, anchor="w", font=(FONT, 8), bg=self.BG_CHAT, fg=INK).pack(side="left")
            entry = tk.Entry(row, font=(FONT, 9), bd=1, relief="solid")
            entry.pack(side="left", fill="x", expand=True, ipady=2)
            self._force_focus_on_click(entry)
            self.contact_entries[label] = entry

        buttons = tk.Frame(frame, bg=self.BG_CHAT)
        buttons.pack(fill="x", padx=6, pady=6)
        self._small_button(buttons, "Add contact", self._add_contact)
        self._small_button(buttons, "Delete selected", self._delete_contact)
        self._refresh_contacts()
        self.contact_entries["Name"].focus_force()

    def _refresh_contacts(self):
        if not self._alive("contacts_popup"):
            return
        names = self._shown_contacts = self._contact_names()
        self.contacts_listbox.delete(0, tk.END)
        if not names:
            self.contacts_listbox.insert(tk.END, "(no contacts yet)")
            return
        phones = {k.lower(): v for k, v in main.DATA["phones"].items()}
        for i, n in enumerate(names, 1):
            parts = (main.DATA["contacts"].get(n, ""), phones.get(n.lower(), ""))
            self.contacts_listbox.insert(tk.END, f"{i}. {n}  -  " + ", ".join(p for p in parts if p))

    def _add_contact(self):
        name = self.contact_entries["Name"].get().strip()
        email_addr = self.contact_entries["Email"].get().strip()
        phone_raw = self.contact_entries["Phone (optional)"].get().strip()
        if not name or not (email_addr or phone_raw):
            self.append_message("Coco", "A contact needs a name and an email (or a phone number).")
            return
        if email_addr:
            if not re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", email_addr):
                self.append_message("Coco", "That email address doesn't look right.")
                return
            main.DATA["contacts"][name] = email_addr
        if phone_raw:
            phone = main._clean_phone(phone_raw)
            if not phone:
                self.append_message("Coco", "That phone number doesn't look right.")
                return
            main.DATA["phones"][name] = phone
        main._save_data()
        for entry in self.contact_entries.values():
            entry.delete(0, tk.END)
        self._refresh_contacts()

    def _delete_contact(self):
        selection = self.contacts_listbox.curselection()
        names = getattr(self, "_shown_contacts", [])
        if selection and selection[0] < len(names):
            main.delete_contact(names[selection[0]])
            self._refresh_contacts()

    def close_app(self):
        main.is_listening = False
        main.stop_alarm()
        try:
            main.stop_recording()
        except Exception:
            pass
        main.running = False
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.root.destroy()


if __name__ == "__main__":
    if main.already_running():
        sys.exit(0)
    app = CocoGUI()
    main.gui_widget = app
    app.setup_first_run()
    threading.Thread(target=main.assistant_backend, daemon=True).start()
    app.root.mainloop()
