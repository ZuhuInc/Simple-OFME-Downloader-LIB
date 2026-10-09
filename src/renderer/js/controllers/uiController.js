/**
 * UI Controller
 * Manages particle backdrop, sidebar tabs navigation, toast notifications, and titlebar window controls.
 */

class UIController {
    constructor() {
        this.navTabs = document.querySelectorAll('.sidebar-nav-item');
        this.tabContents = document.querySelectorAll('.tab-content-panel');
        this.toastContainer = document.getElementById('toastContainer');
    }

    init() {
        this.initParticles();
        this.bindNavigation();
        this.bindWindowControls();
    }

    bindNavigation() {
        this.navTabs.forEach(item => {
            item.addEventListener('click', () => {
                const targetTab = item.dataset.tab;
                this.switchTab(targetTab);
            });
        });
    }

    switchTab(tabId) {
        this.navTabs.forEach(item => {
            item.classList.toggle('active', item.dataset.tab === tabId);
        });

        this.tabContents.forEach(content => {
            content.classList.toggle('active', content.id === tabId);
        });

        if (tabId === 'versionCheckerTab' && window.versionCheckerController) {
            window.versionCheckerController.loadSavedCredentials();
        } else if (tabId === 'settingsTab' && window.settingsController) {
            window.settingsController.loadSettings();
        } else if (tabId === 'steamTab' && window.steamController) {
            window.steamController.loadSteamInfo();
        }
    }

    bindWindowControls() {
        const api = window.api || window.fantaAPI;
        if (!api) return;

        const minBtn = document.getElementById('minBtn');
        const maxBtn = document.getElementById('maxBtn');
        const closeBtn = document.getElementById('closeBtn');

        if (minBtn) minBtn.addEventListener('click', () => api.minimizeWindow && api.minimizeWindow());
        if (maxBtn) maxBtn.addEventListener('click', () => api.maximizeWindow && api.maximizeWindow());
        if (closeBtn) closeBtn.addEventListener('click', () => api.closeWindow && api.closeWindow());
    }

    showToast(message, type = 'info', duration = 3500, action = null) {
        if (!this.toastContainer) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        let icon = 'fa-info-circle';
        if (type === 'success') icon = 'fa-check-circle';
        if (type === 'danger') icon = 'fa-triangle-exclamation';
        if (type === 'warning') icon = 'fa-circle-exclamation';

        let actionHtml = '';
        if (action && action.text) {
            const actionIcon = action.icon ? `<i class="fa-solid ${action.icon}" style="margin-right: 4px;"></i>` : '';
            actionHtml = `<button class="toast-action-btn">${actionIcon}${action.text}</button>`;
        }

        toast.innerHTML = `
            <i class="fa-solid ${icon}"></i>
            <span style="flex: 1;">${message}</span>
            ${actionHtml}
        `;

        if (action && action.callback) {
            const btn = toast.querySelector('.toast-action-btn');
            if (btn) {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    action.callback();
                    toast.classList.remove('visible');
                    setTimeout(() => toast.remove(), 250);
                });
            }
        }

        this.toastContainer.appendChild(toast);

        // Slide in
        setTimeout(() => toast.classList.add('visible'), 20);

        // Remove
        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.remove('visible');
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);
    }

    initParticles() {
        const canvas = document.getElementById('particleCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        let particles = [];
        let mouse = { x: null, y: null };

        function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        }
        window.addEventListener('resize', resize);
        resize();

        class Particle {
            constructor() {
                this.x = Math.random() * canvas.width;
                this.y = Math.random() * canvas.height;
                this.vx = (Math.random() - 0.5) * 0.4;
                this.vy = (Math.random() - 0.5) * 0.4;
                this.size = Math.random() * 2 + 1;
                this.opacity = Math.random() * 0.35 + 0.15;
            }

            update() {
                this.x += this.vx;
                this.y += this.vy;
                if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
                if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
            }

            draw() {
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(212, 168, 83, ${this.opacity})`;
                ctx.fill();
            }
        }

        const count = Math.min(50, Math.floor((canvas.width * canvas.height) / 25000));
        for (let i = 0; i < count; i++) {
            particles.push(new Particle());
        }

        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            particles.forEach(p => {
                p.update();
                p.draw();
            });
            requestAnimationFrame(animate);
        }
        animate();
    }
}

window.uiController = new UIController();
