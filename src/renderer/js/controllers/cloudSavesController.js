/**
 * Cloud Saves Controller
 * Manages Google Drive REST API & Local Cloud Folder synchronization,
 * save game path inspection, cross-PC status comparison, and backups/restores.
 */

class CloudSavesController {
    constructor() {
        this.games = [];
        this.status = null;
        this.currentFilter = 'all';
        this.searchQuery = '';
        this.activeGameForCustomPath = null;
        this.authPollInterval = null;
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        // Provider card selection
        const cardGDrive = document.getElementById('providerCardGDrive');
        const cardLocal = document.getElementById('providerCardLocal');
        const radioGDrive = document.getElementById('radioProviderGDrive');
        const radioLocal = document.getElementById('radioProviderLocal');

        if (cardGDrive && radioGDrive) {
            cardGDrive.addEventListener('click', (e) => {
                if (e.target.tagName !== 'BUTTON' && !e.target.closest('button')) {
                    radioGDrive.checked = true;
                    this.updateProviderCardStyles();
                }
            });
            radioGDrive.addEventListener('change', () => this.updateProviderCardStyles());
        }

        if (cardLocal && radioLocal) {
            cardLocal.addEventListener('click', (e) => {
                if (e.target.tagName !== 'BUTTON' && !e.target.closest('button')) {
                    radioLocal.checked = true;
                    this.updateProviderCardStyles();
                }
            });
            radioLocal.addEventListener('change', () => this.updateProviderCardStyles());
        }

        // Google Drive Auth & Setup Buttons
        const setupCredsBtn = document.getElementById('setupGDriveCredsBtn');
        if (setupCredsBtn) {
            setupCredsBtn.addEventListener('click', () => this.openGoogleDriveSetupModal());
        }

        const connectBtn = document.getElementById('connectGDriveBtn');
        if (connectBtn) {
            connectBtn.addEventListener('click', () => this.connectGoogleDrive());
        }

        const disconnectBtn = document.getElementById('disconnectGDriveBtn');
        if (disconnectBtn) {
            disconnectBtn.addEventListener('click', () => this.disconnectGoogleDrive());
        }

        // Setup Modal Events
        const closeSetupBtn = document.getElementById('closeGDriveSetupModalBtn');
        const cancelSetupBtn = document.getElementById('cancelGDriveSetupBtn');
        if (closeSetupBtn) closeSetupBtn.addEventListener('click', () => this.closeGoogleDriveSetupModal());
        if (cancelSetupBtn) cancelSetupBtn.addEventListener('click', () => this.closeGoogleDriveSetupModal());

        const importJsonBtn = document.getElementById('importGDriveJsonBtn');
        const fileInput = document.getElementById('gdriveCredsFileInput');
        if (importJsonBtn && fileInput) {
            importJsonBtn.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => this.importCredentialsFile(e));
        }

        const saveCredsBtn = document.getElementById('saveGDriveCredsBtn');
        if (saveCredsBtn) {
            saveCredsBtn.addEventListener('click', () => this.saveGoogleCredentials());
        }

        const switchToLocalBtn = document.getElementById('switchToLocalFolderBtn');
        if (switchToLocalBtn) {
            switchToLocalBtn.addEventListener('click', () => this.switchToLocalFolder());
        }

        const gcloudLink = document.getElementById('openGCloudConsoleLink');
        if (gcloudLink) {
            gcloudLink.addEventListener('click', (e) => {
                e.preventDefault();
                if (window.api && window.api.openExternal) {
                    window.api.openExternal('https://console.cloud.google.com/apis/credentials');
                } else {
                    window.open('https://console.cloud.google.com/apis/credentials', '_blank');
                }
            });
        }

        const gdriveModal = document.getElementById('gdriveSetupModal');
        if (gdriveModal) {
            gdriveModal.addEventListener('click', (e) => {
                if (e.target === gdriveModal) this.closeGoogleDriveSetupModal();
            });
        }

