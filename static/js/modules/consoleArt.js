/**
 * Console Easter Egg - Fun ASCII art and messages for curious developers
 */

export function showConsoleArt() {
    // Check if console is available
    if (!window.console || !console.log) return;

    const styles = {
        title: 'font-size: 16px; font-weight: bold; color: #22e4ff; text-shadow: 2px 2px 4px rgba(34, 228, 255, 0.5);',
        subtitle: 'font-size: 12px; color: #64748b; font-weight: normal;',
        accent: 'color: #22e4ff; font-weight: bold;',
        normal: 'color: #94a3b8;',
        success: 'color: #10b981; font-weight: bold;',
        link: 'color: #22e4ff; text-decoration: underline; cursor: pointer;',
        emoji: 'font-size: 18px;',
        divider: 'color: #334155;'
    };

    // Clear console for dramatic effect
    console.clear();

    // ASCII Art Header
    console.log('%c' + `
 ██╗    ██╗██╗██╗  ██╗██╗ ██████╗ ██████╗   █████╗ ██████╗ ██╗  ██╗
 ██║    ██║██║██║ ██╔╝██║██╔════╝ ██╔══██╗██╔══██╗██╔══██╗██║  ██║
 ██║ █╗ ██║██║█████╔╝ ██║██║  ███╗██████╔╝███████║██████╔╝███████║
 ██║███╗██║██║██╔═██╗ ██║██║   ██║██╔══██╗██╔══██║██╔═══╝ ██╔══██║
 ╚███╔███╔╝██║██║  ██╗██║╚██████╔╝██║  ██║██║  ██║██║     ██║  ██║
  ╚══╝╚══╝ ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝
    `, styles.title);

    // Welcome message
    console.log('%c👋 Welcome, curious developer!', styles.emoji + styles.title);
    console.log('%cYou found the secret console message! 🎉\n', styles.subtitle);

    // About the project
    console.log('%c🔍 About This Project:', styles.accent);
    console.log('%cThis tool finds the shortest path between any two Wikipedia articles\nusing a %cbidirectional BFS%c algorithm. Most searches complete in %c2-8 seconds%c! ⚡\n',
        styles.normal, styles.success, styles.normal, styles.success, styles.normal);

    // Algorithm info
    console.log('%c🧠 Algorithm Details:', styles.accent);
    console.log('%c  • Bidirectional BFS (5-10x faster than traditional search)', styles.normal);
    console.log('%c  • Multi-path discovery with diversity scoring', styles.normal);
    console.log('%c  • Intelligent path caching (40-60% hit rate after warm-up)', styles.normal);
    console.log('%c  • Real-time SSE streaming updates\n', styles.normal);

    // Tech stack
    console.log('%c⚙️ Tech Stack:', styles.accent);
    console.log('%c  Backend: FastAPI + Python 3.11 + SQLite (WAL mode)', styles.normal);
    console.log('%c  Frontend: Vanilla JavaScript (ES6 modules) + Canvas API', styles.normal);
    console.log('%c  Deployment: Railway with persistent storage\n', styles.normal);

    // GitHub link
    console.log('%c💻 Open Source:', styles.accent);
    console.log('%c  GitHub: https://github.com/rangulvers/Wiki_Graph', styles.link);
    console.log('%c  Feel free to star ⭐ or contribute!\n', styles.normal);

    // Fun Wikipedia facts
    console.log('%c📊 Fun Wikipedia Facts:', styles.accent);
    console.log('%c  • Wikipedia has over 6.7 million English articles', styles.normal);
    console.log('%c  • Most articles are connected within 3-5 clicks (the "Six Degrees")', styles.normal);
    console.log('%c  • The longest known path ever found was 27 clicks!', styles.normal);
    console.log('%c  • The average path length globally is around 3.2 hops\n', styles.normal);

    // Session stats (if available)
    try {
        const searchHistory = JSON.parse(localStorage.getItem('searchHistory') || '[]');
        if (searchHistory.length > 0) {
            console.log('%c🎯 Your Session Stats:', styles.accent);
            console.log(`%c  • Searches performed: ${searchHistory.length}`, styles.success);

            const successfulSearches = searchHistory.filter(s => s.success);
            if (successfulSearches.length > 0) {
                const avgHops = successfulSearches.reduce((sum, s) => sum + (s.hops || 0), 0) / successfulSearches.length;
                console.log(`%c  • Average path length: ${avgHops.toFixed(1)} hops`, styles.success);
                console.log(`%c  • Success rate: ${((successfulSearches.length / searchHistory.length) * 100).toFixed(0)}%`, styles.success);
            }
            console.log('');
        }
    } catch (e) {
        // Ignore localStorage errors
    }

    // Interactive commands
    console.log('%c🎮 Try These Commands:', styles.accent);
    console.log('%c  wikigraph.stats()  %c- Show global search statistics', styles.link, styles.normal);
    console.log('%c  wikigraph.cache()  %c- Show cache performance metrics', styles.link, styles.normal);
    console.log('%c  wikigraph.about()  %c- Show this message again', styles.link, styles.normal);
    console.log('%c  wikigraph.help()   %c- List all available commands\n', styles.link, styles.normal);

    // Footer
    console.log('%c' + '─'.repeat(70), styles.divider);
    console.log('%cMade with ❤️ and just for fun | %cBuilt by curious developers', styles.subtitle, styles.normal);
    console.log('%c' + '─'.repeat(70) + '\n', styles.divider);
}

