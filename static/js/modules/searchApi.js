/**
 * searchApi.js - Main search orchestration and SSE handling
 *
 * Handles the complete search workflow:
 * - Form validation and UI updates
 * - Server-Sent Events (SSE) streaming
 * - Live event processing
 * - Path animation transitions
 * - Results display
 */
import { SearchParticles } from './SearchParticles.js';
import { showElement, hideElement, showError, escapeHtml } from './utils.js';
import { loadSearchHistory } from './historyManager.js';

// Global search particles instance
export let searchParticles = null;

// Store all found paths
let allPaths = [];
let currentPathIndex = 0;
let mergedGraph = null;

export async function findConnection() {
    const startTerm = document.getElementById('start-term').value.trim();
    const endTerm = document.getElementById('end-term').value.trim();

    if (!startTerm || !endTerm) {
        showError('Please enter both search terms');
        return;
    }

    // Reset paths
    allPaths = [];
    currentPathIndex = 0;

    // Hide previous results/errors
    hideElement('results');
    hideElement('error');
    showElement('loading');

    // Clear previous resolved terms
    const previousResolved = document.querySelector('.resolved-terms');
    if (previousResolved) {
        previousResolved.remove();
    }

    // Reset stats display
    document.getElementById('live-forward-depth').textContent = '0';
    document.getElementById('live-backward-depth').textContent = '0';
    document.getElementById('live-depth').textContent = '0';
    document.getElementById('live-pages').textContent = '0';
    document.getElementById('live-speed').textContent = '0';
    document.querySelector('.search-title').textContent = 'Searching Wikipedia...';

    // Reset all visibility styles for status overlay (in case they were hidden from previous search)
    const liveStatus = document.getElementById('live-status');
    liveStatus.style.cssText = '';  // Clear all inline styles
    liveStatus.offsetHeight;  // Force reflow

    const searchTitle = document.querySelector('.search-title');
    searchTitle.style.cssText = '';  // Clear all inline styles
    searchTitle.offsetHeight;  // Force reflow

    const liveSearchOverlay = document.querySelector('.live-search-overlay');
    if (liveSearchOverlay) {
        liveSearchOverlay.style.cssText = '';  // Clear all inline styles
        liveSearchOverlay.offsetHeight;  // Force reflow
    }

    // Disable button
    const findBtn = document.getElementById('find-btn');
    findBtn.disabled = true;
    findBtn.textContent = 'Searching...';

    // Initialize particle animation
    if (!searchParticles) {
        searchParticles = new SearchParticles('live-search-canvas');
    }
    searchParticles.start();

    // Add initial particle burst
    searchParticles.addParticles(30);

    // Use fetch with SSE manually for POST requests
    try {
        const response = await fetch('/find-path-stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                start: startTerm,
                end: endTerm,
                max_paths: 3,
                min_diversity: 0.3
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalPath = null;

        while (true) {
            const { done, value } = await reader.read();

            if (done) {
                break;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const event = JSON.parse(line.substring(6));
                    const result = handleLiveEvent(event);
                    if (result && result.path) {
                        finalPath = result;
                    }
                }
            }
        }

        // Transition to full graph
        if (finalPath) {
            await transitionToGraph(finalPath);
        }

        // Don't hide loading div (contains canvas) - just hide the status overlay
        // hideElement('loading');  // REMOVED - canvas needs to stay visible
        findBtn.disabled = false;
        findBtn.textContent = 'Find Connection';

        loadSearchHistory();

    } catch (error) {
        hideElement('loading');
        showError('An error occurred. Please try again.');
        console.error('Error:', error);
        findBtn.disabled = false;
        findBtn.textContent = 'Find Connection';
        if (searchParticles) {
            searchParticles.stop();
        }
    }
}

