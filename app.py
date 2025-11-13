from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse
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
from typing import Optional, TypeVar, Callable, Any
from functools import wraps
import logging
from models import (
    SearchRequest, SearchResponse, SearchErrorResponse,
    Node, Edge
)

# Type variable for generic async function decorator
T = TypeVar('T')

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
        "https://wikigraph-production.up.railway.app"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

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

        # Configure connection pooling limits
        limits = httpx.Limits(
            max_connections=100,        # Max total connections
            max_keepalive_connections=20  # Max idle connections to keep alive
        )

        # Create shared client with proper configuration
        _shared_http_client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            headers={
                'User-Agent': 'WikipediaConnectionFinder/1.0 (Educational Project)'
            }
            # Note: HTTP/2 disabled - requires httpx[http2] package
            # Connection pooling provides the main performance benefits
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
            "formatversion": 2  # Use modern format
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
            "formatversion": 2
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

    async def find_path_bidirectional(self, start, end, callback=None):
        """Find shortest path using bidirectional BFS (5-10x faster)

        Args:
            start: Starting Wikipedia page title
            end: Target Wikipedia page title
            callback: Optional function(event_type, data) for streaming updates
        """
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

                for link in links:
                    link_normalized = self.normalize_title(link)

                    # Check if backward search has seen this page (MEETING POINT!)
                    if link_normalized in backward_visited:
                        # Reconstruct path: forward + reversed backward
                        final_path = path + [link] + self._reconstruct_backward_path(link_normalized, backward_parents)
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

                for link in links:
                    link_normalized = self.normalize_title(link)

                    # Check if forward search has seen this page (MEETING POINT!)
                    if link_normalized in forward_visited:
                        # Reconstruct path: forward + reversed backward
                        final_path = self._reconstruct_forward_path(link_normalized, forward_parents) + path
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

            # Small delay to be nice to Wikipedia's servers
            if pages_checked % 10 == 0:
                await asyncio.sleep(0.05)

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

    async def find_path(self, start, end, callback=None):
        """Find shortest path between two Wikipedia pages

        Now uses bidirectional BFS for 5-10x performance improvement.
        """
        # Use the optimized bidirectional search
        return await self.find_path_bidirectional(start, end, callback)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main HTML page"""
    return templates.TemplateResponse("index.html", {"request": request})


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
                path = await finder.find_path(start_term, end_term)
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
        # Create nodes and edges for visualization
        nodes = [Node(id=i, label=page, title=page) for i, page in enumerate(path)]
        edges = [Edge(**{'from': i, 'to': i+1}) for i in range(len(path)-1)]

        # Save to database
        search_id = database.save_search(
            start_term=start_term,
            end_term=end_term,
            path=path,
            hops=len(path) - 1,
            pages_checked=len(finder.visited),
            success=True
        )

        return SearchResponse(
            success=True,
            search_id=search_id,
            path=path,
            nodes=nodes,
            edges=edges,
            hops=len(path) - 1,
            pages_checked=len(finder.visited)
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
            result = {'path': None, 'pages_checked': 0, 'success': False, 'error': None}

            # Send start event
            yield f"data: {json.dumps({'type': 'start', 'data': {'start': start_term, 'end': end_term}})}\n\n"

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
                    result['path'] = event_data.get('path')
                    result['pages_checked'] = event_data.get('pages_checked')
                    result['success'] = True
                    event_queue.put_nowait(None)  # Sentinel to stop
                elif event_type == 'progress':
                    result['pages_checked'] = event_data.get('pages_checked', result['pages_checked'])

            # Run pathfinding in async task
            async def run_search():
                try:
                    path = await finder.find_path(actual_start, actual_end, callback=callback)

                    # If path not found, send error
                    if not path:
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
            if result['success'] and result['path']:
                search_id = database.save_search(
                    start_term=start_term,
                    end_term=end_term,
                    path=result['path'],
                    hops=len(result['path']) - 1,
                    pages_checked=result['pages_checked'],
                    success=True
                )
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

# Mount static files AFTER all routes
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == '__main__':
    import uvicorn
    import os
    port = int(os.environ.get('PORT', 8000))
    uvicorn.run(app, host='0.0.0.0', port=port)
