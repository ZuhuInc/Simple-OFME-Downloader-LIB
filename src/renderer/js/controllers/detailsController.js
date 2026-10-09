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
        this.downloadMainBtn = document.getElementById('detailsDownloadMainBtn');
        this.downloadFixBtn = document.getElementById('detailsDownloadFixBtn');
        this.openMirrorBtn = document.getElementById('detailsOpenMirrorBtn');
        this.addSteamBtn = document.getElementById('detailsAddSteamBtn');
        this.launchBtn = document.getElementById('detailsLaunchBtn');
        this.removeGameBtn = document.getElementById('detailsRemoveGameBtn');

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
                    const targetUrl = (Array.isArray(this.currentGame.parts) && this.currentGame.parts[0]) || this.currentGame.main_game_url || this.currentGame.download_url || this.currentGame.origin_url;
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
        if (this.hostEl) this.hostEl.textContent = game.host || 'Direct';
        if (this.sizeEl) this.sizeEl.textContent = game.approx_size || game.size || 'N/A';
        if (this.versionEl) this.versionEl.textContent = `v${game.version || '1.0'}`;

        if (this.statusEl) {
            const statusClass = game.status === 1 ? 'status-uptodate' : (game.status === 2 ? 'status-update' : 'status-missing');
            const statusLabel = game.status === 1 ? 'Installed (Up to date)' : (game.status === 2 ? 'Update Available' : 'Not Installed');
            this.statusEl.className = `status-pill ${statusClass}`;
            this.statusEl.textContent = statusLabel;
        }

        if (this.locationEl) {
            const defaultBase = window.settingsController?.settings?.extract_path || window.settingsController?.settings?.default_download_path || 'D:\\GAMES2';
            if (game.location) {
                this.locationEl.textContent = game.location;
                this.locationEl.style.color = '#fff';
            } else {
                this.locationEl.textContent = `${defaultBase} (Default)`;
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

        // Action button labels based on status
        if (this.downloadMainBtn) {
            if (game.status === 2) {
                this.downloadMainBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Update Game';
            } else if (game.status === 1) {
                this.downloadMainBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> Re-download';
            } else {
                this.downloadMainBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> Download Game';
            }
        }

        // Toggle Fix button visibility if fix URL is provided
        const hasFix = Boolean(game.fix_url);
        if (this.downloadFixBtn) {
            this.downloadFixBtn.style.display = hasFix ? 'inline-flex' : 'none';
        }
        if (this.downloadMainBtn) {
            this.downloadMainBtn.style.gridColumn = hasFix ? 'auto' : '1 / -1';
        }

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

        this.modal.classList.add('active');
    }

    close() {
        if (this.modal) this.modal.classList.remove('active');
        this.currentGame = null;
    }

    getParentOrSelf(pathStr) {
        if (!pathStr) return 'D:\\GAMES2';
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
                            'D:\\GAMES2';

        const autoExtract = window.settingsController?.settings?.auto_extract !== false;
        const autoDelete = window.settingsController?.settings?.auto_delete_archive !== false;

        // Populate base info
        if (this.setupThumb) this.setupThumb.src = this.currentGame.thumbnail || 'assets/OFME-DWND-ICO.ico';
        if (this.setupGameTitle) this.setupGameTitle.textContent = this.currentGame.title || 'Unknown Game';
        if (this.setupGameVersion) this.setupGameVersion.textContent = `v${this.currentGame.version || '1.0'}`;
        if (this.setupGameSize) this.setupGameSize.textContent = this.currentGame.approx_size || this.currentGame.size || 'Unknown';
        if (this.setupGameHost) this.setupGameHost.textContent = this.currentGame.host || 'Direct';
        if (this.setupAutoExtractCheck) this.setupAutoExtractCheck.checked = autoExtract;
        if (this.setupDeleteArchiveCheck) this.setupDeleteArchiveCheck.checked = autoDelete;

        // Multi-part indicator
        const isMultiPart = Array.isArray(this.currentGame.parts) && this.currentGame.parts.length > 1;
        if (isMultiPart && type === 'main') {
            if (this.setupGameHost) this.setupGameHost.textContent = `${this.currentGame.host || 'Direct'} (${this.currentGame.parts.length} Parts)`;
        }

        // Contextual styling based on action type
        if (type === 'fix') {
            if (this.setupTitle) this.setupTitle.textContent = 'Apply Multiplayer Fix';
            if (this.setupSubtitle) this.setupSubtitle.textContent = 'Confirm target game directory for online fix files.';
            if (this.setupIcon) this.setupIcon.innerHTML = '<i class="fa-solid fa-wrench" style="color: #60a5fa;"></i>';
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
            if (this.setupIcon) this.setupIcon.innerHTML = '<i class="fa-solid fa-arrows-rotate" style="color: var(--warning);"></i>';
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
            if (this.setupIcon) this.setupIcon.innerHTML = '<i class="fa-solid fa-cloud-arrow-down" style="color: var(--success);"></i>';
            if (this.setupActionBadge) {
                this.setupActionBadge.className = 'status-pill status-uptodate';
                this.setupActionBadge.style.cssText = 'font-size: 9px; padding: 2px 8px;';
                this.setupActionBadge.innerHTML = '<i class="fa-solid fa-check"></i> Re-download';
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
            if (this.setupIcon) this.setupIcon.innerHTML = '<i class="fa-solid fa-cloud-arrow-down" style="color: var(--accent);"></i>';
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
        const targetPath = this.setupInstallPathInput ? this.setupInstallPathInput.value.trim() : 'D:\\GAMES2';
        const autoExtract = this.setupAutoExtractCheck ? Boolean(this.setupAutoExtractCheck.checked) : true;
        const autoDelete = this.setupDeleteArchiveCheck ? Boolean(this.setupDeleteArchiveCheck.checked) : true;

        this.closeDownloadSetup();

        // Multi-part game download execution
        if (type === 'main' && Array.isArray(this.currentGame.parts) && this.currentGame.parts.length > 1) {
            try {
                window.uiController.showToast(`Queueing ${this.currentGame.parts.length} parts for ${this.currentGame.title}...`, 'info');
                for (let i = 0; i < this.currentGame.parts.length; i++) {
                    const partUrl = this.currentGame.parts[i];
                    const filename = `${this.currentGame.title}_Part${i + 1}.rar`;
                    await window.apiClient.addDownload(partUrl, filename, {
                        game_id: this.currentGame.id,
                        title: this.currentGame.title,
                        version: this.currentGame.version,
                        type: `main_part_${i + 1}`,
                        extract_dir: targetPath,
                        auto_extract: autoExtract,
                        auto_delete_archive: autoDelete
                    });
                }
                window.uiController.showToast(`Added ${this.currentGame.parts.length} parts to Download Queue`, 'success');
                window.uiController.switchTab('downloadsTab');
                this.close();
                return;
            } catch (err) {
                window.uiController.showToast(`Multi-part download failed: ${err.message}`, 'danger');
                return;
            }
        }

        const targetUrl = type === 'fix' ? this.currentGame.fix_url : (this.currentGame.main_game_url || this.currentGame.download_url);
        if (!targetUrl) {
            window.uiController.showToast('No direct download link configured for this title.', 'warning');
            return;
        }

        try {
            window.uiController.showToast(`Queueing download for ${this.currentGame.title}...`, 'info');
            const filename = `${this.currentGame.title}_${type === 'fix' ? 'Fix' : 'Game'}.rar`;
            const res = await window.apiClient.addDownload(targetUrl, filename, {
                game_id: this.currentGame.id,
                title: this.currentGame.title,
                version: this.currentGame.version,
                location: this.currentGame.location || '',
                extract_dir: targetPath,
                auto_extract: autoExtract,
                auto_delete_archive: autoDelete,
                type: type
            });

            if (res.success) {
                window.uiController.showToast(`Added to Download Queue (Job #${res.job_id})`, 'success');
                window.uiController.switchTab('downloadsTab');
                this.close();
            }
        } catch (err) {
            window.uiController.showToast(`Download failed: ${err.message}`, 'danger');
        }
    }

    async addToSteam() {
        if (!this.currentGame) return;
        if (this.currentGame.steam_url) {
            window.uiController.showToast(`Launching ${this.currentGame.title} on Steam...`, 'info');
            window.apiClient.openUrl(this.currentGame.steam_url);
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
        const baseLoc = this.currentGame.location || 'D:\\GAMES2';
        
        // Prioritize exact game subfolder (e.g. D:\GAMES2\PEAK)
        const candidates = [
            `${baseLoc}\\${title}`,
            `D:\\GAMES2\\${title}`,
            `C:\\Users\\ZUHU\\Documents\\ZuhuProjects\\ZuhuOFME\\extracted\\${title}`,
            baseLoc !== 'D:\\GAMES2' ? baseLoc : null,
            'D:\\GAMES2'
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
