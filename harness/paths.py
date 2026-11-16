"""Locations of the released records and the generated figures.

Analysis scripts read ``BTB_DATA`` (default: ``<repo>/data``) and write
figures to ``BTB_FIGURES`` (default: ``<repo>/figures``). Workspaces created
by a live episode stay under ``harness/runs`` and are not part of the release.
"""
import os

HARNESS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HARNESS)
DATA = os.environ.get("BTB_DATA", os.path.join(ROOT, "data"))
FIGURES = os.environ.get("BTB_FIGURES", os.path.join(ROOT, "figures"))
