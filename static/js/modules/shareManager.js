/**
 * shareManager.js - Social media sharing functionality
 *
 * Handles:
 * - Screenshot capture of path visualization
 * - Share text generation
 * - Native Web Share API integration
 * - Fallback for unsupported browsers
 */

/**
 * Generate share text for social media
 */
function generateShareText(startTerm, endTerm, pathCount, hops, pagesChecked) {
    const pathText = pathCount > 1 ? `${pathCount} paths` : 'a path';
    const hopText = hops === 1 ? '1 hop' : `${hops} hops`;

    // Keep it concise for Twitter (280 char limit)
    const text = `I found ${pathText} between "${startTerm}" and "${endTerm}" on Wikipedia! ${hopText}, ${pagesChecked} pages checked. Check it out at https://wikigraph.up.railway.app`;

    return text;
}

/**
 * Add branding watermark to canvas context
 */
function addBranding(canvas, ctx) {
    const text = 'wikigraph.up.railway.app';
    const padding = 20;
    const fontSize = 14;

    ctx.save();
    ctx.font = `${fontSize}px 'Inter', system-ui, sans-serif`;
    ctx.fillStyle = 'rgba(148, 163, 184, 0.6)';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'bottom';

    // Position in bottom-right corner
    ctx.fillText(text, canvas.width - padding, canvas.height - padding);
    ctx.restore();
}

/**
 * Capture the canvas and overlay as a single image
 */
async function captureVisualization() {
    try {
        const loadingContainer = document.getElementById('loading');

        // Use html2canvas to capture the entire container (canvas + overlays)
        const canvas = await html2canvas(loadingContainer, {
            backgroundColor: '#020617',
            scale: 2, // Higher quality
            logging: false,
            useCORS: true,
            allowTaint: true
        });

        // Add branding watermark
        const ctx = canvas.getContext('2d');
        addBranding(canvas, ctx);

        // Convert to blob
        return new Promise((resolve, reject) => {
            canvas.toBlob((blob) => {
                if (blob) {
                    resolve(blob);
                } else {
                    reject(new Error('Failed to create image blob'));
                }
            }, 'image/png', 0.95);
        });
    } catch (error) {
        console.error('Screenshot capture failed:', error);
        throw error;
    }
}

/**
 * Share using native Web Share API
 */
async function shareViaWebAPI(imageBlob, shareText) {
    if (!navigator.share) {
        throw new Error('Web Share API not supported');
    }

    try {
        // Create a file from the blob
        const file = new File([imageBlob], 'wikipedia-connection.png', { type: 'image/png' });

        // Check if we can share files
        if (navigator.canShare && !navigator.canShare({ files: [file] })) {
            // Fallback: share just the text if files aren't supported
            await navigator.share({
                title: 'Wikipedia Connection Found',
                text: shareText
            });
            return { shared: true, method: 'text-only' };
        }

        // Share both image and text
        await navigator.share({
            title: 'Wikipedia Connection Found',
            text: shareText,
            files: [file]
        });

        return { shared: true, method: 'full' };
    } catch (error) {
        if (error.name === 'AbortError') {
            // User cancelled the share dialog
            return { shared: false, cancelled: true };
        }
        throw error;
    }
}

/**
 * Copy text to clipboard using multiple fallback methods
 */
async function copyTextToClipboard(text) {
    // Method 1: Try modern clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (err) {
            console.log('Clipboard API failed, trying fallback:', err);
        }
    }

    // Method 2: Legacy fallback using textarea
    try {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        textarea.style.pointerEvents = 'none';
        document.body.appendChild(textarea);
        textarea.select();
        textarea.setSelectionRange(0, text.length);
        const success = document.execCommand('copy');
        document.body.removeChild(textarea);
        return success;
    } catch (err) {
        console.error('All clipboard methods failed:', err);
        return false;
    }
}

/**
 * Show modal with share text that user can copy
 */
