"""
Backward-compatible shim — dashboard reads [Raw] Shop Level - Fashion via raw_data.py.
"""

from seller.raw_data import get_raw_shop_row as get_shop_by_id
from seller.raw_data import search_raw_shops as search_shops

__all__ = ["get_shop_by_id", "search_shops"]
