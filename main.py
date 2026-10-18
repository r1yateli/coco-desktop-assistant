import ast
import asyncio
import ctypes
import datetime
import difflib
import email
import heapq
import imaplib
import itertools
import json
import operator
import os
import queue
import random
import re
import smtplib
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

is_listening = False
running = True
gui_widget = None

OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "Coco Output")
MY_NAME = "Riya Teli"
EDGE_VOICE = "en-US-AnaNeural"
EDGE_PITCH = "+12Hz"
EDGE_RATE = "+8%"
DEFAULT_COUNTRY_CODE = "+91"
SPOTIFY_MODE = "youtube"
GROQ_MODELS = ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile")

if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

DATA_FILE = os.path.join(_BASE_DIR, "coco_data.json")
_data_lock = threading.Lock()
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _read_lines(name):
    try:
        with open(os.path.join(_BASE_DIR, name), encoding="utf-8") as f:
            return [ln.strip() for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        return []


def _groq_key():
    return os.environ.get("GROQ_API_KEY", "").strip() or next(iter(_read_lines("groq_key.txt")), "")


def _email_creds():
    addr = os.environ.get("COCO_EMAIL", "").strip()
    pw = os.environ.get("COCO_EMAIL_PASSWORD", "").replace(" ", "").strip()
    if addr and pw:
        return addr, pw
    lines = _read_lines("coco_email.txt")
    return (lines[0], lines[1].replace(" ", "")) if len(lines) >= 2 else ("", "")


_DEFAULT_DATA = {"history": [], "notes": [], "todos": [], "reminders": [], "contacts": {},
                 "phones": {}, "scheduled_emails": []}


def _load_data():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            saved = json.load(f)
    except Exception:
        saved = {}
    return {k: type(v)(saved.get(k, v)) for k, v in _DEFAULT_DATA.items()}


DATA = _load_data()


def _save_data():
    with _data_lock:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(DATA, f, indent=2)
        except Exception as e:
            print(f"Could not save data: {e}")


def _cap(text):
    return text[:1].upper() + text[1:]


def _json_from(raw):
    return json.loads(re.search(r"\{.*\}", raw, re.S).group(0), strict=False)


def _powershell(script, env, timeout):
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   env={**os.environ, **env}, creationflags=_NO_WINDOW, timeout=timeout,
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class CommandHistory:
    def __init__(self, max_size=200):
        self._stack = DATA["history"]
        self._max_size = max_size

    def push(self, command_text):
        self._stack.append({"command": command_text, "time": datetime.datetime.now().strftime("%H:%M:%S")})
        if len(self._stack) > self._max_size:
            self._stack.pop(0)
        _save_data()

    def get_all_most_recent_first(self):
        return list(reversed(self._stack))

    def previous_real_command(self):
        for entry in reversed(self._stack[:-1]):
            if not re.match(r"^\s*(repeat|again|do that again)", entry["command"].lower()):
                return entry["command"]
        return None

    def clear(self):
        self._stack.clear()
        _save_data()


command_history = CommandHistory()


_speech_queue = queue.Queue()

_SAPI_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$f = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Gender -eq 'Female' } "
    "| Select-Object -First 1; "
    "if ($f) { $s.SelectVoice($f.VoiceInfo.Name) }; "
    "$t = [System.Security.SecurityElement]::Escape($env:COCO_SPEAK_TEXT); "
    "$x = '<speak version=\"1.0\" xmlns=\"http://www.w3.org/2001/10/synthesis\" xml:lang=\"en-US\">"
    "<prosody pitch=\"x-high\" rate=\"medium\">' + $t + '</prosody></speak>'; "
    "try { $s.SpeakSsml($x) } catch { $s.Speak($env:COCO_SPEAK_TEXT) }"
)


def _play_mp3(path):
    mci = ctypes.windll.winmm.mciSendStringW
    mci("close cocovoice", None, 0, 0)
    mci(f'open "{path}" type mpegvideo alias cocovoice', None, 0, 0)
    mci("play cocovoice wait", None, 0, 0)
    mci("close cocovoice", None, 0, 0)


def _speak_edge(text):
    try:
        import edge_tts
    except ImportError:
        return False
    path = os.path.join(tempfile.gettempdir(), f"coco_voice_{os.getpid()}.mp3")
    try:
        asyncio.run(edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE, pitch=EDGE_PITCH).save(path))
        _play_mp3(path)
        return True
    except Exception as e:
        print(f"edge-tts failed ({type(e).__name__}: {e}); using offline voice...")
        return False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _speak_blocking(text):
    if os.name == "nt":
        if _speak_edge(text):
            return
        try:
            _powershell(_SAPI_SCRIPT, {"COCO_SPEAK_TEXT": text}, 90)
            return
        except Exception as e:
            print(f"PowerShell speech failed ({e}); falling back to pyttsx3...")
    if pyttsx3:
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 185)
            for v in engine.getProperty("voices"):
                if "zira" in v.name.lower() or "female" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"Speech error: {e}")


def _speech_worker():
    while True:
        text = _speech_queue.get()
        try:
            if text is None:
                break
            _speak_blocking(text)
        finally:
            _speech_queue.task_done()


def is_speaking():
    return _speech_queue.unfinished_tasks > 0


threading.Thread(target=_speech_worker, daemon=True).start()


def speak(text, voice=True):
    print(f"Coco: {text}")
    if gui_widget:
        gui_widget.append_message("Coco", text)
    if voice:
        spoken = re.sub(r"[^\x00-\x7F\u00b0]", "", text)[:400]
        if spoken.strip():
            _speech_queue.put(spoken)


_reminders = []
_reminder_lock = threading.Lock()
_reminder_id = itertools.count()
_UNIT_SECONDS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600}
_UNIT_RE = r"(seconds?|secs?|minutes?|mins?|hours?|hrs?)"
_alarm_stop = threading.Event()


def _to_seconds(n, unit):
    return int(n) * _UNIT_SECONDS.get(unit.rstrip("s"), 60)


def _gui_call(method, *args):
    if gui_widget and hasattr(gui_widget, method):
        gui_widget.root.after(0, getattr(gui_widget, method), *args)


def _drop_saved_reminder(due, message):
    DATA["reminders"] = [r for r in DATA["reminders"] if not (r["due"] == due and r["message"] == message)]


def add_reminder(message, seconds, label=None):
    due = time.time() + seconds
    rid = next(_reminder_id)
    with _reminder_lock:
        heapq.heappush(_reminders, (due, rid, message))
        DATA["reminders"].append({"due": due, "message": message})
    _save_data()
    _gui_call("add_timer_display", rid, label or message, due)
    return rid


def cancel_all_reminders():
    with _reminder_lock:
        ids = [item[1] for item in _reminders]
        _reminders.clear()
        DATA["reminders"] = []
    _save_data()
    for rid in ids:
        _gui_call("remove_timer_display", rid)


for _r in DATA["reminders"]:
    heapq.heappush(_reminders, (_r["due"], next(_reminder_id), _r["message"]))


def _alarm_sound_loop(max_seconds=45):
    end_time = time.time() + max_seconds
    while not _alarm_stop.is_set() and time.time() < end_time:
        try:
            import winsound
            for freq in (880, 1175, 880, 1175, 880, 1175):
                if _alarm_stop.is_set():
                    break
                winsound.Beep(freq, 220)
        except Exception:
            print("\a", end="", flush=True)
            _alarm_stop.wait(0.6)
        _alarm_stop.wait(1.2)


def start_alarm():
    _alarm_stop.clear()
    threading.Thread(target=_alarm_sound_loop, daemon=True).start()


def stop_alarm():
    _alarm_stop.set()


def snooze(message, minutes=5):
    stop_alarm()
    add_reminder(message, minutes * 60)