function showShareTextModal(shareText) {
    const modal = document.createElement('div');
    modal.className = 'share-text-modal';
    modal.innerHTML = `
        <div class="share-text-modal-content">
            <h3>Share Text</h3>
            <p>Copy this text to share with your post:</p>
            <textarea readonly class="share-text-area">${shareText}</textarea>
            <div class="share-text-modal-buttons">
                <button class="copy-text-btn">Copy Text</button>
                <button class="close-modal-btn">Close</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Auto-select text
    const textarea = modal.querySelector('.share-text-area');
    textarea.focus();
    textarea.select();

    // Copy button
    modal.querySelector('.copy-text-btn').addEventListener('click', async () => {
        textarea.select();
        const success = await copyTextToClipboard(shareText);
        const btn = modal.querySelector('.copy-text-btn');
        if (success) {
            btn.textContent = '✓ Copied!';
            btn.style.background = 'linear-gradient(90deg, #00ffbf, #22e4ff)';
            setTimeout(() => {
                document.body.removeChild(modal);
            }, 1000);
        } else {
            btn.textContent = 'Select & Copy Manually';
        }
    });

    // Close button
    modal.querySelector('.close-modal-btn').addEventListener('click', () => {
        document.body.removeChild(modal);
    });

    // Click outside to close
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            document.body.removeChild(modal);
        }
    });
}

/**
 * Fallback: Download image and copy text to clipboard
 */
async function fallbackShare(imageBlob, shareText) {
    // Download the image
    const url = URL.createObjectURL(imageBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'wikipedia-connection.png';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    // Try to copy text to clipboard
    const copied = await copyTextToClipboard(shareText);

    if (copied) {
        return { shared: true, method: 'download-and-copy', textCopied: true };
    } else {
        // Show modal with text if clipboard failed
        showShareTextModal(shareText);
        return { shared: true, method: 'download-with-modal', textCopied: false };
    }
}

/**
 * Show toast notification
 */
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `share-toast share-toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    // Trigger animation
    setTimeout(() => toast.classList.add('show'), 10);

    // Remove after 3 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => document.body.removeChild(toast), 300);
    }, 3000);
}

/**
 * Main share function
 */
export async function shareResult(searchData) {
    const { startTerm, endTerm, pathCount, hops, pagesChecked } = searchData;

    // Show loading state
    const shareBtn = document.getElementById('share-btn');
    const originalHTML = shareBtn.innerHTML;
    shareBtn.disabled = true;
    shareBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinner-icon">
            <circle cx="12" cy="12" r="10"></circle>
        </svg>
        <span>Preparing...</span>
    `;

    try {
        // Capture screenshot
        const imageBlob = await captureVisualization();

        // Generate share text
        const shareText = generateShareText(startTerm, endTerm, pathCount, hops, pagesChecked);

        // Try native share first
        if (navigator.share) {
            // ALWAYS copy text to clipboard first (since Web Share API often ignores text param with files)
            await copyTextToClipboard(shareText);

            const result = await shareViaWebAPI(imageBlob, shareText);

            if (result.shared) {
                if (result.method === 'full') {
                    showToast('Image shared! Share text copied to clipboard - paste it with your image.');
                } else if (result.method === 'text-only') {
                    showToast('Text shared! (Image sharing not supported on this device)');
                }
            }
            // If cancelled, don't show any message
        } else {
            // Fallback for desktop browsers
            const result = await fallbackShare(imageBlob, shareText);

            if (result.textCopied) {
                showToast('Image downloaded and share text copied to clipboard!');
            } else {
                showToast('Image downloaded! Copy the text from the popup.');
            }
        }
    } catch (error) {
        console.error('Share failed:', error);
        showToast('Failed to share. Please try again.', 'error');
    } finally {
        // Restore button state
        shareBtn.disabled = false;
        shareBtn.innerHTML = originalHTML;
    }
}

/**
 * Initialize share button
 */
export function initShareButton(searchData) {
    const shareBtn = document.getElementById('share-btn');

    if (!shareBtn) {
        console.error('Share button not found');
        return;
    }

    // Show the button
    shareBtn.classList.remove('hidden');

    // Remove old listener if exists
    const newBtn = shareBtn.cloneNode(true);
    shareBtn.parentNode.replaceChild(newBtn, shareBtn);

    // Add click listener
    newBtn.addEventListener('click', () => shareResult(searchData));
}
