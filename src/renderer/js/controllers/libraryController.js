/**
 * Library Controller
 * Manages game grid rendering, instant search, host & status filtering, and sorting.
 */

class LibraryController {
    constructor() {
        this.games = [];
        this.filteredGames = [];
        this.currentFilter = 'all';
        this.currentHost = '';
        this.searchQuery = '';
        this.sortBy = 'default';
        this.gridEl = document.getElementById('gameGrid');
        this.searchEl = document.getElementById('gameSearchInput');
        this.hostSelectEl = document.getElementById('hostFilterSelect');
        this.sortSelectEl = document.getElementById('sortFilterSelect');
        this.filterPills = document.querySelectorAll('.filter-pill');
        this.gameCountEl = document.getElementById('libraryGameCount');
    }

    init() {
        this.bindEvents();
        this.loadGames();
    }

    bindEvents() {
        if (this.searchEl) {
            this.searchEl.addEventListener('input', (e) => {
                this.searchQuery = e.target.value.trim().toLowerCase();
                this.applyFilters();
            });
        }

        if (this.hostSelectEl) {
            this.hostSelectEl.addEventListener('change', (e) => {
                this.currentHost = e.target.value;
                this.applyFilters();
            });
        }

        if (this.sortSelectEl) {
            this.sortSelectEl.addEventListener('change', (e) => {
                this.sortBy = e.target.value;
                this.applyFilters();
            });
        }

        this.filterPills.forEach(pill => {
            pill.addEventListener('click', () => {
                this.filterPills.forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                this.currentFilter = pill.dataset.filter || 'all';
                this.applyFilters();
            });
        });

        const refreshBtn = document.getElementById('refreshLibraryBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshLibrary());
        }

        // Auto-load as soon as bridge socket connects
        window.apiClient.on('bridge_status', (status) => {
            if (status.connected && this.games.length === 0) {
                this.loadGames();
            }
        });
    }

    renderSkeletons() {
        if (!this.gridEl) return;
        let html = '';
        for (let i = 0; i < 12; i++) {
            html += `
                <div class="game-card skeleton-card">
                    <div class="skeleton-cover shimmer"></div>
                    <div class="skeleton-info">
                        <div class="skeleton-line shimmer" style="width: 75%;"></div>
                        <div class="skeleton-line shimmer" style="width: 45%; height: 10px; margin-top: 6px;"></div>
                    </div>
                </div>
            `;
        }
        this.gridEl.innerHTML = html;
        if (this.gameCountEl) this.gameCountEl.textContent = 'Syncing catalog database...';
    }

    async loadGames() {
        if (!this.gridEl) return;
        this.renderSkeletons();

        try {
            const data = await window.apiClient.getGames();
            this.games = data.games || [];
            this.populateHostFilter(data.hosts || []);
            this.applyFilters();
        } catch (err) {
            this.gridEl.innerHTML = `
                <div class="grid-empty-card glass-card">
                    <div class="empty-icon-circle" style="border-color: rgba(224, 82, 82, 0.3); color: var(--danger); background: rgba(224, 82, 82, 0.1);">
                        <i class="fa-solid fa-circle-exclamation"></i>
                    </div>
                    <h3 class="empty-title">Connection Error</h3>
                    <p class="empty-subtitle">Could not connect to the backend server. Make sure the Python bridge is active.</p>
                    <button class="btn btn-primary" onclick="window.libraryController.loadGames()">
                        <i class="fa-solid fa-arrows-rotate"></i> Retry Connection
                    </button>
                </div>
            `;
        }
    }

    async refreshLibrary() {
        const btn = document.getElementById('refreshLibraryBtn');
        if (btn) btn.classList.add('fa-spin');
        try {
            const res = await window.apiClient.refreshGames();
            if (res.success) {
                window.uiController.showToast('Game database refreshed successfully', 'success');
                await this.loadGames();
            }
        } catch (err) {
            window.uiController.showToast('Failed to refresh database', 'danger');
        } finally {
            if (btn) btn.classList.remove('fa-spin');
        }
    }

    populateHostFilter(hosts) {
        if (!this.hostSelectEl) return;
        const current = this.hostSelectEl.value;
        this.hostSelectEl.innerHTML = `<option value="">All Hosts</option>`;
        hosts.forEach(host => {
            const opt = document.createElement('option');
            opt.value = host;
            opt.textContent = host;
            this.hostSelectEl.appendChild(opt);
        });
        this.hostSelectEl.value = current;
    }

