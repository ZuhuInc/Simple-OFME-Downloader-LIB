/**
 * Details Controller
 * Manages game details slide-over modal, metadata display, install/update directory selection modal,
 * download triggers, and Steam integration actions.
 */

class DetailsController {
    constructor() {
        this.currentGame = null;
        this.pendingDownloadType = 'main';

        // Details Modal Elements
        this.modal = document.getElementById('gameDetailsModal');
        this.coverEl = document.getElementById('detailsCoverImg');
        this.titleEl = document.getElementById('detailsTitle');
        this.descEl = document.getElementById('detailsDescription');
        this.hostEl = document.getElementById('detailsHost');
        this.sizeEl = document.getElementById('detailsSize');
        this.versionEl = document.getElementById('detailsVersion');
        this.statusEl = document.getElementById('detailsStatus');
        this.locationEl = document.getElementById('detailsLocation');
        this.originLinkEl = document.getElementById('detailsOriginLink');
        this.downloadGroup = document.getElementById('detailsDownloadGroup');
        this.downloadMainBtn = document.getElementById('detailsDownloadMainBtn');
        this.downloadBtnText = document.getElementById('detailsDownloadBtnText');
        this.mirrorToggleBtn = document.getElementById('detailsMirrorToggleBtn');
        this.mirrorDropdown = document.getElementById('detailsMirrorDropdown');
        this.selectedMirrorHost = null;
        this.downloadFixBtn = document.getElementById('detailsDownloadFixBtn');
        this.openMirrorBtn = document.getElementById('detailsOpenMirrorBtn');
        this.addSteamBtn = document.getElementById('detailsAddSteamBtn');
        this.launchBtn = document.getElementById('detailsLaunchBtn');
        this.removeGameBtn = document.getElementById('detailsRemoveGameBtn');

        // Bypass Elements
        this.bypassBtn = document.getElementById('detailsBypassBtn');
        this.bypassIcon = document.getElementById('detailsBypassIcon');
        this.bypassBadge = document.getElementById('detailsBypassBadge');
        this.bypassList = new Set();

        // Download Setup Modal Elements
        this.setupModal = document.getElementById('downloadSetupModal');
        this.setupTitle = document.getElementById('setupModalTitle');
        this.setupSubtitle = document.getElementById('setupModalSubtitle');
        this.setupIcon = document.getElementById('setupModalIcon');
        this.setupThumb = document.getElementById('setupGameThumb');
        this.setupGameTitle = document.getElementById('setupGameTitle');
        this.setupActionBadge = document.getElementById('setupActionBadge');
        this.setupGameVersion = document.getElementById('setupGameVersion');
        this.setupGameSize = document.getElementById('setupGameSize');
        this.setupGameHost = document.getElementById('setupGameHost');
        this.setupLocationLabel = document.getElementById('setupLocationLabel');
        this.setupLocationStatus = document.getElementById('setupLocationStatus');
        this.setupInstallPathInput = document.getElementById('setupInstallPathInput');
        this.setupLocationHelp = document.getElementById('setupLocationHelp');
        this.setupAutoExtractCheck = document.getElementById('setupAutoExtractCheck');
        this.setupDeleteArchiveCheck = document.getElementById('setupDeleteArchiveCheck');
        this.setupHostSelectorRow = document.getElementById('setupHostSelectorRow');
        this.setupHostPills = document.getElementById('setupHostPills');
        this.browseInstallPathBtn = document.getElementById('browseInstallPathBtn');
        this.confirmSetupDownloadBtn = document.getElementById('confirmSetupDownloadBtn');
        this.cancelSetupDownloadBtn = document.getElementById('cancelSetupDownloadBtn');
        this.closeDownloadSetupBtn = document.getElementById('closeDownloadSetupBtn');
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        const closeBtn = document.getElementById('closeDetailsBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.close());
        }

        const openFolderBtn = document.getElementById('openGameFolderBtn');
        if (openFolderBtn) {
            openFolderBtn.addEventListener('click', () => this.openInstallFolder());
        }

        if (this.bypassBtn) {
            this.bypassBtn.addEventListener('click', () => this.toggleBypass());
        }

        if (this.originLinkEl) {
            this.originLinkEl.addEventListener('click', (e) => {
                e.preventDefault();
                if (this.currentGame && this.currentGame.origin_url) {
                    if (window.api && window.api.openExternal) {
                        window.api.openExternal(this.currentGame.origin_url);
                    } else {
                        window.open(this.currentGame.origin_url, '_blank');
                    }
                }
            });
        }

        if (this.openMirrorBtn) {
            this.openMirrorBtn.addEventListener('click', () => {
                if (this.currentGame) {
                    const activeParts = this.getActiveParts();
                    const targetUrl = (Array.isArray(activeParts) && activeParts[0]) || this.currentGame.main_game_url || this.currentGame.download_url || this.currentGame.origin_url;
                    if (targetUrl) {
                        if (window.api && window.api.openExternal) {
                            window.api.openExternal(targetUrl);
                        } else {
                            window.open(targetUrl, '_blank');
                        }
                    } else {
                        window.uiController.showToast('No mirror link available.', 'warning');
                    }
                }
            });
        }

        if (this.mirrorToggleBtn) {
            this.mirrorToggleBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (this.mirrorDropdown) {
                    const isVisible = this.mirrorDropdown.style.display === 'flex';
                    this.mirrorDropdown.style.display = isVisible ? 'none' : 'flex';
                }
            });
        }

        document.addEventListener('click', (e) => {
            if (this.mirrorDropdown && this.mirrorDropdown.style.display === 'flex') {
                if (!this.mirrorDropdown.contains(e.target) && !this.mirrorToggleBtn?.contains(e.target)) {
                    this.mirrorDropdown.style.display = 'none';
                }
            }
        });

        if (this.downloadMainBtn) {
            this.downloadMainBtn.addEventListener('click', () => this.openDownloadSetup('main'));
        }

        if (this.downloadFixBtn) {
            this.downloadFixBtn.addEventListener('click', () => this.openDownloadSetup('fix'));
        }

        if (this.addSteamBtn) {
            this.addSteamBtn.addEventListener('click', () => this.addToSteam());
        }

        if (this.launchBtn) {
            this.launchBtn.addEventListener('click', () => this.launchGame());
        }

        if (this.removeGameBtn) {
            this.removeGameBtn.addEventListener('click', () => this.removeGame());
        }

        // Setup Modal Events
        if (this.browseInstallPathBtn) {
            this.browseInstallPathBtn.addEventListener('click', async () => {
                try {
                    const chosen = await window.api?.selectDirectory();
                    if (chosen && this.setupInstallPathInput) {
                        this.setupInstallPathInput.value = chosen;
                    }
                } catch (err) {
                    console.error('[DetailsController] Directory selection failed:', err);
                }
            });
        }

        if (this.confirmSetupDownloadBtn) {
            this.confirmSetupDownloadBtn.addEventListener('click', () => this.executeDownload());
        }

        if (this.cancelSetupDownloadBtn) {
            this.cancelSetupDownloadBtn.addEventListener('click', () => this.closeDownloadSetup());
        }

        if (this.closeDownloadSetupBtn) {
            this.closeDownloadSetupBtn.addEventListener('click', () => this.closeDownloadSetup());
        }

        // Remove Modal Events
        const deleteFilesBtn = document.getElementById('confirmDeleteAllBtn');
        if (deleteFilesBtn) {
            deleteFilesBtn.addEventListener('click', () => this.executeRemoval(true));
        }

        const unregisterBtn = document.getElementById('confirmUnregisterOnlyBtn');
        if (unregisterBtn) {
            unregisterBtn.addEventListener('click', () => this.executeRemoval(false));
        }

        const removeSteamBtn = document.getElementById('confirmRemoveSteamOnlyBtn');
        if (removeSteamBtn) {
            removeSteamBtn.addEventListener('click', () => this.executeSteamRemoval());
        }

        const cancelRemoveBtn = document.getElementById('cancelRemoveBtn');
        if (cancelRemoveBtn) {
            cancelRemoveBtn.addEventListener('click', () => this.closeRemoveModal());
        }
    }

    openGame(game) {
        this.currentGame = game;
        if (!this.modal) return;

        if (this.coverEl) this.coverEl.src = game.thumbnail || 'assets/OFME-DWND-ICO.ico';
        if (this.titleEl) this.titleEl.textContent = game.title || 'Unknown Game';
        if (this.descEl) this.descEl.textContent = game.description || 'No description available.';
        const hostDisplay = game.source ? `${game.source} (${game.host || 'Direct'})` : (game.host || 'Direct');
        if (this.hostEl) this.hostEl.textContent = hostDisplay;
        if (this.sizeEl) this.sizeEl.textContent = game.approx_size || game.size || 'N/A';
        if (this.versionEl) this.versionEl.textContent = `v${game.version || '1.0'}`;

        if (this.statusEl) {
            const statusClass = game.status === 1 ? 'status-uptodate' : (game.status === 2 ? 'status-update' : 'status-missing');
            const statusLabel = game.status === 1 ? 'Installed (Up to date)' : (game.status === 2 ? 'Update Available' : 'Not Installed');
            this.statusEl.className = `status-pill ${statusClass}`;
            this.statusEl.textContent = statusLabel;
        }

        if (this.locationEl) {
            const defaultBase = window.settingsController?.settings?.extract_path || window.settingsController?.settings?.default_download_path || '';
            if (game.location) {
                this.locationEl.textContent = game.location;
                this.locationEl.style.color = '#fff';
            } else {
                this.locationEl.textContent = defaultBase ? `${defaultBase} (Default)` : 'Not set (Default)';
                this.locationEl.style.color = 'var(--text-secondary)';
            }
        }

        if (this.originLinkEl) {
            if (game.origin_url) {
                this.originLinkEl.href = game.origin_url;
                this.originLinkEl.style.display = 'inline-flex';
            } else {
                this.originLinkEl.style.display = 'none';
            }
        }

        // Steam button state: If already added to Steam (has steam_url), show "Play on Steam"
        if (this.addSteamBtn) {
            if (game.steam_url) {
                this.addSteamBtn.innerHTML = '<i class="fa-brands fa-steam"></i> Play on Steam';
                this.addSteamBtn.title = 'Launch via Steam shortcut';
            } else {
                this.addSteamBtn.innerHTML = '<i class="fa-brands fa-steam"></i> Add to Steam';
                this.addSteamBtn.title = 'Create Steam non-game shortcut';
            }
        }

        this.selectedMirrorHost = null;

        // Action button labels based on status
        const actionLabel = game.status === 2 ? 'Update Game' : (game.status === 1 ? 'Re-download' : 'Download Game');
        if (this.downloadBtnText) {
            this.downloadBtnText.textContent = actionLabel;
        } else if (this.downloadMainBtn) {
            this.downloadMainBtn.innerHTML = `<i class="fa-solid fa-cloud-arrow-down"></i> ${actionLabel}`;
        }

        // Toggle Fix button visibility if fix URL is provided
        const hasFix = Boolean(game.fix_url);
        if (this.downloadFixBtn) {
            this.downloadFixBtn.style.display = hasFix ? 'inline-flex' : 'none';
        }
        if (this.downloadGroup) {
            this.downloadGroup.style.gridColumn = hasFix ? 'auto' : '1 / -1';
        } else if (this.downloadMainBtn) {
            this.downloadMainBtn.style.gridColumn = hasFix ? 'auto' : '1 / -1';
        }

        // Render Mirror Dropdown
        this.renderMirrorDropdown();

        // Show/hide remove button based on installation
        if (this.removeGameBtn) {
            this.removeGameBtn.style.display = (game.status === 1 || game.status === 2 || game.is_downloaded) ? 'inline-flex' : 'none';
        }

        // Show/hide open install folder button based on installation
        const openFolderBtn = document.getElementById('openGameFolderBtn');
        if (openFolderBtn) {
            const isInstalled = (game.status === 1 || game.status === 2 || game.is_downloaded);
            openFolderBtn.style.display = isInstalled ? 'flex' : 'none';
        }

        // Initialize and update bypass status for this game
        const titleKey = (game.title || '').trim().toLowerCase();
        const isBypassed = this.bypassList.has(titleKey);
        this.updateBypassUI(isBypassed);

        this.loadBypassList().then(() => {
            if (this.currentGame && (this.currentGame.title || '').trim().toLowerCase() === titleKey) {
                this.updateBypassUI(this.bypassList.has(titleKey));
            }
        });

        this.modal.classList.add('active');
    }

    async loadBypassList() {
        try {
            const res = await window.apiClient.getBypassList();
            if (res && res.bypass_list) {
                this.bypassList = new Set(res.bypass_list.map(t => String(t).trim().toLowerCase()));
            }
        } catch (e) {
            console.error('[Details] Load bypass list error:', e);
        }
    }

    updateBypassUI(isBypassed) {
        if (this.bypassBadge) this.bypassBadge.style.display = isBypassed ? 'inline-flex' : 'none';
        if (this.bypassBtn) {
            if (isBypassed) {
                this.bypassBtn.classList.add('bypassed');
                this.bypassBtn.title = 'Bypassed in Version Checker (Click to include in audits)';
            } else {
                this.bypassBtn.classList.remove('bypassed');
                this.bypassBtn.title = 'Bypass Version Checker (Click to ignore in audits)';
            }
        }
        if (this.bypassIcon) {
            this.bypassIcon.className = isBypassed ? 'fa-solid fa-bell-slash' : 'fa-solid fa-bell';
            this.bypassIcon.style.color = isBypassed ? 'var(--accent)' : '';
        }
    }

    async toggleBypass(explicitState = null) {
        if (!this.currentGame || !this.currentGame.title) return;
        const title = this.currentGame.title;
        const titleKey = title.trim().toLowerCase();
        try {
            const res = await window.apiClient.toggleBypass(title, explicitState);
            if (res && res.success) {
                const nowBypassed = res.bypassed;
                if (nowBypassed) {
                    this.bypassList.add(titleKey);
                    window.uiController.showToast(`Bypassed "${title}" from version audits`, 'warning');
                } else {
                    this.bypassList.delete(titleKey);
                    window.uiController.showToast(`Included "${title}" in version audits`, 'success');
                }
                this.updateBypassUI(nowBypassed);
            }
        } catch (err) {
            console.error('[Details] Toggle bypass error:', err);
            window.uiController.showToast('Failed to update bypass setting', 'danger');
        }
    }

    close() {
        if (this.modal) this.modal.classList.remove('active');
        this.currentGame = null;
    }

    getParentOrSelf(pathStr) {
        if (!pathStr) return window.settingsController?.settings?.extract_path || '';
        const normalized = pathStr.replace(/[\\/]+$/, '');
        const parts = normalized.split(/[\\/]/);
        if (parts.length > 2) {
            return parts.slice(0, -1).join('\\');
        }
        return normalized;
    }

    openDownloadSetup(type = 'main') {
        if (!this.currentGame || !this.setupModal) return;
        this.pendingDownloadType = type;

        const defaultBase = window.settingsController?.settings?.extract_path || 
                            window.settingsController?.settings?.default_download_path || 
                            '';

        const autoExtract = window.settingsController?.settings?.auto_extract !== false;
        const autoDelete = window.settingsController?.settings?.auto_delete_archive !== false;

        // Populate base info
        if (this.setupThumb) this.setupThumb.src = this.currentGame.thumbnail || 'assets/OFME-DWND-ICO.ico';
        if (this.setupGameTitle) this.setupGameTitle.textContent = this.currentGame.title || 'Unknown Game';
        if (this.setupGameVersion) this.setupGameVersion.textContent = `v${this.currentGame.version || '1.0'}`;
        if (this.setupGameSize) this.setupGameSize.textContent = this.currentGame.approx_size || this.currentGame.size || 'Unknown';
        const hostDisplay = this.currentGame.source ? `${this.currentGame.source} (${this.currentGame.host || 'Direct'})` : (this.currentGame.host || 'Direct');
        if (this.setupGameHost) this.setupGameHost.textContent = hostDisplay;
        if (this.setupAutoExtractCheck) this.setupAutoExtractCheck.checked = autoExtract;
        if (this.setupDeleteArchiveCheck) this.setupDeleteArchiveCheck.checked = autoDelete;

        // Multi-part indicator & Host display
        this.setupHostSelector();
        this.updateSetupHostDisplay();

        // Contextual styling based on action type
        if (type === 'fix') {
            if (this.setupTitle) this.setupTitle.textContent = 'Apply Multiplayer Fix';
            if (this.setupSubtitle) this.setupSubtitle.textContent = 'Confirm target game directory for online fix files.';
            if (this.setupIcon) {
                this.setupIcon.style.background = 'rgba(96, 165, 250, 0.15)';
                this.setupIcon.style.border = '1px solid rgba(96, 165, 250, 0.35)';
                this.setupIcon.style.color = '#60a5fa';
                this.setupIcon.innerHTML = '<i class="fa-solid fa-wrench"></i>';
            }
            if (this.setupActionBadge) {
                this.setupActionBadge.className = 'status-pill';
                this.setupActionBadge.style.cssText = 'font-size: 9px; padding: 2px 8px; background: rgba(96, 165, 250, 0.15); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.35);';
                this.setupActionBadge.innerHTML = '<i class="fa-solid fa-wrench"></i> Multiplayer Fix';
            }
            if (this.setupLocationLabel) this.setupLocationLabel.textContent = 'Game Installation Folder:';
            
            const fixTarget = this.currentGame.location || `${defaultBase}\\${this.currentGame.title}`;
            if (this.setupInstallPathInput) this.setupInstallPathInput.value = fixTarget;
            if (this.setupLocationStatus) this.setupLocationStatus.textContent = this.currentGame.location ? 'Installed Folder' : 'Default Folder';
            if (this.setupLocationHelp) {
                this.setupLocationHelp.innerHTML = '<i class="fa-solid fa-circle-info"></i> The online fix files will be extracted directly into this game folder.';
            }
            if (this.confirmSetupDownloadBtn) {
                this.confirmSetupDownloadBtn.innerHTML = '<i class="fa-solid fa-wrench"></i> Start Fix Download';
            }
        } else if (this.currentGame.status === 2) {
            // Update Game
            if (this.setupTitle) this.setupTitle.textContent = 'Update Game';
            if (this.setupSubtitle) this.setupSubtitle.textContent = 'Confirm installation folder to update the game files.';
            if (this.setupIcon) {
                this.setupIcon.style.background = 'rgba(245, 158, 11, 0.15)';
                this.setupIcon.style.border = '1px solid rgba(245, 158, 11, 0.35)';
                this.setupIcon.style.color = 'var(--warning)';
                this.setupIcon.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i>';
            }
            if (this.setupActionBadge) {
                this.setupActionBadge.className = 'status-pill status-update';
                this.setupActionBadge.style.cssText = 'font-size: 9px; padding: 2px 8px;';
                this.setupActionBadge.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Update Available';
            }
            if (this.setupLocationLabel) this.setupLocationLabel.textContent = 'Installation Directory:';

            const updateTarget = this.currentGame.location ? this.getParentOrSelf(this.currentGame.location) : defaultBase;
            if (this.setupInstallPathInput) this.setupInstallPathInput.value = updateTarget;
            if (this.setupLocationStatus) this.setupLocationStatus.textContent = this.currentGame.location ? 'Existing Install' : 'Default Folder';
            if (this.setupLocationHelp) {
                this.setupLocationHelp.innerHTML = `<i class="fa-solid fa-circle-info"></i> The updated game will extract into this directory (e.g. <code>${updateTarget}\\${this.currentGame.title}</code>).`;
            }
            if (this.confirmSetupDownloadBtn) {
                this.confirmSetupDownloadBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Start Update';
            }
        } else if (this.currentGame.status === 1) {
            // Re-download
            if (this.setupTitle) this.setupTitle.textContent = 'Re-download Game';
            if (this.setupSubtitle) this.setupSubtitle.textContent = 'Confirm target directory for re-installation.';
            if (this.setupIcon) {
                this.setupIcon.style.background = 'rgba(212, 168, 83, 0.15)';
                this.setupIcon.style.border = '1px solid rgba(212, 168, 83, 0.35)';
                this.setupIcon.style.color = 'var(--accent)';
                this.setupIcon.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i>';
            }
            if (this.setupActionBadge) {
                this.setupActionBadge.className = 'status-pill';
                this.setupActionBadge.style.cssText = 'font-size: 9px; padding: 2px 8px; background: rgba(212, 168, 83, 0.15); color: var(--accent); border: 1px solid rgba(212, 168, 83, 0.35);';
                this.setupActionBadge.innerHTML = '<i class="fa-solid fa-rotate-left"></i> Re-download';
            }
            if (this.setupLocationLabel) this.setupLocationLabel.textContent = 'Installation Directory:';

            const reTarget = this.currentGame.location ? this.getParentOrSelf(this.currentGame.location) : defaultBase;
            if (this.setupInstallPathInput) this.setupInstallPathInput.value = reTarget;
            if (this.setupLocationStatus) this.setupLocationStatus.textContent = this.currentGame.location ? 'Existing Install' : 'Default Folder';
            if (this.setupLocationHelp) {
                this.setupLocationHelp.innerHTML = `<i class="fa-solid fa-circle-info"></i> The game will unpack into this directory.`;
            }
            if (this.confirmSetupDownloadBtn) {
                this.confirmSetupDownloadBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> Start Download';
            }
        } else {
            // New Installation
            if (this.setupTitle) this.setupTitle.textContent = 'Install Game';
            if (this.setupSubtitle) this.setupSubtitle.textContent = 'Choose the installation directory for this game.';
            if (this.setupIcon) {
                this.setupIcon.style.background = 'rgba(212, 168, 83, 0.15)';
                this.setupIcon.style.border = '1px solid rgba(212, 168, 83, 0.35)';
                this.setupIcon.style.color = 'var(--accent)';
                this.setupIcon.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i>';
            }
            if (this.setupActionBadge) {
                this.setupActionBadge.className = 'status-pill';
                this.setupActionBadge.style.cssText = 'font-size: 9px; padding: 2px 8px; background: rgba(212, 168, 83, 0.15); color: var(--accent); border: 1px solid rgba(212, 168, 83, 0.35);';
                this.setupActionBadge.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> New Install';
            }
            if (this.setupLocationLabel) this.setupLocationLabel.textContent = 'Installation Directory:';
            if (this.setupInstallPathInput) this.setupInstallPathInput.value = defaultBase;
            if (this.setupLocationStatus) this.setupLocationStatus.textContent = 'Default Folder';
            if (this.setupLocationHelp) {
                this.setupLocationHelp.innerHTML = `<i class="fa-solid fa-circle-info"></i> The game will unpack into its own subfolder inside this directory (e.g. <code>${defaultBase}\\${this.currentGame.title}</code>).`;
            }
            if (this.confirmSetupDownloadBtn) {
                this.confirmSetupDownloadBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> Start Download & Install';
            }
        }

        this.setupModal.classList.add('active');
    }

    closeDownloadSetup() {
        if (this.setupModal) this.setupModal.classList.remove('active');
    }

    async executeDownload() {
        if (!this.currentGame) return;

        const type = this.pendingDownloadType || 'main';
        const defaultBase = window.settingsController?.settings?.extract_path || window.settingsController?.settings?.default_download_path || '';
        const targetPath = (this.setupInstallPathInput ? this.setupInstallPathInput.value.trim() : '') || defaultBase;
        const autoExtract = this.setupAutoExtractCheck ? Boolean(this.setupAutoExtractCheck.checked) : true;
        const autoDelete = this.setupDeleteArchiveCheck ? Boolean(this.setupDeleteArchiveCheck.checked) : true;

        this.closeDownloadSetup();

        const activeParts = this.getActiveParts();
        const activeFix = this.getActiveFix();
        const activeHost = this.getActiveHost();

        // Multi-part game download execution
        if (type === 'main' && Array.isArray(activeParts) && activeParts.length > 1) {
            try {
                window.uiController.showToast(`Queueing ${activeParts.length} parts from ${activeHost} for ${this.currentGame.title}...`, 'info');
                for (let i = 0; i < activeParts.length; i++) {
                    const partUrl = activeParts[i];
                    const filename = `${this.currentGame.title}_Part${i + 1}.rar`;
                    await window.apiClient.addDownload(partUrl, filename, {
                        game_id: this.currentGame.id,
                        title: this.currentGame.title,
                        version: this.currentGame.version,
                        type: `main_part_${i + 1}`,
                        host: activeHost,
                        extract_dir: targetPath,
                        auto_extract: autoExtract,
                        auto_delete_archive: autoDelete
                    });
                }
                window.uiController.showToast(`Added ${activeParts.length} parts to Download Queue`, 'success');
                window.uiController.switchTab('downloadsTab');
                this.close();
                return;
            } catch (err) {
                window.uiController.showToast(`Multi-part download failed: ${err.message}`, 'danger');
                return;
            }
        }

        const targetUrl = type === 'fix' ? activeFix : (activeParts[0] || this.currentGame.main_game_url || this.currentGame.download_url);
        if (!targetUrl) {
            window.uiController.showToast('No direct download link configured for this title.', 'warning');
            return;
        }

        try {
            window.uiController.showToast(`Queueing download from ${activeHost} for ${this.currentGame.title}...`, 'info');
            const filename = `${this.currentGame.title}_${type === 'fix' ? 'Fix' : 'Game'}.rar`;
            const res = await window.apiClient.addDownload(targetUrl, filename, {
                game_id: this.currentGame.id,
                title: this.currentGame.title,
                version: this.currentGame.version,
                location: this.currentGame.location || '',
                host: activeHost,
                extract_dir: targetPath,
                auto_extract: autoExtract,
                auto_delete_archive: autoDelete,
                type: type
            });

            if (res.success) {
                const cleanJobId = String(res.job_id || '').replace(/^job_/i, '');
                window.uiController.showToast(`Added to Download Queue (Job #${cleanJobId})`, 'success');
                window.uiController.switchTab('downloadsTab');
                this.close();
            }
        } catch (err) {
            window.uiController.showToast(`Download failed: ${err.message}`, 'danger');
        }
    }

    // ─── MIRROR HELPERS ───

    getActiveHost() {
        if (!this.currentGame) return 'Direct';
        if (this.selectedMirrorHost && this.currentGame.mirrors && this.currentGame.mirrors[this.selectedMirrorHost]) {
            return this.selectedMirrorHost;
        }
        return this.currentGame.host || 'Direct';
    }

    getActiveParts() {
        if (!this.currentGame) return [];
        if (this.selectedMirrorHost && this.currentGame.mirrors && this.currentGame.mirrors[this.selectedMirrorHost]) {
            const m = this.currentGame.mirrors[this.selectedMirrorHost];
            if (Array.isArray(m.parts) && m.parts.length > 0) return m.parts;
            if (m.url) return [m.url];
        }
        if (Array.isArray(this.currentGame.parts) && this.currentGame.parts.length > 0) {
            return this.currentGame.parts;
        }
        if (this.currentGame.main_game_url) return [this.currentGame.main_game_url];
        if (this.currentGame.download_url) return [this.currentGame.download_url];
        return [];
    }

    getActiveFix() {
        if (!this.currentGame) return '';
        if (this.selectedMirrorHost && this.currentGame.mirrors && this.currentGame.mirrors[this.selectedMirrorHost]) {
            const m = this.currentGame.mirrors[this.selectedMirrorHost];
            if (m.fix_url) return m.fix_url;
        }
        return this.currentGame.fix_url || '';
    }

    selectMirror(hostKey) {
        this.selectedMirrorHost = hostKey;
        if (this.mirrorDropdown) this.mirrorDropdown.style.display = 'none';

        const activeHost = this.getActiveHost();
        const parts = this.getActiveParts();

        if (this.hostEl) {
            this.hostEl.textContent = parts.length > 1 ? `${activeHost} (${parts.length} Parts)` : activeHost;
        }

        const actionLabel = this.currentGame?.status === 2 ? 'Update Game' : (this.currentGame?.status === 1 ? 'Re-download' : 'Download Game');
        if (this.downloadBtnText) {
            this.downloadBtnText.textContent = `${actionLabel} (${activeHost})`;
        }

        if (this.mirrorDropdown) {
            this.mirrorDropdown.querySelectorAll('.mirror-dropdown-item').forEach(el => {
                const elKey = el.getAttribute('data-host');
                if ((!this.selectedMirrorHost && !elKey) || (this.selectedMirrorHost === elKey)) {
                    el.classList.add('active');
                } else {
                    el.classList.remove('active');
                }
            });
        }

        window.uiController?.showToast(`Selected download host: ${activeHost}`, 'info');
    }

    renderMirrorDropdown() {
        if (!this.mirrorDropdown) return;
        this.mirrorDropdown.innerHTML = '';
        this.mirrorDropdown.style.display = 'none';

        if (!this.currentGame) {
            if (this.mirrorToggleBtn) this.mirrorToggleBtn.style.display = 'none';
            if (this.downloadGroup) this.downloadGroup.classList.remove('has-mirrors');
            if (this.downloadMainBtn) {
                this.downloadMainBtn.style.borderTopRightRadius = 'var(--radius-sm)';
                this.downloadMainBtn.style.borderBottomRightRadius = 'var(--radius-sm)';
            }
            return;
        }

        const primaryHost = this.currentGame.host || 'Primary';
        const primaryParts = (Array.isArray(this.currentGame.parts) ? this.currentGame.parts : [this.currentGame.main_game_url || this.currentGame.download_url]).filter(Boolean);
        const mirrors = this.currentGame.mirrors || {};
        const mirrorKeys = Object.keys(mirrors).filter(k => {
            const m = mirrors[k];
            return m && ((Array.isArray(m.parts) && m.parts.length > 0) || m.url || m.fix_url);
        });

        if (mirrorKeys.length === 0) {
            if (this.mirrorToggleBtn) this.mirrorToggleBtn.style.display = 'none';
            if (this.downloadGroup) this.downloadGroup.classList.remove('has-mirrors');
            if (this.downloadMainBtn) {
                this.downloadMainBtn.style.borderTopRightRadius = 'var(--radius-sm)';
                this.downloadMainBtn.style.borderBottomRightRadius = 'var(--radius-sm)';
            }
            return;
        }

        if (this.mirrorToggleBtn) this.mirrorToggleBtn.style.display = 'inline-flex';
        if (this.downloadGroup) this.downloadGroup.classList.add('has-mirrors');
        if (this.downloadMainBtn) {
            this.downloadMainBtn.style.borderTopRightRadius = '0';
            this.downloadMainBtn.style.borderBottomRightRadius = '0';
        }

        // Primary Host option
        const primaryItem = document.createElement('button');
        primaryItem.type = 'button';
        primaryItem.className = `mirror-dropdown-item ${!this.selectedMirrorHost ? 'active' : ''}`;
        primaryItem.setAttribute('data-host', '');
        primaryItem.innerHTML = `
            <span><i class="fa-solid fa-server" style="margin-right: 6px; color: var(--accent);"></i> ${primaryHost} <strong style="font-size: 10px; opacity: 0.7;">(Default)</strong></span>
            <span class="mirror-dropdown-badge">${primaryParts.length} ${primaryParts.length === 1 ? 'part' : 'parts'}</span>
        `;
        primaryItem.addEventListener('click', () => this.selectMirror(null));
        this.mirrorDropdown.appendChild(primaryItem);

        // Secondary Mirrors options
        mirrorKeys.forEach(mKey => {
            const mData = mirrors[mKey];
            const mParts = Array.isArray(mData.parts) ? mData.parts : (mData.url ? [mData.url] : []);
            const item = document.createElement('button');
            item.type = 'button';
            item.className = `mirror-dropdown-item ${this.selectedMirrorHost === mKey ? 'active' : ''}`;
            item.setAttribute('data-host', mKey);
            item.innerHTML = `
                <span><i class="fa-solid fa-cloud-arrow-down" style="margin-right: 6px; color: var(--accent);"></i> ${mKey}</span>
                <span class="mirror-dropdown-badge">${mParts.length} ${mParts.length === 1 ? 'part' : 'parts'}</span>
            `;
            item.addEventListener('click', () => this.selectMirror(mKey));
            this.mirrorDropdown.appendChild(item);
        });
    }

    setupHostSelector() {
        if (!this.currentGame) return;
        const mirrors = this.currentGame.mirrors || {};
        const mirrorKeys = Object.keys(mirrors).filter(k => {
            const m = mirrors[k];
            return m && ((Array.isArray(m.parts) && m.parts.length > 0) || m.url || m.fix_url);
        });

        if (mirrorKeys.length > 0 && this.setupHostSelectorRow && this.setupHostPills) {
            this.setupHostSelectorRow.style.display = 'flex';
            this.setupHostPills.innerHTML = '';

            const primaryHost = this.currentGame.host || 'Primary';
            const primaryPill = document.createElement('button');
            primaryPill.type = 'button';
            primaryPill.className = `host-pill-btn ${!this.selectedMirrorHost ? 'active' : ''}`;
            primaryPill.innerHTML = `<i class="fa-solid fa-check" style="${!this.selectedMirrorHost ? '' : 'display:none;'}"></i> ${primaryHost}`;
            primaryPill.addEventListener('click', () => {
                this.selectMirror(null);
                this.updateSetupHostDisplay();
                this.updateSetupPillsActive();
            });
            this.setupHostPills.appendChild(primaryPill);

            mirrorKeys.forEach(mKey => {
                const pill = document.createElement('button');
                pill.type = 'button';
                pill.className = `host-pill-btn ${this.selectedMirrorHost === mKey ? 'active' : ''}`;
                pill.innerHTML = `<i class="fa-solid fa-check" style="${this.selectedMirrorHost === mKey ? '' : 'display:none;'}"></i> ${mKey}`;
                pill.addEventListener('click', () => {
                    this.selectMirror(mKey);
                    this.updateSetupHostDisplay();
                    this.updateSetupPillsActive();
                });
                this.setupHostPills.appendChild(pill);
            });
        } else if (this.setupHostSelectorRow) {
            this.setupHostSelectorRow.style.display = 'none';
        }
    }

    updateSetupHostDisplay() {
        if (!this.currentGame || !this.setupGameHost) return;
        const activeHost = this.getActiveHost();
        const activeParts = this.getActiveParts();
        const type = this.pendingDownloadType || 'main';
        if (activeParts.length > 1 && type === 'main') {
            this.setupGameHost.textContent = `${activeHost} (${activeParts.length} Parts)`;
        } else {
            this.setupGameHost.textContent = activeHost;
        }
    }

    updateSetupPillsActive() {
        if (!this.setupHostPills) return;
        const pills = this.setupHostPills.querySelectorAll('.host-pill-btn');
        const primaryHost = this.currentGame?.host || 'Primary';
        pills.forEach(pill => {
            const isPrimary = pill.textContent.includes(primaryHost);
            const isActive = (!this.selectedMirrorHost && isPrimary) || (this.selectedMirrorHost && pill.textContent.includes(this.selectedMirrorHost));
            if (isActive) {
                pill.classList.add('active');
                const icon = pill.querySelector('i');
                if (icon) icon.style.display = '';
            } else {
                pill.classList.remove('active');
                const icon = pill.querySelector('i');
                if (icon) icon.style.display = 'none';
            }
        });
    }

    async addToSteam() {
        if (!this.currentGame) return;
        if (this.currentGame.steam_url) {
            window.uiController.showToast(`Launching ${this.currentGame.title} on Steam...`, 'info');
            try {
                if (window.api && window.api.openExternal) {
                    const ok = await window.api.openExternal(this.currentGame.steam_url);
                    if (ok) return;
                }
            } catch (e) {
                console.warn('[DetailsController] openExternal failed:', e);
            }

            try {
                if (window.apiClient && window.apiClient.openExternalUrl) {
                    await window.apiClient.openExternalUrl(this.currentGame.steam_url);
                }
            } catch (e) {
                console.error('[DetailsController] API launch fallback error:', e);
                window.uiController.showToast(`Could not launch ${this.currentGame.title} on Steam`, 'danger');
            }
        } else {
            window.steamController.openAddShortcutDialog(this.currentGame);
        }
    }

    async launchGame() {
        if (!this.currentGame) return;
        window.uiController.showToast(`Launching ${this.currentGame.title}...`, 'info');
    }

    removeGame() {
        if (!this.currentGame) return;
        const removeModal = document.getElementById('removeGameModal');
        const titleSpan = document.getElementById('removeModalGameTitle');
        if (titleSpan) titleSpan.textContent = this.currentGame.title;

        // Toggle "Remove Steam Shortcut Link Only" option
        const removeSteamBtn = document.getElementById('confirmRemoveSteamOnlyBtn');
        if (removeSteamBtn) {
            removeSteamBtn.style.display = this.currentGame.steam_url ? 'block' : 'none';
        }

        if (removeModal) removeModal.classList.add('active');
    }

    closeRemoveModal() {
        const removeModal = document.getElementById('removeGameModal');
        if (removeModal) removeModal.classList.remove('active');
    }

    async executeSteamRemoval() {
        if (!this.currentGame) return;
        const title = this.currentGame.title;
        this.closeRemoveModal();

        try {
            const res = await window.apiClient.removeSteamLink({
                id: this.currentGame.id,
                title: title
            });

            if (res.success) {
                window.uiController.showToast(`Steam shortcut link removed for "${title}".`, 'success');
                this.currentGame.steam_url = null;
                if (this.addSteamBtn) {
                    this.addSteamBtn.innerHTML = '<i class="fa-brands fa-steam"></i> Add to Steam';
                    this.addSteamBtn.title = 'Create Steam non-game shortcut';
                }
                await window.libraryController.loadGames();
            }
        } catch (err) {
            window.uiController.showToast(`Failed to remove Steam link: ${err.message}`, 'danger');
        }
    }

    async executeRemoval(deleteFromDisk) {
        if (!this.currentGame) return;
        const title = this.currentGame.title;
        this.closeRemoveModal();

        try {
            const res = await window.apiClient.removeGame({
                id: this.currentGame.id,
                title: title,
                delete_folder: deleteFromDisk
            });

            if (res.success) {
                const msg = deleteFromDisk 
                    ? `"${title}" and its files were deleted from disk.` 
                    : `"${title}" was uninstalled (files kept on disk).`;
                window.uiController.showToast(msg, 'success');
                await window.libraryController.loadGames();
                this.close();
            }
        } catch (err) {
            window.uiController.showToast(`Failed to remove game: ${err.message}`, 'danger');
        }
    }

    async openInstallFolder() {
        if (!this.currentGame) return;
        const title = this.currentGame.title || '';
        const defaultBase = window.settingsController?.settings?.extract_path || '';
        const baseLoc = this.currentGame.location || defaultBase;
        
        const candidates = [
            baseLoc ? `${baseLoc}\\${title}` : null,
            baseLoc || null,
            defaultBase ? `${defaultBase}\\${title}` : null
        ].filter(Boolean);

        for (const candidate of candidates) {
            try {
                const opened = await window.api?.openPath(candidate);
                if (opened) {
                    window.uiController.showToast(`Opened: ${candidate}`, 'info');
                    return;
                }
            } catch (err) {}
        }
    }
}

window.detailsController = new DetailsController();
