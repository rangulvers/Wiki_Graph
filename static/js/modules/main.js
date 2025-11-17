/**
 * main.js - Application entry point
 *
 * Initializes the Wikipedia Path Finder application:
 * - Sets up autocomplete for search fields
 * - Initializes background particles
 * - Loads search history
 * - Configures event listeners
 * - Makes findConnection globally available
 * - Manages navigation between Search and Graph views
 */
import { findConnection } from './searchApi.js';
import { loadSearchHistory, setupHistorySearch } from './historyManager.js';
import { setupAutocomplete, currentDropdown } from './autocomplete.js';
import { initParticles } from './utils.js';
import { loadGlobalStats } from './statsManager.js';
import { GraphView } from '../graphView.js';

// Make findConnection available globally for inline onclick handler in HTML
window.findConnection = findConnection;

// Global graph view instance
let graphView = null;

/**
 * Switch between Search and Graph views
 */
function switchView(viewName) {
    const searchViewBtn = document.getElementById('searchViewBtn');
    const graphViewBtn = document.getElementById('graphViewBtn');
    const searchViewPanel = document.getElementById('searchViewPanel');
    const graphViewPanel = document.getElementById('graphViewPanel');

    if (viewName === 'search') {
        // Show search view
        searchViewBtn.classList.add('active');
        graphViewBtn.classList.remove('active');
        searchViewPanel.classList.remove('hidden');
        graphViewPanel.classList.add('hidden');
    } else if (viewName === 'graph') {
        // Show graph view
        searchViewBtn.classList.remove('active');
        graphViewBtn.classList.add('active');
        searchViewPanel.classList.add('hidden');
        graphViewPanel.classList.remove('hidden');

        // Initialize graph on first view
        if (!graphView) {
            graphView = new GraphView('graphContainer');
            graphView.loadGraph();
        }
    }
}

/**
 * Refresh the knowledge graph
 */
function refreshGraph() {
    if (graphView) {
        graphView.loadGraph();
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Setup autocomplete for both search fields
    setupAutocomplete('start-term', 'start-suggestions');
    setupAutocomplete('end-term', 'end-suggestions');

    // Allow Enter key to trigger search (only if autocomplete dropdown is not open)
    document.getElementById('start-term').addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !currentDropdown) findConnection();
    });
    document.getElementById('end-term').addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !currentDropdown) findConnection();
    });

    // Setup navigation tabs
    document.getElementById('searchViewBtn').addEventListener('click', () => switchView('search'));
    document.getElementById('graphViewBtn').addEventListener('click', () => switchView('graph'));

    // Setup graph refresh button
    document.getElementById('refreshGraphBtn').addEventListener('click', refreshGraph);

    // Load search history on page load
    loadSearchHistory();

    // Setup history search filter
    setupHistorySearch();

    // Load global statistics
    loadGlobalStats();

    // Initialize particle background
    initParticles();
});
