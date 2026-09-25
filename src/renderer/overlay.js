const { ipcRenderer } = require('electron');

const canvas = document.getElementById('overlayCanvas');
const ctx = canvas.getContext('2d');

let lastConfig = null;

function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    if (lastConfig) {
        drawCrosshair(lastConfig);
    }
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

ipcRenderer.on('crosshair:draw', (event, config) => {
    lastConfig = config;
    drawCrosshair(config);
});

function drawCrosshair(config) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!config) return;

    // Overlay is centered inside a 300x300 window, adjusted by custom offsets (forced to 0 in lines mode)
    const isLines = config.mode === 'lines';
    const cx = canvas.width / 2 + (isLines ? 0 : (config.offsetX || 0));
    const cy = canvas.height / 2 + (isLines ? 0 : (config.offsetY || 0));
    const size = config.size;
    const gap = config.centerGap;
    const thick = config.thickness;
    const color = config.color;
    const mode = config.mode;
    const fill = config.fillShape;

    ctx.lineWidth = thick;
    ctx.lineCap = 'round';
    ctx.globalAlpha = config.opacity !== undefined ? config.opacity : 1.0;

    let targetStyle = color;
    if (config.gradientEffect) {
        // Parse hex color into RGB components
        let r = 212, g = 168, b = 83; // default gold color
        const cleanHex = color.replace('#', '');
        if (cleanHex.length === 6) {
            r = parseInt(cleanHex.substring(0, 2), 16);
            g = parseInt(cleanHex.substring(2, 4), 16);
            b = parseInt(cleanHex.substring(4, 6), 16);
        }
        
        // Create radial gradient centered at crosshair origin
        const innerR = Math.max(0, gap);
        const outerR = gap + size;
        const grad = ctx.createRadialGradient(cx, cy, innerR, cx, cy, outerR);
        
        // Smooth transition: Solid color inside (center) to transparent fade outside (tips)
        grad.addColorStop(0, `rgba(${r}, ${g}, ${b}, 1.0)`);
        grad.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0.0)`);
        targetStyle = grad;
    }

    ctx.strokeStyle = targetStyle;
    ctx.fillStyle = targetStyle;

    if (mode === 'lines') {
        const totalBars = config.barCount;
        for (let i = 0; i < totalBars; i++) {
            // Apply universal rotation shift (-90deg) so Top is vertical (for 2, 3, 4 bars layout)
            const angle = (i * 2 * Math.PI) / totalBars - Math.PI / 2;

            // Check if this specific line index is enabled in the dynamic activeLines list
            if (config.activeLines && config.activeLines[i] === false) {
                continue;
            }

            const x1 = cx + gap * Math.cos(angle);
            const y1 = cy + gap * Math.sin(angle);
            const x2 = cx + (gap + size) * Math.cos(angle);
            const y2 = cy + (gap + size) * Math.sin(angle);

            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
        }
        
        // Draw small center dot if fill is true and gap exists
        if (gap > 2 && fill) {
            ctx.beginPath();
            ctx.arc(cx, cy, 1.5, 0, Math.PI * 2);
            ctx.fill();
        }
    } 
    else if (mode === 'circle') {
        ctx.beginPath();
        ctx.arc(cx, cy, size, 0, Math.PI * 2);
        if (fill) {
            ctx.fill();
        }
        ctx.stroke();

        if (gap > 0) {
            ctx.beginPath();
            ctx.arc(cx, cy, 1, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
        }
    } 
    else if (mode === 'square') {
        ctx.beginPath();
        ctx.rect(cx - size, cy - size, size * 2, size * 2);
        if (fill) {
            ctx.fill();
        }
        ctx.stroke();
    } 
    else if (mode === 'triangle') {
        ctx.beginPath();
        if (config.flipTriangle) {
            ctx.moveTo(cx, cy + size);
            ctx.lineTo(cx + size, cy - size * 0.5);
            ctx.lineTo(cx - size, cy - size * 0.5);
        } else {
            ctx.moveTo(cx, cy - size);
            ctx.lineTo(cx + size, cy + size * 0.5);
            ctx.lineTo(cx - size, cy + size * 0.5);
        }
        ctx.closePath();
        if (fill) {
            ctx.fill();
        }
        ctx.stroke();
    } 
    else if (mode === 'diamond') {
        ctx.beginPath();
        ctx.moveTo(cx, cy - size);
        ctx.lineTo(cx + size, cy);
        ctx.lineTo(cx, cy + size);
        ctx.lineTo(cx - size, cy);
        ctx.closePath();
        if (fill) {
            ctx.fill();
        }
        ctx.stroke();
    }

    // Reset global opacity after drawing
    ctx.globalAlpha = 1.0;
}

// Notify main process that the overlay window is ready
ipcRenderer.send('overlay:ready');
