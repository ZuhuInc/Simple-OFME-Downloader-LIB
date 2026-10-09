/**
 * Settings Controller
 * Handles configuration preferences (WinRAR, download directories, speed units), live config saves, and console logs.
 */

function formatVersion(v) {
    if (!v) return 'v2.0.0';
    return 'v' + String(v).trim().replace(/^[vV]+/i, '');
}

class SettingsController {
    constructor() {
        this.settings = {};
        this.winrarInput = document.getElementById('set_winrar_path');
        this.downloadPathInput = document.getElementById('set_download_path');
        this.extractPathInput = document.getElementById('set_extract_path');
        this.rarPasswordInput = document.getElementById('set_rar_password');
        this.speedUnitSelect = document.getElementById('set_speed_unit');
        this.autoExtractCheck = document.getElementById('set_auto_extract');
        this.autoDeleteArchiveCheck = document.getElementById('set_auto_delete_archive');
        this.concurrencyInput = document.getElementById('set_concurrency');
        this.useLocalDbCheck = document.getElementById('set_use_local_db');
        this.localDbPathInput = document.getElementById('set_local_db_path');
        this.saveBtn = document.getElementById('saveSettingsBtn');
        this.consoleFeed = document.getElementById('consoleLogFeed');

        // Update UI elements
        this.checkUpdatesBtn = document.getElementById('checkForUpdatesBtn');
        this.startDownloadUpdateBtn = document.getElementById('startDownloadUpdateBtn');
        this.restartInstallBtn = document.getElementById('restartAndInstallBtn');
        this.updateStatusIcon = document.getElementById('updateStatusIcon');
        this.updateStatusTitle = document.getElementById('updateStatusTitle');
        this.updateStatusDesc = document.getElementById('updateStatusDesc');
        this.updateProgressContainer = document.getElementById('updateProgressContainer');
        this.updateProgressBar = document.getElementById('updateProgressBar');
        this.updateProgressPercent = document.getElementById('updateProgressPercent');
        this.updateProgressStatus = document.getElementById('updateProgressStatus');
        this.updateVersionBadge = document.getElementById('updateAppVersionBadge');
    }

    init() {
        this.bindEvents();
        this.loadSettings();
        this.initLogListeners();
        this.initUpdaterListeners();
        this.loadAppVersion();
    }

    bindEvents() {
        if (this.saveBtn) {
            this.saveBtn.addEventListener('click', () => this.saveCurrentSettings());
        }

        const copyLogsBtn = document.getElementById('copyConsoleLogsBtn');
        if (copyLogsBtn) {
            copyLogsBtn.addEventListener('click', async () => {
                await this.copyLogsToClipboard(copyLogsBtn);
            });
        }

        const clearLogsBtn = document.getElementById('clearConsoleLogsBtn');
        if (clearLogsBtn) {
            clearLogsBtn.addEventListener('click', () => {
                if (this.consoleFeed) {
                    this.consoleFeed.innerHTML = '';
                    this.appendLog('Console logs cleared', 'info');
                }
            });
        }

        // Auto-updater buttons
        if (this.checkUpdatesBtn) {
            this.checkUpdatesBtn.addEventListener('click', async () => {
                await this.triggerUpdateCheck();
            });
        }

        if (this.startDownloadUpdateBtn) {
            this.startDownloadUpdateBtn.addEventListener('click', async () => {
                await this.startUpdateDownload();
            });
        }

        if (this.restartInstallBtn) {
            this.restartInstallBtn.addEventListener('click', () => {
                if (window.api?.restartAndInstallUpdate) {
                    window.api.restartAndInstallUpdate();
                }
            });
        }

        // Browse directory buttons
        const browseDlBtn = document.getElementById('browseDownloadPathBtn');
        if (browseDlBtn) {
            browseDlBtn.addEventListener('click', async () => {
                const dir = await window.api?.selectDirectory();
                if (dir && this.downloadPathInput) this.downloadPathInput.value = dir;
            });
        }

        const browseExtractBtn = document.getElementById('browseExtractPathBtn');
        if (browseExtractBtn) {
            browseExtractBtn.addEventListener('click', async () => {
                const dir = await window.api?.selectDirectory();
                if (dir && this.extractPathInput) this.extractPathInput.value = dir;
            });
        }

        const browseWinrarBtn = document.getElementById('browseWinrarPathBtn');
        if (browseWinrarBtn) {
            browseWinrarBtn.addEventListener('click', async () => {
                const file = await window.api?.selectFile({
                    filters: [{ name: 'Executables', extensions: ['exe'] }]
                });
                if (file && this.winrarInput) this.winrarInput.value = file;
            });
        }

        // Local DB Browse & Open buttons
        const browseLocalDbBtn = document.getElementById('browseLocalDbBtn');
        if (browseLocalDbBtn) {
            browseLocalDbBtn.addEventListener('click', async () => {
                const file = await window.api?.selectFile({
                    filters: [{ name: 'Data.json Databases', extensions: ['json'] }]
                });
                if (file && this.localDbPathInput) {
                    this.localDbPathInput.value = file;
                    if (this.useLocalDbCheck) this.useLocalDbCheck.checked = true;
                }
            });
        }

        const openLocalDbFolderBtn = document.getElementById('openLocalDbFolderBtn');
        if (openLocalDbFolderBtn) {
            openLocalDbFolderBtn.addEventListener('click', async () => {
                const targetPath = this.localDbPathInput?.value || '';
                if (targetPath && window.api?.openPath) {
                    await window.api.openPath(targetPath);
                } else {
                    window.uiController.showToast('No database path configured', 'warning');
                }
            });
        }

        const reloadDbBtn = document.getElementById('reloadDbFromDiskBtn');
        if (reloadDbBtn) {
            reloadDbBtn.addEventListener('click', async () => {
                try {
                    const isLocal = Boolean(this.useLocalDbCheck?.checked);
                    window.uiController.showToast(isLocal ? 'Reloading database from disk...' : 'Fetching database from GitHub...', 'info');
                    const res = await window.apiClient.refreshGames();
                    if (window.libraryController) {
                        await window.libraryController.loadGames();
                    }
                    window.uiController.showToast(`Loaded ${res.total || 0} games from ${isLocal ? 'local Data.json' : 'GitHub'}`, 'success');
                    this.appendLog(`Loaded ${res.total || 0} games from ${isLocal ? 'local disk' : 'GitHub repository'}`, 'success');
                } catch (err) {
                    window.uiController.showToast(`Failed to reload database: ${err.message}`, 'danger');
                }
            });
        }
    }

