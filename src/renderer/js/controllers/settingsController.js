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
        this.concurrencyInput = document.getElementById('set_concurrency');
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
    }

    async saveCurrentSettings() {
        const payload = {
            winrar_path: this.winrarInput?.value || '',
            download_path: this.downloadPathInput?.value || '',
            extract_path: this.extractPathInput?.value || '',
            rar_password: this.rarPasswordInput?.value || 'online-fix.me',
            concurrent_downloads: parseInt(this.concurrencyInput?.value || 2, 10),
            speed_unit: this.speedUnitSelect?.value || 'MB/s'
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
