"""
app/data/__init__.py

データパッケージ
"""
from .parkings import PARKINGS, get_all_parkings, get_parking_by_id

__all__ = ["PARKINGS", "get_all_parkings", "get_parking_by_id"]