function handleLiveEvent(event) {
    const { type, data } = event;

    switch (type) {
        case 'start':
            break;

        case 'resolving':
            // Show resolving message
            document.querySelector('.search-title').textContent = data.message;
            break;

        case 'resolved':
            // Show what we're actually searching for
            document.querySelector('.search-title').textContent = `Searching Wikipedia...`;

            // Update the status to show resolved terms
            const statusDiv = document.getElementById('live-status');
            const resolvedInfo = document.createElement('div');
            resolvedInfo.className = 'resolved-terms';
            resolvedInfo.style.cssText = 'margin-bottom: 15px; padding: 10px; background: rgba(29, 232, 247, 0.1); border-radius: 8px; font-size: 14px;';
            resolvedInfo.innerHTML = `
                <div style="color: #1DE8F7; margin-bottom: 5px;">
                    <strong>${data.start}</strong> → <strong>${data.end}</strong>
                </div>
            `;
            statusDiv.insertBefore(resolvedInfo, statusDiv.firstChild);
            break;

        case 'progress':
            // Update stats with bidirectional data
            document.getElementById('live-forward-depth').textContent = data.forward_depth || 0;
            document.getElementById('live-backward-depth').textContent = data.backward_depth || 0;
            document.getElementById('live-depth').textContent = data.depth;
            document.getElementById('live-pages').textContent = data.pages_checked;
            document.getElementById('live-speed').textContent = data.pages_per_second;

            // Update waves and add particles for both directions
            if (searchParticles) {
                searchParticles.updateWaves(data.forward_depth || 0, data.backward_depth || 0);
                searchParticles.addParticles(3, 'forward');
                searchParticles.addParticles(3, 'backward');
            }
            break;

        case 'path_found':
            // Store discovered path
            allPaths.push({
                path: data.path,
                hops: data.length,
                meeting_point: data.meeting_point
            });

            // Update UI to show paths found
            const pathsFoundText = allPaths.length > 1 ? ` (${allPaths.length} paths found)` : '';
            document.querySelector('.search-title').textContent = `Searching Wikipedia...${pathsFoundText}`;
            break;

        case 'complete':
            // Store the path if not already stored (single path mode)
            if (allPaths.length === 0 && data.path) {
                allPaths.push({
                    path: data.path,
                    hops: data.path.length - 1,
                    pages_checked: data.pages_checked
                });
            }

            // Fade out stats overlay
            const liveStatus = document.getElementById('live-status');
            liveStatus.style.transition = 'opacity 0.5s';
            liveStatus.style.opacity = '0';

            // Hide search title
            document.querySelector('.search-title').style.opacity = '0';

            // Skip single-path animation if we have multiple paths (go directly to graph)
            // Single-path buildPath() would overwrite node labels incorrectly
            // The graph animation will be triggered by transitionToGraph() instead

            // Return the path data for transition (after animation completes)
            return {
                path: allPaths[0]?.path || data.path,
                pages_checked: data.pages_checked
            };

        case 'error':
            hideElement('loading');
            showError(data.message);
            if (searchParticles) {
                searchParticles.stop();
            }
            break;

        case 'done':
            break;

        case 'keepalive':
            // Ignore keepalive events
            break;
    }

    return null;
}

async function transitionToGraph(data) {
    // Build merged graph from all paths
    mergedGraph = buildMergedGraph(allPaths);

    // Start the graph animation (convergence + connections)
    if (searchParticles) {
        searchParticles.buildGraphPath(mergedGraph, allPaths);
    }

    // Wait for complete animation sequence
    // Convergence: 2000ms + 500ms delay
    // All edges animate simultaneously: 800ms
    const convergenceTime = 2500;
    const connectionTime = 800; // All edges at once
    const animationDuration = convergenceTime + connectionTime + 500;

    await new Promise(resolve => setTimeout(resolve, animationDuration));

    // Keep canvas visible, show results overlay
    showElement('results');
    showElement('path-details-container');

    // Update stats
    document.getElementById('hops-count').textContent = data.path.length - 1;
    document.getElementById('pages-count').textContent = data.pages_checked;

    // Show path selector if multiple paths found
    if (allPaths.length > 1) {
        showPathSelector();
    }

    // Display path list
    displayPathList(data.path);
}

function showPathSelector() {
    // Create or update path selector UI
    let selector = document.getElementById('path-selector');
    if (!selector) {
        selector = document.createElement('div');
        selector.id = 'path-selector';
        selector.className = 'path-selector';

        const pathDetails = document.getElementById('path-details-container');
        pathDetails.insertBefore(selector, pathDetails.firstChild);
    }

    selector.innerHTML = `
        <div class="path-selector-header">
            <h4>Alternative Paths (${allPaths.length} found)</h4>
        </div>
        <div class="path-selector-buttons">
            ${allPaths.map((pathData, index) => `
                <button
                    class="path-button ${index === currentPathIndex ? 'active' : ''}"
                    data-path-index="${index}"
                    onclick="window.switchToPath(${index})"
                >
                    <div class="path-button-label">Path ${index + 1}</div>
                    <div class="path-button-hops">${pathData.hops} hops</div>
                </button>
            `).join('')}
        </div>
    `;
}

// Export function to switch paths
window.switchToPath = function(index) {
    if (index < 0 || index >= allPaths.length) return;

    currentPathIndex = index;
    const pathData = allPaths[index];

    // Update active button
    document.querySelectorAll('.path-button').forEach((btn, i) => {
        btn.classList.toggle('active', i === index);
    });

    // Highlight selected path in graph
    if (searchParticles && mergedGraph) {
        searchParticles.highlightPath(index);
    }

    // Update path details list
    displayPathList(pathData.path);

    // Update stats
    document.getElementById('hops-count').textContent = pathData.hops;
};

