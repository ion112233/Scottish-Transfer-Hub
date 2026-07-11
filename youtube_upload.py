"""
Uploads a finished video to YouTube as a Short using a stored OAuth
refresh token (see get_youtube_token.py for how to generate one).
"""
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import httplib2

import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_service():
    creds = Credentials(
        token=None,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds)


def upload_short(video_path: str, title: str, description: str,
                  tags: list[str] | None = None) -> str:
    """Uploads video_path and returns the resulting YouTube video ID."""
    youtube = _get_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags or [],
            "categoryId": "17",  # Sports
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()

    return response["id"]
