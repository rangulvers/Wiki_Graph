/**
 * SearchParticles - Canvas-based particle animation system
 *
 * Manages the entire visualization lifecycle:
 * - Search phase: Radiating particles from start/end nodes
 * - Convergence phase: Particles materialize into path nodes
 * - Connection phase: Animated beam connecting nodes
 * - Complete phase: Flowing lights along path
 */
import { PathNode } from './PathNode.js';

export class SearchParticles {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.particles = [];
        this.forwardWaveRadius = 50;
        this.backwardWaveRadius = 50;
        this.maxWaveRadius = 200;
        this.animationId = null;
        this.centerY = 0;
        this.leftCenterX = 0;
        this.rightCenterX = 0;
        this.connectionLine = null;
        this.connectionProgress = 0;

        // Path animation state
        this.pathNodes = [];
        this.pathConnections = [];
        this.connectionIndex = 0;
        this.connectionParticles = [];
        this.animationState = 'SEARCHING'; // SEARCHING, CONNECTING, REVEALING, COMPLETE

        // Mouse interaction state
        this.mouseX = 0;
        this.mouseY = 0;
        this.hoveredNode = null;

        // Background ambient particles (float around during search)
        this.backgroundParticles = [];

        // Flowing light particles on connections
        this.flowingLights = [];

        // Graph mode state
        this.graphMode = false;
        this.graphData = null;
        this.allPaths = [];
        this.highlightedPathIndex = -1;
        this.graphNodes = [];
        this.graphEdges = [];

        this.resizeCanvas();
        window.addEventListener('resize', () => this.resizeCanvas());

