# Wikipedia Connection Finder

A modern web application that finds the shortest path between any two Wikipedia topics using bidirectional BFS with real-time streaming updates.

🔗 **Live Demo**: [https://wikigraph.up.railway.app](https://wikigraph.up.railway.app)

<img width="1616" height="1191" alt="image" src="https://github.com/user-attachments/assets/b53905c6-ccc6-4427-a1ad-052732e2390f" />


## ✨ Features

- **⚡ Bidirectional BFS**: 5-10x faster than traditional search
- **🌐 Multi-Path Discovery**: Finds up to 3 diverse paths between topics
- **📊 Interactive Graph**: Merged visualization with clickable nodes
- **📡 Real-time Updates**: Live progress using Server-Sent Events
- **🎨 Particle Animations**: Beautiful convergence and path reveal effects
- **🔍 Smart Autocomplete**: Wikipedia suggestions as you type
- **📚 Search History**: Persistent storage with filtering

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

**Backend**: FastAPI, SQLite, httpx async client
**Frontend**: Vanilla JavaScript (ES6 modules), Canvas API, SSE
**Deployment**: Railway-ready with auto-scaling

## 🎮 Try These Connections

- **"Barack Obama" → "Pizza"**
- **"Python (programming language)" → "Ancient Rome"**
- **"Quantum mechanics" → "Taylor Swift"**
- **"DNA" → "Video game"**

## 📈 Performance

- Average search: 2-8 seconds
- Success rate: ~95% within 6 hops
- Concurrent users: 50+ simultaneous searches
- 60 FPS animations on modern browsers

## 🌐 Deployment

Push to GitHub and connect to Railway - auto-deployment configured via `railway.json` and `Procfile`.

## 📝 License

MIT License - Free for personal and commercial use.

---

**Built with ❤️ and just for fun** | [GitHub Repository](https://github.com/rangulvers/Wiki_Graph)
