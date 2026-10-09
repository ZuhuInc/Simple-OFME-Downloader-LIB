/**
 * Settings Controller
 * Handles configuration preferences (WinRAR, download directories, speed units), live config saves, and console logs.
 */

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
    }

    init() {
        this.bindEvents();
        this.loadSettings();
        this.initLogListeners();
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
}

window.settingsController = new SettingsController();
