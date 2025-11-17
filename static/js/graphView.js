/**
 * GraphView - Force-directed graph visualization of cached Wikipedia segments
 *
 * Displays all cached path segments as an interactive network graph using D3.js
 */
export class GraphView {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.width = this.container.clientWidth;
        this.height = this.container.clientHeight;

        // Create SVG canvas
        this.svg = d3.select(`#${containerId}`)
            .append('svg')
            .attr('width', this.width)
            .attr('height', this.height);

        // Add zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {
                this.g.attr('transform', event.transform);
            });

        this.svg.call(zoom);

        // Main group for zoom/pan
        this.g = this.svg.append('g');

        // Initialize force simulation
        this.simulation = d3.forceSimulation()
            .force('link', d3.forceLink().id(d => d.id).distance(100))
            .force('charge', d3.forceManyBody().strength(-200))
            .force('center', d3.forceCenter(this.width / 2, this.height / 2))
            .force('collision', d3.forceCollide().radius(30));
    }

    /**
     * Load graph data from API and render
     */
    async loadGraph() {
        try {
            const response = await fetch('/api/cache/graph');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            console.log(`Loading graph: ${data.stats.total_nodes} nodes, ${data.stats.total_edges} edges`);

            this.renderGraph(data.nodes, data.edges);
            this.updateStats(data.stats);
        } catch (error) {
            console.error('Failed to load graph:', error);
            this.showError('Failed to load knowledge graph. Please try again.');
        }
    }

    /**
     * Render the force-directed graph
     */
    renderGraph(nodes, edges) {
        // Clear existing graph
        this.g.selectAll('*').remove();

        // Create arrow marker for directed edges with site color
        this.svg.append('defs').selectAll('marker')
            .data(['end'])
            .enter().append('marker')
            .attr('id', 'arrowhead')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 20)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-5L10,0L0,5')
            .attr('fill', 'rgba(34, 228, 255, 0.5)');

        // Create links (edges) with site color scheme
        const link = this.g.append('g')
            .attr('class', 'links')
            .selectAll('line')
            .data(edges)
            .enter().append('line')
            .attr('stroke', 'rgba(34, 228, 255, 0.3)')  // Accent cyan with transparency
            .attr('stroke-opacity', d => 0.3 + (Math.min(d.weight, 10) / 10) * 0.5)  // Opacity based on weight
            .attr('stroke-width', d => 1 + Math.log(d.weight + 1))
            .attr('marker-end', 'url(#arrowhead)');

        // Create nodes with site styling and glow effect
        const node = this.g.append('g')
            .attr('class', 'nodes')
            .selectAll('circle')
            .data(nodes)
            .enter().append('circle')
            .attr('r', d => 5 + Math.sqrt(d.connections) * 2)
            .attr('fill', d => this.getNodeColor(d.total_uses))
            .attr('stroke', d => this.getNodeColor(d.total_uses))
            .attr('stroke-width', 2)
            .attr('stroke-opacity', 0.5)
            .style('cursor', 'pointer')
            .style('filter', 'drop-shadow(0 0 4px rgba(34, 228, 255, 0.4))')
            .call(this.drag(this.simulation))
            .on('mouseover', (event, d) => {
                this.showNodeTooltip(event, d);
                d3.select(event.target)
                    .transition()
                    .duration(200)
                    .attr('r', d => (5 + Math.sqrt(d.connections) * 2) * 1.3)
                    .style('filter', 'drop-shadow(0 0 8px rgba(34, 228, 255, 0.8))');
            })
            .on('mouseout', (event, d) => {
                this.hideNodeTooltip();
                d3.select(event.target)
                    .transition()
                    .duration(200)
                    .attr('r', d => 5 + Math.sqrt(d.connections) * 2)
                    .style('filter', 'drop-shadow(0 0 4px rgba(34, 228, 255, 0.4))');
            });

        // Add labels (only show for important nodes) with site styling
        const label = this.g.append('g')
            .attr('class', 'labels')
            .selectAll('text')
            .data(nodes.filter(d => d.connections > 2))  // Only label well-connected nodes
            .enter().append('text')
            .text(d => d.label.length > 20 ? d.label.substring(0, 17) + '...' : d.label)
            .attr('font-size', '11px')
            .attr('font-family', 'Inter, system-ui, sans-serif')
            .attr('font-weight', '500')
            .attr('fill', '#e5e7eb')  // Site text color
            .attr('dx', 12)
            .attr('dy', 4)
            .style('pointer-events', 'none')
            .style('text-shadow', '0 0 3px rgba(2, 6, 23, 0.9), 0 0 8px rgba(34, 228, 255, 0.3)');

        // Update positions on simulation tick
        this.simulation
            .nodes(nodes)
            .on('tick', () => {
                link
                    .attr('x1', d => d.source.x)
                    .attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x)
                    .attr('y2', d => d.target.y);

                node
                    .attr('cx', d => d.x)
                    .attr('cy', d => d.y);

                label
                    .attr('x', d => d.x)
                    .attr('y', d => d.y);
            });

        this.simulation.force('link').links(edges);

        // Restart simulation
        this.simulation.alpha(1).restart();
    }

    /**
     * Get node color based on usage (hot/cold gradient)
     * Uses site's accent color scheme
     */
    getNodeColor(totalUses) {
        if (totalUses > 50) return '#00ffbf';  // Hot (accent-strong)
        if (totalUses > 20) return '#22e4ff';  // Warm (accent)
        if (totalUses > 10) return '#38bdf8';  // Medium (light blue)
        if (totalUses > 5) return '#60a5fa';   // Cool (blue)
        return '#64748b';  // Cold (slate gray)
    }

    /**
     * Show tooltip with node statistics
     */
    showNodeTooltip(event, node) {
        const tooltip = d3.select('#graph-tooltip');
        tooltip.style('display', 'block')
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY - 10) + 'px')
            .html(`
                <strong>${node.label}</strong><br>
                <span class="tooltip-stat">Connections: ${node.connections}</span><br>
                <span class="tooltip-stat">Total Uses: ${node.total_uses}</span>
            `);
    }

    /**
     * Hide tooltip
     */
    hideNodeTooltip() {
        d3.select('#graph-tooltip').style('display', 'none');
    }

    /**
     * Update statistics display with site styling
     */
    updateStats(stats) {
        const statsElement = document.getElementById('graphStats');
        if (statsElement) {
            statsElement.innerHTML = `
                <span style="color: #22e4ff; font-weight: 700;">${stats.total_nodes}</span> pages |
                <span style="color: #22e4ff; font-weight: 700;">${stats.total_edges}</span> connections
            `;
        }
    }

    /**
     * Show error message
     */
    showError(message) {
        const container = this.container;
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #e74c3c;">
                <p>${message}</p>
            </div>
        `;
    }

    /**
     * Drag behavior for nodes
     */
    drag(simulation) {
        function dragstarted(event) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }

        function dragged(event) {
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }

        function dragended(event) {
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }

        return d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended);
    }
}
