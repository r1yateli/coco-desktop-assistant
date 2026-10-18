# Coco — Desktop Assistant

Coco is a floating desktop assistant for Windows. You can talk to it or type, and it helps you with everyday tasks.

## ✨ Features

- Open apps and websites, and play songs on YouTube
- Timers, reminders, notes, and a to-do list
- Screenshots and screen recording
- Wikipedia lookups, weather, and maths
- Email assistance: summarize emails, find urgent messages, draft emails with AI, and schedule emails
- Understands typos and Hinglish
- Voice replies, system tray icon, and themes

## 🛠️ Setup

1. Install Python 3.12 from [python.org](https://www.python.org/).
2. Open a terminal in the project folder and run:

   ```bash
   pip install -r requirements.txt
   ```

3. Get a Groq API key from [console.groq.com](https://console.groq.com/) and save it in a file named `groq_key.txt` beside `main.py`.
4. Optional: For email features, create `coco_email.txt` with your Gmail address and Gmail App Password on separate lines.
5. Run the application:

   ```bash
   python gui_coco.py
   ```

## 📥 Download

Download the Windows executable from the [GitHub Releases](../../releases) page, when available.

If using the executable, follow the setup instructions for your API key and optional email credentials.

## 👥 Team Coco

-**Riya Teli**
- **Vinaya Tervankar**
- **Harshita Gonewar**


## 🔒 Privacy & Security

- Never share or upload `groq_key.txt` or `coco_email.txt`.
- Keep API keys and email credentials private.
- These credential files are excluded from the repository using `.gitignore`.
