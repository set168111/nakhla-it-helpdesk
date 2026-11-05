"""Explicit retention maintenance. Back up databases first; requires --apply to delete rows.

Example: .venv/Scripts/python.exe -B scripts/maintain_history.py --apply
Normal application startup never invokes retention maintenance.
"""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auth import AuthService
from app.storage import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.getenv('APP_DATA_DIR', ROOT / 'data')))
    parser.add_argument('--apply', action='store_true', help='explicitly delete eligible old history/login records')
    args = parser.parse_args()
    if not args.apply:
        parser.exit(message='No changes. Back up databases and pass --apply to run retention maintenance.\n')
    for name in ['helpdesk.sqlite3', 'auth.sqlite3']:
        if not (args.data_dir / name).is_file():
            parser.error('existing database required: ' + name)
    print(Store(args.data_dir / 'helpdesk.sqlite3').purge_history())
    print({'login_sessions_deleted': AuthService(args.data_dir / 'auth.sqlite3').purge_expired()})


if __name__ == '__main__':
    main()
