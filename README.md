# Wikipedia Connection Finder

A modern web application that finds the shortest path between any two Wikipedia topics using intelligent cache-aware pathfinding with bidirectional BFS and real-time streaming updates.

🔗 **Live Demo**: [https://wikigraph.up.railway.app](https://wikigraph.up.railway.app)

<img width="1616" height="1191" alt="image" src="https://github.com/user-attachments/assets/b53905c6-ccc6-4427-a1ad-052732e2390f" />


## ✨ Features

### Core Search
- **🧠 Cache-Aware Pathfinding**: Intelligent system that reuses path segments from previous searches
- **⚡ Bidirectional BFS**: 5-10x faster than traditional search with Wikipedia API optimization
- **🌐 Multi-Path Discovery**: Finds up to 3 diverse paths between topics with configurable diversity
- **📡 Real-time Updates**: Live progress streaming using Server-Sent Events (SSE)
- **✅ Path Validation**: Ensures all discovered paths are valid and exist on Wikipedia

### Visualization & UI
- **🕸️ Knowledge Graph**: Interactive D3.js force-directed graph showing all cached segments
  - Nodes sized by connections, colored by usage frequency (hot/cold gradient)
  - Drag nodes, zoom, pan, and hover for statistics
  - Reset layout to re-spread clustered nodes
- **📊 Interactive Search Results**: Canvas-based visualization with clickable nodes
- **🎨 Particle Animations**: Beautiful convergence and path reveal effects
- **🎯 Modern Glass-Morphism UI**: Cyan-accented dark theme with smooth transitions
- **📤 Social Media Sharing**: One-click sharing with auto-generated screenshots
  - Native share dialog on mobile (iOS/Android)
  - Auto-generated share text with stats
  - Branded watermark on screenshots
  - Multi-platform clipboard support

### Smart Features
- **💾 LRU Path Cache**: In-memory + SQLite persistence with 10,000 segment capacity
- **🔍 Smart Autocomplete**: Wikipedia suggestions as you type
- **📚 Collapsible Search History**: Persistent storage with filtering (collapsed by default)
- **📈 Global Statistics**: Track total searches, success rate, average hops, and pages checked

## 🚀 Quick Start

```bash
# Clone and install
git clone https://github.com/rangulvers/Wiki_Graph.git
cd Wiki_Graph
pip install -r requirements.txt

# Run locally
python app.py

# Open browser at http://localhost:8000
```

## 🛠️ Tech Stack

**Backend**:
- FastAPI (async web framework)
- SQLite with WAL mode (persistent storage for searches and cache)
- httpx AsyncClient (HTTP/2 connection pooling for Wikipedia API)
- Pydantic (data validation)

**Frontend**:
- Vanilla JavaScript (ES6 modules)
- D3.js v7 (force-directed graph visualization)
- Canvas API (search visualization & animations)
- Server-Sent Events (real-time updates)
- html2canvas (screenshot capture for sharing)
- Web Share API (native mobile sharing)

**Architecture**:
- LRU cache with database persistence
- Bidirectional BFS with edge validation
- Bulk database operations for performance
- Rate limiting (SlowAPI)

**Deployment**: Railway-ready with auto-scaling

## 🎮 Try These Connections

- **"Barack Obama" → "Pizza"**
- **"Python (programming language)" → "Ancient Rome"**
- **"Quantum mechanics" → "Taylor Swift"**
- **"DNA" → "Video game"**

## 📈 Performance

- **Cache Hits**: Direct hits < 100ms, composed paths < 500ms
- **BFS Search**: 2-8 seconds average (5-10x faster than traditional BFS)
- **Success Rate**: ~95% within 6 hops
- **Concurrent Users**: 50+ simultaneous searches
- **Connection Pooling**: HTTP/2 with 500 max connections, 100 keepalive
- **Database**: SQLite WAL mode with 20s timeout for concurrency
- **Animations**: 60 FPS on modern browsers

## 🧠 How the Cache Works

The cache-aware pathfinding system dramatically speeds up searches:

1. **Segment Caching**: Every discovered path is broken into sub-segments and cached
2. **Cache Composition**: Before running BFS, the system tries to compose a path from cached segments
3. **Validation**: All composed paths are validated to ensure edges still exist on Wikipedia
4. **LRU Eviction**: In-memory cache (10,000 segments) with database persistence
5. **Knowledge Graph**: Visualize the growing network of discovered connections

**Example**: After finding "Harry Potter → Laptop", future searches can reuse segments like "Harry Potter → Alfonso Cuarón" or "Apple Inc. → Laptop"

## 📤 Social Media Sharing

Share your discoveries with a single click! The sharing feature captures your complete path visualization and generates ready-to-post content.

### Features
- **📸 Auto Screenshot**: Captures canvas with all paths, stats, and branded watermark
- **📱 Native Sharing**:
  - Mobile: Opens native share sheet (Twitter, LinkedIn, Messages, etc.)
  - Desktop: Downloads image + copies text to clipboard
- **✍️ Smart Text Generation**: Auto-creates share text with stats
  - Example: *"I found 3 paths between 'NBA' and 'Taylor Swift' on Wikipedia! 4 hops, 156 pages checked. Check it out at https://wikigraph.up.railway.app"*
- **🔄 Multi-Platform Support**:
  - Web Share API for mobile devices
  - Clipboard API with legacy fallback
  - Modal popup if clipboard fails
- **🎨 Branded Watermark**: Subtle "wikigraph.up.railway.app" branding on screenshots

### How to Use
1. Run a search and view results
2. Click the **Share** button in the top-right of the stats overlay
3. On mobile: Select your preferred app from the share sheet
4. On desktop: Image downloads and text copies to clipboard
5. Post to social media with your screenshot and caption!

## 🌐 Deployment

Push to GitHub and connect to Railway - auto-deployment configured via `railway.json` and `Procfile`.

The app uses Railway's persistent `/data` directory for SQLite database storage, ensuring cached segments survive deployments.

## 🗂️ Project Structure

```
Wiki_Graph/
├── app/
│   ├── main.py              # Main FastAPI application
│   ├── database.py          # SQLite operations (searches, cache)
│   ├── cache.py             # LRU cache with DB persistence
│   ├── models.py            # Pydantic models
│   ├── config.py            # Configuration management
│   └── utils.py             # Helper functions
├── static/
│   ├── css/style.css        # Modern glass-morphism UI
│   ├── images/              # Icons and assets
│   └── js/
│       ├── graphView.js     # D3.js knowledge graph
│       └── modules/         # ES6 modules
│           ├── main.js              # Entry point
│           ├── searchApi.js         # Search orchestration & SSE
│           ├── shareManager.js      # Social media sharing
│           ├── SearchParticles.js   # Canvas animations
│           ├── PathNode.js          # Node rendering
│           ├── autocomplete.js      # Wikipedia suggestions
│           ├── historyManager.js    # Search history
│           ├── statsManager.js      # Statistics display
│           └── utils.js             # Shared utilities
├── templates/
│   ├── index.html           # Landing/about page
│   └── search.html          # Search application
├── tests/                   # Test suite
├── docs/                    # Documentation
└── data/
    └── wikipedia_searches.db  # SQLite database (persistent)
```

## 🎯 API Endpoints

- `GET /` - Main application
- `POST /find-path` - Non-streaming search
- `POST /find-path-stream` - SSE streaming search
- `GET /api/searches` - Search history with filtering
- `GET /api/searches/{id}` - Individual search details
- `GET /api/stats` - Global statistics
- `GET /api/cache/stats` - Cache performance metrics
- `GET /api/cache/graph` - Knowledge graph data (nodes & edges)
- `GET /api/cache/effectiveness` - Cache utilization details

## 📝 License

MIT License - Free for personal and commercial use.

---

**Built with ❤️ and just for fun** | [GitHub Repository](https://github.com/rangulvers/Wiki_Graph)
