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
        """
        Create normalized cache key from page pair

        Normalizes titles to lowercase and replaces underscores with spaces
        for case-insensitive matching, while cached values retain original titles.
        """
        start_normalized = start_page.strip().replace("_", " ").lower()
        end_normalized = end_page.strip().replace("_", " ").lower()
        return f"{start_normalized}::{end_normalized}"

    def get(self, start_page: str, end_page: str) -> Optional[List[str]]:
        """
        Retrieve a cached path segment

        Args:
            start_page: Starting page title (will be normalized for cache key)
            end_page: Ending page title (will be normalized for cache key)

        Returns:
            List of pages in the segment with original Wikipedia titles, or None if not cached
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
            start_page: Starting page title (will be normalized for cache key)
            end_page: Ending page title (will be normalized for cache key)
            segment_path: List of pages in segment with original Wikipedia titles
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
        Store multiple segments efficiently using a single database transaction

        Args:
            segments: List of (start_page, end_page, segment_path) tuples
        """
        with self._lock:
            # Update in-memory cache first (fast)
            for start_page, end_page, segment_path in segments:
                self._put_internal(start_page, end_page, segment_path, update_db=False)

            # Batch save to database in single transaction (efficient)
            if self.enable_db_persistence and segments:
                try:
                    saved_count = database.save_path_segments_bulk(segments)
                    logger.info(f"Bulk saved {saved_count}/{len(segments)} segments to database")
                except Exception as e:
                    logger.error(f"Failed to bulk save segments to database: {e}", exc_info=True)
                    # Don't raise - in-memory cache is still updated, database is best-effort
                    # Future: Could implement retry queue or warning to user

        logger.info(f"Bulk cached {len(segments)} segments in memory")

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

    def get_connected_nodes(self, page: str, direction: str = 'both') -> List[str]:
        """
        Get all pages connected to the given page in cached segments

        Args:
            page: Page title (normalized)
            direction: 'forward' (page→X), 'backward' (X→page), or 'both' (default)

        Returns:
            List of connected page titles
        """
        connected = set()

        with self._lock:
            # Check in-memory cache
            for key, segment in self._cache.items():
                start, end = key.split('::', 1)
                if direction in ('forward', 'both') and start == page:
                    connected.add(end)
                if direction in ('backward', 'both') and end == page:
                    connected.add(start)

        # Also check database for connections not in memory
        if self.enable_db_persistence:
            try:
                with database.get_db() as conn:
                    cursor = conn.cursor()

                    if direction in ('forward', 'both'):
                        cursor.execute('''
                            SELECT end_page FROM path_segments
                            WHERE start_page = ?
                            ORDER BY use_count DESC
                            LIMIT 50
                        ''', (page,))
                        for row in cursor.fetchall():
                            connected.add(row['end_page'])

                    if direction in ('backward', 'both'):
                        cursor.execute('''
                            SELECT start_page FROM path_segments
                            WHERE end_page = ?
                            ORDER BY use_count DESC
                            LIMIT 50
                        ''', (page,))
                        for row in cursor.fetchall():
                            connected.add(row['start_page'])

            except Exception as e:
                logger.error(f"Failed to query connected nodes from database: {e}")

        return list(connected)

    def compose_path(self, start_page: str, end_page: str, max_hops: int = 3):
        """
        Attempt to compose a path from cached segments

        Uses BFS over cached segments to find a path.

        Args:
            start_page: Starting page (will be normalized for cache key)
            end_page: Ending page (will be normalized for cache key)
            max_hops: Maximum number of hops to try (default: 3)

        Returns:
            Tuple of (path, segment_metadata) if found, or (None, None) if not cached
            Path contains original Wikipedia titles. segment_metadata is list of dicts
            with 'from_page', 'to_page', 'source', 'cached_at'
        """
        # Direct segment check
        direct = self.get(start_page, end_page)
        if direct:
            logger.info(f"Cache composition: Direct hit {start_page} → {end_page}")
            # Get timestamp from database
            cached_at = self._get_segment_timestamp(start_page, end_page)
            segment_metadata = [{
                'from_page': start_page,
                'to_page': end_page,
                'source': 'cache',
                'cached_at': cached_at
            }]
            return (direct, segment_metadata)

        # BFS over cached segments
        from collections import deque

        queue = deque([(start_page, [start_page], 0, [])])  # Add metadata tracking
        visited = {start_page}

        while queue:
            current, path, hops, metadata = queue.popleft()

            if hops >= max_hops:
                continue

            # Get all pages connected to current via cached segments
            connected = self.get_connected_nodes(current, direction='forward')

            for next_page in connected:
                if next_page in visited:
                    continue

                # Get segment from current to next_page
                segment = self.get(current, next_page)
                if not segment:
                    continue

                # Build new path
                new_path = path + segment[1:]  # Skip first node (it's current)

                # Track segment metadata
                cached_at = self._get_segment_timestamp(current, next_page)
                new_metadata = metadata + [{
                    'from_page': current,
                    'to_page': next_page,
                    'source': 'cache',
                    'cached_at': cached_at
                }]

                # Check if we've reached the end
                if next_page == end_page:
                    logger.info(f"Cache composition: Found path with {hops + 1} cached segments")
                    return (new_path, new_metadata)

                visited.add(next_page)
                queue.append((next_page, new_path, hops + 1, new_metadata))

        return (None, None)

    def _get_segment_timestamp(self, start_page: str, end_page: str) -> Optional[str]:
        """
        Get the timestamp when a segment was cached

        Args:
            start_page: Starting page (normalized)
            end_page: Ending page (normalized)

        Returns:
            ISO format timestamp string, or None if not found
        """
        if not self.enable_db_persistence:
            return None

        try:
            with database.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT created_at FROM path_segments
                    WHERE start_page = ? AND end_page = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                ''', (start_page, end_page))

                row = cursor.fetchone()
                if row:
                    return row['created_at']
        except Exception as e:
            logger.error(f"Failed to get segment timestamp: {e}")

        return None

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