_TOAST_SCRIPT = ("Add-Type -AssemblyName System.Windows.Forms; "
                 "Add-Type -AssemblyName System.Drawing; "
                 "$n = New-Object System.Windows.Forms.NotifyIcon; "
                 "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                 "$n.BalloonTipTitle = $env:COCO_NOTE_TITLE; "
                 "$n.BalloonTipText = $env:COCO_NOTE_TEXT; "
                 "$n.Visible = $true; $n.ShowBalloonTip(10000); "
                 "Start-Sleep -Seconds 11; $n.Dispose()")


def notify_desktop(title, message):
    def worker():
        if os.name == "nt":
            try:
                _powershell(_TOAST_SCRIPT, {"COCO_NOTE_TITLE": title, "COCO_NOTE_TEXT": message}, 30)
                return
            except Exception as e:
                print(f"Notification failed: {e}")
        try:
            from plyer import notification
            notification.notify(title=title, message=message, app_name="Coco", timeout=10)
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True).start()


def fire_alarm(message):
    start_alarm()
    notify_desktop("Coco Reminder", message)
    speak(message)
    if gui_widget:
        gui_widget.root.after(0, gui_widget.show_alarm_popup, message)


def _scheduler_loop():
    time.sleep(3)
    while running:
        due = []
        with _reminder_lock:
            while _reminders and _reminders[0][0] <= time.time():
                item = heapq.heappop(_reminders)
                due.append(item)
                _drop_saved_reminder(item[0], item[2])
        if due:
            _save_data()
        for due_ts, rid, message in due:
            _gui_call("remove_timer_display", rid)
            fire_alarm(f"(Missed) {message}" if time.time() - due_ts > 60 else message)
        time.sleep(1)


threading.Thread(target=_scheduler_loop, daemon=True).start()


def add_note(text):
    DATA["notes"].append(text)
    _save_data()


def delete_note(index):
    if 0 <= index < len(DATA["notes"]):
        DATA["notes"].pop(index)
        _save_data()


def add_todo(text, remind_minutes=None):
    DATA["todos"].append({"text": text, "done": False})
    _save_data()
    if remind_minutes:
        add_reminder(f"To-do reminder: {text}", int(remind_minutes * 60))


def toggle_todo(index):
    if 0 <= index < len(DATA["todos"]):
        DATA["todos"][index]["done"] = not DATA["todos"][index]["done"]
        _save_data()


def delete_todo(index):
    if 0 <= index < len(DATA["todos"]):
        DATA["todos"].pop(index)
        _save_data()


def clear_done_todos():
    DATA["todos"] = [t for t in DATA["todos"] if not t["done"]]
    _save_data()


APPS = {
    "notepad": "notepad.exe", "note pad": "notepad.exe",
    "calculator": "calc.exe", "calc": "calc.exe",
    "paint": "mspaint.exe",
    "task manager": "taskmgr.exe",
    "file explorer": "explorer.exe", "explorer": "explorer.exe", "files": "explorer.exe",
    "command prompt": "cmd.exe", "cmd": "cmd.exe", "terminal": "wt",
    "recycle bin": "shell:RecycleBinFolder",
    "settings": "ms-settings:", "control panel": "control.exe",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "spotify": "spotify:",
    "vscode": "code", "vs code": "code", "visual studio code": "code",
    "snipping tool": "snippingtool", "sticky notes": "stikynot",
    "clock": "ms-clock:", "calendar": "outlookcal:",
    "photos": "ms-photos:", "camera": "microsoft.windows.camera:",
    "discord": "discord", "notion": "notion",
}
SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "whatsapp": "https://web.whatsapp.com",
    "github": "https://github.com", "instagram": "https://www.instagram.com",
    "browser": "https://www.google.com", "chrome": "https://www.google.com",
    "wikipedia": "https://www.wikipedia.org", "maps": "https://maps.google.com",
    "chatgpt": "https://chatgpt.com", "reddit": "https://www.reddit.com",
    "linkedin": "https://www.linkedin.com", "stackoverflow": "https://stackoverflow.com",
    "netflix": "https://www.netflix.com", "prime video": "https://www.primevideo.com",
    "hotstar": "https://www.hotstar.com", "google drive": "https://drive.google.com",
    "google translate": "https://translate.google.com",
    "amazon": "https://www.amazon.in",
}
JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "Why did the developer go broke? He used up all his cache.",
    "There are 10 kinds of people: those who understand binary and those who don't.",
    "A SQL query walks into a bar, sees two tables and asks: can I join you?",
    "Why was the stack so tidy? It always popped what it pushed.",
]
HELP_TEXT = ("I can open apps and websites, play songs on YouTube, look things up on Wikipedia, "
             "search Google, do maths, tell the weather, set alarm-style reminders and timers, "
             "keep notes and a to-do list, take screenshots, record your screen, send WhatsApp messages, "
             "and repeat your last command. For email I can read and summarize your unread mails, "
             "find urgent mails, write an email with AI (say 'write an email for leave'), reply to mails, "
             "schedule emails for later, show your contacts, and I always ask you before sending. "
             "I understand typos and Hinglish too.")

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


def _normalize(text):
    t = text.lower().strip()
    t = re.sub(r"^(?:hey|hi|hello|ok|okay)\b[,\s]*(?:coco\b[,\s]*)?", "", t) or t
    t = re.sub(r"^coco\b[,\s]*", "", t)
    t = re.sub(r"\bplease\b", "", t)
    return re.sub(r"\s+", " ", t).strip(" ?!.,")


def _launch(target):
    try:
        os.startfile(target)
        return True
    except Exception as e:
        print(f"Launch error for {target}: {e}")
        return False


_WIKI_UA = "CocoDesktopAssistant/1.0 (student project; python-urllib)"


def _wiki_api(params):
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": _WIKI_UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _wiki_direct(topic):
    data = _wiki_api({"action": "opensearch", "search": topic, "limit": 3, "namespace": 0})
    titles = data[1] if len(data) > 1 else []
    if not titles:
        data = _wiki_api({"action": "query", "list": "search", "srsearch": topic, "srlimit": 3})
        titles = [h["title"] for h in data.get("query", {}).get("search", [])]
    for title in titles:
        d = _wiki_api({"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
                       "exsentences": 2, "redirects": 1, "titles": title})
        for page in d.get("query", {}).get("pages", {}).values():
            extract = (page.get("extract") or "").strip()
            if extract and "may refer to" not in extract[:200]:
                return extract
    return None


def wiki_lookup(topic):
    try:
        return _wiki_direct(topic), None
    except Exception as e:
        print(f"Wikipedia direct API error: {type(e).__name__}: {e}")
        error = f"{type(e).__name__}: {e}"
    try:
        import wikipedia
        if hasattr(wikipedia, "set_user_agent"):
            wikipedia.set_user_agent(_WIKI_UA)
        else:
            wikipedia.wikipedia.USER_AGENT = _WIKI_UA
        try:
            return wikipedia.summary(topic, sentences=2, auto_suggest=False), None
        except wikipedia.exceptions.DisambiguationError as e:
            return wikipedia.summary(e.options[0], sentences=2, auto_suggest=False), None
        except wikipedia.exceptions.PageError:
            found = wikipedia.search(topic, results=1)
            return (wikipedia.summary(found[0], sentences=2, auto_suggest=False) if found else None), None
    except ImportError:
        pass
    except Exception as e:
        print(f"Wikipedia module error: {type(e).__name__}: {e}")
    return None, f"I couldn't reach Wikipedia ({error})."


_chat_memory = []


def _groq(messages, max_tokens=900, temperature=0.5, timeout=25, json_mode=False):
    key = _groq_key()
    if not key:
        return None
    for model in GROQ_MODELS:
        payload = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "messages": messages}
        if model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"].strip()
            if text:
                return text
        except Exception as e:
            print(f"[Groq] {model} failed: {e}")
    return None