    applyFilters() {
        this.filteredGames = this.games.filter(game => {
            // Status check (0: missing, 1: up-to-date, 2: update available)
            if (this.currentFilter === '1' && game.status !== 1) return false;
            if (this.currentFilter === '2' && game.status !== 2) return false;
            if (this.currentFilter === '0' && game.status !== 0) return false;

            // Host check
            if (this.currentHost && game.host !== this.currentHost) return false;

            // Search query
            if (this.searchQuery) {
                const title = (game.title || '').toLowerCase();
                const desc = (game.description || '').toLowerCase();
                if (!title.includes(this.searchQuery) && !desc.includes(this.searchQuery)) {
                    return false;
                }
            }

            return true;
        });

        // Sorting
        if (this.sortBy === 'name-asc') {
            this.filteredGames.sort((a, b) => a.title.localeCompare(b.title));
        } else if (this.sortBy === 'name-desc') {
            this.filteredGames.sort((a, b) => b.title.localeCompare(a.title));
        } else if (this.sortBy === 'size') {
            this.filteredGames.sort((a, b) => (b.size || '').localeCompare(a.size || ''));
        }

        this.renderGrid();
    }

    renderGrid() {
        if (!this.gridEl) return;

        if (this.gameCountEl) {
            this.gameCountEl.textContent = `${this.filteredGames.length} of ${this.games.length} games`;
        }

        if (this.filteredGames.length === 0) {
            this.gridEl.innerHTML = `
                <div class="grid-empty-card glass-card">
                    <div class="empty-icon-circle">
                        <i class="fa-solid fa-ghost"></i>
                    </div>
                    <h3 class="empty-title">No Games Found</h3>
                    <p class="empty-subtitle">No games matched your active search or filter selection.</p>
                    <button class="btn btn-primary" onclick="window.libraryController.resetFilters()">
                        <i class="fa-solid fa-arrows-rotate"></i> Reset All Filters
                    </button>
                </div>
            `;
            return;
        }

        this.gridEl.innerHTML = '';
        this.filteredGames.forEach(game => {
            const card = document.createElement('div');
            card.className = `game-card status-${game.status}`;
            card.dataset.id = game.id;

            const statusClass = game.status === 1 ? 'status-uptodate' : (game.status === 2 ? 'status-update' : 'status-missing');
            const statusLabel = game.status === 1 ? 'INSTALLED' : (game.status === 2 ? 'UPDATE' : 'NOT INSTALLED');

            // Fallback poster if local image not found
            const thumbSrc = game.thumbnail || 'assets/Fanta-Logo.png';

            card.innerHTML = `
                <div class="card-cover-wrapper">
                    <img class="card-cover-img" src="${thumbSrc}" alt="${game.title}" loading="lazy" onerror="this.src='assets/Fanta-Logo.png'">
                    <span class="card-status-badge ${statusClass}">${statusLabel}</span>
                    <div class="card-overlay">
                        <button class="card-view-btn"><i class="fa-solid fa-arrow-up-right-from-square"></i> Details</button>
                    </div>
                </div>
                <div class="card-info">
                    <h3 class="card-title" title="${game.title}">${game.title}</h3>
                    <div class="card-meta">
                        <span class="card-host"><i class="fa-solid fa-server"></i> ${game.host || 'Unknown'}</span>
                        <span class="card-version">v${game.version || '1.0'}</span>
                    </div>
                </div>
            `;

            card.addEventListener('click', () => {
                window.detailsController.openGame(game);
            });

            this.gridEl.appendChild(card);
        });
    }

    resetFilters() {
        this.currentFilter = 'all';
        this.currentHost = '';
        this.searchQuery = '';
        this.sortBy = 'default';

        if (this.searchEl) this.searchEl.value = '';
        if (this.hostSelectEl) this.hostSelectEl.value = '';
        if (this.sortSelectEl) this.sortSelectEl.value = 'default';

        this.filterPills.forEach(p => {
            p.classList.toggle('active', p.dataset.filter === 'all');
        });

        this.applyFilters();
    }
}

window.libraryController = new LibraryController();
