import sqlite3
import json
import time
from datetime import datetime
from contextlib import contextmanager
from app.config import DATABASE_PATH

# Use database path from config
DATABASE_NAME = str(DATABASE_PATH)

@contextmanager
def get_db():
    """Context manager for database connections with proper timeout"""
    # Set timeout to 20 seconds to handle concurrent writes better
    conn = sqlite3.connect(DATABASE_NAME, timeout=20.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    """Initialize the database with required tables and enable WAL mode"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Enable WAL (Write-Ahead Logging) mode for better concurrency
        # This allows multiple readers while a writer is active
        cursor.execute('PRAGMA journal_mode=WAL')

        # Set busy timeout to 20 seconds (20000 milliseconds)
        # This prevents immediate SQLITE_BUSY errors under load
        cursor.execute('PRAGMA busy_timeout=20000')

        # Enable foreign keys for data integrity
        cursor.execute('PRAGMA foreign_keys=ON')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_term TEXT NOT NULL,
                end_term TEXT NOT NULL,
                path TEXT NOT NULL,
                hops INTEGER NOT NULL,
                pages_checked INTEGER NOT NULL,
                success INTEGER NOT NULL,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table for storing multiple paths per search
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                hops INTEGER NOT NULL,
                diversity_score REAL,
                path_order INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (search_id) REFERENCES searches (id) ON DELETE CASCADE
            )
        ''')

        # Table for caching path segments for reuse
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS path_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_page TEXT NOT NULL,
                end_page TEXT NOT NULL,
                segment_path TEXT NOT NULL,
                hops INTEGER NOT NULL,
                use_count INTEGER DEFAULT 1,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create index for faster searches
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_start_term ON searches(start_term)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_end_term ON searches(end_term)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at ON searches(created_at DESC)
        ''')

        # Indexes for search_paths table
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_search_paths_search_id ON search_paths(search_id)
        ''')

        # Indexes for path_segments table (for fast lookups)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_path_segments_lookup ON path_segments(start_page, end_page)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_path_segments_last_used ON path_segments(last_used DESC)
        ''')
        # Index for reverse lookups (cache composition queries)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_path_segments_end_page ON path_segments(end_page)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_path_segments_start_page ON path_segments(start_page)
        ''')

def save_search(start_term, end_term, path, hops, pages_checked, success, error_message=None, max_retries=3):
    """
    Save a search result to the database with retry logic for concurrent write handling

    Args:
        start_term: Starting Wikipedia term
        end_term: Target Wikipedia term
        path: List of pages in the path
        hops: Number of hops in the path
        pages_checked: Total pages explored
        success: Whether the search was successful
        error_message: Optional error message
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        int: The ID of the inserted search record

    Raises:
        sqlite3.OperationalError: If database remains locked after all retries
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            with get_db() as conn:
                cursor = conn.cursor()

                # Convert path list to JSON string (never NULL, use empty array for empty paths)
                path_json = json.dumps(path if path is not None else [])

                cursor.execute('''
                    INSERT INTO searches
                    (start_term, end_term, path, hops, pages_checked, success, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (start_term, end_term, path_json, hops, pages_checked, 1 if success else 0, error_message))

                return cursor.lastrowid

        except sqlite3.OperationalError as e:
            last_exception = e
            # Check if it's a lock/busy error
            error_str = str(e).lower()
            if 'locked' in error_str or 'busy' in error_str:
                if attempt < max_retries - 1:
                    # Exponential backoff: 0.1s, 0.2s, 0.4s
                    sleep_time = 0.1 * (2 ** attempt)
                    print(f"Database locked, retrying in {sleep_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(sleep_time)
                    continue
            # If not a lock error, or last attempt, raise immediately
            raise

    # If we exhausted all retries, raise the last exception
    if last_exception:
        raise last_exception

def get_all_searches(search_query=None, limit=100, offset=0):
    """Get all searches with optional filtering"""
    with get_db() as conn:
        cursor = conn.cursor()

        if search_query:
            # Search in start_term or end_term
            query = '''
                SELECT id, start_term, end_term, hops, pages_checked,
                       success, created_at
                FROM searches
                WHERE start_term LIKE ? OR end_term LIKE ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            '''
            search_pattern = f'%{search_query}%'
            cursor.execute(query, (search_pattern, search_pattern, limit, offset))
        else:
            query = '''
                SELECT id, start_term, end_term, hops, pages_checked,
                       success, created_at
                FROM searches
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            '''
            cursor.execute(query, (limit, offset))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_search_by_id(search_id):
    """Get a specific search by ID with full path details"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, start_term, end_term, path, hops, pages_checked,
                   success, error_message, created_at
            FROM searches
            WHERE id = ?
        ''', (search_id,))

        row = cursor.fetchone()
        if row:
            result = dict(row)
            # Parse path JSON back to list
            if result['path']:
                result['path'] = json.loads(result['path'])
            return result
        return None

def get_search_stats():
    """Get statistics about searches"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                COUNT(*) as total_searches,
                SUM(success) as successful_searches,
                AVG(CASE WHEN success = 1 THEN hops END) as avg_hops,
                AVG(pages_checked) as avg_pages_checked
            FROM searches
        ''')

        row = cursor.fetchone()
        return dict(row) if row else {}

def save_multiple_paths(search_id, paths, diversity_scores=None):
    """
    Save multiple paths for a search

    Args:
        search_id: ID of the parent search
        paths: List of paths (each path is a list of page titles)
        diversity_scores: Optional list of diversity scores for each path
    """
    with get_db() as conn:
        cursor = conn.cursor()

        for idx, path in enumerate(paths):
            path_json = json.dumps(path)
            diversity = diversity_scores[idx] if diversity_scores and idx < len(diversity_scores) else None

            cursor.execute('''
                INSERT INTO search_paths
                (search_id, path, hops, diversity_score, path_order)
                VALUES (?, ?, ?, ?, ?)
            ''', (search_id, path_json, len(path) - 1, diversity, idx))

def get_paths_for_search(search_id):
    """Get all paths associated with a search"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, path, hops, diversity_score, path_order
            FROM search_paths
            WHERE search_id = ?
            ORDER BY path_order
        ''', (search_id,))

        rows = cursor.fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result['path'] = json.loads(result['path'])
            results.append(result)
        return results

def save_path_segment(start_page, end_page, segment_path):
    """
    Save or update a path segment in the cache

    Args:
        start_page: Starting page title (normalized)
        end_page: Ending page title (normalized)
        segment_path: List of pages in the segment

    Returns:
        int: ID of the segment
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Check if segment already exists
        cursor.execute('''
            SELECT id, use_count FROM path_segments
            WHERE start_page = ? AND end_page = ?
        ''', (start_page, end_page))

        existing = cursor.fetchone()

        if existing:
            # Update use count and last_used timestamp
            cursor.execute('''
                UPDATE path_segments
                SET use_count = use_count + 1,
                    last_used = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (existing['id'],))
            return existing['id']
        else:
            # Insert new segment
            segment_json = json.dumps(segment_path)
            cursor.execute('''
                INSERT INTO path_segments
                (start_page, end_page, segment_path, hops)
                VALUES (?, ?, ?, ?)
            ''', (start_page, end_page, segment_json, len(segment_path) - 1))
            return cursor.lastrowid