def groq_task(system, user, max_tokens=900):
    return _groq([{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens)


def ask_groq(prompt):
    messages = [{"role": "system", "content": "You are Coco, a friendly desktop assistant. "
                 "Answer in 1-2 short sentences unless asked for more detail."}]
    messages += _chat_memory[-6:] + [{"role": "user", "content": prompt}]
    text = _groq(messages, max_tokens=1000, temperature=0.7, timeout=15)
    if text:
        _chat_memory.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": text}])
        del _chat_memory[:-10]
    return text


def _youtube_first_video(query):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=10) as r:
        html = r.read().decode("utf-8", "ignore")
    m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})"', html) or re.search(r'"videoId":"([\w-]{11})"', html)
    return m.group(1) if m else None


def play_on_youtube(query):
    try:
        vid = _youtube_first_video(query)
    except Exception as e:
        print(f"YouTube lookup failed: {e}")
        vid = None
    if vid:
        webbrowser.open(f"https://www.youtube.com/watch?v={vid}&autoplay=1")
        return f"Playing {query} on YouTube."
    webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query))
    return f"I couldn't pick a video automatically, so I opened the YouTube results for {query}."


def play_on_spotify(query):
    if SPOTIFY_MODE == "youtube":
        return play_on_youtube(query) + " Spotify can't auto-play, so I used YouTube."
    webbrowser.open("https://open.spotify.com/search/" + urllib.parse.quote(query))
    return f"Searching Spotify for {query}. Press play there - then 'pause' / 'next song' control it."


def _media_key(vk):
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def _dpi_aware_thread():
    try:
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-2))
    except Exception:
        pass


def take_screenshot():
    folder = os.path.join(OUTPUT_DIR, "Screenshots")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, datetime.datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png"))
    try:
        import mss
        with mss.mss() as sct:
            sct.shot(output=path)
        return f"Screenshot saved in {folder}."
    except ImportError:
        pass
    if ImageGrab is None:
        return "Screenshots need mss or Pillow. Run: pip install mss pillow"
    _dpi_aware_thread()
    try:
        ImageGrab.grab(all_screens=True).save(path)
    except TypeError:
        ImageGrab.grab().save(path)
    return f"Screenshot saved in {folder}."


_rec_stop = threading.Event()
_rec_thread = None
_rec_path = None


def _record_worker(path, fps=10):
    _dpi_aware_thread()
    import cv2
    import numpy as np
    try:
        import mss
        sct = mss.mss()
        mon = sct.monitors[0]
        size = (mon["width"], mon["height"])

        def grab():
            return cv2.cvtColor(np.array(sct.grab(mon)), cv2.COLOR_BGRA2BGR)
    except ImportError:
        sct = None
        size = ImageGrab.grab().size

        def grab():
            return cv2.cvtColor(np.array(ImageGrab.grab()), cv2.COLOR_RGB2BGR)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    start, written = time.time(), 0
    try:
        while not _rec_stop.is_set() and running:
            frame = grab()
            target = int((time.time() - start) * fps) + 1
            while written < target:
                writer.write(frame)
                written += 1
    finally:
        writer.release()
        if sct:
            sct.close()


def start_recording():
    global _rec_thread, _rec_path
    if _rec_thread and _rec_thread.is_alive():
        return "I'm already recording your screen."
    if ImageGrab is None:
        return "Screen recording needs Pillow. Run: pip install pillow"
    try:
        import cv2, numpy  # noqa: F401
    except ImportError:
        return "Screen recording needs two packages. Run: pip install opencv-python numpy"
    folder = os.path.join(OUTPUT_DIR, "Recordings")
    os.makedirs(folder, exist_ok=True)
    _rec_path = os.path.join(folder, datetime.datetime.now().strftime("recording_%Y%m%d_%H%M%S.mp4"))
    _rec_stop.clear()
    _rec_thread = threading.Thread(target=_record_worker, args=(_rec_path,), daemon=True)
    _rec_thread.start()
    return "Recording your screen. Say 'stop recording' when you're done."


def stop_recording():
    global _rec_thread
    if not (_rec_thread and _rec_thread.is_alive()):
        return "I'm not recording right now."
    _rec_stop.set()
    _rec_thread.join(timeout=15)
    _rec_thread = None
    return f"Recording saved: {os.path.basename(_rec_path)} in {os.path.dirname(_rec_path)}."


def _spoken_to_address(text):
    t = text.lower().replace(" at the rate of ", "@").replace(" at ", "@").replace(" dot ", ".")
    t = t.replace(" underscore ", "_").replace(" dash ", "-").replace(" ", "")
    return t if re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", t) else None


def _fuzzy_lookup(name, table):
    name = name.strip().lower()
    lowered = {k.lower(): v for k, v in table.items()}
    if name in lowered:
        return lowered[name]
    close = difflib.get_close_matches(name, list(lowered), n=1, cutoff=0.7)
    return lowered[close[0]] if close else None


def _resolve_recipient(name):
    return _fuzzy_lookup(name, DATA["contacts"]) or _spoken_to_address(name.strip().lower())


def _no_email_for(who):
    return f"I don't have an email for {who}. Say: add contact {who} email name at gmail dot com."


def send_email(to_addr, subject, body):
    addr, pw = _email_creds()
    if not (addr and pw):
        webbrowser.open("https://mail.google.com/mail/?view=cm&fs=1&to=" + urllib.parse.quote(to_addr)
                        + "&su=" + urllib.parse.quote(subject) + "&body=" + urllib.parse.quote(body))
        return ("I opened Gmail with the email filled in - just press send. "
                "(To send automatically, put your Gmail and App Password in coco_email.txt.)")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = addr, to_addr, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(addr, pw)
            server.send_message(msg)
        return f"Email sent to {to_addr}."
    except smtplib.SMTPAuthenticationError:
        return "Gmail rejected the login. Use a Gmail App Password, not your normal password."
    except Exception as e:
        return f"I couldn't send the email: {e}"


def _email_text(msg):
    plain = html = ""
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html") or part.get_content_disposition() == "attachment":
            continue
        text = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "ignore")
        if ctype == "text/plain" and not plain:
            plain = text
        elif ctype == "text/html" and not html:
            html = text
    if plain.strip():
        return plain.strip()
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


_last_email = {}


def _fetch_emails(limit=5, unseen=True, sender=None):
    addr, pw = _email_creds()
    if not (addr and pw):
        raise RuntimeError("Email isn't set up yet. Put your Gmail and App Password in coco_email.txt.")
    out = []
    with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
        mail.login(addr, pw)
        mail.select("INBOX", readonly=True)
        criteria = ["UNSEEN"] if unseen else ["ALL"]
        if sender:
            criteria += ["FROM", f'"{sender}"']
        _, data = mail.search(None, *criteria)
        ids = data[0].split()
        for i in ids[-limit:][::-1]:
            _, parts = mail.fetch(i, "(BODY.PEEK[])")
            msg = email.message_from_bytes(parts[0][1])
            subject = str(make_header(decode_header(msg.get("Subject", "(no subject)"))))
            name, address = parseaddr(str(make_header(decode_header(msg.get("From", "")))))
            out.append({"name": name or address, "addr": address, "subject": subject, "body": _email_text(msg)})
    return out, len(ids)


def _mail_error(e):
    if isinstance(e, RuntimeError):
        return str(e)
    if isinstance(e, imaplib.IMAP4.error):
        return "Gmail rejected the login. Use a Gmail App Password (see coco_email.txt)."
    return f"I couldn't read your email: {e}"


def _preview(text, n):
    return re.sub(r"\s+", " ", text)[:n]


