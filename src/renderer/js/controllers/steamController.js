/**
 * Steam Controller
 * Manages Steam profile detection, account switching, non-Steam shortcuts list/search,
 * shortcut launching, adding, and deletion.
 */

class SteamController {
    constructor() {
        this.steamPath = '';
        this.libraries = [];
        this.accounts = [];
        this.activeAccountId = '';
        this.activeAccount = null;
        this.shortcuts = [];
        this.filteredShortcuts = [];
        this.searchQuery = '';
        this.activeFilter = 'fanta'; // 'fanta' or 'all'
        this.activeGame = null;

        // Elements
        this.modal = document.getElementById('steamShortcutModal');
        this.personaEl = document.getElementById('steamPersonaName');
        this.accountIdEl = document.getElementById('steamAccountId');
        this.accountLoginEl = document.getElementById('steamAccountLogin');
        this.shortcutsCountEl = document.getElementById('steamShortcutsCount');
        this.steamPathEl = document.getElementById('steamPathLabel');
        this.accountSelect = document.getElementById('steamAccountSelect');
        this.tableBody = document.getElementById('steamShortcutsTableBody');
        this.searchInput = document.getElementById('steamShortcutSearchInput');
        this.rescanBtn = document.getElementById('rescanSteamBtn');
        this.restartSteamBtn = document.getElementById('restartSteamBtn');
        this.openAddBtn = document.getElementById('openAddManualShortcutBtn');
        this.filterFantaBtn = document.getElementById('steamFilterFantaBtn');
        this.filterAllBtn = document.getElementById('steamFilterAllBtn');
        this.fantaBadge = document.getElementById('fantaShortcutsCountBadge');
        this.allBadge = document.getElementById('allShortcutsCountBadge');
        this.avatarImg = document.getElementById('steamAvatarImg');
        this.avatarFallbackIcon = document.getElementById('steamAvatarFallbackIcon');
    }

    init() {
        this.bindEvents();
        this.loadSteamInfo();
    }

    bindEvents() {
        // Modal Events
        const closeBtn = document.getElementById('closeSteamModalBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeModal());
        }

        const confirmBtn = document.getElementById('confirmAddSteamBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => this.confirmAddShortcut());
        }

        const browseBtn = document.getElementById('browseSteamExeBtn');
        if (browseBtn) {
            browseBtn.addEventListener('click', async () => {
                const file = await window.api?.selectFile({
                    filters: [{ name: 'Game Executable', extensions: ['exe'] }]
                });
                const exeInput = document.getElementById('steamGameExeInput');
                if (file && exeInput) exeInput.value = file;
            });
        }

        // Toolbar Events
        if (this.restartSteamBtn) {
            this.restartSteamBtn.addEventListener('click', () => this.restartSteam());
        }

        if (this.rescanBtn) {
            this.rescanBtn.addEventListener('click', () => this.rescan());
        }

        if (this.openAddBtn) {
            this.openAddBtn.addEventListener('click', () => this.openAddShortcutDialog({ title: '' }));
        }

        if (this.accountSelect) {
            this.accountSelect.addEventListener('change', (e) => {
                this.switchAccount(e.target.value);
            });
        }

        if (this.filterFantaBtn) {
            this.filterFantaBtn.addEventListener('click', () => {
                this.setFilter('fanta');
            });
        }

        if (this.filterAllBtn) {
            this.filterAllBtn.addEventListener('click', () => {
                this.setFilter('all');
            });
        }

        if (this.searchInput) {
            this.searchInput.addEventListener('input', (e) => {
                this.searchQuery = e.target.value.trim().toLowerCase();
                this.renderShortcuts();
            });
        }
    }

    setFilter(filterMode) {
        this.activeFilter = filterMode;
        if (this.filterFantaBtn) {
            this.filterFantaBtn.classList.toggle('active', filterMode === 'fanta');
        }
        if (this.filterAllBtn) {
            this.filterAllBtn.classList.toggle('active', filterMode === 'all');
        }
        this.renderShortcuts();
    }

