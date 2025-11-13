from flask import Flask, render_template, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import requests
from collections import deque
from urllib.parse import unquote
import time
import json
import database
from queue import Queue, Empty
import threading

app = Flask(__name__)
CORS(app)

# Initialize database on startup
database.init_db()

class WikipediaPathFinder:
    def __init__(self, max_depth=6):
        self.max_depth = max_depth
        self.visited = set()
        self.session = requests.Session()
        # Wikipedia requires a User-Agent
        self.session.headers.update({
            'User-Agent': 'WikipediaConnectionFinder/1.0 (Educational Project)'
        })

    def get_wikipedia_links(self, page_title):
        """Get all links from a Wikipedia page (forward direction)"""
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
            response = self.session.get(url, params=params, timeout=10)
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

        except requests.exceptions.RequestException as e:
            print(f"Request error fetching links for {page_title}: {e}")
            return []
        except ValueError as e:
            print(f"JSON parsing error for {page_title}: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error fetching links for {page_title}: {e}")
            return []

    def get_wikipedia_backlinks(self, page_title, limit=500):
        """Get all pages that link TO a Wikipedia page (backward direction)"""
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
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            backlinks = data.get("query", {}).get("backlinks", [])

            # For popular pages with 1000+ backlinks, limit to avoid slowdown
            if len(backlinks) >= 500:
                print(f"Page '{page_title}' has many backlinks, limiting to {limit}")

            return [link["title"] for link in backlinks[:limit]]

        except requests.exceptions.RequestException as e:
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

    def resolve_wikipedia_title(self, search_term):
        """Resolve a search term to an actual Wikipedia article title using search API"""
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "opensearch",
            "search": search_term,
            "limit": 1,
            "namespace": 0,
            "format": "json"
        }

        try:
            response = self.session.get(url, params=params, timeout=10)
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

        except requests.exceptions.RequestException as e:
            print(f"Request error resolving '{search_term}': {e}")
            return None
        except Exception as e:
            print(f"Unexpected error resolving '{search_term}': {e}")
            return None

    def find_path_bidirectional(self, start, end, callback=None):
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
                links = self.get_wikipedia_links(current_page)

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
                links = self.get_wikipedia_backlinks(current_page, limit=300)

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
                time.sleep(0.05)

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

    def find_path(self, start, end, callback=None):
        """Find shortest path between two Wikipedia pages

        Now uses bidirectional BFS for 5-10x performance improvement.
        """
        # Use the optimized bidirectional search
        return self.find_path_bidirectional(start, end, callback)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/find-path', methods=['POST'])
def find_path():
    data = request.json
    start_term = data.get('start', '').strip()
    end_term = data.get('end', '').strip()

    if not start_term or not end_term:
        return jsonify({'error': 'Both search terms are required'}), 400

    print(f"Finding path from '{start_term}' to '{end_term}'")

    finder = WikipediaPathFinder(max_depth=6)
    path = finder.find_path(start_term, end_term)

    if path:
        # Create nodes and edges for visualization
        nodes = [{'id': i, 'label': page, 'title': page} for i, page in enumerate(path)]
        edges = [{'from': i, 'to': i+1} for i in range(len(path)-1)]

        # Save to database
        search_id = database.save_search(
            start_term=start_term,
            end_term=end_term,
            path=path,
            hops=len(path) - 1,
            pages_checked=len(finder.visited),
            success=True
        )

        return jsonify({
            'success': True,
            'search_id': search_id,
            'path': path,
            'nodes': nodes,
            'edges': edges,
            'hops': len(path) - 1,
            'pages_checked': len(finder.visited)
        })
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

        return jsonify({
            'success': False,
            'search_id': search_id,
            'error': error_msg,
            'pages_checked': len(finder.visited)
        })