def read_unread_emails():
    global _last_email
    try:
        mails, total = _fetch_emails(limit=5)
    except Exception as e:
        return _mail_error(e)
    if not mails:
        return "You have no unread emails."
    _last_email = mails[0]
    lines = [f"{n}. {m['name']} - {m['subject']}. {_preview(m['body'], 150)}" for n, m in enumerate(mails, 1)]
    head = f"You have {total} unread email(s)." + (f" Here are the latest {len(mails)}:" if total > len(mails) else "")
    return head + "\n" + "\n".join(lines) + "\nSay 'reply saying ...' to answer the first one."


def summarize_emails():
    global _last_email
    try:
        mails, total = _fetch_emails(limit=5)
    except Exception as e:
        return _mail_error(e)
    if not mails:
        return "You have no unread emails."
    _last_email = mails[0]
    chunks = [f"From: {m['name']}\nSubject: {m['subject']}\n{m['body'][:500]}" for m in mails]
    summary = groq_task("Summarize these emails in 3 short sentences total. Mention who sent what "
                        "and anything urgent. Plain text only.", "\n\n---\n\n".join(chunks))
    return summary or f"You have {total} unread emails, but I need a Groq key + internet to summarize them."


def read_latest_email(who=None):
    global _last_email
    sender = (_resolve_recipient(who) or who) if who else None
    try:
        mails, _ = _fetch_emails(limit=1, unseen=False, sender=sender)
    except Exception as e:
        return _mail_error(e)
    if not mails:
        return "I couldn't find any email" + (f" from {who}." if who else ".")
    _last_email = m = mails[0]
    return f"Latest email from {m['name']}. Subject: {m['subject']}. {_preview(m['body'], 300)}"


_URGENT_WORDS = ("urgent", "asap", "immediately", "important", "deadline", "last date", "due today",
                 "due tomorrow", "action required", "final notice", "interview", "exam", "reminder")


def urgent_emails():
    global _last_email
    try:
        mails, _ = _fetch_emails(limit=10)
    except Exception as e:
        return _mail_error(e)
    if not mails:
        return "You have no unread emails, so nothing is urgent."
    listing = "\n\n".join(f"[{n}] From: {m['name']}\nSubject: {m['subject']}\n{m['body'][:300]}"
                          for n, m in enumerate(mails, 1))
    raw = groq_task('Find the URGENT emails: a deadline, a request for immediate action, an exam, '
                    'interview, payment or security alert, or a message from a boss/teacher. Ignore '
                    'promotions and newsletters. Reply ONLY with JSON: '
                    '{"urgent": [{"n": <email number>, "reason": "<5 words>"}]}. Use [] if none.', listing)
    try:
        found = [(mails[int(i["n"]) - 1], str(i.get("reason", "")).strip()) for i in _json_from(raw)["urgent"]]
        how = "AI"
    except Exception:
        found = [(m, "urgent word found") for m in mails
                 if any(w in (m["subject"] + " " + m["body"][:300]).lower() for w in _URGENT_WORDS)]
        how = "keyword"
    if not found:
        return f"Checked {len(mails)} unread emails - nothing looks urgent."
    _last_email = found[0][0]
    lines = [f"{i}. {m['name']} - {m['subject']} ({why})" for i, (m, why) in enumerate(found, 1)]
    return (f"{len(found)} urgent out of {len(mails)} unread ({how} check):\n" + "\n".join(lines)
            + "\nSay 'reply saying ...' to answer the first one.")


def show_contacts():
    contacts = DATA["contacts"]
    names = list(contacts) + [n for n in DATA["phones"] if n.lower() not in {c.lower() for c in contacts}]
    if not names:
        return "You have no contacts yet. Say: add contact riya email riya at gmail dot com."
    phones = {k.lower(): v for k, v in DATA["phones"].items()}
    lines = [f"{i}. {n} - " + ", ".join(p for p in (contacts.get(n, ""), phones.get(n.lower(), "")) if p)
             for i, n in enumerate(names, 1)]
    return f"You have {len(names)} contact(s):\n" + "\n".join(lines)


def delete_contact(name):
    name = name.strip().lower()
    found = False
    for store in (DATA["contacts"], DATA["phones"]):
        for k in [k for k in store if k.lower() == name]:
            del store[k]
            found = True
    if found:
        _save_data()
        return f"Deleted contact {name}."
    return f"I couldn't find a contact named {name}."


_mail_heap = []
_mail_lock = threading.Lock()
_mail_id = itertools.count()
for _s in DATA["scheduled_emails"]:
    heapq.heappush(_mail_heap, (_s["due"], next(_mail_id), _s["to"], _s["subject"], _s["body"]))


def _parse_when(text):
    t = text.lower().replace(".", "").strip()
    m = re.fullmatch(rf"in (\d+)\s*{_UNIT_RE}", t)
    if m:
        return time.time() + _to_seconds(m.group(1), m.group(2))
    m = re.fullmatch(r"(tomorrow )?at (\d{1,2})(?::(\d{2}))?\s*(a m|p m|am|pm)?", t)
    if not m:
        return None
    tomorrow, hour, minute = m.group(1), int(m.group(2)), int(m.group(3) or 0)
    ampm = (m.group(4) or "").replace(" ", "")
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    now = datetime.datetime.now()
    dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if tomorrow or dt <= now:
        dt += datetime.timedelta(days=1)
    return dt.timestamp()


