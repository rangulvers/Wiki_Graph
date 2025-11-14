"""
Path segment caching for efficient path finding

This module provides in-memory caching of path segments with:
- LRU (Least Recently Used) eviction policy
- Integration with database for persistence
- Thread-safe operations for concurrent access
"""

from collections import OrderedDict
from typing import Optional, List, Tuple
import threading
import database
import logging

logger = logging.getLogger(__name__)


class PathCache:
    """
    In-memory LRU cache for path segments

    This cache stores path segments (A → B connections) discovered during searches.
    When a new search needs to find a path between pages, it can check if segments
    of that path are already cached, significantly reducing search time.

    Features:
    - LRU eviction when cache is full
    - Thread-safe operations
    - Automatic database persistence
    - Cache warming from database on startup
    """

    def __init__(self, max_size: int = 10000, enable_db_persistence: bool = True):
        """
        Initialize the path cache

        Args:
            max_size: Maximum number of segments to cache (default: 10000)
            enable_db_persistence: Whether to sync with database (default: True)
        """
        self.max_size = max_size
        self.enable_db_persistence = enable_db_persistence
        self._cache = OrderedDict()
        self._lock = threading.RLock()  # Reentrant lock for nested operations
        self._hits = 0
        self._misses = 0

        logger.info(f"PathCache initialized with max_size={max_size}, db_persistence={enable_db_persistence}")

    def _make_key(self, start_page: str, end_page: str) -> str:
        """Create cache key from page pair"""
        return f"{start_page}::{end_page}"

    def get(self, start_page: str, end_page: str) -> Optional[List[str]]:
        """
        Retrieve a cached path segment

        Args:
            start_page: Starting page title (normalized)
            end_page: Ending page title (normalized)

        Returns:
            List of pages in the segment, or None if not cached
        """
        key = self._make_key(start_page, end_page)

        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                logger.debug(f"Cache HIT: {start_page} → {end_page}")
                return self._cache[key].copy()  # Return copy to prevent modification

            self._misses += 1
            logger.debug(f"Cache MISS: {start_page} → {end_page}")

            # Try to load from database
            if self.enable_db_persistence:
                segment = database.get_path_segment(start_page, end_page)
                if segment:
                    logger.debug(f"Loaded from DB: {start_page} → {end_page}")
                    self._put_internal(start_page, end_page, segment, update_db=False)
                    return segment.copy()

            return None

    def put(self, start_page: str, end_page: str, segment_path: List[str]):
        """
        Store a path segment in the cache

        Args:
            start_page: Starting page title (normalized)
            end_page: Ending page title (normalized)
            segment_path: List of pages in the segment
        """
        with self._lock:
            self._put_internal(start_page, end_page, segment_path, update_db=True)

    def _put_internal(self, start_page: str, end_page: str, segment_path: List[str], update_db: bool):
        """
        Internal method to store a segment (without acquiring lock)

        Args:
            start_page: Starting page
            end_page: Ending page
            segment_path: Path segment
            update_db: Whether to persist to database
        """
        key = self._make_key(start_page, end_page)

        # Update or add to cache
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            self._cache[key] = segment_path

            # Evict LRU if cache is full
            if len(self._cache) > self.max_size:
                evicted_key = next(iter(self._cache))
                del self._cache[evicted_key]
                logger.debug(f"Evicted LRU segment: {evicted_key}")

        # Persist to database
        if update_db and self.enable_db_persistence:
            try:
                database.save_path_segment(start_page, end_page, segment_path)
            except Exception as e:
                logger.error(f"Failed to save segment to database: {e}")

    def bulk_put(self, segments: List[Tuple[str, str, List[str]]]):
        """
        Store multiple segments efficiently

        Args:
            segments: List of (start_page, end_page, segment_path) tuples
        """
        with self._lock:
            for start_page, end_page, segment_path in segments:
                self._put_internal(start_page, end_page, segment_path, update_db=True)

        logger.info(f"Bulk inserted {len(segments)} segments")

    def warm_cache_from_db(self, limit: int = 1000):
        """
        Pre-load frequently used segments from database

        Args:
            limit: Maximum number of segments to load
        """
        if not self.enable_db_persistence:
            logger.warning("Database persistence disabled, skipping cache warming")
            return

        logger.info(f"Warming cache from database (limit={limit})...")

        # Load most recently used segments
        try:
            with database.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT start_page, end_page, segment_path
                    FROM path_segments
                    ORDER BY last_used DESC, use_count DESC
                    LIMIT ?
                ''', (limit,))

                rows = cursor.fetchall()

                with self._lock:
                    for row in rows:
                        import json
                        segment_path = json.loads(row['segment_path'])
                        self._put_internal(row['start_page'], row['end_page'], segment_path, update_db=False)

                logger.info(f"Warmed cache with {len(rows)} segments from database")

        except Exception as e:
            logger.error(f"Failed to warm cache from database: {e}")

    def extract_segments_from_path(self, path: List[str]) -> List[Tuple[str, str, List[str]]]:
        """
        Extract all possible segments from a path for caching

        For a path A → B → C → D, extracts:
        - A → B
        - B → C
        - C → D
        - A → C
        - B → D
        - A → D

        Args:
            path: List of pages in a complete path

        Returns:
            List of (start_page, end_page, segment) tuples
        """
        segments = []
        n = len(path)

        # Extract all sub-paths (up to length 4 to avoid too many segments)
        for i in range(n):
            for j in range(i + 2, min(i + 5, n + 1)):  # i+2 to ensure at least 2 nodes
                segment = path[i:j]
                if len(segment) >= 2:
                    segments.append((segment[0], segment[-1], segment))

        return segments

    def cache_path(self, path: List[str]):
        """
        Cache all segments from a discovered path

        Args:
            path: Complete path to extract and cache segments from
        """
        if len(path) < 2:
            return

        segments = self.extract_segments_from_path(path)
        self.bulk_put(segments)

        logger.info(f"Cached {len(segments)} segments from path of length {len(path)}")

    def get_stats(self) -> dict:
        """
        Get cache statistics

        Returns:
            Dictionary with cache metrics
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': round(hit_rate, 2),
                'total_requests': total_requests
            }

    def clear(self):
        """Clear all cached segments"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info("Cache cleared")


# Global cache instance
_global_cache: Optional[PathCache] = None


def get_cache() -> PathCache:
    """
    Get or create the global cache instance

    Returns:
        The global PathCache instance
    """
    global _global_cache

    if _global_cache is None:
        _global_cache = PathCache(max_size=10000, enable_db_persistence=True)
        # Warm cache on first access
        _global_cache.warm_cache_from_db(limit=1000)

    return _global_cache
