"""
YouTube Transcript Fetcher
Enter a YouTube video or channel URL and get the transcript on the page.
No Dropbox, no rclone, no sign-in required.

Usage:
    python app.py
    open http://localhost:5002
"""

import re
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)


def extract_video_id(url):
    """Extract YouTube video ID from various URL formats."""
    match = re.search(
        r'(?:v=|youtu\.be/|/embed/|/v/|/shorts/)([a-zA-Z0-9_-]{11})', url
    )
    return match.group(1) if match else None


def get_video_info(video_id):
    """Get video title via yt_dlp. Falls back to generic info if unavailable."""
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
            return {
                "title": info.get("title", "Untitled"),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
    except Exception:
        return {
            "title": "Untitled",
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }


def get_channel_latest_video(channel_url):
    """Return (video_id, title) for the most recent video on a channel."""
    import yt_dlp
    if "/videos" not in channel_url:
        channel_url = channel_url.rstrip("/") + "/videos"
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "playlistend": 1,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        entries = info.get("entries", [])
        if entries:
            entry = entries[0]
            return entry.get("id"), entry.get("title", "Untitled")
    return None, None


def fetch_transcript(video_id):
    """Fetch transcript grouped by real minute using snippet.start timestamps."""
    from youtube_transcript_api import YouTubeTranscriptApi
    ytt = YouTubeTranscriptApi()
    transcript = ytt.fetch(video_id)

    output = []
    current_minute = -1
    current_lines = []
    for snippet in transcript.snippets:
        text = snippet.text.strip()
        if not text:
            continue
        minute = int(snippet.start // 60)
        if minute != current_minute:
            if current_lines:
                output.append(f"[{current_minute}:00] " + " ".join(current_lines))
            current_minute = minute
            current_lines = [text]
        else:
            current_lines.append(text)
    if current_lines:
        output.append(f"[{current_minute}:00] " + " ".join(current_lines))
    return "\n\n".join(output)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/transcript", methods=["POST"])
def api_transcript():
    data = request.get_json()
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        video_id = extract_video_id(url)
        title = None
        video_url = url

        if not video_id:
            # Treat as a channel URL — grab the most recent video
            video_id, title = get_channel_latest_video(url)
            if not video_id:
                return jsonify({"error": "Could not find a video at that URL"}), 400
            video_url = f"https://www.youtube.com/watch?v={video_id}"

        if not title:
            info = get_video_info(video_id)
            title = info["title"]
            video_url = info["url"]

        transcript = fetch_transcript(video_id)

        return jsonify({"title": title, "url": video_url, "transcript": transcript})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5002)
