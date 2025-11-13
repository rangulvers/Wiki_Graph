import sqlite3
import json
import time
from datetime import datetime
from contextlib import contextmanager

DATABASE_NAME = 'wikipedia_searches.db'

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

                # Convert path list to JSON string
                path_json = json.dumps(path) if path else None

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
