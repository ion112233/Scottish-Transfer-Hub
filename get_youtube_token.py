"""
Run this ONCE, locally on your own machine (not in GitHub Actions), to
generate a YOUTUBE_REFRESH_TOKEN you can then store as a GitHub secret.

Prerequisites:
  1. In Google Cloud Console, create a project and enable "YouTube Data API v3".
  2. Create OAuth 2.0 credentials of type "Desktop app".
  3. Download the client_secret.json for that credential and place it next
     to this script.
  4. pip install google-auth-oauthlib

Usage:
  python get_youtube_token.py
This opens a browser window for you to log into the YouTube channel you
want to post to, then prints the refresh token to your terminal.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    print("\n=== Save these as GitHub repo secrets ===")
    print(f"YOUTUBE_CLIENT_ID={creds.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={creds.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
