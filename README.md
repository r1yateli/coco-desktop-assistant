# Coco - Desktop Assistant

Coco is a floating desktop assistant for Windows. You can talk to it or type, and it helps with everyday tasks.

## Features
- Open apps and websites, and play songs on YouTube
- Timers, reminders, notes and a to-do list
- Screenshots and screen recording
- Wikipedia lookups, weather and maths
- Email: read, summarize, find urgent mails, AI-written drafts, scheduled emails
- Understands typos and Hinglish
- Cute voice replies, system tray icon, themes

## Setup
1. Install Python 3.12 from python.org
2. Open a terminal in the project folder and run:
   pip install -r requirements.txt
3. Get a free key from console.groq.com and save it alone in a file called groq_key.txt (next to main.py)
4. Optional, for email: create coco_email.txt with two lines:
   - your Gmail address
   - your Gmail App Password (16 letters)
5. Run:
   python gui_coco.py

## Download
Don't want to install Python? Download Coco.exe from the Releases page and keep groq_key.txt next to it.

## Privacy
Never share groq_key.txt or coco_email.txt. They are kept out of this repo on purpose.