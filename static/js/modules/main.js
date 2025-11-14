/**
 * main.js - Application entry point
 *
 * Initializes the Wikipedia Path Finder application:
 * - Sets up autocomplete for search fields
 * - Initializes background particles
 * - Loads search history
 * - Configures event listeners
 * - Makes findConnection globally available
 */
import { findConnection } from './searchApi.js';
import { loadSearchHistory, setupHistorySearch } from './historyManager.js';
import { setupAutocomplete, currentDropdown } from './autocomplete.js';
import { initParticles } from './utils.js';
import { loadGlobalStats } from './statsManager.js';

// Make findConnection available globally for inline onclick handler in HTML
window.findConnection = findConnection;

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

    // Load search history on page load
    loadSearchHistory();

    // Setup history search filter
    setupHistorySearch();

    // Load global statistics
    loadGlobalStats();

    // Initialize particle background
    initParticles();
});
