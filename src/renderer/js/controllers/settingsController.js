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
    }

    bindEvents() {
        if (this.saveBtn) {
            this.saveBtn.addEventListener('click', () => this.saveCurrentSettings());
        }

        const clearLogsBtn = document.getElementById('clearConsoleLogsBtn');
        if (clearLogsBtn) {
            clearLogsBtn.addEventListener('click', () => {
                if (this.consoleFeed) this.consoleFeed.innerHTML = '--- Live Console Output Cleared ---';
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
            }
        } catch (err) {
            window.uiController.showToast(`Failed to save settings: ${err.message}`, 'danger');
        }
    }

    appendLog(message, level = 'info') {
        if (!this.consoleFeed) return;
        const line = document.createElement('div');
        line.className = `log-line log-${level}`;
        const time = new Date().toLocaleTimeString();
        line.textContent = `[${time}] ${message}`;
        this.consoleFeed.appendChild(line);
        this.consoleFeed.scrollTop = this.consoleFeed.scrollHeight;
    }
}

window.settingsController = new SettingsController();
