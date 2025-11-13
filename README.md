# Wikipedia Connection Finder

A web application that finds the shortest path between any two Wikipedia topics by following links from one page to another.

## Features

- **Intelligent Path Finding**: Uses Breadth-First Search (BFS) algorithm to find the shortest connection
- **Visual Graph Display**: Interactive network visualization using Vis.js
- **Real-time Search**: Searches through Wikipedia's extensive link network
- **Detailed Results**: Shows the complete path with clickable links to each Wikipedia page
- **Search History**: All searches are saved to SQLite database and visible to all users
- **Filter & Search**: Filter through search history with real-time search functionality
- **Clickable History**: Click any previous search to instantly view its results

## How It Works

1. Enter two search terms (e.g., "Harry Potter" and "NBA")
2. The algorithm starts from the first term's Wikipedia page
3. It explores all linked pages using BFS to find the shortest path
4. Results show the connection path with a beautiful graph visualization

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open your browser and navigate to:
```
http://localhost:5000
```

## Technical Details

- **Backend**: Python/Flask
- **Database**: SQLite for storing search history
- **Algorithm**: Breadth-First Search (BFS) for optimal shortest path
- **API**: Wikipedia API for fetching page links
- **Visualization**: Vis.js network graphs
- **Frontend**: HTML/CSS/JavaScript

## Configuration

You can adjust the search depth in `app.py`:
```python
finder = WikipediaPathFinder(max_depth=6)  # Adjust max_depth as needed
```

Higher values will search deeper but take longer. Lower values are faster but may miss connections.

## Examples

Try these interesting connections:
- "Barack Obama" → "Pizza"
- "Python (programming language)" → "Ancient Rome"
- "Harry Potter" → "NBA"
- "Quantum mechanics" → "Taylor Swift"

## Search History

All searches (both successful and failed) are automatically saved to a SQLite database (`wikipedia_searches.db`). The history section at the bottom of the page shows:

- All previous searches by all users
- Filter box to search for specific terms
- Click any history item to view its results
- Success/failure status with visual indicators
- Number of hops and pages checked for each search

## API Endpoints

- `GET /api/searches` - Get all searches (supports `?q=term` for filtering)
- `GET /api/searches/<id>` - Get a specific search by ID
- `GET /api/stats` - Get database statistics
- `POST /find-path` - Create a new search

## Notes

- The search respects Wikipedia's rate limits with built-in delays
- Some very distant topics may take a minute or two to connect
- If no path is found within the max depth, try increasing the depth limit
- All searches are persisted in the database for future reference
- The database file is automatically created on first run
