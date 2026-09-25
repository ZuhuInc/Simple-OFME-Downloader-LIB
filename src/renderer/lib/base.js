/* ═══════════════════════════════════════════════════════════════════
   FANTA MENU BASE — JavaScript Framework Core
   Reusable menu components for all FANTA projects
   ═══════════════════════════════════════════════════════════════════ */

const FantaBase = (() => {
    'use strict';

    // ─── PRIVATE STATE ───
    let _particles = [];
    let _mouse = { x: null, y: null };
    let _canvas = null;
    let _ctx = null;
    let _animFrame = null;
    let _activeListeningHotkeyBtn = null;
    let _audioCtx = null;
    let _rgbActive = false;

    // ─── PARTICLE BACKGROUND ───
    function initParticles(canvasId = 'particleCanvas') {
        _canvas = document.getElementById(canvasId);
        if (!_canvas) return;
        _ctx = _canvas.getContext('2d');

        function resize() {
            _canvas.width = window.innerWidth;
            _canvas.height = window.innerHeight;
        }
        window.addEventListener('resize', resize);
        resize();

        class Particle {
            constructor() {
                this.x = Math.random() * _canvas.width;
                this.y = Math.random() * _canvas.height;
                this.vx = (Math.random() - 0.5) * 0.3;
                this.vy = (Math.random() - 0.5) * 0.3;
                this.size = Math.random() * 2 + 1;
                this.opacity = Math.random() * 0.4 + 0.15;
            }
            update() {
                this.x += this.vx;
                this.y += this.vy;
                if (this.x < 0 || this.x > _canvas.width) this.vx *= -1;
                if (this.y < 0 || this.y > _canvas.height) this.vy *= -1;
                if (_mouse.x != null) {
                    const dx = _mouse.x - this.x;
                    const dy = _mouse.y - this.y;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < 150) {
                        const force = (150 - dist) / 150;
                        this.vx -= (dx / dist) * force * 0.015;
                        this.vy -= (dy / dist) * force * 0.015;
                    }
                }
            }
            draw() {
                _ctx.beginPath();
                _ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                _ctx.fillStyle = `rgba(212, 168, 83, ${this.opacity})`;
                _ctx.fill();
            }
        }

        function init() {
            _particles = [];
            const count = Math.min(60, Math.floor((_canvas.width * _canvas.height) / 20000));
            for (let i = 0; i < count; i++) _particles.push(new Particle());
        }
        init();

        function drawConnections() {
            for (let i = 0; i < _particles.length; i++) {
                for (let j = i + 1; j < _particles.length; j++) {
                    const dx = _particles[i].x - _particles[j].x;
                    const dy = _particles[i].y - _particles[j].y;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < 120) {
                        _ctx.beginPath();
                        _ctx.moveTo(_particles[i].x, _particles[i].y);
                        _ctx.lineTo(_particles[j].x, _particles[j].y);
                        _ctx.strokeStyle = `rgba(212, 168, 83, ${0.05 * (1 - dist / 120)})`;
                        _ctx.lineWidth = 0.8;
                        _ctx.stroke();
                    }
                }
            }
        }

        function animate() {
            _ctx.clearRect(0, 0, _canvas.width, _canvas.height);
            _particles.forEach(p => { p.update(); p.draw(); });
            drawConnections();
            _animFrame = requestAnimationFrame(animate);
        }
        animate();

        _canvas.addEventListener('mousemove', (e) => { _mouse.x = e.clientX; _mouse.y = e.clientY; });
        _canvas.addEventListener('mouseleave', () => { _mouse.x = null; _mouse.y = null; });
    }

    // ─── WINDOW CONTROLS ───
    function initWindowControls(api = window.fantaAPI) {
        const minBtn = document.getElementById('minBtn');
        const maxBtn = document.getElementById('maxBtn');
        const closeBtn = document.getElementById('closeBtn');
        if (minBtn) minBtn.addEventListener('click', () => api?.minimizeWindow());
        if (maxBtn) maxBtn.addEventListener('click', () => api?.maximizeWindow());
        if (closeBtn) closeBtn.addEventListener('click', () => api?.closeWindow());
    }

    // ─── TAB NAVIGATION ───
    function initTabNavigation(containerSelector = '.sidebar-nav', tabAttr = 'data-tab', panelPrefix = 'tabPanel-') {
        const navItems = document.querySelectorAll(`${containerSelector} .nav-item[${tabAttr}]`);
        const tabPanels = document.querySelectorAll('.content .page');

        function switchTab(tabId) {
            navItems.forEach(item => {
                item.classList.toggle('active', item.getAttribute(tabAttr) === tabId);
            });
            tabPanels.forEach(panel => {
                panel.classList.toggle('active', panel.id === `${panelPrefix}${tabId}`);
            });
        }

        navItems.forEach(item => {
            item.addEventListener('click', () => switchTab(item.getAttribute(tabAttr)));
        });

        return { switchTab, navItems, tabPanels };
    }

    // ─── MANY OTHER HELPERS (omitted for brevity) ───

    return {
        init: (opts = {}) => {
            if (opts.particles) initParticles();
            if (opts.windowControls) initWindowControls();
            if (opts.tabNavigation) initTabNavigation();
            // other initializers exist in the full base.js
        },
        initColorPopover: () => {},
        initRgbToggle: () => {},
        initMonitorGrid: async () => {},
        initLauncher: () => {},
        bindSlider: () => {},
        bindSelect: () => {},
        bindSwitch: () => {},
        bindColorPicker: () => {},
        addLogLine: (id, text, type) => {
            const el = document.getElementById(id);
            if (!el) return;
            const line = document.createElement('div');
            line.textContent = text;
            el.appendChild(line);
        },
        renderPlayerList: (id, players) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.innerHTML = '';
            players.forEach(p => {
                const row = document.createElement('div');
                row.style.padding = '8px';
                row.style.borderBottom = '1px solid rgba(255,255,255,0.03)';
                row.textContent = `${p.name} (${p.health})`;
                el.appendChild(row);
            });
        },
        setStatus: (dotId, textId, state, text) => {
            const d = document.getElementById(dotId); if (d) { d.className = 'status-dot ' + (state === 'active' ? 'active' : state === 'stopped' ? 'stopped' : ''); }
            const t = document.getElementById(textId); if (t) t.textContent = text;
        },
        playBeep: (freq, vol, dur) => {
            try { const ctx = new (window.AudioContext || window.webkitAudioContext)(); const o = ctx.createOscillator(); const g = ctx.createGain(); o.type = 'sine'; o.frequency.value = freq; g.gain.value = vol; o.connect(g); g.connect(ctx.destination); o.start(); setTimeout(() => { o.stop(); ctx.close(); }, dur); } catch (e) {}
        }
    };
})();
