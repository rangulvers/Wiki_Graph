# Wikipedia Connection Finder

A modern, high-performance web application that finds the shortest path between any two Wikipedia topics using an optimized bidirectional BFS algorithm with real-time streaming updates.

🔗 **Live Demo**: [https://wikigraph.up.railway.app](https://wikigraph.up.railway.app)

<img width="1295" height="1154" alt="image" src="https://github.com/user-attachments/assets/54e78793-5a13-4d52-87a1-921a44c43631" />


## ✨ Features

### Core Functionality
- **⚡ Bidirectional BFS Algorithm**: 5-10x faster than traditional BFS by searching from both ends simultaneously
- **🌐 Multi-Path Discovery**: Finds up to 3 diverse paths between topics, showing alternative connections
- **📊 Merged Graph Visualization**: All paths displayed simultaneously in an interactive graph with shared nodes
- **📡 Real-time Streaming**: Live progress updates using Server-Sent Events (SSE)
- **🎨 Beautiful Animations**: Particle convergence effects with simultaneous edge reveal animations
- **✨ Interactive Canvas**: Click nodes to visit Wikipedia, hover for details, switch between discovered paths
- **🔍 Smart Autocomplete**: Wikipedia article suggestions as you type
- **📚 Search History**: Persistent storage of all searches with filtering capabilities
- **🎯 Path Highlighting**: Select any path to highlight its nodes and edges in the graph

### Technical Features
- **Async Architecture**: Built with FastAPI and httpx for high concurrency
- **Connection Pooling**: Shared HTTP client for efficient Wikipedia API requests
- **Path Diversity Algorithm**: Jaccard distance-based filtering ensures distinct alternative paths
- **Intelligent Graph Layout**: Left-to-right flow with depth-based positioning and alphabetical sorting
- **Path Segment Caching**: LRU cache for frequently-used connections with database persistence
- **Retry Logic**: Exponential backoff for transient failures
- **Rate Limiting**: Prevents abuse with configurable per-endpoint limits
- **Input Validation**: Comprehensive sanitization and validation using Pydantic
- **Production Ready**: SQLite WAL mode, structured logging, proper error handling

## 🚀 How It Works

1. **Enter Search Terms**: Type two Wikipedia topics (e.g., "Harry Potter" → "NBA")
2. **Live Search Visualization**: Watch particles radiate from start/end nodes as the algorithm explores
3. **Multi-Path Discovery**: Algorithm finds up to 3 diverse paths, streaming each discovery in real-time
4. **Graph Materialization**: Particles converge into nodes, edges reveal simultaneously across all paths
5. **Interactive Exploration**: Click path selector buttons to highlight different routes, hover nodes for details

### Algorithm Details

**Bidirectional BFS with Multi-Path Discovery**:
- Searches forward from start (outbound links) and backward from end (backlinks) simultaneously
- Discovers multiple meeting points as search progresses
- **Diversity filtering**: Uses Jaccard distance to ensure paths are at least 30% different
- **Early termination**: Stops when depth exceeds shortest path + 2 hops
- **Graph merging**: Deduplicates nodes and tracks edge usage across all paths
- Result: 3 diverse paths with 5-10x better performance than unidirectional search

### Visualization Features

**Particle Animation System**:
- **SEARCHING phase**: Particles radiate from start/end nodes during bidirectional search
- **CONVERGING phase**: All particles attracted to discovered path nodes
- **REVEALING phase**: Simultaneous edge animation with beam particles
- **COMPLETE phase**: Flowing lights travel along connections

**Graph Layout**:
- Start node always positioned at left edge
- End node always positioned at right edge
- Intermediate nodes arranged in columns by depth from start
- Nodes within same column sorted alphabetically
- Edge thickness indicates usage (thicker = more paths use this connection)

## 📦 Installation

### Prerequisites
- Python 3.9+
- pip

### Local Development

1. **Clone the repository**:
```bash
git clone https://github.com/yourusername/wikipedia-path-finder.git
cd wikipedia-path-finder
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Run the application**:
```bash
python app.py
```

4. **Open your browser**:
```
http://localhost:8000
```

## 🌐 Deployment

### Railway Deployment

This app is configured for easy deployment on Railway:

1. **Push to GitHub** and connect to Railway
2. **Environment automatically detected** via `railway.json` and `Procfile`
3. **Auto-scaling** with uvicorn workers

The app will automatically:
- Install dependencies from `requirements.txt`
- Initialize SQLite database with WAL mode
- Bind to Railway's provided `$PORT`
- Use 2 uvicorn workers for concurrency

### Manual Deployment

For other platforms, use:
```bash
uvicorn app:app --host 0.0.0.0 --port $PORT --workers 2
```

## 🛠️ Technical Stack

### Backend
- **FastAPI** - Modern async web framework
- **Pydantic** - Data validation and settings management
- **httpx** - Async HTTP client with connection pooling
- **SQLite** - Database with WAL mode for concurrent writes
- **Uvicorn** - ASGI server with multiple workers

### Frontend
- **Modular ES6 JavaScript** - Clean architecture with separate modules
- **Canvas API** - High-performance particle animations and graph rendering
- **Server-Sent Events (SSE)** - Real-time progress streaming
- **PathNode Class** - Object-oriented node rendering with hover/highlight states

### Wikipedia Integration
- **Wikipedia API** - Fetches page links and backlinks
- **OpenSearch API** - Autocomplete suggestions
- **Rate limiting** - Respects Wikipedia's rate limits

## ⚙️ Configuration

### Search Parameters

Adjust in `app.py`:
```python
# Multi-path search configuration
paths = await finder.find_k_paths_bidirectional(
    start_term,
    end_term,
    max_paths=3,        # Number of diverse paths to find (1-5)
    min_diversity=0.3   # Minimum Jaccard distance between paths (0-1)
)

# Max search depth
async with WikipediaPathFinder(max_depth=6) as finder:
    # max_depth: Maximum search depth (default: 6)
    # Higher = finds more distant connections but slower
    # Lower = faster but may miss connections
```

### Rate Limits

Configure in `app.py`:
```python
@limiter.limit("5/minute")  # Streaming search endpoint
@limiter.limit("10/minute") # Non-streaming endpoint
@limiter.limit("30/minute") # API endpoints
```

### CORS Origins

Update allowed origins in `app.py`:
```python
allow_origins=[
    "http://localhost:8000",
    "https://your-domain.com"
]
```

## 📊 API Documentation

### Endpoints

#### `POST /find-path-stream`
Real-time streaming search with SSE updates and multi-path discovery.

**Request**:
```json
{
  "start": "Harry Potter",
  "end": "NBA",
  "max_paths": 3,
  "min_diversity": 0.3
}
```

**Response**: Server-Sent Events stream
- `start` - Search initiated
- `resolving` - Resolving article titles
- `resolved` - Titles resolved
- `progress` - Live search progress (forward_depth, backward_depth, pages_checked, pages_per_second)
- `path_found` - Individual path discovered (streaming multiple times)
- `complete` - All paths found with merged graph data
- `error` - Search failed

#### `POST /find-path`
Non-streaming search (returns complete result).

#### `GET /api/searches?q=term&limit=100&offset=0`
Get search history with optional filtering.

#### `GET /api/searches/{id}`
Get specific search by ID with all discovered paths.

#### `GET /api/stats`
Get aggregate statistics.

#### `GET /api/cache/stats`
Get path segment cache statistics (hit rate, size, performance metrics).

Full interactive docs available at `/docs` when running locally.

## 🎮 Usage Examples

### Interesting Connections to Try

- **"Barack Obama" → "Pizza"** - Politics to food
- **"Python (programming language)" → "Ancient Rome"** - Tech to history
- **"Quantum mechanics" → "Taylor Swift"** - Science to pop culture
- **"DNA" → "Video game"** - Biology to entertainment
- **"Mount Everest" → "iPhone"** - Geography to technology

### Search Tips

1. **Be specific**: Use exact Wikipedia article titles when possible
2. **Use autocomplete**: Select from suggestions for best results
3. **Explore alternatives**: Click path selector buttons to see different routes between topics
4. **Check history**: Someone may have already found your path
5. **Popular pages**: Connecting through highly-linked pages (e.g., "United States", "World War II") often works well
6. **Edge thickness**: Thicker edges indicate connections used by multiple paths

## 🔒 Security Features

- **Rate Limiting**: Prevents API abuse (slowapi)
- **Input Validation**: Sanitizes all user input (Pydantic validators)
- **SQL Injection Protection**: Parameterized queries
- **XSS Prevention**: Input sanitization and safe rendering
- **CORS Restrictions**: Limited to approved origins

## 🏗️ Project Structure

```
wikipedia-path-finder/
├── app.py                      # FastAPI application and core logic
├── models.py                   # Pydantic models and validation
├── database.py                 # SQLite operations with WAL mode
├── path_cache.py               # LRU cache for path segments
├── requirements.txt            # Python dependencies
├── Procfile                    # Railway/Heroku deployment config
├── railway.json                # Railway-specific configuration
├── MULTIPATH_IMPLEMENTATION.md # Detailed multi-path documentation
├── templates/
│   └── index.html              # Main HTML template
└── static/
    ├── css/
    │   └── style.css           # Styles and animations
    └── js/
        └── modules/
            ├── SearchParticles.js  # Canvas particle animation system
            ├── PathNode.js          # Node rendering with interactions
            ├── searchApi.js         # SSE handling and graph building
            ├── historyManager.js    # Search history UI
            └── utils.js             # Shared utilities
```

## 📈 Performance Characteristics

- **Average search time**: 2-5 seconds for 3-4 hop paths (single path), 3-8 seconds (multi-path)
- **Pages checked**: ~50-500 pages depending on connection
- **Success rate**: ~95% within 6 hops (most Wikipedia pages are connected)
- **Path diversity**: ~85% of searches find 2+ distinct paths
- **Cache hit rate**: 40-60% after warm-up (for repeated/overlapping searches)
- **Concurrent users**: Supports 50+ simultaneous searches
- **API response time**: <100ms for history queries
- **Graph rendering**: 60 FPS particle animations on modern browsers

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

- [x] ~~Multi-path discovery and visualization~~ ✅ Completed
- [x] ~~Graph visualization with merged paths~~ ✅ Completed
- [x] ~~Path segment caching~~ ✅ Completed
- [ ] Cache-aware search (check cache before BFS)
- [ ] Path composition from cached segments
- [ ] Add PostgreSQL option for higher scale
- [ ] Dark mode toggle
- [ ] Export results as JSON/image/SVG
- [ ] Statistics dashboard with cache metrics
- [ ] Mobile-optimized touch interactions

## 📝 License

MIT License - feel free to use this project for learning or commercial purposes.

## 🙏 Acknowledgments

- Wikipedia API for providing free access to their data
- FastAPI team for the excellent async framework
- Railway for easy deployment platform

## 🐛 Known Issues

- Very obscure Wikipedia pages may not have many connections
- Search may timeout for extremely distant topics (>8 hops)
- Mobile UI could be improved for smaller screens
- Graph layout with many nodes at same depth can become crowded
- Path diversity depends on connection structure (hub pages reduce diversity)

## 📧 Contact

Questions or suggestions? Open an issue on GitHub!

---

**Built with ❤️ using FastAPI and modern web technologies**
