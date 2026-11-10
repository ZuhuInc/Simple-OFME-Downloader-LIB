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
        const cardSelfHosted = document.getElementById('providerCardSelfHosted');
        const radioGDrive = document.getElementById('radioProviderGDrive');
        const radioLocal = document.getElementById('radioProviderLocal');
        const radioSelfHosted = document.getElementById('radioProviderSelfHosted');

        if (cardGDrive && radioGDrive) {
            cardGDrive.addEventListener('click', (e) => {
                if (e.target.tagName !== 'BUTTON' && !e.target.closest('button') && e.target.tagName !== 'INPUT') {
                    radioGDrive.checked = true;
                    this.updateProviderCardStyles();
                }
            });
            radioGDrive.addEventListener('change', () => this.updateProviderCardStyles());
        }

        if (cardLocal && radioLocal) {
            cardLocal.addEventListener('click', (e) => {
                if (e.target.tagName !== 'BUTTON' && !e.target.closest('button') && e.target.tagName !== 'INPUT') {
                    radioLocal.checked = true;
                    this.updateProviderCardStyles();
                }
            });
            radioLocal.addEventListener('change', () => this.updateProviderCardStyles());
        }

        if (cardSelfHosted && radioSelfHosted) {
            cardSelfHosted.addEventListener('click', (e) => {
                if (e.target.tagName !== 'BUTTON' && !e.target.closest('button') && e.target.tagName !== 'A' && !e.target.closest('a')) {
                    radioSelfHosted.checked = true;
                    this.updateProviderCardStyles();
                }
            });
            radioSelfHosted.addEventListener('change', () => this.updateProviderCardStyles());
        }

        const testSelfHostedBtn = document.getElementById('testSelfHostedBtn');
        if (testSelfHostedBtn) {
            testSelfHostedBtn.addEventListener('click', () => this.testSelfHostedConnection());
        }

        const selfHostedRepoLink = document.getElementById('openSelfHostedRepoLink');
        if (selfHostedRepoLink) {
            selfHostedRepoLink.addEventListener('click', (e) => {
                e.preventDefault();
                const repoUrl = 'https://github.com/ReTr0777/Fanta-OFME-Cloud';
                if (window.api && window.api.openExternal) {
                    window.api.openExternal(repoUrl);
                } else {
                    window.open(repoUrl, '_blank');
                }
            });
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
        const swapTransferBtn = document.getElementById('swapCloudTransferBtn');
        if (swapTransferBtn) {
            swapTransferBtn.addEventListener('click', () => this.swapTransferProviders());
        }
        const startTransferBtn = document.getElementById('startCloudTransferBtn');
        if (startTransferBtn) {
            startTransferBtn.addEventListener('click', () => this.transferAllSaves());
        }
        const autoExcludeSteamToggle = document.getElementById('cloudAutoExcludeSteamToggle');
        if (autoExcludeSteamToggle) {
            autoExcludeSteamToggle.addEventListener('change', async () => {
                await window.apiClient.configureCloud({ auto_exclude_steam_cloud: autoExcludeSteamToggle.checked });
                await this.loadGames();
            });
        }
        if (browseCustomSavePathBtn) {
            browseCustomSavePathBtn.addEventListener('click', () => this.browseDirectory('customSavePathInput'));
        }
    }

    updateProviderCardStyles() {
        const radioGDrive = document.getElementById('radioProviderGDrive');
        const radioLocal = document.getElementById('radioProviderLocal');
        const radioSelfHosted = document.getElementById('radioProviderSelfHosted');
        const cardGDrive = document.getElementById('providerCardGDrive');
        const cardLocal = document.getElementById('providerCardLocal');
        const cardSelfHosted = document.getElementById('providerCardSelfHosted');

        const isLocal = Boolean(radioLocal && radioLocal.checked);
        const isSelfHosted = Boolean(radioSelfHosted && radioSelfHosted.checked);
        const isGDrive = !isLocal && !isSelfHosted;

        if (cardGDrive) {
            cardGDrive.classList.toggle('active', isGDrive);
            cardGDrive.style.borderColor = isGDrive ? 'rgba(212, 168, 83, 0.4)' : 'var(--border-glass)';
            cardGDrive.style.background = isGDrive ? 'rgba(212, 168, 83, 0.06)' : 'rgba(0, 0, 0, 0.2)';
        }
        if (cardLocal) {
            cardLocal.classList.toggle('active', isLocal);
            cardLocal.style.borderColor = isLocal ? 'rgba(212, 168, 83, 0.4)' : 'var(--border-glass)';
            cardLocal.style.background = isLocal ? 'rgba(212, 168, 83, 0.06)' : 'rgba(0, 0, 0, 0.2)';
        }
        if (cardSelfHosted) {
            cardSelfHosted.classList.toggle('active', isSelfHosted);
            cardSelfHosted.style.borderColor = isSelfHosted ? 'rgba(212, 168, 83, 0.4)' : 'var(--border-glass)';
            cardSelfHosted.style.background = isSelfHosted ? 'rgba(212, 168, 83, 0.06)' : 'rgba(0, 0, 0, 0.2)';
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
            const radioSelfHosted = document.getElementById('radioProviderSelfHosted');
            if (data.provider === 'local_folder') {
                if (radioLocal) radioLocal.checked = true;
            } else if (data.provider === 'self_hosted') {
                if (radioSelfHosted) radioSelfHosted.checked = true;
            } else {
                if (radioGDrive) radioGDrive.checked = true;
            }
            this.updateProviderCardStyles();

            // Auto-sync toggle
            const autoSyncToggle = document.getElementById('cloudAutoSyncToggle');
            if (autoSyncToggle) {
                autoSyncToggle.checked = Boolean(data.auto_sync);
            }
            const autoExcludeSteamToggle = document.getElementById('cloudAutoExcludeSteamToggle');
            if (autoExcludeSteamToggle) {
                autoExcludeSteamToggle.checked = data.auto_exclude_steam_cloud !== undefined ? Boolean(data.auto_exclude_steam_cloud) : true;
            }

            // Local cloud path
            const localPathInput = document.getElementById('localCloudPathInput');
            if (localPathInput) {
                localPathInput.value = data.local_cloud_path || data.default_local_path || '';
            }

            // Self-Hosted URL & API Key
            const selfHostedUrlInput = document.getElementById('selfHostedUrlInput');
            const selfHostedApiKeyInput = document.getElementById('selfHostedApiKeyInput');
            const selfHostedStatusText = document.getElementById('selfHostedStatusText');
            if (selfHostedUrlInput) {
                selfHostedUrlInput.value = data.self_hosted_url || '';
            }
            if (selfHostedApiKeyInput) {
                selfHostedApiKeyInput.value = data.self_hosted_api_key || '';
            }
            if (selfHostedStatusText) {
                if (data.self_hosted_configured) {
                    selfHostedStatusText.innerHTML = `
                        <span style="color: var(--accent); font-weight: 500; display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-server"></i> Configured (${this.escapeHtml(data.self_hosted_url)})
                        </span>
                    `;
                } else {
                    selfHostedStatusText.innerHTML = `
                        <span style="color: var(--text-muted); display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-circle-question"></i> Not Configured
                        </span>
                    `;
                }
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
                const byKey = new Map();
                for (const g of data.games) {
                    const key = (g.title || '').trim().toLowerCase();
                    if (!key) continue;
                    const existing = byKey.get(key);
                    // Prefer proper mixed-case title over ALL-CAPS installed key
                    if (!existing || (existing.title === existing.title.toUpperCase() && g.title !== g.title.toUpperCase())) {
                        byKey.set(key, g);
                    }
                }
                this.games = Array.from(byKey.values());
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

        const excludedCount = this.games.filter(g => g.is_excluded).length;
        const excludedPill = document.getElementById('cloudFilterExcludedPill');
        if (excludedPill) {
            excludedPill.innerHTML = `<i class="fa-brands fa-steam" style="margin-right: 3px;"></i> IGNORED${excludedCount > 0 ? ' (' + excludedCount + ')' : ''}`;
        }

        // Filter games
        const filtered = this.games.filter(g => {
            if (this.searchQuery) {
                const titleMatch = g.title.toLowerCase().includes(this.searchQuery);
                const pathMatch = g.save_path && g.save_path.toLowerCase().includes(this.searchQuery);
                if (!titleMatch && !pathMatch) return false;
            }

            if (this.currentFilter === 'excluded') return Boolean(g.is_excluded);
            if (g.is_excluded) return false;
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
                                ${g.is_steam_cloud ? '<span class="status-pill" style="font-size: 9px; padding: 1px 7px; background: rgba(96, 165, 250, 0.16); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.35);"><i class="fa-brands fa-steam"></i> Steam Cloud</span>' : ''}
                                ${g.is_excluded ? `<span class="status-pill" style="font-size: 9px; padding: 1px 7px; background: rgba(239, 68, 68, 0.16); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.35);"><i class="fa-solid fa-eye-slash"></i> ${g.exclude_reason === 'Steam Cloud' ? 'Auto-Ignored' : 'Ignored'}</span>` : ''}
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
                        ${g.is_excluded ? `
                            <button class="btn btn-sm btn-secondary" style="border-color: rgba(96, 165, 250, 0.45); color: #60a5fa;" title="Include this game in Fanta Cloud Sync" onclick="window.cloudSavesController.toggleExcludeGame('${this.escapeHtml(g.title)}', false)">
                                <i class="fa-solid fa-eye"></i> Include in Sync
                            </button>
                        ` : `
                            <button class="btn-icon" title="Ignore / Exclude from Fanta Cloud Sync (e.g. Steam Cloud game)" onclick="window.cloudSavesController.toggleExcludeGame('${this.escapeHtml(g.title)}', true)">
                                <i class="fa-solid fa-eye-slash"></i>
                            </button>
                        `}
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

                        ${g.cloud_exists ? `
                            <button class="btn-icon" style="color: var(--danger); border-color: rgba(239, 68, 68, 0.25);" title="Delete Cloud Backup" onclick="window.cloudSavesController.deleteCloudSave('${this.escapeHtml(g.title)}')">
                                <i class="fa-solid fa-trash-can"></i>
                            </button>
                        ` : ''}
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

    async syncPendingSelfHostedInputs() {
        const radioSelfHosted = document.getElementById('radioProviderSelfHosted');
        const url = document.getElementById('selfHostedUrlInput')?.value?.trim() || '';
        const apiKey = document.getElementById('selfHostedApiKeyInput')?.value?.trim() || '';
        if (radioSelfHosted && radioSelfHosted.checked && url) {
            if (!this.status || this.status.provider !== 'self_hosted' || this.status.self_hosted_url !== url || this.status.self_hosted_api_key !== apiKey) {
                await window.apiClient.configureCloud({ provider: 'self_hosted', self_hosted_url: url, self_hosted_api_key: apiKey });
                if (this.status) {
                    this.status.provider = 'self_hosted';
                    this.status.self_hosted_url = url;
                    this.status.self_hosted_api_key = apiKey;
                }
            }
        }
    }

    async backupGame(title) {
        await this.syncPendingSelfHostedInputs();
        if (!title) return;
        window.uiController.showToast(`Starting save backup for '${title}'...`, 'info');
        try {
            const game = this.games.find(g => g.title === title || g.title.toLowerCase() === title.toLowerCase());
            const payload = { title };
            if (game && game.save_path) {
                payload.save_path = game.save_path;
            }
            const res = await window.apiClient.backupCloudSave(payload);
            if (res && res.success) {
                window.uiController.showToast(`Backup complete for ${title}!`, 'success');
                // Instant live UI update
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
        await this.syncPendingSelfHostedInputs();
        if (!title) return;
        window.uiController.showToast(`Restoring save for '${title}' (Safety rollback created)...`, 'info');
        try {
            const game = this.games.find(g => g.title === title || g.title.toLowerCase() === title.toLowerCase());
            const payload = { title };
            if (game && game.save_path) {
                payload.save_path = game.save_path;
            }
            const res = await window.apiClient.restoreCloudSave(payload);
            if (res && res.success) {
                window.uiController.showToast(`Save restored for ${title}!`, 'success');
                // Instant live UI update
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
        await this.syncPendingSelfHostedInputs();
        const eligible = this.games.filter(g => g.local_exists && !g.is_excluded);
        if (eligible.length === 0) {
            window.uiController.showToast('No local save files detected to backup.', 'warning');
            return;
        }

        window.uiController.showToast(`Backing up saves for ${eligible.length} games...`, 'info');
        let successCount = 0;
        for (const g of eligible) {
            try {
                const payload = { title: g.title };
                if (g.save_path) {
                    payload.save_path = g.save_path;
                }
                const res = await window.apiClient.backupCloudSave(payload);
                if (res && res.success) successCount++;
            } catch (e) {
                console.error(`Backup error for ${g.title}:`, e);
            }
        }

        window.uiController.showToast(`Batch backup finished: ${successCount} / ${eligible.length} games synced.`, 'success');
        await this.loadGames();
    }

    async toggleExcludeGame(title, excluded) {
        if (!title) return;
        try {
            const res = await window.apiClient.toggleCloudExclude({ title, excluded });
            if (res && res.success) {
                window.uiController.showToast(
                    res.message || (excluded ? `Ignored '${title}' from Fanta Cloud Sync.` : `Included '${title}' in Fanta Cloud Sync.`),
                    'info'
                );
                await this.loadGames();
            } else {
                window.uiController.showToast(`Could not update exclusion: ${(res && res.error) || 'Unknown error'}`, 'danger');
            }
        } catch (err) {
            window.uiController.showToast(`Exclusion error: ${err.message}`, 'danger');
        }
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

    async deleteCloudSave(title) {
        if (!title) return;
        window.uiController.showToast(`Deleting cloud backup for '${title}'...`, 'info');
        try {
            const res = await window.apiClient.deleteCloudSave({ title });
            if (res && res.success) {
                window.uiController.showToast(res.message || `Deleted cloud backup for ${title}!`, 'success');
                await this.loadGames();
            } else {
                window.uiController.showToast(`Delete failed: ${res.error || 'Unknown error'}`, 'danger');
            }
        } catch (err) {
            window.uiController.showToast(`Delete error: ${err.message}`, 'danger');
        }
    }

    async testSelfHostedConnection() {
        const urlInput = document.getElementById('selfHostedUrlInput');
        const apiKeyInput = document.getElementById('selfHostedApiKeyInput');
        const statusText = document.getElementById('selfHostedStatusText');
        const testBtn = document.getElementById('testSelfHostedBtn');

        const url = urlInput ? urlInput.value.trim() : '';
        const apiKey = apiKeyInput ? apiKeyInput.value.trim() : '';

        if (!url) {
            window.uiController.showToast('Please enter your Self-Hosted Server URL first.', 'warning');
            return;
        }

        if (testBtn) {
            testBtn.disabled = true;
            testBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Testing...';
        }
        if (statusText) {
            statusText.innerHTML = `<span style="color: var(--text-muted);"><i class="fa-solid fa-spinner fa-spin"></i> Connecting to server...</span>`;
        }

        try {
            const res = await window.apiClient.testSelfHostedCloud({ url, api_key: apiKey });
            if (res && res.success) {
                const latency = res.latency_ms !== undefined ? ` • ${res.latency_ms}ms` : '';
                const srvName = res.server_name || 'Fanta-OFME-Cloud';
                if (statusText) {
                    statusText.innerHTML = `
                        <span style="color: var(--success); font-weight: 600; display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-circle-check"></i> Connected to ${this.escapeHtml(srvName)} (v${this.escapeHtml(res.version || '1.0')}${latency})
                        </span>
                    `;
                }
                await window.apiClient.configureCloud({ provider: 'self_hosted', self_hosted_url: url, self_hosted_api_key: apiKey });
                window.uiController.showToast(`Connected to ${srvName}${latency} & saved settings!`, 'success');
                await this.loadGames();
            } else {
                const errMsg = (res && res.error) ? res.error : 'Connection failed';
                if (statusText) {
                    statusText.innerHTML = `
                        <span style="color: var(--danger); font-weight: 500; display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-circle-exclamation"></i> ${this.escapeHtml(errMsg)}
                        </span>
                    `;
                }
                window.uiController.showToast(errMsg, 'danger');
            }
        } catch (err) {
            if (statusText) {
                statusText.innerHTML = `
                    <span style="color: var(--danger); font-weight: 500; display: flex; align-items: center; gap: 6px;">
                        <i class="fa-solid fa-circle-exclamation"></i> ${this.escapeHtml(err.message)}
                    </span>
                `;
            }
            window.uiController.showToast(`Connection test failed: ${err.message}`, 'danger');
        } finally {
            if (testBtn) {
                testBtn.disabled = false;
                testBtn.innerHTML = '<i class="fa-solid fa-plug-circle-check"></i> Test Connection';
            }
        }
    }

    swapTransferProviders() {
        const srcSelect = document.getElementById('cloudTransferSourceSelect');
        const dstSelect = document.getElementById('cloudTransferTargetSelect');
        if (!srcSelect || !dstSelect) return;
        const tmp = srcSelect.value;
        srcSelect.value = dstSelect.value;
        dstSelect.value = tmp;
        srcSelect.dispatchEvent(new Event('change', { bubbles: true }));
        dstSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }

    async transferAllSaves() {
        const srcSelect = document.getElementById('cloudTransferSourceSelect');
        const dstSelect = document.getElementById('cloudTransferTargetSelect');
        const modeSelect = document.getElementById('cloudTransferModeSelect');
        const startBtn = document.getElementById('startCloudTransferBtn');
        const statusEl = document.getElementById('cloudTransferStatusText');

        const sourceProvider = srcSelect ? srcSelect.value : 'gdrive_api';
        const targetProvider = dstSelect ? dstSelect.value : 'self_hosted';
        const mode = modeSelect ? modeSelect.value : 'newer_or_missing';

        if (sourceProvider === targetProvider) {
            window.uiController.showToast('Please select two different providers to transfer between.', 'warning');
            return;
        }

        // First persist any typed URL / API key / Local Cloud Path in the UI inputs
        const localCloudPath = document.getElementById('localCloudPathInput')?.value?.trim() || '';
        const selfHostedUrl = document.getElementById('selfHostedUrlInput')?.value?.trim() || '';
        const selfHostedApiKey = document.getElementById('selfHostedApiKeyInput')?.value?.trim() || '';
        try {
            await window.apiClient.configureCloud({
                local_cloud_path: localCloudPath,
                self_hosted_url: selfHostedUrl,
                self_hosted_api_key: selfHostedApiKey
            });
        } catch (_) {}

        if (startBtn) {
            startBtn.disabled = true;
            startBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Transferring...';
        }
        if (statusEl) {
            statusEl.style.display = 'block';
            statusEl.innerHTML = `<span style="color: var(--text-muted);"><i class="fa-solid fa-spinner fa-spin"></i> Transferring save archives across providers...</span>`;
        }

        try {
            const res = await window.apiClient.transferCloudSaves({
                source_provider: sourceProvider,
                target_provider: targetProvider,
                mode,
                switch_to_target: true
            });

            if (res && res.success) {
                if (statusEl) {
                    statusEl.innerHTML = `
                        <span style="color: var(--success); font-weight: 600; display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-circle-check"></i> ${this.escapeHtml(res.message || 'Transfer completed!')}
                        </span>
                    `;
                }
                window.uiController.showToast(res.message || 'Transfer completed successfully!', 'success');
                await this.loadAll();
            } else {
                const errMsg = (res && res.error) ? res.error : (res && res.message ? res.message : 'Transfer failed');
                if (statusEl) {
                    statusEl.innerHTML = `
                        <span style="color: var(--danger); font-weight: 500; display: flex; align-items: center; gap: 6px;">
                            <i class="fa-solid fa-circle-exclamation"></i> ${this.escapeHtml(errMsg)}
                        </span>
                    `;
                }
                window.uiController.showToast(errMsg, 'danger');
            }
        } catch (err) {
            if (statusEl) {
                statusEl.innerHTML = `
                    <span style="color: var(--danger); font-weight: 500; display: flex; align-items: center; gap: 6px;">
                        <i class="fa-solid fa-circle-exclamation"></i> ${this.escapeHtml(err.message)}
                    </span>
                `;
            }
            window.uiController.showToast(`Transfer error: ${err.message}`, 'danger');
        } finally {
            if (startBtn) {
                startBtn.disabled = false;
                startBtn.innerHTML = '<i class="fa-solid fa-truck-fast"></i> Transfer All Saves';
            }
        }
    }

    async savePreferences() {
        const radioLocal = document.getElementById('radioProviderLocal');
        const radioSelfHosted = document.getElementById('radioProviderSelfHosted');
        let provider = 'gdrive_api';
        if (radioLocal && radioLocal.checked) {
            provider = 'local_folder';
        } else if (radioSelfHosted && radioSelfHosted.checked) {
            provider = 'self_hosted';
        }

        const autoSync = document.getElementById('cloudAutoSyncToggle')?.checked || false;
        const autoExcludeSteamCloud = document.getElementById('cloudAutoExcludeSteamToggle')?.checked ?? true;
        const localCloudPath = document.getElementById('localCloudPathInput')?.value?.trim() || '';
        const selfHostedUrl = document.getElementById('selfHostedUrlInput')?.value?.trim() || '';
        const selfHostedApiKey = document.getElementById('selfHostedApiKeyInput')?.value?.trim() || '';

        if (provider === 'self_hosted' && !selfHostedUrl) {
            window.uiController.showToast('Please enter a Server URL for your Self-Hosted Cloud Server.', 'warning');
            return;
        }

        try {
            await window.apiClient.configureCloud({
                provider,
                auto_sync: autoSync,
                auto_exclude_steam_cloud: autoExcludeSteamCloud,
                local_cloud_path: localCloudPath,
                self_hosted_url: selfHostedUrl,
                self_hosted_api_key: selfHostedApiKey
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
