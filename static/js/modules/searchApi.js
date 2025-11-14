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

export async function findConnection() {
    const startTerm = document.getElementById('start-term').value.trim();
    const endTerm = document.getElementById('end-term').value.trim();

    if (!startTerm || !endTerm) {
        showError('Please enter both search terms');
        return;
    }

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
                end: endTerm
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

        case 'complete':
            // Fade out stats overlay
            const liveStatus = document.getElementById('live-status');
            liveStatus.style.transition = 'opacity 0.5s';
            liveStatus.style.opacity = '0';

            // Hide search title
            document.querySelector('.search-title').style.opacity = '0';

            // Start Minority Report style path animation
            if (searchParticles) {
                setTimeout(() => {
                    searchParticles.buildPath(data.path);
                }, 500);
            }

            // Return the path data for transition (after animation completes)
            return { path: data.path, pages_checked: data.pages_checked };

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
    // Wait for complete animation sequence
    // Convergence: 2000ms + 500ms delay
    // Each connection: ~800ms (500ms beam + 300ms delay)
    const convergenceTime = 2500;
    const connectionTime = (data.path.length - 1) * 800;
    const animationDuration = convergenceTime + connectionTime + 500;

    await new Promise(resolve => setTimeout(resolve, animationDuration));

    // Keep canvas visible, show results overlay
    showElement('results');
    showElement('path-details-container');

    // Update stats
    document.getElementById('hops-count').textContent = data.path.length - 1;
    document.getElementById('pages-count').textContent = data.pages_checked;

    // Display path list
    displayPathList(data.path);
}

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
