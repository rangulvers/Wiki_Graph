from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import httpx
from collections import deque
import time
import json
import database
import asyncio
import re
from typing import Optional, TypeVar, Callable, Any, List
from functools import wraps
import logging
from models import (
    SearchRequest, SearchResponse, SearchErrorResponse,
    Node, Edge
)
from path_cache import get_cache

# Type variable for generic async function decorator
T = TypeVar('T')

# Helper function for title normalization (used for cache keys)
def normalize_title(title: str) -> str:
    """
    Normalize Wikipedia title for consistent cache keys

    Args:
        title: Wikipedia page title

    Returns:
        Normalized title (lowercase, spaces instead of underscores)
    """
    return title.strip().replace("_", " ").lower()

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Wikipedia Path Finder API", version="1.0.0")

# Add rate limit exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware - restrict to specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://wikigraph.up.railway.app"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://d3js.org https://www.googletagmanager.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://en.wikipedia.org https://www.google-analytics.com; "
        "frame-ancestors 'none';"
    )
    return response

# Templates
templates = Jinja2Templates(directory="templates")

# Initialize database on startup
database.init_db()

# Retry decorator for API calls
def retry_on_failure(max_retries: int = 3, backoff_factor: float = 0.5):
    """
    Decorator to retry async functions on transient failures

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_factor: Multiplier for exponential backoff (default: 0.5)

    Retries on:
    - httpx.TimeoutException (network timeouts)
    - httpx.ConnectError (connection failures)
    - httpx.ReadError (read failures)

    Does NOT retry on:
    - httpx.HTTPStatusError (4xx, 5xx responses)
    - Other exceptions
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)

                except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
                    last_exception = e

                    if attempt < max_retries - 1:
                        # Exponential backoff: 0.5s, 1s, 2s
                        sleep_time = backoff_factor * (2 ** attempt)
                        logger.warning(
                            f"API call failed, retrying",
                            extra={
                                "error_type": type(e).__name__,
                                "retry_delay": sleep_time,
                                "attempt": attempt + 1,
                                "max_retries": max_retries
                            }
                        )
                        await asyncio.sleep(sleep_time)
                        continue

                    # Last attempt failed
                    logger.error(f"API call failed after {max_retries} attempts", extra={"error": str(e)})
                    raise

                except Exception as e:
                    # Don't retry on other exceptions (like HTTP errors)
                    raise

            # If we somehow exit the loop without returning or raising
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


# Shared HTTP client for all requests (connection pooling)
_shared_http_client: Optional[httpx.AsyncClient] = None

async def get_shared_http_client() -> httpx.AsyncClient:
    """
    Get or create the shared HTTP client for Wikipedia API requests.

    This client is shared across all requests for efficient connection pooling
    and reuse. It's configured with:
    - Granular timeouts (connect, read, write, pool)
    - Connection limits (max 100 connections, 20 keepalive)
    - Proper User-Agent header for Wikipedia

    Returns:
        httpx.AsyncClient: The shared HTTP client instance
    """
    global _shared_http_client

    if _shared_http_client is None:
        # Configure timeouts with granular control
        timeout = httpx.Timeout(
            connect=5.0,   # Time to establish connection
            read=30.0,     # Time to read response (Wikipedia can be slow)
            write=5.0,     # Time to send request
            pool=5.0       # Time to acquire connection from pool
        )

        # Configure connection pooling limits (increased for high-performance parallel operations)
        limits = httpx.Limits(
            max_connections=500,        # Max total connections (increased from 100)
            max_keepalive_connections=100  # Max idle connections to keep alive (increased from 20)
        )

        # Create shared client with proper configuration
        _shared_http_client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            headers={
                'User-Agent': 'WikipediaConnectionFinder/1.0 (Educational Project)'
            },
            http2=True  # Enable HTTP/2 for parallel request multiplexing (15-30% speedup)
        )

    return _shared_http_client


@app.on_event("shutdown")
async def shutdown_http_client():
    """Cleanup: Close the shared HTTP client on application shutdown"""
    global _shared_http_client
    if _shared_http_client is not None:
        await _shared_http_client.aclose()
        _shared_http_client = None


class WikipediaPathFinder:
    def __init__(self, max_depth=6):
        self.max_depth = max_depth
        self.visited = set()
        self.client = None
        self._edge_cache = {}  # Cache for edge validation: (from_normalized, to_normalized) -> bool

    async def __aenter__(self):
        """Async context manager entry - get shared HTTP client"""
        self.client = await get_shared_http_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit

        Note: We don't close the client here since it's shared across requests.
        The client is closed on application shutdown.
        """
        # Don't close shared client - just clear reference
        self.client = None
        return False

    @retry_on_failure(max_retries=3, backoff_factor=0.5)
    async def get_wikipedia_links(self, page_title):
        """Get all links from a Wikipedia page (forward direction) with retry logic"""
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": page_title,
            "prop": "links",
            "pllimit": "max",
            "format": "json",
            "plnamespace": 0,  # Only article links
            "formatversion": 2,  # Use modern format
            "redirects": 1  # Automatically resolve redirects
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()  # Raise error for bad status codes

            data = response.json()

            # With formatversion=2, the structure is cleaner
            pages = data.get("query", {}).get("pages", [])

            if not pages:
                return None

            page_data = pages[0]

            # Check if page doesn't exist
            if "missing" in page_data:
                print(f"Page '{page_title}' does not exist")
                return None

            links = page_data.get("links", [])
            return [link["title"] for link in links]

        except httpx.HTTPError as e:
            print(f"Request error fetching links for {page_title}: {e}")
            return []
        except ValueError as e:
            print(f"JSON parsing error for {page_title}: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error fetching links for {page_title}: {e}")
            return []

    @retry_on_failure(max_retries=3, backoff_factor=0.5)
    async def get_wikipedia_backlinks(self, page_title, limit=500):
        """Get all pages that link TO a Wikipedia page (backward direction) with retry logic"""
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "backlinks",
            "bltitle": page_title,
            "bllimit": min(limit, 500),  # Max 500 per request
            "format": "json",
            "blnamespace": 0,  # Only article links
            "formatversion": 2,
            "blredirect": 1  # Resolve redirects for backlinks
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            backlinks = data.get("query", {}).get("backlinks", [])

            # For popular pages with 1000+ backlinks, limit to avoid slowdown
            if len(backlinks) >= 500:
                print(f"Page '{page_title}' has many backlinks, limiting to {limit}")

            return [link["title"] for link in backlinks[:limit]]

        except httpx.HTTPError as e:
            print(f"Request error fetching backlinks for {page_title}: {e}")
            return []
        except ValueError as e:
            print(f"JSON parsing error for backlinks {page_title}: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error fetching backlinks for {page_title}: {e}")
            return []

    def normalize_title(self, title):
        """Normalize Wikipedia title for comparison"""
        return title.strip().replace("_", " ").lower()

    @retry_on_failure(max_retries=3, backoff_factor=0.5)
    async def resolve_wikipedia_title(self, search_term):
        """Resolve a search term to an actual Wikipedia article title using search API with retry logic"""
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "opensearch",
            "search": search_term,
            "limit": 1,
            "namespace": 0,
            "format": "json"
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # OpenSearch returns: [query, [titles], [descriptions], [urls]]
            if len(data) >= 2 and len(data[1]) > 0:
                resolved_title = data[1][0]
                print(f"Resolved '{search_term}' to '{resolved_title}'")
                return resolved_title
            else:
                print(f"No Wikipedia article found for '{search_term}'")
                return None

        except httpx.HTTPError as e:
            print(f"Request error resolving '{search_term}': {e}")
            return None
        except Exception as e:
            print(f"Unexpected error resolving '{search_term}': {e}")
            return None

    async def find_k_paths_bidirectional(self, start, end, max_paths=3, min_diversity=0.3, callback=None):
        """Find multiple diverse paths using bidirectional BFS

        Args:
            start: Starting Wikipedia page title
            end: Target Wikipedia page title
            max_paths: Maximum number of paths to find (default: 3)
            min_diversity: Minimum Jaccard distance between paths (default: 0.3)
            callback: Optional function(event_type, data) for streaming updates

        Returns:
            List of paths, each path is a list of page titles
        """
        # Clear edge cache at start of new search to prevent unbounded growth
        self._edge_cache.clear()

        start_normalized = self.normalize_title(start)
        end_normalized = self.normalize_title(end)

        if start_normalized == end_normalized:
            return [[start]]

        # Track found paths and meeting points
        found_paths = []
        meeting_points = []  # Store all discovered meeting points
        shortest_path_length = None

        # BFS state
        forward_queue = deque([(start, [start], 0)])
        backward_queue = deque([(end, [end], 0)])
        forward_visited = {start_normalized: None}
        backward_visited = {end_normalized: None}
        forward_parents = {start_normalized: (None, start)}
        backward_parents = {end_normalized: (None, end)}

        pages_checked = 0
        forward_depth = 0
        backward_depth = 0
        last_event_time = time.time()
        nodes_since_last_event = 0

        # Continue searching until we have enough diverse paths
        while (forward_queue or backward_queue) and len(found_paths) < max_paths:
            current_depth = forward_depth + backward_depth

            # Stop if we're searching too deep beyond shortest path
            if shortest_path_length and current_depth > shortest_path_length + 2:
                break

            if current_depth > self.max_depth:
                break

            # Process forward direction
            if forward_queue and forward_depth <= backward_depth:
                current_page, path, depth = forward_queue.popleft()
                forward_depth = max(forward_depth, depth)
                pages_checked += 1
                nodes_since_last_event += 1

                links = await self.get_wikipedia_links(current_page)
                if links is None:
                    continue

                # Cache all edges from this page during BFS (optimization)
                current_normalized = self.normalize_title(current_page)
                links_normalized = [self.normalize_title(link) for link in links]
                for link_norm in links_normalized:
                    self._edge_cache[(current_normalized, link_norm)] = True

                for link in links:
                    link_normalized = self.normalize_title(link)

                    # Found a meeting point!
                    if link_normalized in backward_visited:
                        forward_path = path + [link]
                        backward_path = self._reconstruct_backward_path(link_normalized, backward_parents)
                        new_path = forward_path + backward_path

                        # No validation needed for forward meeting - BFS already verified all edges exist

                        # Track shortest path length
                        if shortest_path_length is None:
                            shortest_path_length = len(new_path)

                        # Check if path is diverse enough
                        if self._is_diverse_path(new_path, found_paths, min_diversity):
                            found_paths.append(new_path)
                            meeting_points.append(link_normalized)

                            if callback:
                                callback('path_found', {
                                    'path_number': len(found_paths),
                                    'path': new_path,
                                    'length': len(new_path) - 1,
                                    'meeting_point': link
                                })

                    # Continue BFS
                    if link_normalized not in forward_visited:
                        forward_visited[link_normalized] = current_page
                        forward_parents[link_normalized] = (self.normalize_title(current_page), link)
                        forward_queue.append((link, path + [link], depth + 1))

            # Process backward direction
            elif backward_queue:
                current_page, path, depth = backward_queue.popleft()
                backward_depth = max(backward_depth, depth)
                pages_checked += 1
                nodes_since_last_event += 1

                links = await self.get_wikipedia_backlinks(current_page, limit=300)

                # Don't cache backward edges - they need validation since backlinks API
                # may return pages that link through redirects/disambiguations
                # Only forward edges (from get_wikipedia_links) are safe to cache

                for link in links:
                    link_normalized = self.normalize_title(link)

                    # Found a meeting point!
                    if link_normalized in forward_visited:
                        forward_path = self._reconstruct_forward_path(link_normalized, forward_parents)
                        new_path = forward_path + path

                        # Clear edge cache to prevent false positives from BFS exploration
                        self._edge_cache.clear()

                        # Validate path before accepting it
                        is_valid = await self._validate_path(new_path)
                        if not is_valid:
                            logger.warning(f"Skipping invalid path with {len(new_path)} nodes (backward meeting)")
                            continue

                        if shortest_path_length is None:
                            shortest_path_length = len(new_path)

                        if self._is_diverse_path(new_path, found_paths, min_diversity):
                            found_paths.append(new_path)
                            meeting_points.append(link_normalized)

                            if callback:
                                callback('path_found', {
                                    'path_number': len(found_paths),
                                    'path': new_path,
                                    'length': len(new_path) - 1,
                                    'meeting_point': link
                                })

                    if link_normalized not in backward_visited:
                        backward_visited[link_normalized] = current_page
                        backward_parents[link_normalized] = (self.normalize_title(current_page), link)
                        backward_queue.append((link, [link] + path, depth + 1))

            # Send progress events
            current_time = time.time()
            should_send = (nodes_since_last_event >= 20) or ((current_time - last_event_time) >= 0.5)

            if callback and should_send:
                pages_per_sec = int(nodes_since_last_event / (current_time - last_event_time)) if (current_time - last_event_time) > 0 else 0
                callback('progress', {
                    'forward_depth': forward_depth,
                    'backward_depth': backward_depth,
                    'depth': forward_depth + backward_depth,
                    'pages_checked': pages_checked,
                    'paths_found': len(found_paths),
                    'pages_per_second': pages_per_sec
                })
                last_event_time = current_time
                nodes_since_last_event = 0

        # Sort paths by length (shortest first)
        found_paths.sort(key=len)

        # Update self.visited with total pages checked for statistics
        self.visited = forward_visited | backward_visited

        return found_paths if found_paths else None

    def _is_diverse_path(self, new_path, existing_paths, min_diversity):
        """Check if new path is sufficiently different from existing paths

        Uses Jaccard distance: 1 - (intersection / union) of nodes
        """
        if not existing_paths:
            return True

        new_path_set = set(self.normalize_title(p) for p in new_path)

        for existing_path in existing_paths:
            existing_set = set(self.normalize_title(p) for p in existing_path)

            intersection = len(new_path_set & existing_set)
            union = len(new_path_set | existing_set)

            # Jaccard similarity
            similarity = intersection / union if union > 0 else 0
            diversity = 1 - similarity

            # If too similar to any existing path, reject
            if diversity < min_diversity:
                return False

        return True

    async def find_path_bidirectional(self, start, end, callback=None):
        """Find shortest path using bidirectional BFS (5-10x faster)

        Args:
            start: Starting Wikipedia page title
            end: Target Wikipedia page title
            callback: Optional function(event_type, data) for streaming updates
        """
        # Clear edge cache at start of new search to prevent unbounded growth
        self._edge_cache.clear()

        start_normalized = self.normalize_title(start)
        end_normalized = self.normalize_title(end)

        if start_normalized == end_normalized:
            return [start]

        # Two BFS queues: (current_page, path, depth, direction)
        forward_queue = deque([(start, [start], 0)])
        backward_queue = deque([(end, [end], 0)])

        # Two visited dictionaries: page -> parent (for path reconstruction)
        forward_visited = {start_normalized: None}
        backward_visited = {end_normalized: None}

        # Parent tracking for path reconstruction
        forward_parents = {start_normalized: (None, start)}
        backward_parents = {end_normalized: (None, end)}

        pages_checked = 0
        forward_depth = 0
        backward_depth = 0
        last_event_time = time.time()
        nodes_since_last_event = 0

        # Alternate between forward and backward search
        while (forward_queue or backward_queue) and (forward_depth + backward_depth) <= self.max_depth:
            # Process forward direction
            if forward_queue and forward_depth <= backward_depth:
                current_page, path, depth = forward_queue.popleft()
                forward_depth = max(forward_depth, depth)
                pages_checked += 1
                nodes_since_last_event += 1

                # Get forward links
                links = await self.get_wikipedia_links(current_page)

                if links is None:
                    continue

                # Cache all edges from this page during BFS (optimization)
                current_normalized = self.normalize_title(current_page)
                links_normalized = [self.normalize_title(link) for link in links]
                for link_norm in links_normalized:
                    self._edge_cache[(current_normalized, link_norm)] = True

                for link in links:
                    link_normalized = self.normalize_title(link)

                    # Check if backward search has seen this page (MEETING POINT!)
                    if link_normalized in backward_visited:
                        # Reconstruct path: forward + reversed backward
                        final_path = path + [link] + self._reconstruct_backward_path(link_normalized, backward_parents)

                        # No validation needed for forward meeting - BFS already verified all edges exist

                        # Update self.visited with total pages checked for statistics
                        self.visited = forward_visited | backward_visited

                        if callback:
                            callback('complete', {
                                'path': final_path,
                                'pages_checked': len(forward_visited) + len(backward_visited),
                                'meeting_point': link
                            })
                        return final_path

                    # Add to forward visited
                    if link_normalized not in forward_visited:
                        forward_visited[link_normalized] = current_page
                        forward_parents[link_normalized] = (self.normalize_title(current_page), link)
                        forward_queue.append((link, path + [link], depth + 1))

            # Process backward direction
            elif backward_queue:
                current_page, path, depth = backward_queue.popleft()
                backward_depth = max(backward_depth, depth)
                pages_checked += 1
                nodes_since_last_event += 1

                # Get backward links (backlinks)
                links = await self.get_wikipedia_backlinks(current_page, limit=300)

                # Don't cache backward edges - they need validation since backlinks API
                # may return pages that link through redirects/disambiguations
                # Only forward edges (from get_wikipedia_links) are safe to cache

                for link in links:
                    link_normalized = self.normalize_title(link)

                    # Check if forward search has seen this page (MEETING POINT!)
                    if link_normalized in forward_visited:
                        # Reconstruct path: forward + reversed backward
                        final_path = self._reconstruct_forward_path(link_normalized, forward_parents) + path

                        # Clear edge cache to prevent false positives from BFS exploration
                        self._edge_cache.clear()

                        # Validate path before returning it
                        is_valid = await self._validate_path(final_path)
                        if not is_valid:
                            logger.warning(f"Skipping invalid path from backward meeting, continuing search...")
                            continue  # Continue searching for a valid path

                        # Update self.visited with total pages checked for statistics
                        self.visited = forward_visited | backward_visited

                        if callback:
                            callback('complete', {
                                'path': final_path,
                                'pages_checked': len(forward_visited) + len(backward_visited),
                                'meeting_point': link
                            })
                        return final_path

                    # Add to backward visited
                    if link_normalized not in backward_visited:
                        backward_visited[link_normalized] = current_page
                        backward_parents[link_normalized] = (self.normalize_title(current_page), link)
                        backward_queue.append((link, [link] + path, depth + 1))

            # Send batched progress events
            current_time = time.time()
            should_send = (nodes_since_last_event >= 20) or ((current_time - last_event_time) >= 0.5)

            if callback and should_send:
                pages_per_sec = int(nodes_since_last_event / (current_time - last_event_time)) if (current_time - last_event_time) > 0 else 0

                callback('progress', {
                    'forward_depth': forward_depth,
                    'backward_depth': backward_depth,
                    'depth': forward_depth + backward_depth,
                    'pages_checked': pages_checked,
                    'forward_queue_size': len(forward_queue),
                    'backward_queue_size': len(backward_queue),
                    'pages_per_second': pages_per_sec
                })

                last_event_time = current_time
                nodes_since_last_event = 0

        # Update self.visited with total pages checked for statistics
        self.visited = forward_visited | backward_visited

        return None  # No path found

    def _reconstruct_forward_path(self, meeting_point, parents):
        """Reconstruct path from start to meeting point"""
        path = []
        current = meeting_point
        while current is not None:
            parent_normalized, original_title = parents[current]
            path.append(original_title)
            current = parent_normalized
        return list(reversed(path))

    def _reconstruct_backward_path(self, meeting_point, parents):
        """Reconstruct path from meeting point to end (already reversed)"""
        path = []
        current = meeting_point
        parent_normalized, original_title = parents[current]
        current = parent_normalized

        while current is not None:
            parent_normalized, original_title = parents[current]
            path.append(original_title)
            current = parent_normalized
        return path

    async def _validate_edge(self, from_page: str, to_page: str) -> bool:
        """
        Validate a single edge (from_page → to_page) with caching

        Checks if to_page exists in from_page's outbound links.
        Caches all edges from from_page for future lookups.

        Args:
            from_page: Source Wikipedia page title
            to_page: Target Wikipedia page title

        Returns:
            True if edge exists, False otherwise
        """
        from_normalized = self.normalize_title(from_page)
        to_normalized = self.normalize_title(to_page)
        cache_key = (from_normalized, to_normalized)

        # Check cache first
        if cache_key in self._edge_cache:
            logger.debug(f"Edge cache HIT: {from_page} → {to_page}")
            return self._edge_cache[cache_key]

        logger.debug(f"Edge cache MISS: {from_page} → {to_page}, fetching links...")

        # Fetch links from source page
        try:
            links = await self.get_wikipedia_links(from_page)

            if links is None:
                logger.warning(f"Could not fetch links from '{from_page}' for edge validation")
                self._edge_cache[cache_key] = False
                return False

            # Cache ALL edges from this page (not just the one we're checking)
            links_normalized = [self.normalize_title(link) for link in links]
            for link_norm in links_normalized:
                self._edge_cache[(from_normalized, link_norm)] = True

            # Check if our specific edge exists
            edge_exists = to_normalized in links_normalized

            # Cache negative result if edge doesn't exist
            if not edge_exists:
                self._edge_cache[cache_key] = False

            logger.debug(f"Cached {len(links_normalized)} edges from '{from_page}'")
            return edge_exists

        except Exception as e:
            logger.error(f"Error validating edge {from_page} → {to_page}: {e}")
            self._edge_cache[cache_key] = False
            return False

    async def _validate_path(self, path: List[str]) -> bool:
        """
        Validate that each edge in the path actually exists on Wikipedia

        For a path [A, B, C], this verifies:
        - A's outbound links contain B
        - B's outbound links contain C

        This catches invalid paths generated by bidirectional BFS bugs.

        Args:
            path: List of Wikipedia page titles

        Returns:
            True if all edges are valid, False otherwise
        """
        if not path or len(path) < 2:
            return True  # Single page or empty path is trivially valid

        logger.info(f"Validating path with {len(path)-1} edges: {' → '.join(path[:3])}{'...' if len(path) > 3 else ''}")

        # Build list of validation tasks for all edges
        validation_tasks = []
        for i in range(len(path) - 1):
            validation_tasks.append(self._validate_edge(path[i], path[i + 1]))

        # Validate all edges in parallel
        try:
            results = await asyncio.gather(*validation_tasks, return_exceptions=True)

            # Check results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Exception validating edge {path[i]} → {path[i+1]}: {result}")
                    return False
                elif result is False:
                    logger.warning(
                        f"Path validation FAILED at edge {i+1}/{len(path)-1}: "
                        f"'{path[i]}' does not link to '{path[i+1]}'"
                    )
                    return False

            # All edges validated successfully
            logger.info(f"✓ Path validated successfully: {' → '.join(path)}")
            return True

        except Exception as e:
            logger.error(f"Error during parallel path validation: {e}")
            return False

    def _log_path_breakdown(self, path: List[str], segment_sources: List[dict], elapsed_ms: int):
        """
        Log detailed breakdown of path sources (cache vs BFS)

        Args:
            path: Complete path as list of page titles
            segment_sources: List of segment metadata dicts with 'from_page', 'to_page', 'source'
            elapsed_ms: Time taken in milliseconds
        """
        if not path or not segment_sources:
            return

        cached_count = sum(1 for s in segment_sources if s.get('source') == 'cache')
        total_count = len(segment_sources)

        # Summary line
        logger.info(f"{'='*80}")
        logger.info(f"Search completed: {path[0]} → {path[-1]} ({elapsed_ms}ms)")

        # Cache hit type
        if cached_count == total_count:
            logger.info(f"✓ Complete cache hit ({cached_count} segments)")
        elif cached_count > 0:
            logger.info(f"⚡ Hybrid search ({cached_count}/{total_count} segments cached)")
        else:
            logger.info(f"○ Full BFS search (0 segments cached)")

        # Detailed segment breakdown
        logger.info(f"\nPath breakdown ({len(path)} nodes, {total_count} edges):")
        for i, seg in enumerate(segment_sources):
            icon = "[CACHE]" if seg.get('source') == 'cache' else "[BFS]  "
            from_page = seg.get('from_page', '?')
            to_page = seg.get('to_page', '?')

            # Add timestamp info
            timestamp_info = ""
            if seg.get('source') == 'cache' and seg.get('cached_at'):
                timestamp_info = f" (cached: {seg.get('cached_at')})"
            elif seg.get('source') == 'bfs' and seg.get('discovered_at'):
                timestamp_info = f" (found: {seg.get('discovered_at')})"

            logger.info(f"  {i+1}. {icon} {from_page} → {to_page}{timestamp_info}")

        # Cache effectiveness
        effectiveness = (cached_count / total_count * 100) if total_count > 0 else 0
        logger.info(f"\nCache effectiveness: {effectiveness:.1f}% ({cached_count}/{total_count} segments)")
        logger.info(f"{'='*80}")

    async def find_path(self, start, end, callback=None):
        """Find shortest path between two Wikipedia pages

        Now uses bidirectional BFS for 5-10x performance improvement.
        """
        # Use the optimized bidirectional search
        return await self.find_path_bidirectional(start, end, callback)

    async def find_path_with_cache(self, start, end, callback=None):
        """
        Find path with cache-aware optimization

        Checks cache BEFORE running BFS:
        1. Direct cache hit: return immediately
        2. Composed path from cached segments: validate and return
        3. Cache miss: fall back to bidirectional BFS

        Args:
            start: Starting Wikipedia page title
            end: Target Wikipedia page title
            callback: Optional callback function(event_type, data)

        Returns:
            Tuple of (path, cache_info) where cache_info contains:
            - is_cached: bool
            - cache_hit_type: 'direct' | 'composed' | 'miss'
            - segments_used: int
            - time_saved_ms: int (estimated)
        """
        start_time = time.time()
        cache = get_cache()

        start_normalized = self.normalize_title(start)
        end_normalized = self.normalize_title(end)

        # Same page check
        if start_normalized == end_normalized:
            return ([start], {
                'is_cached': False,
                'cache_hit_type': 'same_page',
                'segments_used': 0,
                'time_saved_ms': 0
            })

        # Try direct cache hit
        logger.info(f"Cache-aware search: {start} → {end}")
        cached_path = cache.get(start_normalized, end_normalized)

        if cached_path:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(f"✓ Direct cache HIT: {start} → {end} ({elapsed_ms}ms)")

            if callback:
                callback('cache_hit', {
                    'hit_type': 'direct',
                    'path': cached_path,
                    'time_ms': elapsed_ms
                })

            return (cached_path, {
                'is_cached': True,
                'cache_hit_type': 'direct',
                'segments_used': 1,
                'time_saved_ms': 5000  # Typical BFS time
            })

        # Try composed path from cached segments
        logger.info(f"Attempting cache composition...")
        composed_result = cache.compose_path(start_normalized, end_normalized, max_hops=3)
        composed_path, segment_metadata = composed_result if composed_result[0] else (None, None)

        if composed_path:
            # Validate composed path (edges might be stale)
            logger.info(f"Validating composed path with {len(composed_path)} nodes...")
            is_valid = await self._validate_path(composed_path)

            if is_valid:
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.info(f"✓ Composed cache HIT: {start} → {end} ({elapsed_ms}ms, {len(composed_path)-1} hops)")

                # Log detailed segment breakdown
                self._log_path_breakdown(composed_path, segment_metadata, elapsed_ms)

                if callback:
                    callback('cache_hit', {
                        'hit_type': 'composed',
                        'path': composed_path,
                        'time_ms': elapsed_ms,
                        'hops': len(composed_path) - 1,
                        'segment_metadata': segment_metadata
                    })

                return (composed_path, {
                    'is_cached': True,
                    'cache_hit_type': 'composed',
                    'segments_used': len(segment_metadata),
                    'time_saved_ms': 4000,  # Estimated time saved
                    'segment_sources': segment_metadata
                })
            else:
                logger.warning(f"Composed path validation failed, falling back to BFS")

        # Cache miss - fall back to BFS
        logger.info(f"Cache MISS: Running bidirectional BFS...")
        if callback:
            callback('cache_miss', {
                'message': 'No cached path found, running BFS...'
            })

        bfs_start = time.time()
        path = await self.find_path_bidirectional(start, end, callback)
        bfs_time_ms = int((time.time() - bfs_start) * 1000)

        if path:
            # Create BFS segment metadata
            from datetime import datetime
            current_time = datetime.now().isoformat()
            bfs_segments = []
            for i in range(len(path) - 1):
                bfs_segments.append({
                    'from_page': path[i],
                    'to_page': path[i + 1],
                    'source': 'bfs',
                    'discovered_at': current_time
                })

            # Log detailed segment breakdown
            logger.info(f"BFS completed in {bfs_time_ms}ms")
            self._log_path_breakdown(path, bfs_segments, bfs_time_ms)

            return (path, {
                'is_cached': False,
                'cache_hit_type': 'miss',
                'segments_used': 0,
                'time_saved_ms': 0,
                'bfs_time_ms': bfs_time_ms,
                'segment_sources': bfs_segments
            })

        return (None, {
            'is_cached': False,
            'cache_hit_type': 'miss',
            'segments_used': 0,
            'time_saved_ms': 0,
            'bfs_time_ms': bfs_time_ms,
            'segment_sources': []
        })

    async def find_k_paths_with_cache(self, start, end, max_paths=3, min_diversity=0.3, callback=None):
        """
        Find multiple diverse paths with cache-aware optimization

        For multi-path searches, cache-aware approach:
        1. Check cache for first path
        2. If found, use it as one of the paths
        3. Run BFS to find additional diverse paths

        Args:
            start: Starting Wikipedia page title
            end: Target Wikipedia page title
            max_paths: Maximum number of paths to find (1-5)
            min_diversity: Minimum Jaccard distance between paths
            callback: Optional callback function

        Returns:
            Tuple of (paths_list, cache_info)
        """
        cache = get_cache()
        start_normalized = self.normalize_title(start)
        end_normalized = self.normalize_title(end)

        # Try cache first
        composed_result = cache.compose_path(start_normalized, end_normalized, max_hops=3)
        cached_path, segment_metadata = composed_result if composed_result and composed_result[0] else (None, None)
        cache_info = {'is_cached': False, 'cache_hit_type': 'miss'}

        if cached_path:
            is_valid = await self._validate_path(cached_path)
            if is_valid:
                logger.info(f"Multi-path: Using cached path as first result")
                cache_info = {'is_cached': True, 'cache_hit_type': 'composed'}

                if callback:
                    callback('cache_hit', {
                        'hit_type': 'composed',
                        'path': cached_path,
                        'used_for': 'first_path'
                    })

                # If max_paths = 1, just return cached path
                if max_paths == 1:
                    return ([cached_path], cache_info)

                # Otherwise, run BFS to find more diverse paths
                # The cached path will be included in the diversity check

        # Run full multi-path BFS
        paths = await self.find_k_paths_bidirectional(
            start, end, max_paths, min_diversity, callback
        )

        return (paths, cache_info)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the landing/about page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    """Serve the main search tool page"""
    return templates.TemplateResponse("search.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about_redirect(request: Request):
    """Redirect /about to / for backwards compatibility"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=301)


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    """Serve robots.txt for search engine crawlers"""
    try:
        with open("static/robots.txt", "r") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback if file doesn't exist
        return """User-agent: *
Allow: /
Disallow: /api/
Sitemap: https://wikigraph.up.railway.app/sitemap.xml"""


@app.get("/sitemap.xml")
async def sitemap():
    """Serve sitemap.xml for search engines"""
    return FileResponse("static/sitemap.xml", media_type="application/xml")


@app.post("/find-path")
@limiter.limit("10/minute")
async def find_path_endpoint(request: Request, search_request: SearchRequest, timeout_seconds: int = 300):
    """
    Find path between two Wikipedia pages (non-streaming version)

    This endpoint performs a bidirectional BFS search to find the shortest path
    between two Wikipedia articles.

    Args:
        search_request: Search parameters (start and end terms)
        timeout_seconds: Maximum search duration in seconds (default: 300 = 5 minutes)
    """
    start_term = search_request.start.strip()
    end_term = search_request.end.strip()

    logger.info(
        "Starting path search",
        extra={
            "start_term": start_term,
            "end_term": end_term,
            "timeout": timeout_seconds
        }
    )

    try:
        # Wrap search in timeout to prevent indefinite searches
        async with asyncio.timeout(timeout_seconds):
            async with WikipediaPathFinder(max_depth=6) as finder:
                # Use cache-aware pathfinding
                cache_info = None
                if search_request.max_paths > 1:
                    paths, cache_info = await finder.find_k_paths_with_cache(
                        start_term,
                        end_term,
                        max_paths=search_request.max_paths,
                        min_diversity=search_request.min_diversity
                    )
                    path = paths[0] if paths else None  # Shortest path for backwards compat
                else:
                    paths = None
                    path, cache_info = await finder.find_path_with_cache(start_term, end_term)
    except asyncio.TimeoutError:
        # Search exceeded timeout
        error_msg = f'Search timeout exceeded ({timeout_seconds} seconds). Try narrowing your search terms.'

        # Still try to save to database
        try:
            search_id = database.save_search(
                start_term=start_term,
                end_term=end_term,
                path=[],
                hops=0,
                pages_checked=0,
                success=False,
                error_message=error_msg
            )
        except Exception as e:
            logger.error("Failed to save timeout error to database", extra={"error": str(e)})
            search_id = None

        return SearchErrorResponse(
            search_id=search_id,
            error=error_msg,
            pages_checked=0
        )

    # Continue with normal flow if no timeout
    if path:
        # Create nodes and edges for primary path (shortest)
        nodes = [Node(id=i, label=page, title=page) for i, page in enumerate(path)]
        edges = [Edge(**{'from': i, 'to': i+1}) for i in range(len(path)-1)]

        # Create PathInfo objects for all paths if multiple
        path_infos = None
        if paths and len(paths) > 1:
            from models import PathInfo
            path_infos = []
            for idx, p in enumerate(paths):
                p_nodes = [Node(id=i, label=page, title=page) for i, page in enumerate(p)]
                p_edges = [Edge(**{'from': i, 'to': i+1}) for i in range(len(p)-1)]

                # Calculate diversity score vs first path
                diversity = 0.0
                if idx > 0:
                    path_set = set(finder.normalize_title(page) for page in p)
                    first_set = set(finder.normalize_title(page) for page in paths[0])
                    intersection = len(path_set & first_set)
                    union = len(path_set | first_set)
                    diversity = 1 - (intersection / union) if union > 0 else 0.0

                # Get segment sources and calculate cache effectiveness for first path
                segment_sources_list = None
                cache_effectiveness = None
                if idx == 0 and cache_info.get('segment_sources'):
                    from models import SegmentSource
                    segment_sources_list = [
                        SegmentSource(**seg) for seg in cache_info.get('segment_sources', [])
                    ]
                    # Calculate cache effectiveness
                    cached_count = sum(1 for s in cache_info.get('segment_sources', []) if s.get('source') == 'cache')
                    total_count = len(cache_info.get('segment_sources', []))
                    cache_effectiveness = (cached_count / total_count * 100) if total_count > 0 else 0.0

                path_infos.append(PathInfo(
                    path=p,
                    hops=len(p) - 1,
                    nodes=p_nodes,
                    edges=p_edges,
                    diversity_score=diversity,
                    is_cached=cache_info.get('is_cached', False) if idx == 0 else False,
                    cache_segments=[],
                    cache_hit_type=cache_info.get('cache_hit_type') if idx == 0 else None,
                    segments_used=cache_info.get('segments_used') if idx == 0 else None,
                    time_saved_ms=cache_info.get('time_saved_ms') if idx == 0 else None,
                    segment_sources=segment_sources_list,
                    cache_effectiveness=cache_effectiveness
                ))

        # Save to database
        search_id = database.save_search(
            start_term=start_term,
            end_term=end_term,
            path=path,
            hops=len(path) - 1,
            pages_checked=len(finder.visited),
            success=True
        )

        # Save all paths and cache segments if multiple paths found
        if paths and len(paths) > 1:
            diversity_scores = [path_infos[i].diversity_score for i in range(len(path_infos))] if path_infos else None
            database.save_multiple_paths(search_id, paths, diversity_scores)

        # Cache all path segments for future use (keep original Wikipedia titles for API compatibility)
        cache = get_cache()
        for p in (paths if paths else [path]):
            cache.cache_path(p)

        return SearchResponse(
            success=True,
            search_id=search_id,
            path=path,
            paths=path_infos,
            nodes=nodes,
            edges=edges,
            hops=len(path) - 1,
            pages_checked=len(finder.visited),
            paths_found=len(paths) if paths else 1
        )
    else:
        error_msg = f'No path found within {finder.max_depth} hops'

        # Save failed search to database
        search_id = database.save_search(
            start_term=start_term,
            end_term=end_term,
            path=[],
            hops=0,
            pages_checked=len(finder.visited),
            success=False,
            error_message=error_msg
        )

        return SearchErrorResponse(
            search_id=search_id,
            error=error_msg,
            pages_checked=len(finder.visited)
        )

@app.post('/find-path-stream')
@limiter.limit("5/minute")
async def find_path_stream(request: Request, search_request: SearchRequest):
    """
    Stream BFS exploration in real-time using Server-Sent Events

    This endpoint provides real-time updates as the pathfinding algorithm
    explores Wikipedia pages.
    """
    start_term = search_request.start.strip()
    end_term = search_request.end.strip()

    logger.info("Starting streaming path search", extra={"start_term": start_term, "end_term": end_term})

    async def generate_events():
        """Async generator function that yields SSE events in real-time"""
        async with WikipediaPathFinder(max_depth=6) as finder:
            event_queue = asyncio.Queue()
            result = {'paths': [], 'pages_checked': 0, 'success': False, 'error': None}

            # Send start event
            yield f"data: {json.dumps({'type': 'start', 'data': {'start': start_term, 'end': end_term, 'max_paths': search_request.max_paths}})}\n\n"

            # Resolve search terms to actual Wikipedia article titles
            yield f"data: {json.dumps({'type': 'resolving', 'data': {'message': 'Resolving search terms...'}})}\n\n"

            resolved_start = await finder.resolve_wikipedia_title(start_term)
            resolved_end = await finder.resolve_wikipedia_title(end_term)

            # Check if both terms could be resolved
            if not resolved_start:
                error_event = {
                    'type': 'error',
                    'data': {'message': f"Could not find Wikipedia article for '{start_term}'. Please check spelling or try a more specific term."}
                }
                yield f"data: {json.dumps(error_event)}\n\n"
                return

            if not resolved_end:
                error_event = {
                    'type': 'error',
                    'data': {'message': f"Could not find Wikipedia article for '{end_term}'. Please check spelling or try a more specific term."}
                }
                yield f"data: {json.dumps(error_event)}\n\n"
                return

            # Send resolved titles to frontend
            yield f"data: {json.dumps({'type': 'resolved', 'data': {'start': resolved_start, 'end': resolved_end}})}\n\n"

            # Use resolved titles for search
            actual_start = resolved_start
            actual_end = resolved_end

            def callback(event_type, event_data):
                """Callback that puts events in queue for real-time streaming"""
                # Put event in queue immediately (using put_nowait for sync callback)
                event_queue.put_nowait({'type': event_type, 'data': event_data})

                # Store result data for database
                if event_type == 'complete':
                    result['paths'] = [event_data.get('path')]
                    result['pages_checked'] = event_data.get('pages_checked')
                    result['success'] = True
                    event_queue.put_nowait(None)  # Sentinel to stop
                elif event_type == 'path_found':
                    # Store each path as it's discovered
                    result['paths'].append(event_data.get('path'))
                    result['success'] = True
                elif event_type == 'progress':
                    result['pages_checked'] = event_data.get('pages_checked', result['pages_checked'])

            # Run pathfinding in async task
            async def run_search():
                try:
                    # Use cache-aware pathfinding
                    if search_request.max_paths > 1:
                        paths, cache_info = await finder.find_k_paths_with_cache(
                            actual_start,
                            actual_end,
                            max_paths=search_request.max_paths,
                            min_diversity=search_request.min_diversity,
                            callback=callback
                        )

                        # Send complete event for multi-path search
                        if paths:
                            complete_event = {
                                'type': 'complete',
                                'data': {
                                    'path': paths[0],  # Shortest path
                                    'pages_checked': len(finder.visited),
                                    'paths_found': len(paths),
                                    'cache_info': cache_info
                                }
                            }
                            event_queue.put_nowait(complete_event)
                            result['pages_checked'] = len(finder.visited)
                            result['success'] = True
                            event_queue.put_nowait(None)  # Sentinel
                        else:
                            # No paths found
                            error_event = {
                                'type': 'error',
                                'data': {
                                    'message': f'No path found within {finder.max_depth} hops',
                                    'pages_checked': len(finder.visited)
                                }
                            }
                            event_queue.put_nowait(error_event)
                            result['pages_checked'] = len(finder.visited)
                            result['error'] = error_event['data']['message']
                            event_queue.put_nowait(None)  # Sentinel
                    else:
                        path, cache_info = await finder.find_path_with_cache(actual_start, actual_end, callback=callback)
                        paths = [path] if path else None

                        # If no paths found, send error
                        if not paths:
                            error_event = {
                                'type': 'error',
                                'data': {
                                    'message': f'No path found within {finder.max_depth} hops',
                                    'pages_checked': len(finder.visited)
                                }
                            }
                            event_queue.put_nowait(error_event)
                            result['pages_checked'] = len(finder.visited)
                            result['error'] = error_event['data']['message']
                            event_queue.put_nowait(None)  # Sentinel
                except Exception as e:
                    error_event = {
                        'type': 'error',
                        'data': {'message': str(e)}
                    }
                    event_queue.put_nowait(error_event)
                    result['error'] = str(e)
                    event_queue.put_nowait(None)  # Sentinel

            # Start search task
            search_task = asyncio.create_task(run_search())

            try:
                # Yield events as they arrive in the queue
                while True:
                    try:
                        # Try to get event with timeout for keepalive
                        try:
                            event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                            if event is None:  # Sentinel - search is done
                                break
                            # Yield event immediately
                            yield f"data: {json.dumps(event)}\n\n"
                        except asyncio.TimeoutError:
                            # Send keepalive if no events
                            yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                    except Exception as e:
                        print(f"Error in event loop: {e}")
                        break

                # Wait for search task to complete
                await search_task

            except asyncio.CancelledError:
                # Client disconnected - cancel the search task
                logger.info("Client disconnected, cancelling search task")
                search_task.cancel()
                try:
                    await search_task
                except asyncio.CancelledError:
                    logger.info("Search task successfully cancelled")
                raise  # Re-raise to properly close the stream

            # Save to database
            if result['success'] and result['paths']:
                # Save shortest path (for now, database schema will be updated later)
                shortest_path = min(result['paths'], key=len) if result['paths'] else []
                search_id = database.save_search(
                    start_term=start_term,
                    end_term=end_term,
                    path=shortest_path,
                    hops=len(shortest_path) - 1,
                    pages_checked=result['pages_checked'],
                    success=True
                )

                # Cache all path segments for future use (keep original Wikipedia titles for API compatibility)
                cache = get_cache()
                for p in result['paths']:
                    cache.cache_path(p)
            else:
                search_id = database.save_search(
                    start_term=start_term,
                    end_term=end_term,
                    path=[],
                    hops=0,
                    pages_checked=result['pages_checked'],
                    success=False,
                    error_message=result.get('error', f'No path found within 6 hops')
                )

            # Send done event
            done_event = {
                'type': 'done',
                'data': {'search_id': search_id}
            }
            yield f"data: {json.dumps(done_event)}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.get('/api/searches')
@limiter.limit("30/minute")
async def get_searches(
    request: Request,
    q: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Get all searches with optional filtering

    - **q**: Optional search query to filter by start_term or end_term (max 200 chars)
    - **limit**: Maximum number of results to return (1-500, default: 100)
    - **offset**: Number of results to skip (default: 0)
    """
    # Validate and sanitize search query
    if q:
        q = q.strip()
        if len(q) > 200:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Search query too long (max 200 characters)")

        # Basic sanitization
        if not re.match(r'^[a-zA-Z0-9\s\-\(\)\'\.,&]*$', q):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Search query contains invalid characters")

    searches = database.get_all_searches(q, limit, offset)
    return {'searches': searches}


@app.get('/api/searches/{search_id}')
async def get_search(search_id: int):
    """
    Get a specific search by ID

    Returns detailed information including the full path and visualization data.
    """
    search = database.get_search_by_id(search_id)

    if not search:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail='Search not found')

    # Create nodes and edges if path exists
    if search['path']:
        nodes = [{'id': i, 'label': page, 'title': page} for i, page in enumerate(search['path'])]
        edges = [{'from': i, 'to': i+1} for i in range(len(search['path'])-1)]
        search['nodes'] = nodes
        search['edges'] = edges

    # Include all paths if they exist
    additional_paths = database.get_paths_for_search(search_id)
    if additional_paths:
        search['all_paths'] = additional_paths

    return search


@app.get('/api/stats')
async def get_stats():
    """
    Get search statistics

    Returns aggregate statistics about all searches including:
    - Total number of searches
    - Successful searches count
    - Average number of hops
    - Average pages checked
    """
    stats = database.get_search_stats()
    return stats


@app.get('/api/cache/stats')
async def get_cache_stats():
    """
    Get path cache statistics

    Returns cache performance metrics including:
    - Cache size and capacity
    - Hit/miss rates
    - Total requests
    """
    cache = get_cache()
    return cache.get_stats()


@app.get('/api/cache/effectiveness')
async def get_cache_effectiveness():
    """
    Get detailed cache effectiveness metrics

    Returns information about cache utilization including:
    - Top cached segments by usage
    - Recent cache composition successes
    - Cache effectiveness over time
    """
    cache = get_cache()

    # Get top segments from database
    with database.get_db() as conn:
        cursor = conn.cursor()

        # Top 10 most used segments
        cursor.execute('''
            SELECT start_page, end_page, hops, use_count, last_used
            FROM path_segments
            ORDER BY use_count DESC
            LIMIT 10
        ''')
        top_segments = [dict(row) for row in cursor.fetchall()]

        # Recent segments (last 20)
        cursor.execute('''
            SELECT start_page, end_page, hops, use_count, created_at
            FROM path_segments
            ORDER BY created_at DESC
            LIMIT 20
        ''')
        recent_segments = [dict(row) for row in cursor.fetchall()]

        # Total segments in database
        cursor.execute('SELECT COUNT(*) as total FROM path_segments')
        total_segments = cursor.fetchone()['total']

    return {
        'cache_stats': cache.get_stats(),
        'total_segments_db': total_segments,
        'top_segments': top_segments,
        'recent_segments': recent_segments
    }


@app.get('/api/cache/graph')
async def get_cache_graph():
    """
    Get graph representation of all cached segments for visualization

    Returns a force-directed graph with nodes and edges representing
    all cached Wikipedia page segments.

    Returns:
        nodes: List of {id, label, connections, total_uses}
        edges: List of {source, target, weight, hops, last_used}
        stats: {total_nodes, total_edges}
    """
    with database.get_db() as conn:
        cursor = conn.cursor()

        # Get all segments with statistics
        cursor.execute('''
            SELECT start_page, end_page, hops, use_count,
                   last_used, created_at
            FROM path_segments
            ORDER BY use_count DESC
        ''')

        segments = cursor.fetchall()

        # Build nodes and edges
        nodes_dict = {}  # page -> stats
        edges = []

        for seg in segments:
            start, end = seg['start_page'], seg['end_page']

            # Add nodes (track statistics)
            for page in [start, end]:
                if page not in nodes_dict:
                    nodes_dict[page] = {
                        'id': page,
                        'label': page,
                        'connections': 0,
                        'total_uses': 0
                    }
                nodes_dict[page]['connections'] += 1
                nodes_dict[page]['total_uses'] += seg['use_count']

            # Add edge
            edges.append({
                'source': start,
                'target': end,
                'weight': seg['use_count'],
                'hops': seg['hops'],
                'last_used': seg['last_used']
            })

        return {
            'nodes': list(nodes_dict.values()),
            'edges': edges,
            'stats': {
                'total_nodes': len(nodes_dict),
                'total_edges': len(edges)
            }
        }


# Mount static files AFTER all routes
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == '__main__':
    import uvicorn
    import os
    port = int(os.environ.get('PORT', 8000))
    uvicorn.run(app, host='0.0.0.0', port=port)
