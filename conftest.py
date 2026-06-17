"""Root conftest — ensures the project root is on sys.path for tests."""
import sys
import os

# Make sure `app` package is importable
sys.path.insert(0, os.path.dirname(__file__))