    async loadSteamInfo() {
        try {
            const data = await window.apiClient.getSteamAccounts();
            this.steamPath = data.steam_path || 'C:\\Program Files (x86)\\Steam';
            this.accounts = data.accounts || [];
            this.activeAccountId = data.active_user || (this.accounts[0]?.account_id || '');
            this.activeAccount = data.active_account || this.accounts.find(a => a.account_id === this.activeAccountId) || this.accounts[0] || null;

            this.updateProfileBanner();
            this.populateAccountSelect();

            if (this.activeAccountId) {
                await this.loadShortcuts(this.activeAccountId);
            }
        } catch (err) {
            console.error('[SteamController] Failed to load steam accounts:', err);
            if (this.tableBody) {
                this.tableBody.innerHTML = `
                    <tr class="empty-row">
                        <td colspan="4" style="text-align: center; color: var(--danger); padding: 36px;">
                            Failed to connect to Steam: ${err.message}
                        </td>
                    </tr>
                `;
            }
        }
    }

    updateProfileBanner() {
        if (this.personaEl) {
            this.personaEl.textContent = this.activeAccount?.persona_name || 'Steam User';
        }
        if (this.accountIdEl) {
            this.accountIdEl.textContent = this.activeAccountId || 'None Detected';
        }
        if (this.accountLoginEl) {
            this.accountLoginEl.textContent = this.activeAccount?.account_name || 'N/A';
        }
        if (this.shortcutsCountEl) {
            this.shortcutsCountEl.textContent = String(this.activeAccount?.shortcuts_count ?? this.shortcuts.length);
        }
        if (this.steamPathEl) {
            this.steamPathEl.textContent = this.steamPath || 'C:\\Program Files (x86)\\Steam';
            this.steamPathEl.title = this.steamPath;
        }

        // Avatar
        if (this.avatarImg && this.avatarFallbackIcon) {
            const avatarUrl = this.activeAccount?.avatar_url;
            if (avatarUrl) {
                this.avatarImg.src = avatarUrl;
                this.avatarImg.style.display = 'block';
                this.avatarFallbackIcon.style.display = 'none';
                this.avatarImg.onerror = () => {
                    this.avatarImg.style.display = 'none';
                    this.avatarFallbackIcon.style.display = 'block';
                };
            } else {
                this.avatarImg.style.display = 'none';
                this.avatarFallbackIcon.style.display = 'block';
            }
        }
    }

    populateAccountSelect() {
        if (!this.accountSelect) return;
        this.accountSelect.innerHTML = '';

        if (this.accounts.length === 0) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'No Steam Profiles Found';
            this.accountSelect.appendChild(opt);
            return;
        }