        const customPathModal = document.getElementById('customSavePathModal');
        if (customPathModal) {
            customPathModal.addEventListener('click', (e) => {
                if (e.target === customPathModal) this.closeCustomPathModal();
            });
        }

        // Auto-detect My Drive / OneDrive
        const detectMyDriveBtn = document.getElementById('detectMyDriveBtn');
        if (detectMyDriveBtn) {
            detectMyDriveBtn.addEventListener('click', () => this.detectDefaultCloudPath());
        }

        // Browse local cloud path
        const browseLocalPathBtn = document.getElementById('browseLocalCloudPathBtn');
        if (browseLocalPathBtn) {
            browseLocalPathBtn.addEventListener('click', () => this.browseDirectory('localCloudPathInput'));
        }

        // Save Preferences Button
        const saveSettingsBtn = document.getElementById('saveCloudSettingsBtn');
        if (saveSettingsBtn) {
            saveSettingsBtn.addEventListener('click', () => this.savePreferences());
        }

        // Refresh & Backup All Buttons
        const refreshBtn = document.getElementById('refreshCloudGamesBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadAll(true));
        }

        const backupAllBtn = document.getElementById('backupAllGamesBtn');
        if (backupAllBtn) {
            backupAllBtn.addEventListener('click', () => this.backupAllGames());
        }

