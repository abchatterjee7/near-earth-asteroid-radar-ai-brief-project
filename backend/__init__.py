"""Asteroid Radar backend package.

Loading .env here means every module in the package sees the same settings,
no matter which one is imported first.
"""

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is in requirements.txt; this keeps tests light
    pass