        this.accounts.forEach(acc => {
            const opt = document.createElement('option');
            opt.value = acc.account_id;
            const recentTag = acc.most_recent ? ' (Most Recent)' : '';
            const countTag = acc.shortcuts_count ? ` - ${acc.shortcuts_count} shortcuts` : '';
            opt.textContent = `${acc.persona_name} (${acc.account_id})${countTag}${recentTag}`;
            if (acc.account_id === this.activeAccountId) {
                opt.selected = true;
            }
            this.accountSelect.appendChild(opt);
        });
    }

    async switchAccount(accountId) {
        if (!accountId || accountId === this.activeAccountId) return;
        this.activeAccountId = accountId;
        this.activeAccount = this.accounts.find(a => a.account_id === accountId) || null;

        try {
            window.uiController.showToast('Switching Steam profile...', 'info');
            const res = await window.apiClient.selectSteamAccount(accountId);
            if (res.success) {
                this.activeAccount = res.active_account || this.activeAccount;
                this.updateProfileBanner();
                await this.loadShortcuts(accountId);
                window.uiController.showToast(`Switched to profile: ${this.activeAccount?.persona_name || accountId}`, 'success');
            }
        } catch (err) {
            window.uiController.showToast(`Failed to switch profile: ${err.message}`, 'danger');
        }
    }

    async rescan() {
        try {
            window.uiController.showToast('Re-scanning Steam profiles and shortcuts...', 'info');
            if (this.tableBody) {
                this.tableBody.innerHTML = `
                    <tr class="empty-row">
                        <td colspan="4" style="text-align: center; color: var(--text-muted); padding: 36px;">
                            <i class="fa-solid fa-spinner fa-spin" style="margin-right: 8px;"></i> Scanning Steam installation...
                        </td>
                    </tr>
                `;
            }

            const res = await window.apiClient.rescanSteam();
            if (res.success) {
                this.steamPath = res.steam_path;
                this.accounts = res.accounts || [];
                this.activeAccountId = res.active_user || this.activeAccountId;
                this.activeAccount = this.accounts.find(a => a.account_id === this.activeAccountId) || this.accounts[0] || null;
                this.shortcuts = res.shortcuts || [];

                this.updateProfileBanner();
                this.populateAccountSelect();
                this.renderShortcuts();
                window.uiController.showToast(`Scan complete: Found ${this.accounts.length} profiles, ${this.shortcuts.length} shortcuts.`, 'success');
            }
        } catch (err) {
            window.uiController.showToast(`Rescan failed: ${err.message}`, 'danger');
        }
    }

    async loadShortcuts(accountId) {
        if (!this.tableBody) return;

        this.tableBody.innerHTML = `
            <tr class="empty-row">
                <td colspan="4" style="text-align: center; color: var(--text-muted); padding: 36px;">
                    <i class="fa-solid fa-spinner fa-spin" style="margin-right: 8px;"></i> Reading shortcuts.vdf...
                </td>
            </tr>
        `;

        try {
            const data = await window.apiClient.getSteamShortcuts(accountId);
            this.shortcuts = data.shortcuts || [];
            
            const fantaCount = this.shortcuts.filter(s => s.is_fanta).length;
            if (this.fantaBadge) this.fantaBadge.textContent = String(fantaCount);
            if (this.allBadge) this.allBadge.textContent = String(this.shortcuts.length);
            if (this.shortcutsCountEl) {
                this.shortcutsCountEl.textContent = String(this.shortcuts.length);
            }
            this.renderShortcuts();
        } catch (err) {
            console.error('[SteamController] Failed to load shortcuts:', err);
            this.tableBody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="4" style="text-align: center; color: var(--danger); padding: 36px;">
                        Failed to read shortcuts.vdf: ${err.message}
                    </td>
                </tr>
            `;
        }
    }

    renderShortcuts() {
        if (!this.tableBody) return;

        const fantaCount = this.shortcuts.filter(s => s.is_fanta).length;
        if (this.fantaBadge) this.fantaBadge.textContent = String(fantaCount);
        if (this.allBadge) this.allBadge.textContent = String(this.shortcuts.length);

        let list = this.shortcuts;

        // Apply Fanta vs All filter
        if (this.activeFilter === 'fanta') {
            list = list.filter(s => s.is_fanta);
        }

        // Apply Search query
        if (this.searchQuery) {
            const q = this.searchQuery;
            list = list.filter(s => 
                (s.name && s.name.toLowerCase().includes(q)) || 
                (s.exe && s.exe.toLowerCase().includes(q)) ||
                (s.fanta_title && s.fanta_title.toLowerCase().includes(q)) ||
                (String(s.appid).includes(q))
            );
        }

        if (this.totalText) {
            if (this.activeFilter === 'fanta') {
                this.totalText.textContent = `Showing ${list.length} of ${fantaCount} Fanta Shortcuts`;
            } else {
                this.totalText.textContent = `Showing ${list.length} of ${this.shortcuts.length} Steam Shortcuts`;
            }
        }

        if (list.length === 0) {
            let msg = 'No shortcuts match your filter.';
            if (this.searchQuery) {
                msg = `No shortcuts match "${this.searchQuery}"`;
            } else if (this.activeFilter === 'fanta') {
                msg = 'No Fanta shortcuts detected. Add a game to Steam to see it here!';
            } else {
                msg = 'No non-Steam shortcuts registered in this profile yet.';
            }

            this.tableBody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="4" style="text-align: center; color: var(--text-muted); padding: 40px;">
                        ${msg}
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        list.forEach((sc) => {
            const thumbUrl = sc.fanta_thumbnail || sc.icon;
            const isImage = thumbUrl && (thumbUrl.endsWith('.png') || thumbUrl.endsWith('.jpg') || thumbUrl.endsWith('.jpeg') || thumbUrl.endsWith('.ico') || thumbUrl.startsWith('http'));
            const iconHtml = isImage 
                ? `<img src="${thumbUrl}" onerror="this.parentElement.innerHTML='<i class=\\'fa-solid fa-gamepad\\'></i>'">`
                : `<i class="fa-solid fa-gamepad"></i>`;

            const statusDot = sc.exists_on_disk 
                ? `<i class="fa-solid fa-circle-check" style="color: var(--success); font-size: 11px;" title="File exists on disk"></i>`
                : `<i class="fa-solid fa-triangle-exclamation" style="color: var(--warning); font-size: 11px;" title="Target file not found at this path"></i>`;

            const cleanExe = sc.exe || 'N/A';
            const escapedName = (sc.name || 'Unknown Game').replace(/'/g, "\\'");
            const escapedExe = cleanExe.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            const escapedStartDir = (sc.start_dir || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");

            const fantaBadge = sc.is_fanta 
                ? `<span class="status-pill status-uptodate" style="font-size: 9px; padding: 1px 6px; margin-left: 6px;"><i class="fa-solid fa-cloud-arrow-down" style="font-size: 8px;"></i> Fanta</span>` 
                : '';

            const versionText = sc.fanta_version ? `<span style="color: var(--accent); font-size: 10px; margin-left: 4px;">v${sc.fanta_version}</span>` : '';

            html += `
                <tr>
                    <td>
                        <div class="shortcut-game-cell">
                            <div class="shortcut-game-icon">
                                ${iconHtml}
                            </div>
                            <div>
                                <div style="display: flex; align-items: center; flex-wrap: wrap;">
                                    <strong style="color: #fff; font-size: 13px;">${sc.name || 'Untitled Shortcut'}</strong>
                                    ${fantaBadge}
                                    ${versionText}
                                </div>
                                ${sc.tags && sc.tags.length ? `<div style="font-size: 10px; color: var(--text-muted); margin-top: 2px;">${sc.tags.join(', ')}</div>` : ''}
                            </div>
                        </div>
                    </td>
                    <td>
                        <div class="shortcut-exe-path" title="${cleanExe}">
                            ${statusDot}
                            <span>${cleanExe}</span>
                        </div>
                    </td>
                    <td>
                        <span class="shortcut-appid-badge" title="Steam Shortcut AppID">${sc.appid}</span>
                    </td>
                    <td style="text-align: right;">
                        <div style="display: inline-flex; align-items: center; gap: 6px; justify-content: flex-end;">
                            <button class="btn btn-primary btn-sm" title="Launch via Steam" onclick="window.steamController.launchShortcut('${sc.steam_url}')" style="padding: 5px 10px; font-size: 11px;">
                                <i class="fa-brands fa-steam"></i> Play
                            </button>
                            <button class="btn btn-secondary btn-sm" title="Open Game Folder" onclick="window.steamController.openShortcutFolder('${escapedExe}', '${escapedStartDir}')" style="padding: 5px 8px; font-size: 11px;">
                                <i class="fa-solid fa-folder-open"></i>
                            </button>
                            <button class="btn btn-danger btn-sm" title="Delete Shortcut from Steam" onclick="window.steamController.deleteShortcut('${sc.appid}', '${escapedName}')" style="padding: 5px 8px; font-size: 11px;">
                                <i class="fa-solid fa-trash-can"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        });

        this.tableBody.innerHTML = html;
    }

    launchShortcut(steamUrl) {
        if (!steamUrl) return;
        window.uiController.showToast('Launching shortcut on Steam...', 'info');
        if (window.api && window.api.openExternal) {
            window.api.openExternal(steamUrl);
        } else {
            window.open(steamUrl);
        }
    }

    async openShortcutFolder(exePath, startDir) {
        if (!exePath && !startDir) return;
        try {
            let targetFolder = startDir;
            if (!targetFolder && exePath) {
                const lastSlash = Math.max(exePath.lastIndexOf('\\'), exePath.lastIndexOf('/'));
                if (lastSlash > 0) {
                    targetFolder = exePath.substring(0, lastSlash);
                } else {
                    targetFolder = exePath;
                }
            }

            let opened = false;
            if (window.api?.showItemInFolder && exePath && (exePath.toLowerCase().endsWith('.exe') || exePath.includes('.'))) {
                opened = await window.api.showItemInFolder(exePath);
            } else if (window.api?.openPath) {
                opened = await window.api.openPath(targetFolder || exePath);
            }

            if (opened) {
                window.uiController.showToast(`Opened folder in Explorer`, 'info');
            } else {
                window.uiController.showToast('Could not open folder on disk', 'warning');
            }
        } catch (err) {
            console.error('[SteamController] Error opening folder:', err);
        }
    }

    async restartSteam() {
        try {
            window.uiController.showToast('Gracefully restarting Steam to reload library...', 'info', 4000);
            const res = await window.apiClient.restartSteam();
            if (res.success) {
                window.uiController.showToast(res.message || 'Steam restarted successfully!', 'success');
            } else {
                window.uiController.showToast(res.error || 'Failed to restart Steam.', 'danger');
            }
        } catch (err) {
            window.uiController.showToast(`Error restarting Steam: ${err.message}`, 'danger');
        }
    }

    async deleteShortcut(appid, name) {
        if (!appid && !name) return;
        
        try {
            window.uiController.showToast(`Deleting "${name}" from Steam shortcuts...`, 'info');
            const res = await window.apiClient.deleteSteamShortcut({
                appid: appid,
                name: name,
                account_id: this.activeAccountId
            });

            if (res.success) {
                window.uiController.showToast(`Removed "${name}" from Steam!`, 'success', 6000, {
                    text: 'Restart Steam',
                    icon: 'fa-rotate',
                    callback: () => this.restartSteam()
                });
                // Remove from local array
                this.shortcuts = this.shortcuts.filter(s => String(s.appid) !== String(appid) && s.name !== name);
                if (this.shortcutsCountEl) {
                    this.shortcutsCountEl.textContent = String(this.shortcuts.length);
                }
                this.renderShortcuts();
            } else {
                window.uiController.showToast(`Failed to delete shortcut: ${res.error || res.message}`, 'danger');
            }
        } catch (err) {
            window.uiController.showToast(`Delete failed: ${err.message}`, 'danger');
        }
    }

    openAddShortcutDialog(game = {}) {
        this.activeGame = game;
        if (!this.modal) return;

        const titleInput = document.getElementById('steamModalGameTitle');
        if (titleInput) {
            if (titleInput.tagName === 'INPUT') {
                titleInput.value = game.title || '';
            } else {
                titleInput.textContent = game.title || 'Custom Game';
            }
        }

        const exeInput = document.getElementById('steamGameExeInput');
        if (exeInput) {
            exeInput.value = game.location ? `${game.location}\\${game.title}.exe` : '';
        }

        this.modal.classList.add('active');
    }

    closeModal() {
        if (this.modal) this.modal.classList.remove('active');
        this.activeGame = null;
    }

    async confirmAddShortcut() {
        const titleEl = document.getElementById('steamModalGameTitle');
        const title = (this.activeGame?.title || (titleEl ? (titleEl.value || titleEl.textContent) : '') || '').trim();
        const exePath = document.getElementById('steamGameExeInput')?.value?.trim() || '';

        if (!title) {
            window.uiController.showToast('Please enter a game name.', 'warning');
            return;
        }

        if (!exePath) {
            window.uiController.showToast('Please specify or browse the game executable (.exe) path.', 'warning');
            return;
        }

        try {
            window.uiController.showToast(`Adding "${title}" to Steam shortcuts...`, 'info');
            const res = await window.apiClient.addSteamShortcut({
                name: title,
                exe_path: exePath,
                icon_path: this.activeGame?.thumbnail || '',
                account_id: this.activeAccountId
            });

            if (res.success) {
                window.uiController.showToast(
                    `"${title}" added to Steam!`,
                    'success',
                    7000,
                    {
                        text: 'Restart Steam',
                        icon: 'fa-rotate',
                        callback: () => this.restartSteam()
                    }
                );
                this.closeModal();

                // Update details controller if active
                if (window.detailsController?.currentGame) {
                    const curr = window.detailsController.currentGame;
                    if (curr.title?.toLowerCase() === title.toLowerCase() || curr.id === this.activeGame?.id) {
                        curr.steam_url = res.steam_url;
                        if (window.detailsController.addSteamBtn) {
                            window.detailsController.addSteamBtn.innerHTML = '<i class="fa-brands fa-steam"></i> Play on Steam';
                            window.detailsController.addSteamBtn.title = 'Launch via Steam shortcut';
                        }
                    }
                }

                // Update game in libraryController list if present
                if (window.libraryController?.games) {
                    const match = window.libraryController.games.find(g => g.title?.toLowerCase() === title.toLowerCase());
                    if (match) {
                        match.steam_url = res.steam_url;
                    }
                }

                await this.loadShortcuts(this.activeAccountId);
            } else {
                window.uiController.showToast(res.error || res.message || 'Failed to add shortcut', 'danger');
            }
        } catch (err) {
            window.uiController.showToast(`Error adding shortcut: ${err.message}`, 'danger');
        }
    }
}

window.steamController = new SteamController();
