/**
 * autocomplete.js - Wikipedia autocomplete functionality
 *
 * Provides real-time search suggestions from Wikipedia:
 * - Debounced API calls
 * - Keyboard navigation (Arrow keys, Enter, Escape)
 * - Mouse interaction
 * - Loading states
 */

// Module-level variables for autocomplete state
let debounceTimer = null;
let currentSelectedIndex = -1;
export let currentDropdown = null;

export async function fetchWikipediaSuggestions(query) {
    if (query.length < 2) return [];

    const url = `https://en.wikipedia.org/w/api.php?action=opensearch&search=${encodeURIComponent(query)}&limit=10&namespace=0&format=json&origin=*`;

    try {
        const response = await fetch(url);
        const data = await response.json();
        // OpenSearch returns: [query, [titles], [descriptions], [urls]]
        return data[1] || [];
    } catch (error) {
        console.error('Error fetching suggestions:', error);
        return [];
    }
}

function showSuggestions(suggestions, inputElement, dropdownElement) {
    if (suggestions.length === 0) {
        dropdownElement.innerHTML = '<div class="autocomplete-empty">No results found</div>';
        dropdownElement.classList.remove('hidden');
        return;
    }

    dropdownElement.innerHTML = '';
    currentSelectedIndex = -1;

    suggestions.forEach((suggestion, index) => {
        const item = document.createElement('div');
        item.className = 'autocomplete-item';
        item.textContent = suggestion;
        item.dataset.index = index;

        item.addEventListener('click', function() {
            inputElement.value = suggestion;
            dropdownElement.classList.add('hidden');
            currentDropdown = null;
        });

        dropdownElement.appendChild(item);
    });

    dropdownElement.classList.remove('hidden');
    currentDropdown = dropdownElement;
}

function hideSuggestions(dropdownElement) {
    dropdownElement.classList.add('hidden');
    currentSelectedIndex = -1;
    currentDropdown = null;
}

function updateSelectedItem(items) {
    items.forEach((item, index) => {
        if (index === currentSelectedIndex) {
            item.classList.add('selected');
            item.scrollIntoView({ block: 'nearest' });
        } else {
            item.classList.remove('selected');
        }
    });
}

export function setupAutocomplete(inputId, dropdownId) {
    const inputElement = document.getElementById(inputId);
    const dropdownElement = document.getElementById(dropdownId);

    // Input event with debouncing
    inputElement.addEventListener('input', function(e) {
        const query = e.target.value.trim();

        clearTimeout(debounceTimer);

        if (query.length < 2) {
            hideSuggestions(dropdownElement);
            return;
        }

        // Show loading state
        dropdownElement.innerHTML = '<div class="autocomplete-loading">Searching...</div>';
        dropdownElement.classList.remove('hidden');

        debounceTimer = setTimeout(async () => {
            const suggestions = await fetchWikipediaSuggestions(query);
            showSuggestions(suggestions, inputElement, dropdownElement);
        }, 300);
    });

    // Keyboard navigation
    inputElement.addEventListener('keydown', function(e) {
        if (!currentDropdown || currentDropdown !== dropdownElement) return;

        const items = dropdownElement.querySelectorAll('.autocomplete-item');
        if (items.length === 0) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            currentSelectedIndex = Math.min(currentSelectedIndex + 1, items.length - 1);
            updateSelectedItem(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            currentSelectedIndex = Math.max(currentSelectedIndex - 1, -1);
            updateSelectedItem(items);
        } else if (e.key === 'Enter') {
            if (currentSelectedIndex >= 0) {
                e.preventDefault();
                items[currentSelectedIndex].click();
            }
        } else if (e.key === 'Escape') {
            hideSuggestions(dropdownElement);
        }
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (e.target !== inputElement && !dropdownElement.contains(e.target)) {
            hideSuggestions(dropdownElement);
        }
    });

    // Close dropdown on blur (with small delay for click handling)
    inputElement.addEventListener('blur', function() {
        setTimeout(() => {
            if (!dropdownElement.matches(':hover')) {
                hideSuggestions(dropdownElement);
            }
        }, 200);
    });
}