def _fmt_when(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%I:%M %p on %d %b")


def schedule_email(to, subject, body, due):
    with _mail_lock:
        heapq.heappush(_mail_heap, (due, next(_mail_id), to, subject, body))
        DATA["scheduled_emails"].append({"due": due, "to": to, "subject": subject, "body": body})
    _save_data()
    return f"Done! I'll send that email to {to} at {_fmt_when(due)}. Keep Coco running until then."


def show_scheduled():
    if not DATA["scheduled_emails"]:
        return "You have no scheduled emails."
    items = sorted(DATA["scheduled_emails"], key=lambda s: s["due"])
    return "Scheduled emails:\n" + "\n".join(
        f"{i}. To {s['to']} at {_fmt_when(s['due'])} - {s['subject']}" for i, s in enumerate(items, 1))


def cancel_scheduled():
    with _mail_lock:
        n = len(_mail_heap)
        _mail_heap.clear()
        DATA["scheduled_emails"] = []
    _save_data()
    return f"Cancelled {n} scheduled email(s)." if n else "You have no scheduled emails."


def _mail_scheduler_loop():
    time.sleep(5)
    while running:
        due = []
        with _mail_lock:
            while _mail_heap and _mail_heap[0][0] <= time.time():
                item = heapq.heappop(_mail_heap)
                due.append(item)
                DATA["scheduled_emails"] = [s for s in DATA["scheduled_emails"] if not (
                    s["due"] == item[0] and s["to"] == item[2] and s["subject"] == item[3])]
        if due:
            _save_data()
        for _, _, to, subject, body in due:
            speak("Scheduled email: " + send_email(to, subject, body))
        time.sleep(5)


threading.Thread(target=_mail_scheduler_loop, daemon=True).start()


_pending = None
_YES_RE = (r"(?:yes|yeah|yep|yup|ya|y|sure|ok|okay|send|send it|send it now|yes send it|yes send|"
           r"go ahead|confirm|haan|han|ha|haan bhej do|bhej do|bhej|kar do)")
_CANCEL_RE = r"cancel|never mind|nevermind|stop|forget it|no|nope|nah|nahi|mat bhejo|dont send|don't send"
_NO_ADDRESS = ("Hmm, I don't have an email for {}. "
               "Say a saved contact's name, or an address like 'john at gmail dot com'.")


def _ask(prompt, state):
    global _pending
    _pending = {**state, "time": time.time()}
    return prompt


def _draft_and_confirm(to, subject, body, due=None):
    if due:
        state = {"type": "email_schedule", "due": due}
        ask = f"Say 'yes' to schedule it for {_fmt_when(due)} or 'cancel' to discard."
    else:
        state = {"type": "email_confirm"}
        ask = "Say 'yes' to send it or 'cancel' to discard."
    return _ask(f"Draft to {to}. {ask}\nSubject: {subject}\n\n{body}",
                {**state, "to": to, "subject": subject, "body": body})


def _ai_draft(topic, context=""):
    sign = (f'End the body with "Regards," and then the name "{MY_NAME}" on the next line.'
            if MY_NAME else 'End the body with "Regards".')
    raw = groq_task("You write emails for a student or employee. The request may be in Hinglish "
                    "(for example 'chutti' means leave / time off). Write a short, polite, professional "
                    "email in English. Reply ONLY with JSON: {\"subject\": \"...\", \"body\": \"...\"}. "
                    + sign, f"{context}Write an email about: {topic}")
    try:
        d = _json_from(raw)
        return {"subject": str(d["subject"]).strip(), "body": str(d["body"]).strip()}
    except Exception:
        return None


_DRAFT_FAILED = "Sorry, I couldn't write that email. Check your Groq key and internet, then try again."


def _start_ai_draft(to, topic):
    d = _ai_draft(topic)
    return _draft_and_confirm(to, d["subject"], d["body"]) if d else _DRAFT_FAILED


def _compose_for(who, topic):
    to = _resolve_recipient(who)
    return _start_ai_draft(to, topic) if to else _no_email_for(who)


def _finish_pending(p, raw, cmd):
    kind = p["type"]
    if re.fullmatch(_CANCEL_RE, cmd):
        return "Okay, cancelled. I did not send anything."
    if kind in ("email_confirm", "email_schedule"):
        if not re.fullmatch(_YES_RE, cmd):
            verb = "send" if kind == "email_confirm" else "schedule"
            return f"I didn't hear a clear 'yes', so I did NOT {verb} it. Say the command again to redo the draft."
        if kind == "email_confirm":
            return send_email(p["to"], p["subject"], p["body"])
        return schedule_email(p["to"], p["subject"], p["body"], p["due"])
    if kind in ("ai_email_to", "email_to"):
        to = _resolve_recipient(raw.strip())
        if not to:
            return _ask(_NO_ADDRESS.format(raw.strip()), p)
        if kind == "ai_email_to":
            return _start_ai_draft(to, p["topic"])
        return _ask("Got it. What's the subject of the email?", {"type": "email_subject", "to": to})
    if kind == "email_subject":
        subject = _cap(raw.strip() or "(no subject)")
        return _ask("Okay. What should the email say?", {"type": "email_body", "to": p["to"], "subject": subject})
    if kind == "email_body":
        return send_email(p["to"], p.get("subject") or "Message from Coco", _cap(raw.strip()))
    return None


def h_repeat(cmd):
    if not re.fullmatch(r"repeat(?: (?:that|last|the last))?(?: command)?|again|do that again", cmd):
        return None
    previous = command_history.previous_real_command()
    return process_command(previous) if previous else "There's nothing to repeat yet."


def h_history(cmd):
    if re.search(r"\b(show|open|view)\b.*\bhistory\b", cmd):
        if gui_widget:
            gui_widget.root.after(0, gui_widget.open_history_popup)
        return "Here's your command history."
    return None


def h_reminder(cmd):
    m = re.match(rf"^remind me (?:to |about )?(.+?) (?:in|after) (\d+)\s*{_UNIT_RE}$", cmd)
    if m:
        task, n, unit = m.groups()
    else:
        m = re.match(rf"^remind me (?:in|after) (\d+)\s*{_UNIT_RE} (?:to |about )?(.+)$", cmd)
        if not m:
            return None
        n, unit, task = m.groups()
    add_reminder(f"Reminder: {task}", _to_seconds(n, unit), label=task)
    return f"Okay, I'll remind you to {task} in {n} {unit}."


def h_timer(cmd):
    if re.fullmatch(r"(?:cancel|stop|delete|remove|clear|end)(?: all| my| the)*(?: timers?| alarms?| reminders?)", cmd):
        stop_alarm()
        cancel_all_reminders()
        return "All timers cancelled."
    m = (re.match(rf"^(?:set |start |make )?(?:an? )?(?:timer|alarm)(?: for| of| after| in)? (\d+)\s*{_UNIT_RE}$", cmd)
         or re.match(rf"^(?:set |start |make )?(?:an? )?(\d+)\s*{_UNIT_RE} (?:timer|alarm)$", cmd))
    if not m:
        return None
    n, unit = m.groups()
    add_reminder(f"Time's up! Your {n} {unit} timer is done.", _to_seconds(n, unit), label=f"{n} {unit} timer")
    return f"Timer set for {n} {unit}."


_EMAIL_PREFIX = r"^(?:(?:send|write|compose)(?: an?)? )?(?:e-?mail|mail)(?: to| for)? "


def h_email(cmd):
    m = re.match(r"^add contact (.+?) (?:with )?(?:e-?mail|address) (.+)$", cmd)
    if m:
        name, spoken = m.groups()
        addr = _spoken_to_address(spoken)
        if not addr:
            return "That email address didn't sound right. Say it like: john at gmail dot com."
        DATA["contacts"][name.strip()] = addr
        _save_data()
        return f"Saved {name} as {addr}."
    if re.fullmatch(r"(?:check|read|show)(?: me)?(?: my)? (?:new )?(?:e-?mails?|mail|inbox)", cmd):
        return read_unread_emails()
    if re.fullmatch(r"(?:write|compose|create|draft|send)(?: an?)? (?:e-?)?mail(?: for (?:me|mw|my ?self|us))?$", cmd):
        return _ask("Sure! Who should I send it to? (Say 'cancel' to stop.)", {"type": "email_to"})
    m = re.match(_EMAIL_PREFIX + r"(.+?) subject (.+?) (?:message|body|saying|says) (.+)$", cmd)
    if m:
        who, subject, body = m.groups()
        to = _resolve_recipient(who)
        return send_email(to, subject.capitalize(), _cap(body)) if to else _no_email_for(who)
    m = re.match(_EMAIL_PREFIX + r"(.+?) (?:saying|that says|message|and say|body|that) (.+)$", cmd)
    if m:
        who, body = m.groups()
        to = _resolve_recipient(who)
        return send_email(to, "Message from Coco", _cap(body)) if to else _no_email_for(who)
    m = re.match(_EMAIL_PREFIX + r"(.+)$", cmd)
    if m:
        to = _resolve_recipient(m.group(1))
        if not to:
            return _no_email_for(m.group(1))
        return _ask("Okay. What's the subject of the email? (Say 'cancel' to stop.)", {"type": "email_subject", "to": to})
    return None


def _clean_phone(text):
    digits = re.sub(r"[^\d+]", "", text)
    if not re.fullmatch(r"\+?\d{8,15}", digits):
        return None
    if digits.startswith("+"):
        return digits
    digits = digits.lstrip("0")
    return DEFAULT_COUNTRY_CODE + digits if len(digits) == 10 else "+" + digits


def _resolve_phone(name):
    return _fuzzy_lookup(name, DATA["phones"]) or _clean_phone(name.strip().lower())


def send_whatsapp(phone, text):
    try:
        import pywhatkit
    except ImportError:
        webbrowser.open("https://wa.me/" + phone.lstrip("+") + "?text=" + urllib.parse.quote(text))
        return ("I opened WhatsApp with your message typed in - press Enter to send. "
                "(For automatic sending run: pip install pywhatkit)")

    def worker():
        try:
            pywhatkit.sendwhatmsg_instantly(phone, text, wait_time=15, tab_close=True, close_time=3)
        except Exception as e:
            print(f"WhatsApp send failed: {e}")
    threading.Thread(target=worker, daemon=True).start()
    return f"Sending your WhatsApp message to {phone}. Please don't touch the keyboard for about 20 seconds."


def h_whatsapp(cmd):
    m = re.match(r"^(?:add|save)(?: a)? (?:phone|number|whatsapp)(?: number)?(?: for)? ([a-z][a-z ]*?) ([\d+][\d\s+-]{7,})$", cmd)
    if m:
        name, number = m.groups()
        phone = _clean_phone(number)
        if not phone:
            return "That phone number doesn't look right. Say it like: add phone riya 9876543210."
        DATA["phones"][name.strip()] = phone
        _save_data()
        return f"Saved {name} as {phone}."
    m = (re.match(r"^(?:send |write )?(?:a )?(?:whatsapp|whats app)(?: message| msg| text)?(?: to)? (.+?) "
                  r"(?:saying|that says|to say|and say|message|:) (.+)$", cmd)
         or re.match(r"^(?:send |text |message |msg )(?:a message to )?(.+?) on (?:whatsapp|whats app) "
                     r"(?:saying|that says|to say|and say|message|:)\s*(.+)$", cmd))
    if not m:
        return None
    who, body = m.groups()
    phone = _resolve_phone(who)
    if not phone:
        return f"I don't have a number for {who}. Say: add phone {who} 9876543210."
    return send_whatsapp(phone, _cap(body))


def h_media(cmd):
    if cmd != "stop" and re.fullmatch(
            r"(?:pause|resume|continue|unpause|play|stop)(?: it| that| this| the| my| again)*"
            r"(?: music| song| songs| video| playback| spotify| track)?(?: again)?", cmd):
        _media_key(0xB3)
        return "Okay."
    if re.fullmatch(r"(?:next|skip)(?: it| this| the| one| song| track)*", cmd):
        _media_key(0xB0)
        return "Next song."
    if cmd not in ("last", "back") and re.fullmatch(r"(?:previous|prev|go back|last|back)(?: the| one| song| track)*", cmd):
        _media_key(0xB1)
        return "Previous song."
    return None


def h_youtube(cmd):
    m = re.match(r"^(?:play|search|put on)\s+(.+?)\s+(?:on|in|using|with)\s+(youtube|spotify)$", cmd)
    if m:
        return play_on_youtube(m.group(1)) if m.group(2) == "youtube" else play_on_spotify(m.group(1))
    m = re.match(r"^(youtube|spotify)\s+(?:play\s+)?(.+)$", cmd)
    if m:
        return play_on_youtube(m.group(2)) if m.group(1) == "youtube" else play_on_spotify(m.group(2))
    m = re.match(r"^play\s+(.+)$", cmd)
    return play_on_youtube(m.group(1)) if m else None


def h_notes(cmd):
    if re.fullmatch(r"(?:clear|delete) (?:all )?(?:my )?notes", cmd):
        DATA["notes"].clear()
        _save_data()
        return "All notes cleared."
    if re.fullmatch(r"(?:(?:show|read|list|open)(?: me)? )?(?:my )?notes", cmd):
        if not DATA["notes"]:
            return "You have no notes yet."
        return "Your notes: " + "; ".join(f"{i}. {n}" for i, n in enumerate(DATA["notes"], 1))
    m = re.match(r"^(?:take a note|add a note|add note|note down|note|remember(?: that)?)\s+(.+)$", cmd)
    if m:
        add_note(m.group(1))
        return f"Noted: {m.group(1)}."
    return None


def h_todo(cmd):
    m = re.match(r"^(?:add (?:a )?(?:task|todo|to-do|to do)|new task|todo)\s+(.+)$", cmd)
    if m:
        add_todo(m.group(1))
        return f"Added to your to-do list: {m.group(1)}."
    if re.fullmatch(r"(?:(?:show|list|read|open)(?: me)? )?(?:my )?(?:tasks|todos|to-dos|to do list|todo list)", cmd):
        todos = DATA["todos"]
        if not todos:
            return "Your to-do list is empty."
        return "To-do: " + "; ".join(f"{i}. {'done - ' if t['done'] else ''}{t['text']}" for i, t in enumerate(todos, 1))
    m = re.match(r"^(?:mark task |complete task |finish task |done )(\d+)(?: as done| as complete)?$", cmd)
    if m:
        i = int(m.group(1)) - 1
        if 0 <= i < len(DATA["todos"]):
            toggle_todo(i)
            return f"Updated task {i + 1}."
        return "I don't have a task with that number."
    return None


def h_calc(cmd):
    expr = re.sub(r"^(?:calculate|calc|compute|solve|what is|what's|whats)\s+", "", cmd)
    for word, sym in (("multiplied by", "*"), ("divided by", "/"), ("to the power of", "**"),
                      ("plus", "+"), ("minus", "-"), ("times", "*"), ("into", "*"),
                      ("over", "/"), ("mod", "%")):
        expr = expr.replace(word, sym)
    expr = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", expr).replace("^", "**")
    if not (re.fullmatch(r"[\d\s.+\-*/()%]+", expr) and re.search(r"\d", expr) and re.search(r"[+\-*/%]", expr)):
        return None
    try:
        result = _safe_eval(ast.parse(expr.strip(), mode="eval"))
    except ZeroDivisionError:
        return "You can't divide by zero."
    except Exception:
        return None
    if isinstance(result, float):
        result = int(result) if result.is_integer() else round(result, 4)
    return f"The answer is {result}."


def h_weather(cmd):
    m = re.search(r"\bweather(?:\s+(?:in|at|for|of))?\s*(.*)$", cmd)
    if not m:
        return None
    city = re.sub(r"\b(today|now|like|outside|right|currently)\b", "", m.group(1)).strip(" ?.")
    try:
        req = urllib.request.Request("https://wttr.in/" + urllib.parse.quote(city) + "?format=3",
                                     headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read().decode("utf-8").strip()
    except Exception:
        return "I couldn't fetch the weather. Check your internet connection."


def h_time_date(cmd):
    now = datetime.datetime.now()
    if re.search(r"\b(?:time now|current time|the time|what time)\b", cmd) or cmd == "time":
        return f"It's {now.strftime('%I:%M %p')}."
    if re.search(r"\b(?:today'?s date|the date|what date|what day|current date)\b", cmd) or cmd in ("date", "day"):
        return f"Today is {now.strftime('%A, %d %B %Y')}."
    return None


def h_smalltalk(cmd):
    if re.fullmatch(r"(?:hi+|hello+|hey+|yo|hola|namaste)(?: coco)?", cmd):
        return random.choice(["Hey! How can I help?", "Hello! What can I do for you?", "Hi there!"])
    if re.search(r"\b(?:your name|who are you)\b", cmd):
        return "I'm Coco, your desktop assistant."
    if re.search(r"\bhow are you\b", cmd):
        return "I'm doing great, thanks for asking!"
    if re.search(r"\b(?:thanks|thank you)\b", cmd):
        return "Anytime!"
    if re.search(r"\bjoke\b", cmd):
        return random.choice(JOKES)
    if re.search(r"\b(?:what can you do|help|commands)\b", cmd):
        return HELP_TEXT
    return None


def h_folder(cmd):
    if re.fullmatch(r"open (?:the |my )?(?:coco |output |screenshots? |recordings? )+folder", cmd):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        _launch(OUTPUT_DIR)
        return "Opening your output folder."
    return None


def h_open(cmd):
    m = re.match(r"^(?:open|launch|start|run)\s+(?:the\s+)?(.+)$", cmd)
    if not m:
        return None
    name = m.group(1).strip()
    keys = list(APPS) + list(SITES)
    match = name if name in keys else next(iter(difflib.get_close_matches(name, keys, n=1, cutoff=0.7)), None)
    if not match:
        return f"I don't know how to open {name} yet."
    if match in APPS:
        return f"Opening {match}." if _launch(APPS[match]) else f"I couldn't open {match}."
    webbrowser.open(SITES[match])
    return f"Opening {match}."


def h_search(cmd):
    m = re.match(r"^(?:search|google)(?: for)?\s+(?!wikipedia)(.+)$", cmd)
    if not m:
        return None
    query = re.sub(r"\s+on google$", "", m.group(1)).strip()
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))
    return f"Searching Google for {query}."