    async initLogListeners() {
        this.appendLog('Fanta OFME Downloader GUI initialized', 'info');

        // Fetch buffered startup logs if running in Electron
        if (window.api && typeof window.api.getInitialLogs === 'function') {
            try {
                const initialLogs = await window.api.getInitialLogs();
                if (Array.isArray(initialLogs)) {
                    initialLogs.forEach(entry => {
                        this.appendLog(entry.text, entry.level, entry.time);
                    });
                }
            } catch (err) {
                console.error('[SettingsController] Failed to fetch initial logs:', err);
            }
        }

        // Listen for live backend logs from Electron main process
        if (window.api && typeof window.api.onBackendLog === 'function') {
            window.api.onBackendLog(log => {
                this.appendLog(log.text, log.level, log.time);
            });
        }

        // Listen for Socket.IO bridge connection state changes
        if (window.apiClient) {
            window.apiClient.on('bridge_status', (status) => {
                if (status && status.connected) {
                    this.appendLog('Connected to Python Bridge via WebSocket', 'success');
                } else {
                    this.appendLog('Disconnected from Python Bridge WebSocket', 'warning');
                }
            });
        }
    }

    async copyLogsToClipboard(btn) {
        if (!this.consoleFeed) return;

        const logLines = Array.from(this.consoleFeed.querySelectorAll('.log-line'))
            .map(el => el.textContent.trim())
            .filter(Boolean);

        const fullText = logLines.length > 0 ? logLines.join('\n') : (this.consoleFeed.textContent.trim() || 'No logs recorded.');

        try {
            await navigator.clipboard.writeText(fullText);
            if (window.uiController) {
                window.uiController.showToast('Console logs copied to clipboard!', 'success');
            }
            if (btn) {
                const originalHtml = btn.innerHTML;
                btn.innerHTML = '<i class="fa-solid fa-check" style="color: var(--success);"></i>';
                setTimeout(() => {
                    btn.innerHTML = originalHtml;
                }, 1500);
            }
        } catch (err) {
            console.error('[SettingsController] Failed to copy console logs:', err);
            if (window.uiController) {
                window.uiController.showToast('Failed to copy logs to clipboard', 'danger');
            }
        }
    }

    async loadSettings() {
        try {
            const data = await window.apiClient.getSettings();
            this.settings = data.settings || {};
            this.populateForm();
        } catch (err) {
            console.error('[SettingsController] Failed to load settings:', err);
        }
    }

