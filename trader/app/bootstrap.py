
# Compose your dependencies here if needed.
# We keep it minimal to avoid changing logic; caller supplies `client`.
from trader.app.runner import run_loop

def start(client):
    # No changes to client wiring; just delegate to run_loop
    run_loop(client)
