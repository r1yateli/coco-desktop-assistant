# Coco-Desktop Assistant

Coco is a floating desktop assistant for Windows. Talk to Coco or type messages to get help with everyday tasks.

## ✨ Features

- Open apps and websites, and play songs on YouTube
- Timers, reminders, notes, and a to-do list
- Screenshots and screen recording
- Wikipedia lookups, weather, and maths
- AI-powered email summarization
- Find urgent emails and schedule emails
- Understands typos and Hinglish
- Voice replies, system tray icon, and themes
- First-launch setup for your name and Groq API key

## 📥 Download Coco for Windows

**Recommended: Download the ready-to-use executable.**

1. Open the [GitHub Releases page](../../releases).
2. Open the latest release.
3. Under **Assets**, download `Coco.exe` (or the executable filename listed in that release).
4. Save the file to a folder on your computer.
5. Double-click the downloaded executable to launch Coco.

### First-time setup

When you launch Coco for the first time:

1. **Enter your name.** Coco uses this name in AI-generated email sign-offs.
2. **Enter your Groq API key** when prompted. You can get your own key from [Groq Console](https://console.groq.com/).
3. Wait for Coco to open, then type a message to test it.

Your name and API key are saved locally on your computer. You normally won't need to enter them again on every launch.

**Important:** Each user must provide their own Groq API key. Do not use or share another person's key. AI features require a valid API key and an internet connection.

### Optional: Email features

To use email features, create a file named `coco_email.txt` in the same folder as `Coco.exe`.

Put your credentials on separate lines:

1. Your Gmail address
2. Your Gmail App Password

Use a Gmail App Password rather than your regular Gmail password. Email features may also require additional setup or permissions.

Keep this file private. Never upload it to GitHub.

## 🛠️ Run from source (for developers)

### Requirements

- Windows
- Python 3.12
- Git (optional)

### Installation

1. Download or clone this repository.
2. Open a terminal in the project folder.
3. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Run Coco:

   ```bash
   python gui_coco.py
   ```

5. Follow the first-launch prompts to enter your name and Groq API key.

If you prefer manual API-key setup, create a file named `groq_key.txt` beside `main.py` and put your Groq API key inside it.

## 🔒 Privacy and Security

- Never share or upload `groq_key.txt` or `coco_email.txt`.
- Never commit API keys, passwords, or other private credentials to GitHub.
- Credential files and local application data should remain excluded through `.gitignore`.
- Your Groq API key is used to access Groq's AI service. Review Groq's own privacy and usage policies before using it.
- Download executable files only from releases you trust.

## 👥 Team Coco

- **Riya Teli**
- **Vinaya Tervankar**
- **Harshita Gonewar**

## 🐛 Troubleshooting

- **Coco does not respond:** Check your internet connection and verify that your Groq API key is valid.
- **The API-key prompt does not appear:** A key may already be configured through an environment variable or a local `groq_key.txt` file.
- **The app cannot save your key:** Move Coco to a folder where your Windows account has permission to save files.
- **Email features do not work:** Check that `coco_email.txt` contains the correct Gmail address and App Password, and confirm any additional email setup required.

If the issue continues, open an issue in this repository and include the error message. Never include API keys or passwords in screenshots or issue reports.

---

**Coco - Your personal desktop assistant.**