    populateForm() {
        if (this.winrarInput) this.winrarInput.value = this.settings.winrar_path || '';
        if (this.downloadPathInput) this.downloadPathInput.value = this.settings.download_path || '';
        if (this.extractPathInput) this.extractPathInput.value = this.settings.extract_path || '';
        if (this.rarPasswordInput) this.rarPasswordInput.value = this.settings.rar_password || 'online-fix.me';
        if (this.concurrencyInput) this.concurrencyInput.value = this.settings.concurrent_downloads || 2;
        if (this.speedUnitSelect) this.speedUnitSelect.value = this.settings.speed_unit || 'MB/s';
        if (this.autoExtractCheck) this.autoExtractCheck.checked = this.settings.auto_extract !== false;
        if (this.autoDeleteArchiveCheck) this.autoDeleteArchiveCheck.checked = this.settings.auto_delete_archive !== false;
        if (this.useLocalDbCheck) this.useLocalDbCheck.checked = Boolean(this.settings.use_local_db);
        if (this.localDbPathInput) this.localDbPathInput.value = this.settings.local_db_path || '';
    }

    async saveCurrentSettings() {
        const payload = {
            winrar_path: this.winrarInput?.value || '',
            download_path: this.downloadPathInput?.value || '',
            extract_path: this.extractPathInput?.value || '',
            rar_password: this.rarPasswordInput?.value || 'online-fix.me',
            concurrent_downloads: parseInt(this.concurrencyInput?.value || 2, 10),
            speed_unit: this.speedUnitSelect?.value || 'MB/s',
            auto_extract: Boolean(this.autoExtractCheck?.checked),
            auto_delete_archive: Boolean(this.autoDeleteArchiveCheck?.checked),
            use_local_db: Boolean(this.useLocalDbCheck?.checked),
            local_db_path: this.localDbPathInput?.value.trim() || ''
        };

        if (window.downloadController) {
            window.downloadController.speedUnit = payload.speed_unit;
        }

        try {
            const res = await window.apiClient.saveSettings(payload);
            if (res.success) {
                this.settings = res.settings;
                window.uiController.showToast('Settings saved successfully', 'success');
                this.appendLog('Settings saved successfully', 'success');

                // Reload Game Library in the UI so that switching between local and remote updates the view immediately
                if (window.libraryController) {
                    await window.libraryController.loadGames();
                }

                // Update addGameController active path and environment
                if (window.addGameController) {
                    await window.addGameController.checkEnvironment();
                }
            }
        } catch (err) {
            window.uiController.showToast(`Failed to save settings: ${err.message}`, 'danger');
            this.appendLog(`Failed to save settings: ${err.message}`, 'danger');
        }
    }

    appendLog(message, level = 'info', timeStr = null) {
        if (!this.consoleFeed || !message) return;

        // Cap log entries to prevent DOM bloating
        if (this.consoleFeed.children.length > 400) {
            while (this.consoleFeed.children.length > 300) {
                this.consoleFeed.removeChild(this.consoleFeed.firstChild);
            }
        }

        const line = document.createElement('div');
        line.className = `log-line log-${level}`;
        const time = timeStr || new Date().toLocaleTimeString();
        line.textContent = `[${time}] ${message}`;
        this.consoleFeed.appendChild(line);
        this.consoleFeed.scrollTop = this.consoleFeed.scrollHeight;
    }

    async loadAppVersion() {
        try {
            const version = await window.api?.getAppVersion();
            if (version) {
                if (this.updateVersionBadge) {
                    this.updateVersionBadge.textContent = `v${version}`;
                }
                const appVersionTags = document.querySelectorAll('.app-version-tag');
                appVersionTags.forEach(el => el.textContent = `v${version}`);
            }

            const isPort = await window.api?.isPortable?.();
            const isSrc = await window.api?.isSourceMode?.();
            if (isSrc) {
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = 'Development Mode';
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = 'Running directly from source code.';
            } else if (isPort) {
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = 'Standalone Portable Build';
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = 'Self-contained executable. Full background auto-updating is active in the NSIS Installer version.';
            }
        } catch (e) {
            console.warn('[Settings] Failed to fetch app version:', e);
        }
    }

    initUpdaterListeners() {
        if (!window.api?.onUpdaterEvent) return;

        window.api.onUpdaterEvent((evt) => {
            this.handleUpdaterEvent(evt);
        });
    }