def h_system(cmd):
    if re.search(r"\bscreen ?shot\b|\bcapture (?:the |my )?screen\b", cmd):
        return take_screenshot()
    if re.search(r"\b(?:stop|end|finish)\b.*\b(?:record|recording)\b", cmd):
        return stop_recording()
    if re.search(r"\b(?:start|begin)\b.*\b(?:record|recording)\b|\brecord (?:the |my )?screen\b|\bscreen record", cmd):
        return start_recording()
    if re.search(r"\block (?:the |my )?(?:pc|computer|screen|laptop)\b", cmd):
        try:
            ctypes.windll.user32.LockWorkStation()
            return "Locking the computer."
        except Exception:
            return "Locking isn't supported here."
    if re.search(r"\b(?:empty|clear)\b.*\brecycle bin\b", cmd):
        try:
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2)
            return "Recycle bin emptied."
        except Exception:
            return "Couldn't empty the recycle bin."
    if re.search(r"\bcancel\b.*\b(?:shutdown|shut down|restart)\b", cmd):
        os.system("shutdown /a")
        return "Cancelled."
    if re.search(r"\bshut ?down\b", cmd):
        os.system("shutdown /s /t 15")
        return "Shutting down in 15 seconds. Say 'cancel shutdown' to stop it."
    if re.search(r"\brestart\b", cmd):
        os.system("shutdown /r /t 15")
        return "Restarting in 15 seconds. Say 'cancel restart' to stop it."
    return None


