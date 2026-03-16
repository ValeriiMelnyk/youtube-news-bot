#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║  setup_youtube_auth.py — ОДНОРАЗОВЕ НАЛАШТУВАННЯ        ║
║  Запусти один раз на своєму комп'ютері,                  ║
║  щоб отримати YOUTUBE_REFRESH_TOKEN для GitHub Secrets  ║
╚══════════════════════════════════════════════════════════╝

ЗАПУСК:
  pip install google-auth-oauthlib
  python setup_youtube_auth.py
"""

import os
import json
import sys


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("❌ Потрібна бібліотека. Запусти:")
        print("   pip install google-auth-oauthlib")
        sys.exit(1)

    print("=" * 60)
    print("  YouTube OAuth 2.0 — Отримання Refresh Token")
    print("=" * 60)
    print()
    print("Цей скрипт потрібно запустити ОДИН РАЗ локально.")
    print("Після цього Google не вимагатиме повторного входу.")
    print()

    # Введення даних
    print("Спочатку перейди на: https://console.cloud.google.com")
    print("→ APIs & Services → Credentials → OAuth 2.0 Client ID")
    print()
    client_id = input("Введи Client ID: ").strip()
    client_secret = input("Введи Client Secret: ").strip()

    if not client_id or not client_secret:
        print("❌ Client ID та Client Secret обов'язкові!")
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    # Тимчасовий файл конфігурації
    config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }
    secrets_file = "temp_client_secrets.json"
    with open(secrets_file, "w") as f:
        json.dump(config, f)

    try:
        print()
        print("Зараз відкриється браузер для авторизації...")
        print("Увійди в Google-акаунт, до якого прив'язаний YouTube-канал")
        print()

        flow = InstalledAppFlow.from_client_secrets_file(
            secrets_file,
            scopes=SCOPES
        )

        # Спроба відкрити браузер автоматично
        try:
            creds = flow.run_local_server(
                port=8080,
                prompt="consent",
                access_type="offline"
            )
        except Exception:
            # Якщо немає GUI — показуємо посилання
            flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                prompt="consent"
            )
            print("Відкрий це посилання в браузері:")
            print()
            print(f"  {auth_url}")
            print()
            code = input("Скопіюй код авторизації сюди: ").strip()
            flow.fetch_token(code=code)
            creds = flow.credentials

        print()
        print("=" * 60)
        print("✅  УСПІХ! Ось твої GitHub Secrets:")
        print("=" * 60)
        print()
        print(f"YOUTUBE_CLIENT_ID      = {client_id}")
        print(f"YOUTUBE_CLIENT_SECRET  = {client_secret}")
        print(f"YOUTUBE_REFRESH_TOKEN  = {creds.refresh_token}")
        print()
        print("=" * 60)
        print("Збережи ці три значення в GitHub → Settings → Secrets")
        print("(Детальні інструкції у SETUP_GUIDE.md)")
        print("=" * 60)

        # Зберегти у файл для зручності
        output = {
            "YOUTUBE_CLIENT_ID": client_id,
            "YOUTUBE_CLIENT_SECRET": client_secret,
            "YOUTUBE_REFRESH_TOKEN": creds.refresh_token
        }
        with open("youtube_credentials.json", "w") as f:
            json.dump(output, f, indent=2)
        print()
        print("💾  Також збережено у файл: youtube_credentials.json")
        print("⚠️   НЕ публікуй цей файл у GitHub! Додай у .gitignore")

    finally:
        if os.path.exists(secrets_file):
            os.remove(secrets_file)


if __name__ == "__main__":
    main()