        // Add mouse event listeners for interactivity
        this.canvas.addEventListener('mousemove', (e) => this.handleMouseMove(e));
        this.canvas.addEventListener('click', (e) => this.handleClick(e));
        this.canvas.addEventListener('mouseout', () => this.handleMouseOut());
    }

    resizeCanvas() {
        this.canvas.width = this.canvas.clientWidth;
        this.canvas.height = this.canvas.clientHeight;
        this.centerY = this.canvas.height / 2;
        this.leftCenterX = this.canvas.width * 0.25;
        this.rightCenterX = this.canvas.width * 0.75;
    }

    start() {
        this.particles = [];
        this.forwardWaveRadius = 50;
        this.backwardWaveRadius = 50;
        this.connectionLine = null;
        this.connectionProgress = 0;
        this.pathNodes = [];
        this.pathConnections = [];
        this.connectionIndex = 0;
        this.connectionParticles = [];
        this.animationState = 'SEARCHING';

        // Create start and end nodes in their final positions immediately
        this.createStartEndNodes();

        // Generate background ambient particles
        this.createBackgroundParticles();

        this.animate();
    }

    createBackgroundParticles() {
        this.backgroundParticles = [];
        const count = 30 + Math.floor(Math.random() * 10); // 30-40 particles

        for (let i = 0; i < count; i++) {
            this.backgroundParticles.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                vx: (Math.random() - 0.5) * 0.5,
                vy: (Math.random() - 0.5) * 0.5,
                size: 0.8 + Math.random() * 1.2,
                opacity: 0.2 + Math.random() * 0.2,
                color: Math.random() > 0.5 ? '34, 228, 255' : '0, 255, 191', // Mix of cyan and cyan-green
                frozen: false
            });
        }
    }

    updateBackgroundParticles() {
        this.backgroundParticles.forEach(p => {
            if (!p.frozen) {
                // Normal drifting movement
                p.x += p.vx;
                p.y += p.vy;

                // Wrap around edges
                if (p.x < 0) p.x = this.canvas.width;
                if (p.x > this.canvas.width) p.x = 0;
                if (p.y < 0) p.y = this.canvas.height;
                if (p.y > this.canvas.height) p.y = 0;
            } else {
                // Frozen - converge toward nearest path node
                if (this.pathNodes.length > 0 && this.intermediateNodeData.length > 0) {
                    // Find closest node position (including intermediate node data)
                    let minDist = Infinity;
                    let targetX, targetY;

                    // Check all path nodes
                    for (const node of this.pathNodes) {
                        const dx = node.x - p.x;
                        const dy = node.y - p.y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist < minDist) {
                            minDist = dist;
                            targetX = node.x;
                            targetY = node.y;
                        }
                    }

                    // Check intermediate node positions
                    for (const nodeData of this.intermediateNodeData) {
                        const dx = nodeData.x - p.x;
                        const dy = nodeData.y - p.y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist < minDist) {
                            minDist = dist;
                            targetX = nodeData.x;
                            targetY = nodeData.y;
                        }
                    }

                    // Strong attraction toward target - accelerate as we get closer
                    const dx = targetX - p.x;
                    const dy = targetY - p.y;
                    const dist = Math.sqrt(dx * dx + dy * dy);

                    if (dist > 2) {
                        // Stronger, faster convergence
                        const attraction = 0.15;
                        p.vx += (dx / dist) * attraction;
                        p.vy += (dy / dist) * attraction;

                        // Add damping to prevent overshooting
                        p.vx *= 0.92;
                        p.vy *= 0.92;

                        p.x += p.vx;
                        p.y += p.vy;
                    } else {
                        // Very close - snap to position and fade quickly
                        p.x = targetX;
                        p.y = targetY;
                        p.vx = 0;
                        p.vy = 0;
                        p.opacity = Math.max(0, p.opacity - 0.02);
                    }
                } else {
                    // No path nodes yet, just fade out
                    p.opacity = Math.max(0, p.opacity - 0.005);
                }
            }
        });

        // Remove fully faded particles
        this.backgroundParticles = this.backgroundParticles.filter(p => p.opacity > 0);
    }

    drawBackgroundParticles() {
        this.backgroundParticles.forEach(p => {
            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(${p.color}, ${p.opacity})`;
            this.ctx.fill();
        });
    }

    createStartEndNodes() {
        const padding = 100;
        const leftX = padding;
        const rightX = this.canvas.width - padding;

        // Create start node (left side)
        const startNode = new PathNode(
            leftX, this.centerY,
            'Start', // Temporary label, will be updated when path is found
            0,
            true, // isStart
            false
        );
        startNode.opacity = 1.0;
        startNode.labelOpacity = 0; // Hide label during search

        // Create end node (right side)
        const endNode = new PathNode(
            rightX, this.centerY,
            'End', // Temporary label, will be updated when path is found
            1,
            false,
            true // isEnd
        );
        endNode.opacity = 1.0;
        endNode.labelOpacity = 0; // Hide label during search

        this.pathNodes = [startNode, endNode];
    }

    buildPath(pathArray) {
        // Freeze background particles (they'll start converging to path)
        this.backgroundParticles.forEach(p => {
            p.frozen = true;
        });

        // Transition to convergence animation
        this.animationState = 'CONVERGING';
        this.connectionIndex = 0;
        this.connectionParticles = [];

        const padding = 100;
        const leftX = padding;
        const rightX = this.canvas.width - padding;
        const width = rightX - leftX;
        const waveAmplitude = 60;

        // Update start and end node labels (we only have 2 nodes at this point)
        this.pathNodes[0].label = pathArray[0];
        this.pathNodes[1].label = pathArray[pathArray.length - 1];

        // Store intermediate node positions (but don't create them yet)
        this.intermediateNodeData = [];
        for (let i = 1; i < pathArray.length - 1; i++) {
            const progress = i / (pathArray.length - 1);
            const x = leftX + progress * width;
            const y = this.centerY - Math.sin(progress * Math.PI) * waveAmplitude;

            this.intermediateNodeData.push({
                x: x,
                y: y,
                label: pathArray[i],
                index: i
            });
        }

        // Start convergence animation
        this.startConvergence();
    }

    startConvergence() {
        // Make all search particles converge toward the path
        this.convergenceProgress = 0;
        this.materializingNodeIndex = 0;

        // Particles will converge over ~2 seconds
        this.convergenceStartTime = Date.now();
        this.convergenceDuration = 2000;
    }

    drawConvergenceAnimation() {
        const elapsed = Date.now() - this.convergenceStartTime;
        this.convergenceProgress = Math.min(elapsed / this.convergenceDuration, 1.0);

        // Draw start and end nodes (now with real labels)
        this.pathNodes[0].labelOpacity = this.convergenceProgress;
        this.pathNodes[this.pathNodes.length - 1].labelOpacity = this.convergenceProgress;
        this.pathNodes[0].draw(this.ctx, this.hoveredNode === this.pathNodes[0]);
        this.pathNodes[this.pathNodes.length - 1].draw(this.ctx, this.hoveredNode === this.pathNodes[this.pathNodes.length - 1]);

        // Update particles to converge toward path arc
        if (this.particles && this.particles.length > 0) {
            this.particles.forEach(p => {
            // Find closest point on the path arc for this particle
            let targetX, targetY;

            if (this.intermediateNodeData.length > 0) {
                // Find nearest intermediate node position
                let minDist = Infinity;
                let closestNodeData = this.intermediateNodeData[0];

                for (const nodeData of this.intermediateNodeData) {
                    const dx = nodeData.x - p.x;
                    const dy = nodeData.y - p.y;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < minDist) {
                        minDist = dist;
                        closestNodeData = nodeData;
                    }
                }

                targetX = closestNodeData.x;
                targetY = closestNodeData.y;
            } else {
                // If no intermediate nodes, converge to center
                targetX = (this.pathNodes[0].x + this.pathNodes[1].x) / 2;
                targetY = (this.pathNodes[0].y + this.pathNodes[1].y) / 2;
            }

            // Attract particles toward their target
            const dx = targetX - p.x;
            const dy = targetY - p.y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist > 5) {
                const attraction = 0.1 * this.convergenceProgress;
                p.vx += (dx / dist) * attraction;
                p.vy += (dy / dist) * attraction;
            }

            // Slow down particles as they converge
            p.vx *= 0.95;
            p.vy *= 0.95;
            });
        }

        // Materialize nodes from particle clusters
        const nodeRevealProgress = this.convergenceProgress;
        const nodesToReveal = Math.floor(nodeRevealProgress * this.intermediateNodeData.length);

        if (this.graphMode) {
            // Graph mode: Fade in existing nodes (they're already in pathNodes)
            for (let i = 0; i < nodesToReveal; i++) {
                if (i < this.pathNodes.length) {
                    const node = this.pathNodes[i];
                    // Gradually fade in opacity
                    const targetOpacity = Math.min((nodeRevealProgress - (i / this.intermediateNodeData.length)) * 2, 1.0);
                    node.opacity = Math.max(node.opacity, targetOpacity);
                    node.labelOpacity = Math.max(node.labelOpacity, targetOpacity);
                }
            }
        } else {
            // Original single-path mode: Create nodes dynamically via splice
            for (let i = 0; i < nodesToReveal; i++) {
                if (i >= this.materializingNodeIndex) {
                    // Create new node from intermediate data
                    const data = this.intermediateNodeData[i];
                    const newNode = new PathNode(
                        data.x, data.y,
                        data.label,
                        data.index,
                        false,
                        false
                    );

                    // Start with low opacity and fade in
                    newNode.opacity = 0;
                    newNode.labelOpacity = 0;

                    // Insert in correct position (between start and end)
                    this.pathNodes.splice(data.index, 0, newNode);

                    // Fade in the node
                    const node = newNode;
                    const fadeIn = setInterval(() => {
                        node.opacity = Math.min(node.opacity + 0.1, 1.0);
                        node.labelOpacity = Math.min(node.labelOpacity + 0.1, 1.0);
                        if (node.opacity >= 1.0) clearInterval(fadeIn);
                    }, 30);

                    this.materializingNodeIndex = i + 1;
                }
            }
        }

        // Draw materialized nodes
        for (let i = 1; i < this.pathNodes.length - 1; i++) {
            const node = this.pathNodes[i];
            if (node.opacity > 0) {
                const isHovered = this.hoveredNode === node;
                node.draw(this.ctx, isHovered);
            }
        }

        // Transition to connection phase when convergence is complete
        if (this.convergenceProgress >= 1.0 && this.animationState === 'CONVERGING') {
            setTimeout(() => {
                // Clear search particles (they've done their job)
                this.particles = [];

                if (this.graphMode) {
                    // Graph mode: Transition to REVEALING for simultaneous edge animation
                    this.animationState = 'REVEALING';
                    this.startGraphEdgeAnimation();
                } else {
                    // Single-path mode: Use sequential CONNECTING animation
                    this.animationState = 'CONNECTING';
                    this.connectionIndex = 0;

                    if (this.pathNodes.length > 0) {
                        this.pathNodes[0].isActive = true;
                        this.animateNextConnection();
                    }
                }
            }, 500);
        }
    }

    stop() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }
    }

    addParticles(count, direction = 'forward') {
        // Get the actual node position (not the old wave center)
        const sourceNode = direction === 'forward' ? this.pathNodes[0] : this.pathNodes[this.pathNodes.length - 1];
        if (!sourceNode) return;

        const centerX = sourceNode.x;
        const centerY = sourceNode.y;
        const color = direction === 'forward' ? '34, 228, 255' : '0, 255, 191'; // cyan : cyan-green

        for (let i = 0; i < count; i++) {
            // Shoot particles in random directions (full 360 degrees)
            const angle = Math.random() * Math.PI * 2;
            const speed = 1.5 + Math.random() * 2.5;
            const size = 1.5 + Math.random() * 2;

            this.particles.push({
                x: centerX,
                y: centerY,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                size: size,
                opacity: 0.7,
                life: 1.0,
                color: color,
                direction: direction
            });
        }
    }

    updateWaves(forwardDepth, backwardDepth, maxDepth = 6) {
        this.forwardWaveRadius = 50 + (forwardDepth / maxDepth) * (this.maxWaveRadius - 50);
        this.backwardWaveRadius = 50 + (backwardDepth / maxDepth) * (this.maxWaveRadius - 50);
    }

    animateNextConnection() {
        if (this.connectionIndex >= this.pathNodes.length - 1) {
            // All connections complete - transition to final state
            this.animationState = 'COMPLETE';
            // Start flowing lights only (ambient particles already exist from search)
            this.startFlowingLights();
            return;
        }

        const sourceNode = this.pathNodes[this.connectionIndex];
        const targetNode = this.pathNodes[this.connectionIndex + 1];

        // Create particle beam from source to target
        const beamParticleCount = 20;
        this.connectionParticles = [];

        for (let i = 0; i < beamParticleCount; i++) {
            this.connectionParticles.push({
                progress: i / beamParticleCount,
                speed: 0.05,
                sourceNode: sourceNode,
                targetNode: targetNode,
                size: 2 + Math.random() * 2
            });
        }

        // Wait for beam to reach target, then continue
        setTimeout(() => {
            targetNode.isActive = true;
            sourceNode.isActive = false;

            // Create pulse effect at target
            this.createPulseEffect(targetNode);

            // Move to next connection
            this.connectionIndex++;
            setTimeout(() => this.animateNextConnection(), 300);
        }, 500);
    }

    createPulseEffect(node) {
        let pulseRadius = 0;
        const maxRadius = 30;
        const pulseInterval = setInterval(() => {
            pulseRadius += 2;
            if (pulseRadius > maxRadius) {
                clearInterval(pulseInterval);
            }
        }, 16);

        // Store pulse for rendering
        node.pulseRadius = 0;
        node.pulseAnimation = setInterval(() => {
            node.pulseRadius = (node.pulseRadius || 0) + 2;
            if (node.pulseRadius > maxRadius) {
                clearInterval(node.pulseAnimation);
                delete node.pulseRadius;
            }
        }, 16);
    }


    startAmbientParticles() {
        // Generate very subtle ambient particles that drift around the path
        const particleCount = Math.min(this.pathNodes.length * 1, 12);

        for (let i = 0; i < particleCount; i++) {
            // Pick a random node to orbit around
            const targetNode = this.pathNodes[Math.floor(Math.random() * this.pathNodes.length)];
            const angle = Math.random() * Math.PI * 2;
            const radius = 40 + Math.random() * 80;

            const x = targetNode.x + Math.cos(angle) * radius;
            const y = targetNode.y + Math.sin(angle) * radius;

            this.ambientParticles.push({
                x: x,
                y: y,
                vx: (Math.random() - 0.5) * 0.3,
                vy: (Math.random() - 0.5) * 0.3,
                size: 0.8 + Math.random() * 1.2,
                opacity: 0.15 + Math.random() * 0.2,
                color: targetNode.getColor(),
                targetNode: targetNode,
                orbitSpeed: 0.01 + Math.random() * 0.02,
                orbitRadius: radius,
                orbitAngle: angle
            });
        }

        // Start flowing lights on connections
        this.startFlowingLights();
    }

    startGraphEdgeAnimation() {
        // Initialize simultaneous animation for all edges in graph mode
        this.edgeRevealStartTime = Date.now();
        this.edgeRevealDuration = 1000; // 1 second for all edges to reveal

        // Create beam particles for all edges simultaneously
        this.pathConnections.forEach(conn => {
            const beamParticleCount = 15;

            for (let i = 0; i < beamParticleCount; i++) {
                this.connectionParticles.push({
                    progress: i / beamParticleCount,
                    speed: 0.04,
                    connection: conn,
                    sourceNode: conn.from,
                    targetNode: conn.to,
                    size: 2 + Math.random() * 2,
                    startDelay: Math.random() * 200 // Stagger start times slightly
                });
            }
        });
    }

    startFlowingLights() {
        // In graph mode, create flowing lights for all edges
        if (this.graphMode && this.pathConnections) {
            this.pathConnections.forEach((conn, connIndex) => {
                // Create multiple lights per connection at different starting positions
                const lightsPerConnection = 2;
                for (let j = 0; j < lightsPerConnection; j++) {
                    this.flowingLights.push({
                        connection: conn,
                        progress: j / lightsPerConnection, // Stagger starting positions
                        speed: 0.005 + Math.random() * 0.003,
                        size: 2 + Math.random() * 2,
                        opacity: 0.7 + Math.random() * 0.3,
                        color: '179, 229, 255' // Blue-white
                    });
                }
            });
        } else {
            // Original single-path mode
            for (let i = 0; i < this.pathNodes.length - 1; i++) {
                // Create multiple lights per connection at different starting positions
                const lightsPerConnection = 1;
                for (let j = 0; j < lightsPerConnection; j++) {
                    this.flowingLights.push({
                        sourceIndex: i,
                        targetIndex: i + 1,
                        progress: j / lightsPerConnection, // Stagger starting positions
                        speed: 0.005 + Math.random() * 0.003,
                        size: 2 + Math.random() * 2,
                        opacity: 0.7 + Math.random() * 0.3,
                        color: '179, 229, 255' // Blue-white
                    });
                }
            }
        }
    }

    updateFlowingLights() {
        this.flowingLights.forEach(light => {
            light.progress += light.speed;

            // Loop back to start when reaching end
            if (light.progress >= 1.0) {
                light.progress = 0;
            }

            // Pulsing effect
            light.opacity = 0.5 + Math.sin(light.progress * Math.PI * 2) * 0.3;
        });
    }

    drawFlowingLights() {
        this.flowingLights.forEach(light => {
            let sourceNode, targetNode;

            // Graph mode: use connection object
            if (light.connection) {
                sourceNode = light.connection.from;
                targetNode = light.connection.to;
            } else {
                // Original mode: use indices
                sourceNode = this.pathNodes[light.sourceIndex];
                targetNode = this.pathNodes[light.targetIndex];
            }

            if (!sourceNode || !targetNode) return;

            // Calculate position along the connection
            const x = sourceNode.x + (targetNode.x - sourceNode.x) * light.progress;
            const y = sourceNode.y + (targetNode.y - sourceNode.y) * light.progress;

            // Draw subtle particle with minimal glow
            this.ctx.shadowBlur = 8;
            this.ctx.shadowColor = `rgba(${light.color}, ${light.opacity * 0.5})`;

            this.ctx.beginPath();
            this.ctx.arc(x, y, light.size * 0.8, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(${light.color}, ${light.opacity * 0.6})`;
            this.ctx.fill();

            this.ctx.shadowBlur = 0;
        });
    }

    updateAmbientParticles() {
        this.ambientParticles.forEach(p => {
            // Gentle drift
            p.x += p.vx;
            p.y += p.vy;

            // Subtle attraction to target node (keeps particles near path)
            const dx = p.targetNode.x - p.x;
            const dy = p.targetNode.y - p.y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist > p.orbitRadius + 50) {
                // Pull back toward orbit
                p.vx += (dx / dist) * 0.01;
                p.vy += (dy / dist) * 0.01;
            }

            // Damping to prevent runaway velocity
            p.vx *= 0.99;
            p.vy *= 0.99;

            // Gentle pulsing opacity
            p.opacity = 0.3 + Math.sin(Date.now() / 1000 + p.x) * 0.2;
        });
    }

    drawAmbientParticles() {
        this.ambientParticles.forEach(p => {
            // Draw particle (very subtle, no glow)
            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(${p.color}, ${p.opacity})`;
            this.ctx.fill();
        });
    }

    animate() {
        // Fully clear the canvas each frame (no trails) - match new background
        this.ctx.fillStyle = 'rgba(2, 6, 23, 1.0)';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Update and draw background particles
        this.updateBackgroundParticles();
        this.drawBackgroundParticles();

        // Update and draw flowing lights if in COMPLETE state
        if (this.animationState === 'COMPLETE' && this.flowingLights.length > 0) {
            this.updateFlowingLights();
            this.drawFlowingLights();
        }

        // Render based on animation state
        if (this.animationState === 'SEARCHING') {
            // Draw start and end nodes
            if (this.pathNodes.length >= 2) {
                this.pathNodes[0].draw(this.ctx, this.hoveredNode === this.pathNodes[0]);
                this.pathNodes[1].draw(this.ctx, this.hoveredNode === this.pathNodes[1]);
            }
        } else if (this.animationState === 'CONVERGING') {
            // Draw convergence animation
            this.drawConvergenceAnimation();
        } else if (this.animationState === 'REVEALING') {
            // Draw REVEALING state (simultaneous edge animation in graph mode)
            this.drawPathAnimation();
        } else if (this.animationState !== 'SEARCHING') {
            // Path animation mode - draw nodes and connections
            this.drawPathAnimation();
        }

        // Update and draw particles
        for (let i = this.particles.length - 1; i >= 0; i--) {
            const p = this.particles[i];

            p.x += p.vx;
            p.y += p.vy;

            // Don't let particles die during convergence
            if (this.animationState !== 'CONVERGING') {
                p.life -= 0.005;
            }
            p.opacity = p.life * 0.8;

            // Remove dead particles
            if (p.life <= 0 ||
                p.x < 0 || p.x > this.canvas.width ||
                p.y < 0 || p.y > this.canvas.height) {
                this.particles.splice(i, 1);
                continue;
            }

            // Draw particle with directional color
            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(${p.color}, ${p.opacity})`;
            this.ctx.fill();

            // Draw glow
            const gradient = this.ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size * 3);
            gradient.addColorStop(0, `rgba(${p.color}, ${p.opacity * 0.3})`);
            gradient.addColorStop(1, `rgba(${p.color}, 0)`);
            this.ctx.fillStyle = gradient;
            this.ctx.fillRect(p.x - p.size * 3, p.y - p.size * 3, p.size * 6, p.size * 6);
        }

        // Draw connection line if path is found
        if (this.connectionLine) {
            this.drawConnectionLine();
        }

        this.animationId = requestAnimationFrame(() => this.animate());
    }

    drawConnectionLine() {
        const centerX = this.canvas.width / 2;

        // Animate connection progress
        if (this.connectionProgress < 1.0) {
            this.connectionProgress += 0.02;
        }

        // Draw line from left to center to right
        const leftToCenter = {
            startX: this.leftCenterX,
            endX: centerX,
            y: this.centerY
        };
        const centerToRight = {
            startX: centerX,
            endX: this.rightCenterX,
            y: this.centerY
        };

        // Draw left to center (first half of animation)
        if (this.connectionProgress <= 0.5) {
            const progress = this.connectionProgress * 2;
            const currentX = leftToCenter.startX + (leftToCenter.endX - leftToCenter.startX) * progress;

            this.ctx.beginPath();
            this.ctx.moveTo(leftToCenter.startX, leftToCenter.y);
            this.ctx.lineTo(currentX, leftToCenter.y);
            this.ctx.strokeStyle = 'rgba(34, 228, 255, 0.8)';
            this.ctx.lineWidth = 4;
            this.ctx.shadowBlur = 20;
            this.ctx.shadowColor = 'rgba(34, 228, 255, 0.8)';
            this.ctx.stroke();
            this.ctx.shadowBlur = 0;
        } else {
            // Draw complete left-to-center line
            this.ctx.beginPath();
            this.ctx.moveTo(leftToCenter.startX, leftToCenter.y);
            this.ctx.lineTo(leftToCenter.endX, leftToCenter.y);
            this.ctx.strokeStyle = 'rgba(34, 228, 255, 0.8)';
            this.ctx.lineWidth = 4;
            this.ctx.shadowBlur = 20;
            this.ctx.shadowColor = 'rgba(34, 228, 255, 0.8)';
            this.ctx.stroke();
            this.ctx.shadowBlur = 0;

            // Draw center to right (second half of animation)
            const progress = (this.connectionProgress - 0.5) * 2;
            const currentX = centerToRight.startX + (centerToRight.endX - centerToRight.startX) * progress;

            this.ctx.beginPath();
            this.ctx.moveTo(centerToRight.startX, centerToRight.y);
            this.ctx.lineTo(currentX, centerToRight.y);
            this.ctx.strokeStyle = 'rgba(0, 255, 191, 0.8)';
            this.ctx.lineWidth = 4;
            this.ctx.shadowBlur = 20;
            this.ctx.shadowColor = 'rgba(0, 255, 191, 0.8)';
            this.ctx.stroke();
            this.ctx.shadowBlur = 0;
        }

        // Draw meeting point flash when complete
        if (this.connectionProgress >= 0.5) {
            const pulse = Math.sin(Date.now() / 200) * 0.3 + 0.7;
            this.ctx.beginPath();
            this.ctx.arc(centerX, this.centerY, 8, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(255, 255, 255, ${pulse})`;
            this.ctx.shadowBlur = 30;
            this.ctx.shadowColor = 'rgba(255, 255, 255, 1)';
            this.ctx.fill();
            this.ctx.shadowBlur = 0;
        }
    }

    drawPathAnimation() {
        // Handle REVEALING state (graph mode simultaneous edge animation)
        if (this.animationState === 'REVEALING') {
            const elapsed = Date.now() - this.edgeRevealStartTime;
            const revealProgress = Math.min(elapsed / this.edgeRevealDuration, 1.0);

            // Draw all edges with fade-in effect
            this.pathConnections.forEach(conn => {
                const isHighlighted = this.highlightedPathIndex >= 0 &&
                    conn.pathIndices.includes(this.highlightedPathIndex);
                const baseOpacity = isHighlighted ? 0.8 : 0.3;
                const opacity = baseOpacity * revealProgress;

                this.ctx.save();
                this.ctx.strokeStyle = `rgba(34, 228, 255, ${opacity})`;
                this.ctx.lineWidth = conn.thickness;
                this.ctx.lineCap = 'round';

                this.ctx.beginPath();
                this.ctx.moveTo(conn.from.x, conn.from.y);
                this.ctx.lineTo(conn.to.x, conn.to.y);
                this.ctx.stroke();

                this.ctx.restore();
            });

            // Draw beam particles along all edges
            this.connectionParticles.forEach(p => {
                p.progress = Math.min(p.progress + p.speed, 1.0);

                if (p.progress <= 1.0 && p.connection) {
                    const x = p.sourceNode.x + (p.targetNode.x - p.sourceNode.x) * p.progress;
                    const y = p.sourceNode.y + (p.targetNode.y - p.sourceNode.y) * p.progress;

                    const color = '179, 229, 255';

                    this.ctx.beginPath();
                    this.ctx.arc(x, y, p.size, 0, Math.PI * 2);
                    this.ctx.fillStyle = `rgba(${color}, ${1.0 - p.progress * 0.5})`;
                    this.ctx.shadowBlur = 10;
                    this.ctx.shadowColor = `rgba(${color}, 0.8)`;
                    this.ctx.fill();
                    this.ctx.shadowBlur = 0;
                }
            });

            // Transition to COMPLETE when animation finishes
            if (revealProgress >= 1.0) {
                this.animationState = 'COMPLETE';
                this.connectionParticles = []; // Clear beam particles
                this.startFlowingLights(); // Start flowing lights
            }

            // Draw all nodes
            this.pathNodes.forEach(node => {
                let isHighlighted = false;
                if (this.highlightedPathIndex >= 0 && this.allPaths) {
                    isHighlighted = this.allPaths[this.highlightedPathIndex].path.includes(node.label);
                }
                const isHovered = this.hoveredNode === node;
                node.draw(this.ctx, isHovered, isHighlighted);
            });

            return; // Exit early, handled REVEALING state
        }

        // In graph mode, draw all edges with highlighting
        if (this.graphMode && this.pathConnections) {
            this.pathConnections.forEach(conn => {
                // Check if this edge is in the highlighted path
                const isHighlighted = this.highlightedPathIndex >= 0 &&
                    conn.pathIndices.includes(this.highlightedPathIndex);

                // Set opacity based on highlight state
                const opacity = isHighlighted ? 0.8 : 0.3;

                this.ctx.save();
                this.ctx.strokeStyle = `rgba(34, 228, 255, ${opacity})`;
                this.ctx.lineWidth = conn.thickness;
                this.ctx.lineCap = 'round';

                // Add glow for highlighted edges
                if (isHighlighted) {
                    this.ctx.shadowBlur = 15;
                    this.ctx.shadowColor = 'rgba(34, 228, 255, 0.8)';
                }

                this.ctx.beginPath();
                this.ctx.moveTo(conn.from.x, conn.from.y);
                this.ctx.lineTo(conn.to.x, conn.to.y);
                this.ctx.stroke();

                this.ctx.restore();
            });
        } else {
            // Original single-path mode: draw connection lines between completed nodes
            for (let i = 0; i < this.pathNodes.length - 1; i++) {
                if (i < this.connectionIndex) {
                    const node1 = this.pathNodes[i];
                    const node2 = this.pathNodes[i + 1];

                    // Draw connection line
                    this.ctx.beginPath();
                    this.ctx.moveTo(node1.x, node1.y);
                    this.ctx.lineTo(node2.x, node2.y);
                    this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
                    this.ctx.lineWidth = 2;
                    this.ctx.stroke();
                }
            }
        }

        // Draw connection particles (beam effect)
        this.connectionParticles.forEach(p => {
            p.progress = Math.min(p.progress + p.speed, 1.0);

            if (p.progress <= 1.0) {
                const x = p.sourceNode.x + (p.targetNode.x - p.sourceNode.x) * p.progress;
                const y = p.sourceNode.y + (p.targetNode.y - p.sourceNode.y) * p.progress;

                // Draw particle with gradient color
                const color = p.sourceNode.isStart ? '34, 228, 255' : '255, 255, 255';

                this.ctx.beginPath();
                this.ctx.arc(x, y, p.size, 0, Math.PI * 2);
                this.ctx.fillStyle = `rgba(${color}, ${1.0 - p.progress * 0.5})`;
                this.ctx.shadowBlur = 10;
                this.ctx.shadowColor = `rgba(${color}, 0.8)`;
                this.ctx.fill();
                this.ctx.shadowBlur = 0;
            }
        });

        // Draw all nodes
        this.pathNodes.forEach(node => {
            if (node.isActive) {
                node.pulsePhase += 0.1;
            }

            // In graph mode, check if node is in highlighted path
            let isHighlighted = false;
            if (this.graphMode && this.highlightedPathIndex >= 0 && this.allPaths) {
                isHighlighted = this.allPaths[this.highlightedPathIndex].path.includes(node.label);
            }

            // Draw pulse ring if exists
            if (node.pulseRadius) {
                this.ctx.beginPath();
                this.ctx.arc(node.x, node.y, node.pulseRadius, 0, Math.PI * 2);
                this.ctx.strokeStyle = `rgba(${node.getColor()}, ${1.0 - node.pulseRadius / 30})`;
                this.ctx.lineWidth = 2;
                this.ctx.stroke();
            }

            // Check if this node is hovered
            const isHovered = this.hoveredNode === node;
            node.draw(this.ctx, isHovered, isHighlighted);
        });
    }

    startConnection() {
        this.connectionLine = true;
        this.connectionProgress = 0;
    }

    converge() {
        // Make particles move toward the connection line
        const centerX = this.canvas.width / 2;

        this.particles.forEach(p => {
            const targetY = this.centerY;
            const targetX = p.direction === 'forward' ? centerX : centerX;

            const dx = targetX - p.x;
            const dy = targetY - p.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist > 5) {
                p.vx = (dx / dist) * 3;
                p.vy = (dy / dist) * 3;
            }
        });

        // Shrink waves
        const shrinkInterval = setInterval(() => {
            this.forwardWaveRadius *= 0.9;
            this.backwardWaveRadius *= 0.9;
            if (this.forwardWaveRadius < 10 && this.backwardWaveRadius < 10) {
                clearInterval(shrinkInterval);
                setTimeout(() => this.stop(), 1000);
            }
        }, 30);
    }

    handleMouseMove(e) {
        const rect = this.canvas.getBoundingClientRect();
        this.mouseX = e.clientX - rect.left;
        this.mouseY = e.clientY - rect.top;

        // Check if hovering over any node
        let foundHover = false;
        for (const node of this.pathNodes) {
            const dx = this.mouseX - node.x;
            const dy = this.mouseY - node.y;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (distance <= node.radius + 10) {
                // Hovering over this node
                if (this.hoveredNode !== node) {
                    this.hoveredNode = node;
                    this.canvas.style.cursor = 'pointer';
                }
                foundHover = true;
                break;
            }
        }

        if (!foundHover && this.hoveredNode) {
            this.hoveredNode = null;
            this.canvas.style.cursor = 'default';
        }
    }

    handleClick(e) {
        if (this.hoveredNode) {
            // Open Wikipedia page for clicked node
            const pageTitle = this.hoveredNode.label;
            window.open(`https://en.wikipedia.org/wiki/${encodeURIComponent(pageTitle)}`, '_blank');
        }
    }

    handleMouseOut() {
        this.hoveredNode = null;
        this.canvas.style.cursor = 'default';
    }

    /**
     * Build graph path - animate all nodes and edges for merged graph
     */
    buildGraphPath(graphData, allPaths) {
        this.graphMode = true;
        this.graphData = graphData;
        this.allPaths = allPaths;
        this.highlightedPathIndex = 0;

        // Create PathNode objects for all graph nodes
        this.pathNodes = graphData.nodes.map((node, index) => {
            return new PathNode(
                node.x,
                node.y,
                node.title,
                index,
                node.isStart || false,
                node.isEnd || false
            );
        });

        // Store graph nodes reference
        this.graphNodes = this.pathNodes;

        // Initialize all nodes with zero opacity (they'll fade in during convergence)
        this.pathNodes.forEach(node => {
            node.opacity = 0;
            node.labelOpacity = 0;
        });

        // Create all edges (connections between nodes)
        this.pathConnections = [];
        graphData.edges.forEach(edge => {
            const fromNode = this.pathNodes.find(n => n.label === edge.from);
            const toNode = this.pathNodes.find(n => n.label === edge.to);

            if (fromNode && toNode) {
                this.pathConnections.push({
                    from: fromNode,
                    to: toNode,
                    progress: 0,
                    pathIndices: edge.pathIndices,
                    thickness: edge.thickness
                });
            }
        });

        // Freeze background particles for convergence
        this.backgroundParticles.forEach(p => {
            p.frozen = true;
        });

        // Reset connection tracking
        this.connectionIndex = 0;
        this.connectionParticles = [];

        // Populate intermediateNodeData with all graph node positions for particle convergence
        this.intermediateNodeData = this.pathNodes.map(node => ({
            x: node.x,
            y: node.y,
            label: node.label,
            index: node.index
        }));

        // Start convergence animation
        this.animationState = 'CONVERGING';
        this.startConvergence();
    }

    /**
     * Convert existing particles to be attracted to graph nodes
     */
    convertToGraphParticles() {
        // Keep background particles but make them attracted to nodes
        this.backgroundParticles = this.backgroundParticles.slice(0, 80); // Increase to 80 particles

        // Add more particles if needed
        while (this.backgroundParticles.length < 80) {
            this.backgroundParticles.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                vx: (Math.random() - 0.5) * 1.5,
                vy: (Math.random() - 0.5) * 1.5,
                size: 0.8 + Math.random() * 1.2,
                opacity: 0.3 + Math.random() * 0.3,
                color: Math.random() > 0.5 ? '34, 228, 255' : '0, 255, 191',
                targetNode: null
            });
        }

        // Assign target nodes to particles
        this.backgroundParticles.forEach(particle => {
            particle.targetNode = this.graphNodes[Math.floor(Math.random() * this.graphNodes.length)];
        });
    }

    /**
     * Highlight a specific path in the graph
     */
    highlightPath(pathIndex) {
        this.highlightedPathIndex = pathIndex;
    }

    /**
     * Update particles in graph mode - attracted to nearest forward node
     */
    updateGraphParticles() {
        this.backgroundParticles.forEach(particle => {
            // Find nodes to the right (forward direction)
            const forwardNodes = this.graphNodes.filter(n => n.x > particle.x);

            // If no forward nodes, reset to left side
            if (forwardNodes.length === 0) {
                particle.x = 50;
                particle.y = Math.random() * this.canvas.height;
                particle.targetNode = this.graphNodes[0];
                return;
            }

            // Find nearest forward node
            let nearest = forwardNodes[0];
            let minDist = this.distance(particle, nearest);

            forwardNodes.forEach(node => {
                const dist = this.distance(particle, node);
                if (dist < minDist) {
                    minDist = dist;
                    nearest = node;
                }
            });

            particle.targetNode = nearest;

            // Apply attraction force
            const dx = nearest.x - particle.x;
            const dy = nearest.y - particle.y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist > 5) {
                const force = 0.02; // Attraction strength
                particle.vx += (dx / dist) * force;
                particle.vy += (dy / dist) * force;

                // Apply damping
                particle.vx *= 0.95;
                particle.vy *= 0.95;

                // Limit speed
                const speed = Math.sqrt(particle.vx * particle.vx + particle.vy * particle.vy);
                if (speed > 3) {
                    particle.vx = (particle.vx / speed) * 3;
                    particle.vy = (particle.vy / speed) * 3;
                }

                particle.x += particle.vx;
                particle.y += particle.vy;
            }

            // Bounce off canvas edges
            if (particle.x < 0 || particle.x > this.canvas.width) particle.vx *= -0.5;
            if (particle.y < 0 || particle.y > this.canvas.height) particle.vy *= -0.5;
        });
    }

    /**
     * Draw the graph (nodes and edges)
     */
    drawGraph() {
        const ctx = this.ctx;

        // Draw edges first (behind nodes)
        this.graphData.edges.forEach(edge => {
            const fromNode = this.graphNodes.find(n => n.label === edge.from);
            const toNode = this.graphNodes.find(n => n.label === edge.to);

            if (!fromNode || !toNode) return;

            // Check if this edge is in the highlighted path
            const isHighlighted = this.highlightedPathIndex >= 0 &&
                edge.pathIndices.includes(this.highlightedPathIndex);

            // Set opacity based on highlight state
            const opacity = isHighlighted ? 0.8 : 0.3;

            ctx.save();
            ctx.strokeStyle = `rgba(34, 228, 255, ${opacity})`;
            ctx.lineWidth = edge.thickness;
            ctx.lineCap = 'round';

            // Add glow for highlighted edges
            if (isHighlighted) {
                ctx.shadowBlur = 15;
                ctx.shadowColor = 'rgba(34, 228, 255, 0.8)';
            }

            ctx.beginPath();
            ctx.moveTo(fromNode.x, fromNode.y);
            ctx.lineTo(toNode.x, toNode.y);
            ctx.stroke();

            ctx.restore();
        });

        // Draw nodes on top
        this.graphNodes.forEach(node => {
            // Check if this node is in the highlighted path
            const isHighlighted = this.highlightedPathIndex >= 0 &&
                this.allPaths[this.highlightedPathIndex].path.includes(node.label);

            const isHovered = this.hoveredNode === node;

            // Enhance node appearance if highlighted
            if (isHighlighted) {
                node.pulsePhase = (node.pulsePhase || 0) + 0.1;
            }

            node.draw(ctx, isHovered, isHighlighted);
        });
    }

    /**
     * Calculate distance between two points
     */
    distance(p1, p2) {
        const dx = p1.x - p2.x;
        const dy = p1.y - p2.y;
        return Math.sqrt(dx * dx + dy * dy);
    }

    /**
     * Update hovered node in graph mode
     */
    updateGraphHover() {
        let foundHover = false;

        for (const node of this.graphNodes) {
            const dx = this.mouseX - node.x;
            const dy = this.mouseY - node.y;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (distance < node.size + 10) {
                if (this.hoveredNode !== node) {
                    this.hoveredNode = node;
                    this.canvas.style.cursor = 'pointer';
                }
                foundHover = true;
                break;
            }
        }

        if (!foundHover && this.hoveredNode) {
            this.hoveredNode = null;
            this.canvas.style.cursor = 'default';
        }
    }
}