        // Search Input
        const searchInput = document.getElementById('cloudGameSearchInput');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchQuery = (e.target.value || '').trim().toLowerCase();
                this.renderGames();
            });
        }

        // Filter Pills
        const filterPills = document.querySelectorAll('[data-cloud-filter]');
        filterPills.forEach(pill => {
            pill.addEventListener('click', () => {
                filterPills.forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                this.currentFilter = pill.dataset.cloudFilter;
                this.renderGames();
            });
        });

        // Custom Save Path Modal
        const closePathModalBtn = document.getElementById('closeSavePathModalBtn');
        const cancelPathModalBtn = document.getElementById('cancelSavePathBtn');
        if (closePathModalBtn) closePathModalBtn.addEventListener('click', () => this.closeCustomPathModal());
        if (cancelPathModalBtn) cancelPathModalBtn.addEventListener('click', () => this.closeCustomPathModal());

        const saveCustomPathBtn = document.getElementById('saveCustomSavePathBtn');
        if (saveCustomPathBtn) {
            saveCustomPathBtn.addEventListener('click', () => this.saveCustomPath());
        }

        const browseCustomSavePathBtn = document.getElementById('browseCustomSavePathBtn');
        if (browseCustomSavePathBtn) {
            browseCustomSavePathBtn.addEventListener('click', () => this.browseDirectory('customSavePathInput'));
        }
    }

    updateProviderCardStyles() {
        const radioGDrive = document.getElementById('radioProviderGDrive');
        const cardGDrive = document.getElementById('providerCardGDrive');
        const cardLocal = document.getElementById('providerCardLocal');

        const isGDrive = radioGDrive ? radioGDrive.checked : true;
        if (cardGDrive) {
            cardGDrive.classList.toggle('active', isGDrive);
            cardGDrive.style.borderColor = isGDrive ? 'rgba(212, 168, 83, 0.4)' : 'var(--border-glass)';
            cardGDrive.style.background = isGDrive ? 'rgba(212, 168, 83, 0.06)' : 'rgba(0, 0, 0, 0.2)';
        }
        if (cardLocal) {
            cardLocal.classList.toggle('active', !isGDrive);
            cardLocal.style.borderColor = !isGDrive ? 'rgba(212, 168, 83, 0.4)' : 'var(--border-glass)';
            cardLocal.style.background = !isGDrive ? 'rgba(212, 168, 83, 0.06)' : 'rgba(0, 0, 0, 0.2)';
        }
    }

    async loadAll(notify = false) {
        if (notify && window.uiController) {
            window.uiController.showToast('Refreshing save states and cloud metadata...', 'info');
        }
        await Promise.all([
            this.loadStatus(),
            this.loadGames()
        ]);
    }

    async loadStatus() {
        try {
            const data = await window.apiClient.getCloudStatus();
            this.status = data;

            // Provider selection
            const radioGDrive = document.getElementById('radioProviderGDrive');
            const radioLocal = document.getElementById('radioProviderLocal');
            if (data.provider === 'local_folder') {
                if (radioLocal) radioLocal.checked = true;
            } else {
                if (radioGDrive) radioGDrive.checked = true;
            }
            this.updateProviderCardStyles();

            // Auto-sync toggle
            const autoSyncToggle = document.getElementById('cloudAutoSyncToggle');
            if (autoSyncToggle) {
                autoSyncToggle.checked = Boolean(data.auto_sync);
            }

            // Local cloud path
            const localPathInput = document.getElementById('localCloudPathInput');
            if (localPathInput) {
                localPathInput.value = data.local_cloud_path || data.default_local_path || '';
            }

            // Google Drive status display
            const statusText = document.getElementById('gdriveStatusText');
            const connectBtn = document.getElementById('connectGDriveBtn');
            const disconnectBtn = document.getElementById('disconnectGDriveBtn');
            const setupCredsBtn = document.getElementById('setupGDriveCredsBtn');

            if (data.gdrive_connected && data.gdrive_email) {
                if (statusText) {
                    statusText.innerHTML = `
                        <span style="color: var(--success); font-weight: 600; display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-circle-check"></i> Connected as ${data.gdrive_email}
                        </span>
                    `;
                }
                if (connectBtn) connectBtn.style.display = 'none';
                if (disconnectBtn) disconnectBtn.style.display = 'inline-flex';
                if (setupCredsBtn) setupCredsBtn.style.display = 'none';
            } else if (!data.has_credentials) {
                if (statusText) {
                    statusText.innerHTML = `
                        <span style="color: #e09f3e; font-weight: 500; display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-key"></i> API Setup Required
                        </span>
                    `;
                }
                // Hide Sign In button until valid API info/credentials are configured
                if (connectBtn) connectBtn.style.display = 'none';
                if (disconnectBtn) disconnectBtn.style.display = 'none';
                if (setupCredsBtn) {
                    setupCredsBtn.style.display = 'inline-flex';
                    setupCredsBtn.className = 'btn btn-sm btn-primary';
                    setupCredsBtn.innerHTML = '<i class="fa-solid fa-key"></i> Setup API Credentials';
                }
            } else {
                if (statusText) {
                    statusText.innerHTML = `
                        <span style="color: var(--text-muted); display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-circle-question"></i> Not Connected
                        </span>
                    `;
                }
                // API credentials ready: Show Sign In with Google directly
                if (connectBtn) {
                    connectBtn.style.display = 'inline-flex';
                    connectBtn.className = 'btn btn-sm btn-primary';
                    connectBtn.innerHTML = '<i class="fa-brands fa-google"></i> Sign In with Google';
                }
                if (disconnectBtn) disconnectBtn.style.display = 'none';
                if (setupCredsBtn) setupCredsBtn.style.display = 'none';
            }
        } catch (err) {
            console.error('[CloudSavesController] loadStatus error:', err);
        }
    }

    async loadGames() {
        const container = document.getElementById('cloudGamesList');
        if (container && this.games.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; color: var(--text-muted); padding: 40px;">
                    <i class="fa-solid fa-spinner fa-spin" style="font-size: 24px; color: var(--accent); margin-bottom: 10px;"></i>
                    <p style="font-size: 13px;">Inspecting local game save folders and cloud archives...</p>
                </div>
            `;
        }

        try {
            const data = await window.apiClient.getCloudGames();
            if (data && Array.isArray(data.games)) {
                this.games = data.games;
                this.renderGames();
            }
        } catch (err) {
            console.error('[CloudSavesController] loadGames error:', err);
            if (container) {
                container.innerHTML = `
                    <div style="text-align: center; color: var(--danger); padding: 30px;">
                        <i class="fa-solid fa-triangle-exclamation" style="font-size: 20px; margin-bottom: 8px;"></i>
                        <p style="font-size: 13px;">Failed to load game save information: ${err.message}</p>
                    </div>
                `;
            }
        }
    }

    renderGames() {
        const container = document.getElementById('cloudGamesList');
        if (!container) return;

        // Filter games
        const filtered = this.games.filter(g => {
            if (this.searchQuery) {
                const titleMatch = g.title.toLowerCase().includes(this.searchQuery);
                const pathMatch = g.save_path && g.save_path.toLowerCase().includes(this.searchQuery);
                if (!titleMatch && !pathMatch) return false;
            }

            if (this.currentFilter === 'in_sync') return g.sync_state === 'in_sync';
            if (this.currentFilter === 'local_newer') return g.sync_state === 'local_newer';
            if (this.currentFilter === 'cloud_newer') return g.sync_state === 'cloud_newer';
            if (this.currentFilter === 'local_only') return g.sync_state === 'local_only';
            return true;
        });

        if (filtered.length === 0) {
            container.innerHTML = `
                <div class="glass-card" style="text-align: center; padding: 48px 24px; color: var(--text-muted); background: rgba(0,0,0,0.15);">
                    <i class="fa-solid fa-ghost" style="font-size: 28px; margin-bottom: 12px; color: var(--accent); opacity: 0.7;"></i>
                    <h4 style="font-size: 14px; color: #fff; margin-bottom: 4px;">No matching save records found</h4>
                    <p style="font-size: 12px;">Install games or adjust search filter to display saves.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = filtered.map(g => this.renderGameCardHtml(g)).join('');
    }

    renderGameCardHtml(g) {
        // Sync badge representation
        let badgeHtml = '';
        switch (g.sync_state) {
            case 'in_sync':
                badgeHtml = `<span class="cloud-sync-badge badge-sync"><i class="fa-solid fa-check"></i> In Sync</span>`;
                break;
            case 'local_newer':
                badgeHtml = `<span class="cloud-sync-badge badge-local-newer" title="Local save was modified more recently than cloud"><i class="fa-solid fa-arrow-right"></i> Local Newer</span>`;
                break;
            case 'cloud_newer':
                badgeHtml = `<span class="cloud-sync-badge badge-cloud-newer" title="Cloud save was modified more recently than local"><i class="fa-solid fa-arrow-left"></i> Cloud Newer</span>`;
                break;
            case 'local_only':
                badgeHtml = `<span class="cloud-sync-badge badge-unbacked" title="Save exists locally but has not been uploaded"><i class="fa-solid fa-cloud-arrow-up"></i> Needs Backup</span>`;
                break;
            case 'cloud_only':
                badgeHtml = `<span class="cloud-sync-badge badge-cloud-only" title="Cloud backup exists but not found on this PC"><i class="fa-solid fa-cloud"></i> Cloud Only</span>`;
                break;
            default:
                badgeHtml = `<span class="cloud-sync-badge badge-no-saves"><i class="fa-solid fa-circle-question"></i> No Save Found</span>`;
        }

        const thumb = g.thumbnail || 'assets/OFME-DWND-ICO.ico';
        const localSizeStr = g.local_size_bytes > 0 ? this.formatBytes(g.local_size_bytes) : '';
        const cloudSizeStr = g.cloud_size_bytes > 0 ? this.formatBytes(g.cloud_size_bytes) : '';

        return `
            <div class="glass-card cloud-game-card status-${g.sync_state}" id="save-card-${this.escapeId(g.title)}">
                <!-- Top Row: Thumbnail + Title + Sync State Badge + Actions -->
                <div class="cloud-game-header">
                    <div style="display: flex; align-items: center; gap: 14px; min-width: 0; flex: 1;">
                        <img src="${thumb}" class="cloud-game-thumb" onerror="this.src='assets/OFME-DWND-ICO.ico'">
                        <div style="min-width: 0;">
                            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 2px;">
                                <h4 class="cloud-game-title">${g.title}</h4>
                                ${badgeHtml}
                                ${g.is_installed ? '<span class="status-pill" style="font-size: 9px; padding: 1px 6px;">Installed</span>' : ''}
                            </div>
                            <div style="display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">
                                <span style="color: var(--accent);"><i class="fa-solid fa-tag"></i> ${g.detection_type}</span>
                                ${g.save_path ? `&bull; <span class="cloud-path-truncate" title="${g.save_path}">${g.save_path}</span>` : '&bull; <span style="color: var(--danger);">No save folder detected</span>'}
                                <button class="btn-icon" style="width: 22px; height: 22px; font-size: 10px;" title="Change save location" onclick="window.cloudSavesController.openCustomPathModal('${this.escapeHtml(g.title)}', '${this.escapeHtml(g.save_path || '')}')">
                                    <i class="fa-solid fa-pencil"></i>
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Action Buttons -->
                    <div class="cloud-card-actions">
                        ${g.save_path ? `
                            <button class="btn-icon" title="Open Local Save Folder" onclick="window.cloudSavesController.openFolder('${this.escapePath(g.save_path)}')">
                                <i class="fa-solid fa-folder-open"></i>
                            </button>
                        ` : ''}

                        <button class="btn btn-sm btn-primary" title="Backup local save to cloud (overwrites cloud)" ${g.local_exists ? '' : 'disabled'} onclick="window.cloudSavesController.backupGame('${this.escapeHtml(g.title)}')">
                            <i class="fa-solid fa-cloud-arrow-up"></i> Backup Now
                        </button>

                        <button class="btn btn-sm btn-secondary" title="Restore save from cloud (creates local rollback first)" ${g.cloud_exists ? '' : 'disabled'} onclick="window.cloudSavesController.restoreGame('${this.escapeHtml(g.title)}')">
                            <i class="fa-solid fa-cloud-arrow-down"></i> Restore Save
                        </button>
                    </div>
                </div>

                <!-- Bottom Row: Local Save vs Cloud Save Comparison Comparison Split -->
                <div class="cloud-comparison-grid">
                    <!-- Local Save Box -->
                    <div class="cloud-comp-box ${g.sync_state === 'local_newer' ? 'highlight-box' : ''}">
                        <div class="cloud-comp-header">
                            <span style="color: #fff; font-weight: 600;"><i class="fa-solid fa-desktop" style="color: var(--accent); margin-right: 6px;"></i> Local Save on this PC</span>
                            ${localSizeStr ? `<span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${localSizeStr}</span>` : ''}
                        </div>
                        <div class="cloud-comp-body">
                            ${g.local_exists ? `
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="color: var(--text-secondary);"><i class="fa-solid fa-clock" style="margin-right: 4px;"></i> Modified:</span>
                                    <strong style="color: ${g.sync_state === 'local_newer' ? 'var(--accent)' : '#fff'}; font-family: var(--font-mono);">${g.local_mtime_str}</strong>
                                </div>
                            ` : `
                                <span style="color: var(--text-muted); font-style: italic;"><i class="fa-solid fa-circle-exclamation"></i> No save files found in local directory</span>
                            `}
                        </div>
                    </div>

                    <!-- Sync Direction Arrow Divider -->
                    <div class="cloud-direction-divider">
                        ${g.sync_state === 'local_newer' ? '<i class="fa-solid fa-arrow-right-long" style="color: var(--accent); font-size: 16px;"></i>' : 
                          (g.sync_state === 'cloud_newer' ? '<i class="fa-solid fa-arrow-left-long" style="color: var(--warning); font-size: 16px;"></i>' : 
                          '<i class="fa-solid fa-equals" style="color: var(--success); font-size: 14px;"></i>')}
                    </div>

                    <!-- Cloud Save Box -->
                    <div class="cloud-comp-box ${g.sync_state === 'cloud_newer' ? 'highlight-box-warning' : ''}">
                        <div class="cloud-comp-header">
                            <span style="color: #fff; font-weight: 600;"><i class="fa-solid fa-cloud" style="color: #4da3ff; margin-right: 6px;"></i> Cloud Backup</span>
                            ${cloudSizeStr ? `<span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${cloudSizeStr}</span>` : ''}
                        </div>
                        <div class="cloud-comp-body">
                            ${g.cloud_exists ? `
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="color: var(--text-secondary);"><i class="fa-solid fa-clock" style="margin-right: 4px;"></i> Uploaded:</span>
                                    <strong style="color: ${g.sync_state === 'cloud_newer' ? 'var(--warning)' : '#fff'}; font-family: var(--font-mono);">${g.cloud_mtime_str}</strong>
                                </div>
                            ` : `
                                <span style="color: var(--text-muted); font-style: italic;"><i class="fa-solid fa-cloud-slash"></i> No cloud backup saved yet</span>
                            `}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async backupGame(title) {
        if (!title) return;
        window.uiController.showToast(`Starting save backup for '${title}'...`, 'info');
        try {
            const res = await window.apiClient.backupCloudSave({ title });
            if (res && res.success) {
                window.uiController.showToast(`Backup complete for ${title}!`, 'success');
                // Instant live UI update
                const game = this.games.find(g => g.title === title || g.title.toLowerCase() === title.toLowerCase());
                if (game) {
                    game.cloud_exists = true;
                    game.cloud_size_bytes = game.local_size_bytes;
                    game.cloud_mtime = res.mtime || game.local_mtime;
                    game.cloud_mtime_str = game.local_mtime_str;
                    game.sync_state = 'in_sync';
                    game.sync_state_label = 'In Sync';
                    this.renderGames();
                }
                await this.loadGames();
            } else {
                window.uiController.showToast(`Backup failed: ${res.error || 'Unknown error'}`, 'danger');
            }
        } catch (err) {
            window.uiController.showToast(`Backup error: ${err.message}`, 'danger');
        }
    }

    async restoreGame(title) {
        if (!title) return;
        window.uiController.showToast(`Restoring save for '${title}' (Safety rollback created)...`, 'info');
        try {
            const res = await window.apiClient.restoreCloudSave({ title });
            if (res && res.success) {
                window.uiController.showToast(`Save restored for ${title}!`, 'success');
                // Instant live UI update
                const game = this.games.find(g => g.title === title || g.title.toLowerCase() === title.toLowerCase());
                if (game) {
                    game.local_exists = true;
                    game.sync_state = 'in_sync';
                    game.sync_state_label = 'In Sync';
                    this.renderGames();
                }
                await this.loadGames();
            } else {
                window.uiController.showToast(`Restore failed: ${res.error || 'Unknown error'}`, 'danger');
            }
        } catch (err) {
            window.uiController.showToast(`Restore error: ${err.message}`, 'danger');
        }
    }

    async backupAllGames() {
        const eligible = this.games.filter(g => g.local_exists);
        if (eligible.length === 0) {
            window.uiController.showToast('No local save files detected to backup.', 'warning');
            return;
        }

        window.uiController.showToast(`Backing up saves for ${eligible.length} games...`, 'info');
        let successCount = 0;
        for (const g of eligible) {
            try {
                const res = await window.apiClient.backupCloudSave({ title: g.title });
                if (res && res.success) successCount++;
            } catch (e) {
                console.error(`Backup error for ${g.title}:`, e);
            }
        }

        window.uiController.showToast(`Batch backup finished: ${successCount} / ${eligible.length} games synced.`, 'success');
        await this.loadGames();
    }

    async connectGoogleDrive() {
        if (this.status && !this.status.has_credentials) {
            this.openGoogleDriveSetupModal();
            return;
        }

        try {
            const res = await window.apiClient.getCloudAuthUrl();
            if (res && res.needs_setup) {
                this.openGoogleDriveSetupModal();
                return;
            }
            if (res && res.auth_url) {
                window.uiController.showToast('Opening Google Authorization in your web browser...', 'info');
                if (window.api && window.api.openExternal) {
                    await window.api.openExternal(res.auth_url);
                } else {
                    window.open(res.auth_url, '_blank');
                }

                // Poll for connection status
                if (this.authPollInterval) clearInterval(this.authPollInterval);
                let attempts = 0;
                this.authPollInterval = setInterval(async () => {
                    attempts++;
                    if (attempts > 45) {
                        clearInterval(this.authPollInterval);
                        return;
                    }
                    const st = await window.apiClient.getCloudStatus();
                    if (st && st.gdrive_connected) {
                        clearInterval(this.authPollInterval);
                        window.uiController.showToast(`Connected to Google Drive as ${st.gdrive_email}!`, 'success');
                        await this.loadStatus();
                        await this.loadGames();
                    }
                }, 2000);
            }
        } catch (err) {
            if (err && err.message && (err.message.includes('credentials') || err.message.includes('not configured'))) {
                this.openGoogleDriveSetupModal();
            } else {
                window.uiController.showToast(`Failed to open Google authorization: ${err.message}`, 'warning');
                this.openGoogleDriveSetupModal();
            }
        }
    }

    async disconnectGoogleDrive() {
        try {
            await window.apiClient.disconnectCloud();
            window.uiController.showToast('Disconnected Google Drive account.', 'info');
            await this.loadStatus();
            await this.loadGames();
        } catch (err) {
            window.uiController.showToast('Could not disconnect account', 'danger');
        }
    }

    async savePreferences() {
        const radioGDrive = document.getElementById('radioProviderGDrive');
        const provider = (radioGDrive && radioGDrive.checked) ? 'gdrive_api' : 'local_folder';
        const autoSync = document.getElementById('cloudAutoSyncToggle')?.checked || false;
        const localCloudPath = document.getElementById('localCloudPathInput')?.value?.trim() || '';

        try {
            await window.apiClient.configureCloud({
                provider,
                auto_sync: autoSync,
                local_cloud_path: localCloudPath
            });
            window.uiController.showToast('Cloud & Save preferences saved!', 'success');
            await this.loadAll();
        } catch (err) {
            window.uiController.showToast(`Failed to save preferences: ${err.message}`, 'danger');
        }
    }

    async detectDefaultCloudPath() {
        if (!this.status || !this.status.default_local_path) return;
        const input = document.getElementById('localCloudPathInput');
        if (input) {
            input.value = this.status.default_local_path;
            window.uiController.showToast(`Detected cloud directory: ${this.status.default_local_path}`, 'info');
        }
    }

    async browseDirectory(targetInputId) {
        if (window.api && window.api.selectDirectory) {
            const path = await window.api.selectDirectory();
            if (path) {
                const input = document.getElementById(targetInputId);
                if (input) input.value = path;
            }
        } else {
            window.uiController.showToast('Please type or paste the folder path into the input field.', 'info');
        }
    }

    async openFolder(folderPath) {
        if (!folderPath) return;
        if (window.api && window.api.openPath) {
            await window.api.openPath(folderPath);
        } else {
            window.uiController.showToast(`Folder location: ${folderPath}`, 'info');
        }
    }

    openGoogleDriveSetupModal() {
        const modal = document.getElementById('gdriveSetupModal');
        const cidInput = document.getElementById('gdriveClientIdInput');
        if (cidInput && this.status && this.status.gdrive_client_id) {
            cidInput.value = this.status.gdrive_client_id;
        }
        if (modal) {
            modal.classList.add('active');
            modal.classList.add('visible');
        }
    }

    closeGoogleDriveSetupModal() {
        const modal = document.getElementById('gdriveSetupModal');
        if (modal) {
            modal.classList.remove('active');
            modal.classList.remove('visible');
        }
    }

    async importCredentialsFile(e) {
        const file = e.target.files && e.target.files[0];
        if (!file) return;

        try {
            const text = await file.text();
            const json = JSON.parse(text);
            const app = json.installed || json.web || json;
            const clientId = app.client_id || '';
            const clientSecret = app.client_secret || '';

            if (clientId) {
                const cidInput = document.getElementById('gdriveClientIdInput');
                if (cidInput) cidInput.value = clientId;
            }
            if (clientSecret) {
                const csecInput = document.getElementById('gdriveClientSecretInput');
                if (csecInput) csecInput.value = clientSecret;
            }
            window.uiController.showToast('Imported credentials.json successfully!', 'success');
        } catch (err) {
            window.uiController.showToast(`Invalid credentials JSON: ${err.message}`, 'danger');
        }
    }

    async saveGoogleCredentials() {
        const cid = document.getElementById('gdriveClientIdInput')?.value?.trim();
        const csec = document.getElementById('gdriveClientSecretInput')?.value?.trim();

        if (!cid) {
            window.uiController.showToast('Please enter your Google OAuth Client ID', 'warning');
            return;
        }

        try {
            const res = await window.apiClient.saveCloudCredentials({
                client_id: cid,
                client_secret: csec
            });
            if (res && res.success) {
                window.uiController.showToast('Google API credentials saved!', 'success');
                this.closeGoogleDriveSetupModal();
                await this.loadStatus();
                // Immediately initiate sign-in
                await this.connectGoogleDrive();
            } else {
                window.uiController.showToast(res?.error || 'Failed to save credentials', 'danger');
            }
        } catch (err) {
            window.uiController.showToast(`Error saving credentials: ${err.message}`, 'danger');
        }
    }

    async switchToLocalFolder() {
        const radioLocal = document.getElementById('radioProviderLocal');
        if (radioLocal) radioLocal.checked = true;
        this.updateProviderCardStyles();
        this.closeGoogleDriveSetupModal();
        await this.savePreferences();
        window.uiController.showToast('Switched to Local Cloud Folder ("My Drive" / OneDrive)!', 'info');
    }

    openCustomPathModal(title, currentPath) {
        this.activeGameForCustomPath = title;
        const titleElem = document.getElementById('customSaveGameTitle');
        const input = document.getElementById('customSavePathInput');
        const modal = document.getElementById('customSavePathModal');

        if (titleElem) titleElem.textContent = title;
        if (input) input.value = currentPath || '';
        if (modal) {
            modal.classList.add('active');
            modal.classList.add('visible');
        }
    }

    closeCustomPathModal() {
        const modal = document.getElementById('customSavePathModal');
        if (modal) {
            modal.classList.remove('active');
            modal.classList.remove('visible');
        }
        this.activeGameForCustomPath = null;
    }

    async saveCustomPath() {
        if (!this.activeGameForCustomPath) return;
        const input = document.getElementById('customSavePathInput');
        const path = input ? input.value.trim() : '';

        try {
            await window.apiClient.setCloudSavePath({
                title: this.activeGameForCustomPath,
                save_path: path
            });
            window.uiController.showToast(`Updated save location for ${this.activeGameForCustomPath}!`, 'success');
            this.closeCustomPathModal();
            await this.loadGames();
        } catch (err) {
            window.uiController.showToast(`Failed to update save path: ${err.message}`, 'danger');
        }
    }

    formatBytes(bytes) {
        if (!bytes || bytes <= 0) return '0 B';
        const KB = 1024;
        const MB = 1024 * 1024;
        const GB = 1024 * 1024 * 1024;
        if (bytes >= GB) return (bytes / GB).toFixed(1) + ' GB';
        if (bytes >= MB) return (bytes / MB).toFixed(1) + ' MB';
        if (bytes >= KB) return (bytes / KB).toFixed(0) + ' KB';
        return bytes + ' B';
    }

    escapeHtml(str) {
        return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
    }

    escapePath(str) {
        return (str || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    }

    escapeId(str) {
        return (str || '').replace(/[^a-zA-Z0-9]/g, '_');
    }
}

window.cloudSavesController = new CloudSavesController();
