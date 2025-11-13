import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager

DATABASE_NAME = 'wikipedia_searches.db'

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DATABASE_NAME)
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
    """Initialize the database with required tables"""
    with get_db() as conn:
        cursor = conn.cursor()
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

def save_search(start_term, end_term, path, hops, pages_checked, success, error_message=None):
    """Save a search result to the database"""
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
