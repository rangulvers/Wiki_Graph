/**
 * PathNode - Represents a node in the Wikipedia path visualization
 *
 * Handles rendering of individual nodes with:
 * - Pulsing animations
 * - Hover effects
 * - Tooltips
 * - Color coding (start, end, intermediate)
 */
export class PathNode {
    constructor(x, y, label, index, isStart, isEnd) {
        this.x = x;
        this.y = y;
        this.label = label;
        this.index = index;
        this.radius = 8;
        this.isStart = isStart;
        this.isEnd = isEnd;
        this.isActive = false;
        this.pulsePhase = 0;
        this.opacity = 0;
        this.labelOpacity = 0;
    }

    getColor() {
        if (this.isStart) return '29, 232, 247'; // Cyan
        if (this.isEnd) return '0, 255, 200'; // Green
        return '179, 229, 255'; // Blue-white
    }

    draw(ctx, isHovered = false) {
        const pulse = this.isActive ? Math.sin(this.pulsePhase) * 0.3 + 0.7 : 1.0;
        const hoverScale = isHovered ? 1.3 : 1.0;
        const color = this.getColor();

        // Draw glow (enhanced on hover)
        ctx.shadowBlur = isHovered ? 40 : (this.isActive ? 30 : 15);
        ctx.shadowColor = `rgba(${color}, ${this.opacity})`;

        // Draw node (larger on hover)
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius * pulse * hoverScale, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${color}, ${this.opacity})`;
        ctx.fill();

        // Draw outer ring (brighter on hover)
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius * pulse * hoverScale + 3, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${color}, ${this.opacity * (isHovered ? 0.8 : 0.5)})`;
        ctx.lineWidth = isHovered ? 3 : 2;
        ctx.stroke();

        ctx.shadowBlur = 0;

        // Draw label (always visible on hover)
        const labelOpacity = isHovered ? 1.0 : this.labelOpacity;
        if (labelOpacity > 0) {
            ctx.font = isHovered ? 'bold 14px Inter' : '12px Inter';
            ctx.fillStyle = `rgba(255, 255, 255, ${labelOpacity})`;
            ctx.textAlign = 'center';
            ctx.fillText(this.label, this.x, this.y - (isHovered ? 25 : 20));
        }

        // Draw tooltip on hover
        if (isHovered && this.opacity > 0.5) {
            this.drawTooltip(ctx);
        }
    }

    drawTooltip(ctx) {
        // Measure text for tooltip sizing
        ctx.font = 'bold 13px Inter';
        const textWidth = ctx.measureText(this.label).width;
        const padding = 12;
        const tooltipWidth = textWidth + padding * 2;
        const tooltipHeight = 32;
        const tooltipX = this.x - tooltipWidth / 2;
        const tooltipY = this.y - 50;

        // Draw tooltip background
        ctx.shadowBlur = 15;
        ctx.shadowColor = 'rgba(0, 0, 0, 0.5)';

        ctx.fillStyle = 'rgba(17, 23, 62, 0.95)';
        ctx.beginPath();
        ctx.roundRect(tooltipX, tooltipY, tooltipWidth, tooltipHeight, 8);
        ctx.fill();

        // Draw tooltip border
        ctx.strokeStyle = `rgba(${this.getColor()}, 0.8)`;
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.shadowBlur = 0;

        // Draw tooltip text
        ctx.font = 'bold 13px Inter';
        ctx.fillStyle = `rgba(${this.getColor()}, 1.0)`;
        ctx.textAlign = 'center';
        ctx.fillText(this.label, this.x, tooltipY + 20);

        // Draw small arrow pointing to node
        ctx.fillStyle = 'rgba(17, 23, 62, 0.95)';
        ctx.beginPath();
        ctx.moveTo(this.x, tooltipY + tooltipHeight);
        ctx.lineTo(this.x - 6, tooltipY + tooltipHeight);
        ctx.lineTo(this.x, tooltipY + tooltipHeight + 6);
        ctx.lineTo(this.x + 6, tooltipY + tooltipHeight);
        ctx.closePath();
        ctx.fill();
    }
}