    async triggerUpdateCheck() {
        if (!this.checkUpdatesBtn) return;
        this.checkUpdatesBtn.disabled = true;
        this.checkUpdatesBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking...';

        try {
            const res = await window.api?.checkForUpdates();
            if (res?.status === 'dev-mode') {
                window.uiController.showToast('Auto-updater is inactive in source/development mode.', 'info');
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = 'Development Mode';
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = 'Running from source tree.';
            } else if (res?.status === 'portable-update-available') {
                const cleanV = formatVersion(res.version);
                if (this.updateStatusIcon) {
                    this.updateStatusIcon.innerHTML = '<i class="fa-solid fa-cloud-arrow-down fa-bounce" style="color: var(--accent);"></i>';
                }
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = `New Release Available: ${cleanV}`;
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = `A newer standalone build is available on GitHub Releases.`;
                window.uiController.showToast(
                    `New release ${cleanV} available!`,
                    'info',
                    10000,
                    {
                        text: 'View Release',
                        icon: 'fa-arrow-up-right-from-square',
                        callback: () => {
                            if (window.api?.openExternal && res.releaseUrl) {
                                window.api.openExternal(res.releaseUrl);
                            }
                        }
                    }
                );
            }
 else if (res?.status === 'portable-mode') {
                window.uiController.showToast('Checked GitHub for updates (app is up to date).', 'info');
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = 'Up to Date';
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = 'Your standalone portable build is on the latest release.';
            } else if (res?.status === 'no-release') {
                window.uiController.showToast('Application is up to date (no newer GitHub releases found).', 'info');
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = 'Up to Date';
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = 'No newer releases published on GitHub repository yet.';
            } else if (res?.status === 'up-to-date') {
                window.uiController.showToast('Application is up to date.', 'info');
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = 'Up to Date';
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = res.message || 'You are running the latest release.';
            } else if (res?.status === 'error') {
                window.uiController.showToast(`Update check notice: ${res.error}`, 'warning');
            } else if (res?.status === 'success') {
                window.uiController.showToast('Checked GitHub for updates.', 'info');
            }
        } catch (err) {
            window.uiController.showToast(`Update notice: ${err.message}`, 'warning');
        } finally {
            setTimeout(() => {
                if (this.checkUpdatesBtn) {
                    this.checkUpdatesBtn.disabled = false;
                    this.checkUpdatesBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Check for Updates';
                }
            }, 2000);
        }
    }

    async startUpdateDownload() {
        if (this.startDownloadUpdateBtn) {
            this.startDownloadUpdateBtn.disabled = true;
            this.startDownloadUpdateBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Starting Download...';
        }
        if (this.updateProgressContainer) {
            this.updateProgressContainer.style.display = 'flex';
        }
        if (this.updateStatusDesc) {
            this.updateStatusDesc.textContent = 'Downloading update package in background...';
        }
        try {
            window.uiController.showToast('Starting update download...', 'info');
            const res = await window.api?.startDownloadUpdate?.();
            if (res?.status === 'error') {
                window.uiController.showToast(`Update download notice: ${res.error || res.message}`, 'warning');
                if (this.startDownloadUpdateBtn) {
                    this.startDownloadUpdateBtn.disabled = false;
                    this.startDownloadUpdateBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> Download Update';
                }
            }
        } catch (err) {
            window.uiController.showToast(`Download error: ${err.message}`, 'danger');
            if (this.startDownloadUpdateBtn) {
                this.startDownloadUpdateBtn.disabled = false;
                this.startDownloadUpdateBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> Download Update';
            }
        }
    }

