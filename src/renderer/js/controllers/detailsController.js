/**
 * Details Controller
 * Manages game details slide-over modal, metadata display, download triggers, and Steam integration actions.
 */

class DetailsController {
    constructor() {
        this.currentGame = null;
        this.modal = document.getElementById('gameDetailsModal');
        this.coverEl = document.getElementById('detailsCoverImg');
        this.titleEl = document.getElementById('detailsTitle');
        this.descEl = document.getElementById('detailsDescription');
        this.hostEl = document.getElementById('detailsHost');
        this.sizeEl = document.getElementById('detailsSize');
        this.versionEl = document.getElementById('detailsVersion');
        this.statusEl = document.getElementById('detailsStatus');
        this.originLinkEl = document.getElementById('detailsOriginLink');
        this.downloadMainBtn = document.getElementById('detailsDownloadMainBtn');
        this.downloadFixBtn = document.getElementById('detailsDownloadFixBtn');
        this.addSteamBtn = document.getElementById('detailsAddSteamBtn');
        this.launchBtn = document.getElementById('detailsLaunchBtn');
        this.removeGameBtn = document.getElementById('detailsRemoveGameBtn');
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

        if (this.downloadMainBtn) {
            this.downloadMainBtn.addEventListener('click', () => this.downloadGame('main'));
        }

        if (this.downloadFixBtn) {
            this.downloadFixBtn.addEventListener('click', () => this.downloadGame('fix'));
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
        if (this.downloadFixBtn) {
            this.downloadFixBtn.style.display = game.fix_url ? 'inline-flex' : 'none';
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

    async downloadGame(type = 'main') {
        if (!this.currentGame) return;

        // Multi-part game support
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
                        type: `main_part_${i + 1}`
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