def get_path_segment(start_page, end_page):
    """
    Retrieve a cached path segment

    Args:
        start_page: Starting page title (normalized)
        end_page: Ending page title (normalized)

    Returns:
        List of pages in the segment, or None if not found
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT segment_path FROM path_segments
            WHERE start_page = ? AND end_page = ?
        ''', (start_page, end_page))

        row = cursor.fetchone()
        if row:
            # Update last_used timestamp
            cursor.execute('''
                UPDATE path_segments
                SET last_used = CURRENT_TIMESTAMP,
                    use_count = use_count + 1
                WHERE start_page = ? AND end_page = ?
            ''', (start_page, end_page))
            return json.loads(row['segment_path'])
        return None

def save_path_segments_bulk(segments, max_retries=3):
    """
    Save multiple path segments in a single transaction with retry logic

    This is much more efficient than calling save_path_segment() multiple times
    because it uses a single database connection and transaction for all segments.

    Args:
        segments: List of (start_page, end_page, segment_path) tuples
        max_retries: Maximum retry attempts for database lock errors (default: 3)

    Returns:
        int: Number of segments successfully saved

    Raises:
        sqlite3.OperationalError: If database remains locked after all retries
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                saved_count = 0

                for start_page, end_page, segment_path in segments:
                    # Check if segment already exists
                    cursor.execute('''
                        SELECT id FROM path_segments
                        WHERE start_page = ? AND end_page = ?
                    ''', (start_page, end_page))

                    existing = cursor.fetchone()

                    if existing:
                        # Update use count and last_used timestamp
                        cursor.execute('''
                            UPDATE path_segments
                            SET use_count = use_count + 1,
                                last_used = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (existing['id'],))
                    else:
                        # Insert new segment
                        segment_json = json.dumps(segment_path)
                        cursor.execute('''
                            INSERT INTO path_segments
                            (start_page, end_page, segment_path, hops)
                            VALUES (?, ?, ?, ?)
                        ''', (start_page, end_page, segment_json, len(segment_path) - 1))

                    saved_count += 1

                # All segments saved in single transaction
                return saved_count

        except sqlite3.OperationalError as e:
            last_exception = e
            # Check if it's a lock/busy error
            error_str = str(e).lower()
            if 'locked' in error_str or 'busy' in error_str:
                if attempt < max_retries - 1:
                    # Exponential backoff: 0.1s, 0.2s, 0.4s
                    sleep_time = 0.1 * (2 ** attempt)
                    print(f"Database locked during bulk segment save, retrying in {sleep_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(sleep_time)
                    continue
            # If not a lock error, or last attempt, raise immediately
            raise

    # If we exhausted all retries, raise the last exception
    if last_exception:
        raise last_exception

def cleanup_old_segments(days_old=30, max_segments=10000):
    """
    Clean up old, rarely-used path segments

    Args:
        days_old: Remove segments older than this many days
        max_segments: Keep at most this many segments (keep most recently used)
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Remove segments older than days_old that haven't been used recently
        cursor.execute('''
            DELETE FROM path_segments
            WHERE last_used < datetime('now', '-' || ? || ' days')
        ''', (days_old,))

        # Keep only the max_segments most recently used
        cursor.execute('''
            DELETE FROM path_segments
            WHERE id NOT IN (
                SELECT id FROM path_segments
                ORDER BY last_used DESC
                LIMIT ?
            )
        ''', (max_segments,))
