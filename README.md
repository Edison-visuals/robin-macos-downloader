<p align="center">
  <img src="Robin_Icon.png" alt="Robin logo" width="120">
</p>

<h1 align="center">Robin</h1>

<p align="center">
  A native macOS video and audio downloader powered by <a href="https://github.com/yt-dlp/yt-dlp">yt-dlp</a> and <a href="https://pywebview.flowrl.com/">pywebview</a>.
</p>

Robin runs as a regular Mac app—there is no browser tab, localhost server, or cloud backend. Paste a supported media URL, inspect the available formats, choose an output, and save the result directly to your Mac.

> **Note:** Robin's current interface is in Traditional Chinese. This README provides English setup and usage instructions.

## Features

- Download video as MP4, MOV, MKV, or WebM
- Extract audio as MP3, M4A, WAV, FLAC, or Opus
- Select video quality up to the resolutions offered by the source
- Download playlists and multiple URLs in a batch
- Pause or cancel active downloads
- Use browser cookies for content that requires an authenticated session
- Choose a download folder, notification sound, and light or dark theme
- Keep a local history of the most recent downloads
- Update yt-dlp from inside the app

## Requirements

- macOS
- Python 3.11 or later
- [FFmpeg](https://ffmpeg.org/) for merging high-quality video/audio streams and converting audio
- An internet connection during the first launch, when Robin installs its Python dependencies

Install FFmpeg with [Homebrew](https://brew.sh/):

```bash
brew install ffmpeg
```

## Install the app

1. Download `Robin.dmg` from the latest GitHub release.
2. Open the DMG and drag `Robin.app` into **Applications**.
3. The app is currently unsigned. On the first launch, Control-click or right-click `Robin.app`, choose **Open**, and confirm. You only need to do this once.
4. Wait while Robin creates a private Python environment and installs its dependencies. This normally takes about a minute.

You can also run the `Robin.app` bundle directly from a clone of this repository.

## How to use Robin

1. Copy or paste a supported video or audio URL into the input field.
2. Click the arrow to inspect the media.
3. Choose **Video** (`影片`) or **Audio** (`音訊`).
4. Select a file format and, for video, a maximum resolution.
5. Click **Download** (`下載`). The default destination is `~/Downloads`.

For several links, open **MULTIPLES**, add one URL per row, choose each format, and start the batch. Robin also recognizes supported playlist URLs and can add their entries to the batch view.

### Settings

Open **SETTINGS** to:

- change the output folder;
- select Chrome, Safari, Firefox, Edge, or Brave cookies for media that requires login;
- choose a completion sound;
- review recent download history; or
- update yt-dlp.

macOS may request Keychain or file-access permission when browser cookies are used. Robin only requests cookies when you explicitly select a browser.

## Run from source

```bash
git clone https://github.com/Edison-visuals/robin-macos-downloader.git
cd robin-macos-downloader
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r Robin.app/Contents/Resources/requirements.txt
python Robin.app/Contents/Resources/main.py
```

The source entry point is `Robin.app/Contents/Resources/main.py`, and the interface is in `Robin.app/Contents/Resources/ui/index.html`.

## Build the DMG

Run the included build script on macOS:

```bash
bash "打包 DMG.command"
```

The script packages `Robin.app` into `Robin.dmg` and adds an Applications shortcut. It also removes Python cache files from the packaged app.

## Local data and privacy

Robin has no application server and does not send analytics. Its settings and recent-download history are stored locally in:

```text
~/Library/Application Support/Robin/
```

Network requests needed to inspect and download media are made by yt-dlp. Review yt-dlp's documentation and the source platform's privacy terms if this matters for your use case.

## Responsible use

Download only content that you own or have permission to download. You are responsible for complying with copyright law, the source website's terms, and any other rules that apply in your location. Robin is not affiliated with YouTube or any other media platform.

## Contributing

Issues and pull requests are welcome. Please describe the platform, URL type, expected behavior, and relevant error message when reporting a bug. Do not include private URLs, account cookies, or personal data.

## License

Robin is available under the [MIT License](LICENSE).
