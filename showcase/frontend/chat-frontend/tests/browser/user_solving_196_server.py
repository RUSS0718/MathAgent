"""Offline real HTTP seam for #196: no remote provider."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from showcase.flask_app import create_app
with tempfile.TemporaryDirectory() as directory:
    app = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': directory,
        'SHOWCASE_PRESENTATION_ENABLED': True, 'SHOWCASE_JOB_DELAY_SECONDS': 0,
        'SHOWCASE_REVIEWER_SECRET': 'local-browser-fixture'})
    app.run(host='127.0.0.1', port=8096, threaded=True, use_reloader=False)