function displayPathList(path) {
    const pathDetails = document.getElementById('path-details');
    pathDetails.innerHTML = '';

    path.forEach((page, index) => {
        const item = document.createElement('div');
        item.className = 'path-item';
        if (index === 0) item.classList.add('start');
        if (index === path.length - 1) item.classList.add('end');

        item.innerHTML = `
            <div class="path-item-number">Step ${index + 1} of ${path.length}</div>
            <div class="path-item-title">${escapeHtml(page)}</div>
        `;

        // Click to open Wikipedia
        item.addEventListener('click', function() {
            window.open(`https://en.wikipedia.org/wiki/${encodeURIComponent(page)}`, '_blank');
        });

        // Hover highlight corresponding canvas node
        item.addEventListener('mouseenter', function() {
            if (searchParticles && searchParticles.pathNodes[index]) {
                searchParticles.pathNodes[index].isHovered = true;
            }
        });

        item.addEventListener('mouseleave', function() {
            if (searchParticles && searchParticles.pathNodes[index]) {
                searchParticles.pathNodes[index].isHovered = false;
            }
        });

        pathDetails.appendChild(item);
    });
}

/**
 * Build a merged graph structure from all paths
 * Deduplicates nodes and tracks edge usage across paths
 */
function buildMergedGraph(paths) {
    const nodeMap = new Map(); // title -> node data
    const edgeMap = new Map(); // "from->to" -> edge data

    // Get start and end titles (should be same across all paths)
    const startTitle = paths[0].path[0];
    const endTitle = paths[0].path[paths[0].path.length - 1];

    // Extract unique nodes and track which paths use them
    paths.forEach((pathData, pathIndex) => {
        pathData.path.forEach((title, nodeIndex) => {
            if (!nodeMap.has(title)) {
                nodeMap.set(title, {
                    id: nodeMap.size,
                    title: title,
                    pathIndices: [],
                    minDepth: nodeIndex, // Track minimum distance from start
                    isStart: title === startTitle,
                    isEnd: title === endTitle
                });
            }
            const node = nodeMap.get(title);
            node.pathIndices.push(pathIndex);
            node.minDepth = Math.min(node.minDepth, nodeIndex);
        });
    });

    // Build edges with usage tracking
    paths.forEach((pathData, pathIndex) => {
        const path = pathData.path;
        for (let i = 0; i < path.length - 1; i++) {
            const from = path[i];
            const to = path[i + 1];
            const edgeKey = `${from}->${to}`;

            if (!edgeMap.has(edgeKey)) {
                edgeMap.set(edgeKey, {
                    from: from,
                    to: to,
                    pathIndices: [],
                    thickness: 2
                });
            }

            const edge = edgeMap.get(edgeKey);
            edge.pathIndices.push(pathIndex);
            edge.thickness = 2 + (edge.pathIndices.length * 2); // Base 2px, +2px per path
        };
    });

    const graph = {
        nodes: Array.from(nodeMap.values()),
        edges: Array.from(edgeMap.values())
    };

    // Calculate positions using left-to-right layout
    return calculateLeftToRightLayout(graph);
}

/**
 * Calculate node positions using left-to-right flow layout
 * Nodes are arranged in columns by depth, with vertical spacing
 * ENSURES: Start node is always leftmost (column 0), end node is always rightmost
 */
function calculateLeftToRightLayout(graph) {
    const canvas = document.getElementById('live-search-canvas');
    const width = canvas.width;
    const height = canvas.height;

    const padding = 100;
    const usableWidth = width - (padding * 2);
    const usableHeight = height - (padding * 2);

    // Force start node to depth 0 and find end node
    let endNode = null;

    graph.nodes.forEach(node => {
        if (node.isStart) {
            node.minDepth = 0;
        }
        if (node.isEnd) {
            endNode = node;
        }
    });

    // Find maximum depth from intermediate nodes (exclude start and end)
    let maxIntermediateDepth = 0;
    graph.nodes.forEach(node => {
        if (!node.isStart && !node.isEnd) {
            maxIntermediateDepth = Math.max(maxIntermediateDepth, node.minDepth);
        }
    });

    // Force end node to be at rightmost column
    // Place it one column after the deepest intermediate node
    if (endNode) {
        endNode.minDepth = maxIntermediateDepth + 1;
    }

    // Group nodes by depth (column)
    const depthGroups = new Map();
    graph.nodes.forEach(node => {
        if (!depthGroups.has(node.minDepth)) {
            depthGroups.set(node.minDepth, []);
        }
        depthGroups.get(node.minDepth).push(node);
    });

    // Sort nodes within each depth group for consistent positioning
    depthGroups.forEach(nodesInColumn => {
        nodesInColumn.sort((a, b) => {
            // Sort by title alphabetically for consistent ordering
            return a.title.localeCompare(b.title);
        });
    });

    const maxDepth = Math.max(...Array.from(depthGroups.keys()));
    const columnSpacing = maxDepth > 0 ? usableWidth / maxDepth : 0;

    // Position nodes
    graph.nodes.forEach(node => {
        const column = node.minDepth;
        const nodesInColumn = depthGroups.get(column);
        const nodeIndexInColumn = nodesInColumn.indexOf(node);
        const verticalSpacing = usableHeight / (nodesInColumn.length + 1);

        node.x = padding + (column * columnSpacing);
        node.y = padding + ((nodeIndexInColumn + 1) * verticalSpacing);
        node.size = 15 + (node.pathIndices.length * 5); // Larger if used by more paths
    });

    return graph;
}
