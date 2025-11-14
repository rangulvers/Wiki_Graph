/**
 * statsManager.js - Global statistics management
 *
 * Fetches and displays global statistics about all searches
 */

export async function loadGlobalStats() {
    try {
        const response = await fetch('/api/stats');
        if (!response.ok) {
            console.warn('Failed to load stats');
            return;
        }

        const stats = await response.json();

        // Update stat values with animation
        updateStatValue('stat-total', stats.total_searches || 0);

        // Calculate success rate percentage
        const successRate = stats.total_searches > 0
            ? Math.round((stats.successful_searches / stats.total_searches) * 100)
            : 0;
        updateStatValue('stat-success', `${successRate}%`);

        // Format average hops (1 decimal place)
        const avgHops = stats.avg_hops ? stats.avg_hops.toFixed(1) : '0.0';
        updateStatValue('stat-hops', avgHops);

        // Format average pages (whole number)
        const avgPages = stats.avg_pages_checked ? Math.round(stats.avg_pages_checked) : 0;
        updateStatValue('stat-pages', avgPages);

        // Show the stats section
        const statsSection = document.getElementById('global-stats');
        if (statsSection) {
            statsSection.classList.remove('hidden');
        }

    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

function updateStatValue(elementId, value) {
    const element = document.getElementById(elementId);
    if (!element) return;

    // Animate number counting up
    const finalValue = typeof value === 'string' && value.includes('%')
        ? parseInt(value)
        : typeof value === 'number'
            ? value
            : parseFloat(value);

    if (isNaN(finalValue)) {
        element.textContent = value;
        return;
    }

    const duration = 1000; // 1 second animation
    const steps = 30;
    const stepValue = finalValue / steps;
    const stepDuration = duration / steps;
    let currentStep = 0;

    const interval = setInterval(() => {
        currentStep++;
        const currentValue = stepValue * currentStep;

        if (currentStep >= steps) {
            // Final value
            if (typeof value === 'string' && value.includes('%')) {
                element.textContent = `${Math.round(finalValue)}%`;
            } else if (typeof value === 'string' && value.includes('.')) {
                element.textContent = finalValue.toFixed(1);
            } else {
                element.textContent = Math.round(finalValue).toLocaleString();
            }
            clearInterval(interval);
        } else {
            // Intermediate value
            if (typeof value === 'string' && value.includes('%')) {
                element.textContent = `${Math.round(currentValue)}%`;
            } else if (typeof value === 'string' && value.includes('.')) {
                element.textContent = currentValue.toFixed(1);
            } else {
                element.textContent = Math.round(currentValue).toLocaleString();
            }
        }
    }, stepDuration);
}