    handleUpdaterEvent(evt) {
        if (!evt) return;

        switch (evt.type) {
            case 'checking':
                if (this.updateStatusIcon) {
                    this.updateStatusIcon.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                }
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = 'Checking for updates...';
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = 'Contacting GitHub releases repository...';
                break;

            case 'portable-available':
                const cleanPortV = formatVersion(evt.version);
                if (this.updateStatusIcon) {
                    this.updateStatusIcon.innerHTML = '<i class="fa-solid fa-cloud-arrow-down fa-bounce" style="color: var(--accent);"></i>';
                }
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = `New Release Available: ${cleanPortV}`;
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = 'A newer version has been released on GitHub.';
                window.uiController.showToast(
                    `Fanta OFME ${cleanPortV} is now available on GitHub!`,
                    'info',
                    15000,
                    {
                        text: 'View Release',
                        icon: 'fa-arrow-up-right-from-square',
                        callback: () => {
                            if (window.api?.openExternal && evt.releaseUrl) {
                                window.api.openExternal(evt.releaseUrl);
                            }
                        }
                    }
                );
                break;

            case 'available':
                const cleanAvailV = formatVersion(evt.version);
                if (this.updateStatusIcon) {
                    this.updateStatusIcon.innerHTML = '<i class="fa-solid fa-cloud-arrow-down fa-bounce" style="color: var(--accent);"></i>';
                }
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = `New Update Available: ${cleanAvailV}`;
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = `Version ${cleanAvailV} is ready. Click "Download Update" to start downloading.`;
                if (this.startDownloadUpdateBtn) {
                    this.startDownloadUpdateBtn.disabled = false;
                    this.startDownloadUpdateBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> Download Update';
                    this.startDownloadUpdateBtn.style.display = 'inline-flex';
                }
                if (this.restartInstallBtn) this.restartInstallBtn.style.display = 'none';
                if (this.updateProgressContainer) this.updateProgressContainer.style.display = 'none';

                // Prominent notification with direct action button to download
                window.uiController.showToast(
                    `Update ${cleanAvailV} is available!`,
                    'info',
                    15000,
                    {
                        text: 'Update Now',
                        icon: 'fa-cloud-arrow-down',
                        callback: async () => {
                            await this.startUpdateDownload();
                        }
                    }
                );
                break;

            case 'not-available':
                const cleanNotAvailV = formatVersion(evt.version);
                if (this.updateStatusIcon) {
                    this.updateStatusIcon.innerHTML = '<i class="fa-solid fa-circle-check"></i>';
                }
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = 'Up to Date';
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = `You are running the latest release (${cleanNotAvailV}).`;
                if (this.updateProgressContainer) this.updateProgressContainer.style.display = 'none';
                if (this.startDownloadUpdateBtn) this.startDownloadUpdateBtn.style.display = 'none';
                if (this.restartInstallBtn) this.restartInstallBtn.style.display = 'none';
                break;

            case 'progress':
                if (this.updateProgressContainer) this.updateProgressContainer.style.display = 'flex';
                if (this.updateProgressBar) this.updateProgressBar.style.width = `${evt.percent}%`;
                if (this.updateProgressPercent) this.updateProgressPercent.textContent = `${evt.percent}% (${evt.speed})`;
                if (this.updateProgressStatus) this.updateProgressStatus.textContent = `Downloading update (${evt.percent}%)...`;
                if (this.startDownloadUpdateBtn) {
                    this.startDownloadUpdateBtn.style.display = 'inline-flex';
                    this.startDownloadUpdateBtn.disabled = true;
                    this.startDownloadUpdateBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Downloading (${evt.percent}%)...`;
                }
                break;

            case 'downloaded':
                const cleanDownV = formatVersion(evt.version);
                if (this.updateStatusIcon) {
                    this.updateStatusIcon.innerHTML = '<i class="fa-solid fa-circle-check" style="color: #2ecc71;"></i>';
                }
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = `Update ${cleanDownV} Ready!`;
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = 'Download completed. Restart application now to install.';
                if (this.updateProgressContainer) this.updateProgressContainer.style.display = 'none';
                if (this.startDownloadUpdateBtn) this.startDownloadUpdateBtn.style.display = 'none';
                if (this.restartInstallBtn) this.restartInstallBtn.style.display = 'inline-flex';

                // Prominent Toast with 1-click Restart
                window.uiController.showToast(
                    `Update ${cleanDownV} downloaded! Restart now to apply.`,
                    'success',
                    20000,
                    {
                        text: 'Restart & Apply',
                        icon: 'fa-bolt',
                        callback: () => {
                            if (window.api?.restartAndInstallUpdate) {
                                window.api.restartAndInstallUpdate();
                            }
                        }
                    }
                );
                break;

            case 'error':
                if (this.updateStatusIcon) {
                    this.updateStatusIcon.innerHTML = '<i class="fa-solid fa-triangle-exclamation" style="color: #ff6b6b;"></i>';
                }
                if (this.updateStatusTitle) this.updateStatusTitle.textContent = 'Update Check Notice';
                if (this.updateStatusDesc) this.updateStatusDesc.textContent = evt.message || 'Unable to check for updates.';
                if (this.updateProgressContainer) this.updateProgressContainer.style.display = 'none';
                if (this.startDownloadUpdateBtn) {
                    this.startDownloadUpdateBtn.disabled = false;
                    this.startDownloadUpdateBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> Download Update';
                }
                break;
        }
    }
}

window.settingsController = new SettingsController();

