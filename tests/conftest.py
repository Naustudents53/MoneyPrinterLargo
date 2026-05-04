"""
pytest config: ensure `src/` is on sys.path so tests can `import youtube_upload`,
`import classes.YouTubeUploader`, etc. (mirrors how src/main.py runs).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
