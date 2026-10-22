"""Run the Commodity Desk:  python3 commodity_sim/app.py   then open http://127.0.0.1:8010/"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from csim.server import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
