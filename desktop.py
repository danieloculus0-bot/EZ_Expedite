from __future__ import annotations

import threading
import time
import webbrowser

from waitress import serve

from ez_expedite.db import connect, get_setting
from ez_expedite.expediter import run_expeditor
from ez_expedite.helpers import db_path, m365
from ez_expedite.web import create_app

HOST = "127.0.0.1"
PORT = 5050


def expeditor_worker(app):
    time.sleep(20)
    while True:
        interval = 30
        try:
            with app.app_context():
                with connect(db_path()) as con:
                    try:
                        interval = max(5, int(get_setting(con, "expediter_interval_minutes", "30")))
                    except ValueError:
                        interval = 30
                try:
                    client = m365()
                    client.me()
                    notifier = lambda recipient, message: client.send_teams_message(recipient, message)
                except Exception:
                    notifier = None
                with connect(db_path()) as con:
                    run_expeditor(con, notify_teams=notifier)
        except Exception:
            pass
        time.sleep(interval * 60)


def main():
    app = create_app()
    threading.Thread(target=expeditor_worker, args=(app,), daemon=True).start()
    threading.Timer(1.25, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    print("EZ Expedite is running.")
    print(f"Open http://{HOST}:{PORT}")
    print("Close this window to stop EZ Expedite.")
    serve(app, host=HOST, port=PORT, threads=8)


if __name__ == "__main__":
    main()
