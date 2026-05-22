"""Routing strategies for CXL fabric simulator."""

from .strategy import RoutingStrategy, StaticRouting, ECMPRouting, WeightedRouting

__all__ = [
    'RoutingStrategy',
    'StaticRouting',
    'ECMPRouting',
    'WeightedRouting',
]