_WIKI_RE = re.compile(
    r"^(?:search wikipedia for|wikipedia|who is|who was|who are|what is|what was|what are|"
    r"what's|tell me about|explain|define|describe)\s+(.+)$")


def h_wikipedia(cmd):
    m = _WIKI_RE.match(cmd)
    if not m:
        return None
    topic = re.sub(r"^(?:a |an |the |about )", "", m.group(1).strip())
    if not topic:
        return None
    summary, error = wiki_lookup(topic)
    return summary or ask_groq(cmd) or error or f"I couldn't find anything about {topic} on Wikipedia."


_COMPOSE = r"^(?:write|compose|draft|send|make|create)(?: an?)? (?:e-?mail|mail)"
_SCHED = r"^(?:schedule|send|write|compose|draft)(?: an?)? (?:e-?mail|mail) to "
_WHEN = r"((?:tomorrow )?(?:at|in) \d[\w:. ]*?)"


def h_smart_email(cmd):
    if re.fullmatch(r"(?:summari[sz]e|summary of)(?: my)?(?: new| unread)? (?:e-?mails?|mail|mails|inbox)", cmd):
        return summarize_emails()
    if (re.fullmatch(r"(?:(?:read|check|show|tell|open|give)(?: me)?(?: all)?(?: my)? )?(?:unread|new) "
                     r"(?:e-?mails?|mails?|messages?|inbox)", cmd)
            or re.fullmatch(r"do i have (?:any )?(?:unread|new) (?:e-?mails?|mails?)", cmd)):
        return read_unread_emails()
    m = re.match(r"^(?:read|show|open)(?: me)?(?: my)? (?:latest|last|newest) (?:e-?mail|mail)(?: from (.+))?$", cmd)
    if m:
        return read_latest_email(m.group(1))
    if re.fullmatch(r"(?:(?:check|show|find|read|list|give)(?: me)?(?: my)?|do i have(?: any)?|any|are there any|"
                    r"is there any)? ?(?:urgent|important|priority) (?:e-?mails?|mails?|messages?)(?: in my inbox)?", cmd):
        return urgent_emails()
    if re.fullmatch(r"(?:(?:show|list|read|tell|give)(?: me)?(?: all)?(?: my)?(?: saved)? contacts?(?: list)?|"
                    r"who(?: all)? (?:is|are) (?:in )?my contacts?|my contacts?|contacts?)", cmd):
        return show_contacts()
    m = re.match(r"^(?:delete|remove) contact (.+)$", cmd)
    if m:
        return delete_contact(m.group(1))
    if re.fullmatch(r"(?:show|list|view|check)(?: me)?(?: my| all)? (?:scheduled|pending) (?:e-?mails?|mails?)", cmd):
        return show_scheduled()
    if re.fullmatch(r"(?:cancel|delete|clear|remove)(?: all| my)? (?:scheduled|pending) (?:e-?mails?|mails?)", cmd):
        return cancel_scheduled()
    for pattern, order in ((_SCHED + r"(.+?) " + _WHEN + r" (?:for|about|regarding) (.+)$", "wt"),
                           (_SCHED + r"(.+?) (?:for|about|regarding) (.+?) " + _WHEN + r"$", "tw")):
        m = re.match(pattern, cmd)
        if m:
            who, x, y = m.groups()
            when, topic = (x, y) if order == "wt" else (y, x)
            due = _parse_when(when)
            if not due:
                continue
            to = _resolve_recipient(who)
            if not to:
                return _no_email_for(who)
            d = _ai_draft(topic)
            return _draft_and_confirm(to, d["subject"], d["body"], due=due) if d else _DRAFT_FAILED
    m = re.match(r"^reply\b(?: to (?:that|it|the last|last|the latest|latest|first))?(?: e-?mail| mail)?"
                 r"(?: saying| and say| with| that)? ?(.*)$", cmd)
    if m:
        if not _last_email:
            return "First say 'read my unread emails', then tell me what to reply."
        d = _ai_draft(m.group(1) or "a polite acknowledgement",
                      f"You are replying to this email from {_last_email['name']} "
                      f"(subject: {_last_email['subject']}): {_last_email['body'][:400]}\n")
        if not d:
            return "Sorry, I couldn't write the reply. Check your Groq key and internet."
        subject = _last_email["subject"]
        return _draft_and_confirm(_last_email["addr"],
                                  subject if subject.lower().startswith("re:") else "Re: " + subject, d["body"])
    m = re.match(r"^(?:ai|smart) (?:e-?mail|mail) (?:to )?(.+?) (?:about|regarding|for) (.+)$", cmd)
    if m:
        return _compose_for(*m.groups())
    if re.search(r"\b(?:subject|saying|message|body|that says)\b", cmd):
        return None
    m = re.match(_COMPOSE + r" to (.+?) (?:for|about|regarding) (.+)$", cmd)
    if m:
        return _compose_for(*m.groups())
    m = re.match(_COMPOSE + r" (?:for|about|regarding) (.+?) to (.+)$", cmd)
    if m:
        return _compose_for(m.group(2), m.group(1))
    m = re.match(_COMPOSE + r" (?:for|about|regarding) (.+)$", cmd)
    if m and not re.fullmatch(r"(?:me|mw|my ?self|us)", m.group(1)):
        return _ask(f"Sure, I'll write an email about {m.group(1)}. Who should I send it to? (Say 'cancel' to stop.)",
                    {"type": "ai_email_to", "topic": m.group(1)})
    return None


