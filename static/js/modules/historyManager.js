/**
 * historyManager.js - Search history management
 *
 * Handles:
 * - Loading search history from API
 * - Displaying history list with filtering
 * - Loading and displaying historical searches
 * - Static path visualization for history
 */
import { PathNode } from './PathNode.js';
import { SearchParticles } from './SearchParticles.js';
import { showElement, hideElement, showError, escapeHtml } from './utils.js';

// Global variables
export let searchParticles = null;
let searchDebounceTimer;

export async function loadSearchHistory(query = '') {
    showElement('history-loading');

    try {
        const url = query ? `/api/searches?q=${encodeURIComponent(query)}` : '/api/searches';
        const response = await fetch(url);
        const data = await response.json();

        hideElement('history-loading');
        displaySearchHistory(data.searches);
    } catch (error) {
        hideElement('history-loading');
        console.error('Error loading history:', error);
    }
}

function displaySearchHistory(searches) {
    const historyList = document.getElementById('history-list');

    if (!searches || searches.length === 0) {
        historyList.innerHTML = '<div class="history-empty"><p>No searches yet. Try searching for a connection above!</p></div>';
        return;
    }

    historyList.innerHTML = '';

    searches.forEach(search => {
        const item = document.createElement('div');
        item.className = `history-item ${search.success ? '' : 'failed'}`;
        item.onclick = () => loadSearchById(search.id);

        const date = new Date(search.created_at).toLocaleString();

        item.innerHTML = `
            <div class="history-item-header">
                <div class="history-item-terms">
                    ${escapeHtml(search.start_term)}
                    <span class="history-item-arrow">→</span>
                    ${escapeHtml(search.end_term)}
                </div>
                <div class="history-item-date">${date}</div>
            </div>
            <div class="history-item-stats">
                ${search.success ? `
                    <div class="history-item-stat">
                        <strong>${search.hops}</strong> hops
                    </div>
                    <div class="history-item-stat">
                        <strong>${search.pages_checked}</strong> pages checked
                    </div>
                ` : `
                    <div class="history-item-stat" style="color: #ff5252;">
                        <strong>Failed</strong>
                    </div>
                `}
            </div>
        `;

        historyList.appendChild(item);
    });
}

async function loadSearchById(searchId) {
    // Scroll to top to see results
    window.scrollTo({ top: 0, behavior: 'smooth' });

    hideElement('error');
    showElement('loading');

    try {
        const response = await fetch(`/api/searches/${searchId}`);
        const data = await response.json();

        if (data.success && data.path) {
            // Display static path visualization (no animation)
            displayStaticPath(data.path, data.hops, data.pages_checked);
        } else {
            hideElement('loading');
            showError(data.error_message || 'This search failed');
        }
    } catch (error) {
        hideElement('loading');
        showError('Error loading search. Please try again.');
        console.error('Error:', error);
    }
}

function displayStaticPath(pathArray, hops, pagesChecked) {
    // Hide the live search overlay (used during active search)
    const liveSearchOverlay = document.querySelector('.live-search-overlay');
    if (liveSearchOverlay) {
        liveSearchOverlay.style.display = 'none';
    }

    // Initialize particle system if needed
    if (!searchParticles) {
        searchParticles = new SearchParticles('live-search-canvas');
    }

    // Set to CONNECTING state for the animation
    searchParticles.animationState = 'CONNECTING';
    searchParticles.pathNodes = [];
    searchParticles.particles = [];
    searchParticles.backgroundParticles = [];
    searchParticles.connectionParticles = [];
    searchParticles.flowingLights = [];
    searchParticles.connectionIndex = 0;

    const padding = 100;
    const leftX = padding;
    const rightX = searchParticles.canvas.width - padding;
    const width = rightX - leftX;
    const waveAmplitude = 60;
    const centerY = searchParticles.canvas.height / 2;

    // Create all nodes with initial opacity 0
    for (let i = 0; i < pathArray.length; i++) {
        const progress = pathArray.length > 1 ? i / (pathArray.length - 1) : 0.5;
        const x = leftX + progress * width;
        const y = centerY - Math.sin(progress * Math.PI) * waveAmplitude;

        const node = new PathNode(
            x, y,
            pathArray[i],
            i,
            i === 0,
            i === pathArray.length - 1
        );

        // Start and end nodes visible immediately, others fade in
        if (i === 0 || i === pathArray.length - 1) {
            node.opacity = 1.0;
            node.labelOpacity = 1.0;
        } else {
            node.opacity = 0;
            node.labelOpacity = 0;
        }

        searchParticles.pathNodes.push(node);
    }

    // Start the animation loop if not running
    if (!searchParticles.animationId) {
        searchParticles.animate();
    }

    // Animate nodes appearing one by one
    searchParticles.pathNodes.forEach((node, i) => {
        if (i > 0 && i < pathArray.length - 1) {
            setTimeout(() => {
                const fadeIn = setInterval(() => {
                    node.opacity = Math.min(node.opacity + 0.15, 1.0);
                    node.labelOpacity = Math.min(node.labelOpacity + 0.15, 1.0);
                    if (node.opacity >= 1.0) clearInterval(fadeIn);
                }, 30);
            }, i * 150);
        }
    });

    // Start connection animation
    if (searchParticles.pathNodes.length > 0) {
        searchParticles.pathNodes[0].isActive = true;
        setTimeout(() => {
            searchParticles.animateNextConnection();
        }, 300);
    }

    // Wait for animation to complete before showing results
    const animationDuration = pathArray.length * 150 + (pathArray.length - 1) * 800 + 1000;
    setTimeout(() => {
        // Show results
        showElement('results');
        showElement('path-details-container');

        // Update stats
        document.getElementById('hops-count').textContent = hops;
        document.getElementById('pages-count').textContent = pagesChecked;

        // Display path list (imported from searchApi)
        import('./searchApi.js').then(module => {
            // Can't easily import displayPathList since it's not exported
            // Instead, duplicate the logic here
            const pathDetails = document.getElementById('path-details');
            pathDetails.innerHTML = '';

            pathArray.forEach((page, index) => {
                const item = document.createElement('div');
                item.className = 'path-item';
                if (index === 0) item.classList.add('start');
                if (index === pathArray.length - 1) item.classList.add('end');

                item.innerHTML = `
                    <div class="path-item-number">Step ${index + 1} of ${pathArray.length}</div>
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
        });
    }, animationDuration);
}

export function setupHistorySearch() {
    const searchInput = document.getElementById('history-search');
    searchInput.addEventListener('input', function(e) {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            loadSearchHistory(e.target.value);
        }, 300);
    });
}