/**
 * Global wikigraph commands available in console
 */
window.wikigraph = {
    /**
     * Show global search statistics
     */
    stats: async function() {
        const accent = 'color: #22e4ff; font-weight: bold;';
        const normal = 'color: #94a3b8;';

        try {
            console.log('%c📊 Fetching global statistics...', accent);
            const response = await fetch('/api/stats');
            const data = await response.json();

            console.log('\n%c📈 Global Search Statistics:', accent);
            console.table(data);

            // Calculate some interesting metrics
            if (data.total_searches > 0) {
                const successRate = ((data.successful_searches / data.total_searches) * 100).toFixed(1);
                console.log(`%c✓ Success Rate: ${successRate}%`, 'color: #10b981; font-weight: bold;');
            }

        } catch (error) {
            console.error('%c✗ Failed to fetch statistics:', 'color: #ef4444; font-weight: bold;', error);
        }
    },

    /**
     * Show cache performance metrics
     */
    cache: async function() {
        const accent = 'color: #22e4ff; font-weight: bold;';

        try {
            console.log('%c💾 Fetching cache statistics...', accent);
            const response = await fetch('/api/cache/stats');
            const data = await response.json();

            console.log('\n%c📦 Cache Performance:', accent);
            console.table(data);

            // Show cache hit rate if available
            if (data.hit_rate !== undefined) {
                const hitRate = (data.hit_rate * 100).toFixed(1);
                console.log(`%c⚡ Cache Hit Rate: ${hitRate}%`, 'color: #10b981; font-weight: bold;');
            }

        } catch (error) {
            console.error('%c✗ Failed to fetch cache stats:', 'color: #ef4444; font-weight: bold;', error);
        }
    },

    /**
     * Show the ASCII art welcome message
     */
    about: function() {
        showConsoleArt();
    },

    /**
     * Show help for available commands
     */
    help: function() {
        const accent = 'color: #22e4ff; font-weight: bold;';
        const link = 'color: #22e4ff; text-decoration: underline;';
        const normal = 'color: #94a3b8;';

        console.log('%c🎮 Available Commands:\n', accent);
        console.log('%c  wikigraph.stats()  %c- Show global search statistics', link, normal);
        console.log('%c  wikigraph.cache()  %c- Show cache performance metrics', link, normal);
        console.log('%c  wikigraph.about()  %c- Show project information and ASCII art', link, normal);
        console.log('%c  wikigraph.help()   %c- Show this help message\n', link, normal);

        console.log('%c💡 Tip: You can also check the Network tab to see SSE events in action!', normal);
    }
};

// Add helpful hint about commands
console.info('%c💡 Tip: Type %cwikigraph.help()%c for available commands',
    'color: #94a3b8;', 'color: #22e4ff; font-weight: bold;', 'color: #94a3b8;');