AI_PROMPT = """You are the command parser of a desktop assistant.
The user's message may contain spelling mistakes, speech-recognition errors, Hinglish,
filler words or number words. Work out what they want and reply with ONLY one JSON object:
{"intent": "<name>", "args": {...}}

Intents and their args:
media: {"action": "pause" | "play" | "next" | "previous"}
timer: {"seconds": <integer>}
reminder: {"seconds": <integer>, "task": "<text>"}
cancel_timers: {}
screenshot: {}
record: {"action": "start" | "stop"}
youtube: {"query": "<song or video>"}   (use this for ANY request to play a song/video)
open: {"name": "<app or website>"}
search: {"query": "<text>"}
weather: {"city": "<city or empty string>"}
calc: {"expression": "<maths expression using + - * / ( )>"}
note: {"text": "<text>"}
todo: {"text": "<task>"}
show_notes: {}
show_todos: {}
email: {}      (user wants to write or send an email)
read_unread: {}   (user wants to hear / read their unread or new emails)
summarize_email: {}   (user wants a summary of their emails)
whatsapp: {"to": "<person's name or number>", "text": "<the message>"}
time: {}       (user asks the current time)
date: {}       (user asks today's date or day)
lock: {}       (user wants to lock the computer)
other: {}   (chit-chat, general questions, or anything not listed)

Examples of messy input -> the correct JSON:
  "bhai 5 mint ka timer laga"                      -> {"intent": "timer", "args": {"seconds": 300}}
  "remind kar mujhe pani peene ko 10 second mein"  -> {"intent": "reminder", "args": {"seconds": 10, "task": "pani peena"}}
  "gana chala ophelia"                             -> {"intent": "youtube", "args": {"query": "ophelia"}}
  "screenshot le le"                               -> {"intent": "screenshot", "args": {}}
  "screen record karna start kar"                  -> {"intent": "record", "args": {"action": "start"}}
  "kal mumbai ka mausam kaisa rahega"              -> {"intent": "weather", "args": {"city": "mumbai"}}
  "yaar spotify band kar do"                       -> {"intent": "media", "args": {"action": "pause"}}
  "meri notes dikha"                               -> {"intent": "show_notes", "args": {}}
  "kitne baje hain"                                -> {"intent": "time", "args": {}}
  "mail likh do kisi ko"                           -> {"intent": "email", "args": {}}
  "mere unread mail padh do"                       -> {"intent": "read_unread", "args": {}}
  "riya ko whatsapp kar ki main late aa raha hu"   -> {"intent": "whatsapp", "args": {"to": "riya", "text": "I am coming late"}}
"""


def ai_parse(command):
    if not _groq_key():
        print("[AI] No Groq key found. Create groq_key.txt next to main.py.")
        return None
    raw = _groq([{"role": "system", "content": AI_PROMPT}, {"role": "user", "content": command}],
                max_tokens=800, temperature=0, timeout=10, json_mode=True)
    try:
        data = _json_from(raw)
        args = data.get("args")
        return data["intent"], (args if isinstance(args, dict) else {})
    except Exception:
        return None


def _secs(a):
    try:
        return max(0, min(int(float(a.get("seconds", 0))), 86400))
    except (TypeError, ValueError):
        return 0


def _fmt_duration(s):
    if s % 3600 == 0:
        return f"{s // 3600} hour(s)"
    if s % 60 == 0:
        return f"{s // 60} minute(s)"
    return f"{s} second(s)"


def _a_media(a):
    _media_key({"pause": 0xB3, "play": 0xB3, "next": 0xB0, "previous": 0xB1}.get(a.get("action"), 0xB3))
    return "Okay."


def _a_timer(a):
    s = _secs(a)
    if not s:
        return None
    d = _fmt_duration(s)
    add_reminder(f"Time's up! Your {d} timer is done.", s, label=f"{d} timer")
    return f"Timer set for {d}."


def _a_reminder(a):
    s, task = _secs(a), str(a.get("task", "")).strip()
    if not s or not task:
        return None
    add_reminder(f"Reminder: {task}", s, label=task)
    return f"Okay, I'll remind you to {task} in {_fmt_duration(s)}."


def _a_cancel_timers(a):
    stop_alarm()
    cancel_all_reminders()
    return "All timers cancelled."


def _a_text(adder, reply):
    def action(a):
        text = str(a.get("text", "")).strip()
        if not text:
            return None
        adder(text)
        return reply.format(text)
    return action


AI_ACTIONS = {
    "media": _a_media,
    "timer": _a_timer,
    "reminder": _a_reminder,
    "cancel_timers": _a_cancel_timers,
    "screenshot": lambda a: take_screenshot(),
    "record": lambda a: start_recording() if a.get("action") == "start" else stop_recording(),
    "youtube": lambda a: play_on_youtube(a["query"]) if a.get("query") else None,
    "open": lambda a: h_open("open " + a["name"]) if a.get("name") else None,
    "search": lambda a: h_search("search " + a["query"]) if a.get("query") else None,
    "weather": lambda a: h_weather("weather in " + str(a.get("city", ""))),
    "calc": lambda a: h_calc("calculate " + str(a.get("expression", ""))),
    "note": _a_text(add_note, "Noted: {}."),
    "todo": _a_text(add_todo, "Added to your to-do list: {}."),
    "show_notes": lambda a: h_notes("show notes"),
    "show_todos": lambda a: h_todo("show tasks"),
    "email": lambda a: h_email("write an email for me"),
    "read_unread": lambda a: read_unread_emails(),
    "summarize_email": lambda a: summarize_emails(),
    "whatsapp": lambda a: (h_whatsapp(f"whatsapp {a['to']} saying {a['text']}")
                           if a.get("to") and a.get("text") else None),
    "time": lambda a: h_time_date("what time"),
    "date": lambda a: h_time_date("what date"),
    "lock": lambda a: h_system("lock my pc"),
}


def ai_understand(command):
    parsed = ai_parse(command)
    if not parsed:
        return None
    intent, args = parsed
    print(f"[AI] {command!r} -> {intent} {args}")
    action = AI_ACTIONS.get(intent)
    try:
        return action(args) if action else None
    except Exception as e:
        print(f"[AI] action '{intent}' failed: {e}")
        return None


_mutex_handle = None
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def already_running():
    global _mutex_handle
    if os.name != "nt":
        return False
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, "CocoAssistantSingleton")
    return ctypes.windll.kernel32.GetLastError() == 183


def _launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    return f'"{pyw}" "{os.path.join(_BASE_DIR, "gui_coco.py")}"'


def is_autostart():
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, "Coco")
        return True
    except Exception:
        return False


def set_autostart(on):
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "Coco", 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(k, "Coco")
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"Autostart change failed: {e}")
        return False


HANDLERS = [h_repeat, h_history, h_reminder, h_timer, h_smart_email, h_email, h_whatsapp, h_media,
            h_youtube, h_notes, h_todo, h_calc, h_weather, h_time_date, h_smalltalk, h_folder,
            h_open, h_search, h_system, h_wikipedia]


def process_command(command):
    global _pending
    cmd = _normalize(command)
    if _pending:
        p, _pending = _pending, None
        if time.time() - p["time"] < 180:
            reply = _finish_pending(p, command, cmd)
            if reply:
                return reply
    for handler in HANDLERS:
        try:
            reply = handler(cmd)
        except Exception as e:
            print(f"Handler {handler.__name__} failed: {e}")
            reply = f"Sorry, something went wrong: {e}"
        if reply:
            return reply
    return (ai_understand(command) or ask_groq(command)
            or "Sorry, I don't know that one yet. Say 'what can you do' to see my skills.")


def handle_command(command):
    if not command.strip():
        return
    command_history.push(command)
    if gui_widget:
        gui_widget.root.after(0, gui_widget.refresh_history_if_open)
    speak(process_command(command))


def assistant_backend():
    while running:
        time.sleep(0.5)


if __name__ == "__main__":
    print("Coco Desktop Assistant - Terminal Mode")
    print("Type your command below, or type 'exit' / 'quit' to stop.\n")
    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ("exit", "quit"):
                break
            handle_command(user_input)
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break