@app.route('/find-path-stream', methods=['POST'])
def find_path_stream():
    """Stream BFS exploration in real-time using Server-Sent Events"""
    data = request.json
    start_term = data.get('start', '').strip()
    end_term = data.get('end', '').strip()

    if not start_term or not end_term:
        def error_generator():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Both search terms are required'})}\n\n"
        return Response(error_generator(), mimetype='text/event-stream')

    print(f"Streaming path search from '{start_term}' to '{end_term}'")

    def generate_events():
        """Generator function that yields SSE events in real-time"""
        finder = WikipediaPathFinder(max_depth=6)
        event_queue = Queue()
        result = {'path': None, 'pages_checked': 0, 'success': False, 'error': None}

        # Send start event
        yield f"data: {json.dumps({'type': 'start', 'data': {'start': start_term, 'end': end_term}})}\n\n"

        # Resolve search terms to actual Wikipedia article titles
        yield f"data: {json.dumps({'type': 'resolving', 'data': {'message': 'Resolving search terms...'}})}\n\n"

        resolved_start = finder.resolve_wikipedia_title(start_term)
        resolved_end = finder.resolve_wikipedia_title(end_term)

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
            # Put event in queue immediately
            event_queue.put({'type': event_type, 'data': event_data})

            # Store result data for database
            if event_type == 'complete':
                result['path'] = event_data.get('path')
                result['pages_checked'] = event_data.get('pages_checked')
                result['success'] = True
                event_queue.put(None)  # Sentinel to stop
            elif event_type == 'progress':
                result['pages_checked'] = event_data.get('pages_checked', result['pages_checked'])

        # Run pathfinding in separate thread so we can yield events concurrently
        def run_search():
            try:
                path = finder.find_path(actual_start, actual_end, callback=callback)

                # If path not found, send error
                if not path:
                    error_event = {
                        'type': 'error',
                        'data': {
                            'message': f'No path found within {finder.max_depth} hops',
                            'pages_checked': len(finder.visited)
                        }
                    }
                    event_queue.put(error_event)
                    result['pages_checked'] = len(finder.visited)
                    result['error'] = error_event['data']['message']
                    event_queue.put(None)  # Sentinel
            except Exception as e:
                error_event = {
                    'type': 'error',
                    'data': {'message': str(e)}
                }
                event_queue.put(error_event)
                result['error'] = str(e)
                event_queue.put(None)  # Sentinel

        search_thread = threading.Thread(target=run_search)
        search_thread.start()

        # Yield events as they arrive in the queue
        while True:
            try:
                event = event_queue.get(timeout=30)  # 30 second timeout for keepalive
                if event is None:  # Sentinel - search is done
                    break
                # Yield event immediately
                yield f"data: {json.dumps(event)}\n\n"
            except Empty:
                # Send keepalive to prevent connection timeout
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

        # Wait for search thread to complete
        search_thread.join()

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
                error_message=result.get('error', f'No path found within {finder.max_depth} hops')
            )

        # Send done event
        done_event = {
            'type': 'done',
            'data': {'search_id': search_id}
        }
        yield f"data: {json.dumps(done_event)}\n\n"

    response = Response(stream_with_context(generate_events()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
    return response

@app.route('/api/searches', methods=['GET'])
def get_searches():
    """Get all searches with optional filtering"""
    search_query = request.args.get('q', None)
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))

    searches = database.get_all_searches(search_query, limit, offset)
    return jsonify({'searches': searches})

@app.route('/api/searches/<int:search_id>', methods=['GET'])
def get_search(search_id):
    """Get a specific search by ID"""
    search = database.get_search_by_id(search_id)

    if not search:
        return jsonify({'error': 'Search not found'}), 404

    # Create nodes and edges if path exists
    if search['path']:
        nodes = [{'id': i, 'label': page, 'title': page} for i, page in enumerate(search['path'])]
        edges = [{'from': i, 'to': i+1} for i in range(len(search['path'])-1)]
        search['nodes'] = nodes
        search['edges'] = edges

    return jsonify(search)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get search statistics"""
    stats = database.get_search_stats()
    return jsonify(stats)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
