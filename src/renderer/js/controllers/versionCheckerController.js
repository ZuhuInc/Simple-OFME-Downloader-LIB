/**
 * Version Checker Controller
 * Audits installed games against Online-Fix.me and SteamRIP updates,
 * handles webhook alerts, and manages credential auto-fill.
 */

class VersionCheckerController {
    constructor() {
        this.isScanning = false;
        this.resultsTable = null;
        this.scanOfmeBtn = null;
        this.scanSteamripBtn = null;
        this.scanAllSourcesBtn = null;
        this.installedOnlyCheck = null;
        this.stopBtn = null;
        this.progressBar = null;
        this.scanStatusText = null;
    }

    init() {
        this.queryElements();
        this.bindEvents();
        this.loadSavedCredentials();
    }

    queryElements() {
        this.resultsTable = document.getElementById('vcResultsTableBody');
        this.scanOfmeBtn = document.getElementById('scanOfmeBtn');
        this.scanSteamripBtn = document.getElementById('scanSteamripBtn');
        this.scanAllSourcesBtn = document.getElementById('scanAllSourcesBtn');
        this.installedOnlyCheck = document.getElementById('vcInstalledOnlyCheck');
        this.stopBtn = document.getElementById('stopScanBtn');
        this.progressBar = document.getElementById('vcProgressBar');
        this.scanStatusText = document.getElementById('vcScanStatusText');
    }

    isInstalledOnly() {
        if (!this.installedOnlyCheck) {
            this.installedOnlyCheck = document.getElementById('vcInstalledOnlyCheck');
        }
        return this.installedOnlyCheck ? this.installedOnlyCheck.checked : true;
    }

    async loadSavedCredentials(retries = 3) {
        try {
            const res = await window.apiClient.getSettings();
            if (res && res.settings) {
                const s = res.settings;
                const userInput = document.getElementById('vcUsernameInput');
                const passInput = document.getElementById('vcPasswordInput');
                const webhookInput = document.getElementById('vcWebhookInput');
                const enableCheck = document.getElementById('vcEnableWebhookCheck');

                if (userInput && s.ofme_username) userInput.value = s.ofme_username;
                if (passInput && s.ofme_password) passInput.value = s.ofme_password;
                if (webhookInput && s.webhook_url) webhookInput.value = s.webhook_url;
                if (enableCheck && s.enable_webhook !== undefined) enableCheck.checked = s.enable_webhook;
            }
        } catch (e) {
            if (retries > 0) {
                setTimeout(() => this.loadSavedCredentials(retries - 1), 1000);
            } else {
                console.error('[VC Controller] Failed to load saved credentials:', e);
            }
        }
    }

    bindEvents() {
        if (this.scanOfmeBtn) {
            this.scanOfmeBtn.addEventListener('click', () => {
                this.startScan({ source: 'ofme', installed_only: this.isInstalledOnly() });
            });
        }

        if (this.scanSteamripBtn) {
            this.scanSteamripBtn.addEventListener('click', () => {
                this.startScan({ source: 'sr', installed_only: this.isInstalledOnly() });
            });
        }

        if (this.scanAllSourcesBtn) {
            this.scanAllSourcesBtn.addEventListener('click', () => {
                this.startScan({ source: 'all', installed_only: this.isInstalledOnly() });
            });
        }

        if (this.stopBtn) {
            this.stopBtn.addEventListener('click', () => this.stopScan());
        }

        const saveCredsBtn = document.getElementById('saveVcCredsBtn');
        if (saveCredsBtn) {
            saveCredsBtn.addEventListener('click', () => this.saveCredentials());
        }

        if (window.apiClient) {
            window.apiClient.on('version_check_progress', (data) => {
                this.handleScanProgress(data);
            });
        }
    }

    async startScan(options = {}) {
        if (this.isScanning) return;
        this.isScanning = true;
        this.updateButtons();

        // Clear existing table and show scanning indicator
        if (!this.resultsTable) this.queryElements();
        if (this.resultsTable) {
            this.resultsTable.innerHTML = `
                <tr class="empty-row">
                    <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">
                        <i class="fa-solid fa-spinner fa-spin" style="margin-right: 8px; color: var(--accent);"></i> Auditing library... Outdated games will appear here.
                    </td>
                </tr>
            `;
        }

        const srcName = options.source === 'ofme' ? 'Online-Fix (OFME)' : (options.source === 'sr' ? 'SteamRIP (SR)' : 'All Sources');
        const scopeName = options.installed_only ? 'Installed Only' : 'All Games';
        if (this.scanStatusText) this.scanStatusText.textContent = `Auditing ${srcName} [${scopeName}]...`;
        if (this.progressBar) this.progressBar.style.width = '0%';

        try {
            const res = await window.apiClient.scanVersions(options);
            if (res && res.success) {
                window.uiController.showToast(`Audit started for ${res.total} games (${srcName})`, 'info');
            }
        } catch (err) {
            this.isScanning = false;
            this.updateButtons();
            window.uiController.showToast(`Failed to start audit: ${err.message}`, 'danger');
        }
    }

    async stopScan() {
        try {
            await window.apiClient.stopVersionScan();
            this.isScanning = false;
            this.updateButtons();
            if (this.scanStatusText) this.scanStatusText.textContent = 'Scan stopped by user.';
            window.uiController.showToast('Scan stopped', 'warning');
        } catch (err) {
            window.uiController.showToast('Failed to stop scan', 'danger');
        }
    }

    handleScanProgress(data) {
        if (!data) return;

        if (data.status === 'progress') {
            const current = data.current || 0;
            const total = data.total || 1;
            const percent = ((current / total) * 100).toFixed(1);

            if (this.progressBar) this.progressBar.style.width = `${percent}%`;
            if (this.scanStatusText) {
                this.scanStatusText.textContent = `Auditing [${current}/${total}]: ${data.game || 'Game'}`;
            }

            // Only append row if game actually requires an update!
            if (data.update_available) {
                this.appendResultRow(data);
            }
        } else if (data.status === 'completed') {
            this.isScanning = false;
            this.updateButtons();
            if (this.progressBar) this.progressBar.style.width = '100%';
            
            const count = data.updates_found || 0;
            if (this.scanStatusText) {
                this.scanStatusText.textContent = count > 0 
                    ? `Audit Complete. Found ${count} update${count > 1 ? 's' : ''}.`
                    : `Audit Complete. All checked games are up to date!`;
            }

            if (!this.resultsTable) this.queryElements();
            if (this.resultsTable) {
                const emptyRow = this.resultsTable.querySelector('.empty-row');
                if (count === 0 || this.resultsTable.children.length === 0 || (emptyRow && this.resultsTable.children.length === 1)) {
                    this.resultsTable.innerHTML = `
                        <tr class="empty-row">
                            <td colspan="6" style="text-align: center; color: var(--success); padding: 35px;">
                                <i class="fa-solid fa-circle-check" style="font-size: 24px; display: block; margin-bottom: 8px;"></i>
                                All checked games are up to date! No updates needed.
                            </td>
                        </tr>
                    `;
                }
            }

            window.uiController.showToast(`Audit finished! (${count} updates found)`, count > 0 ? 'warning' : 'success');
        }
    }

    appendResultRow(data) {
        if (!this.resultsTable) {
            this.resultsTable = document.getElementById('vcResultsTableBody');
        }
        if (!this.resultsTable) return;

        // Clear empty placeholder if present
        const emptyRow = this.resultsTable.querySelector('.empty-row');
        if (emptyRow) emptyRow.remove();

        const tr = document.createElement('tr');
        const hasUpdate = data.update_available;
        const isInstalled = data.is_installed;
        
        let statusBadge = `<span class="badge badge-warning"><i class="fa-solid fa-arrows-rotate"></i> New Patch Online</span>`;
        if (isInstalled) {
            statusBadge += ` <span class="badge badge-success" style="margin-left: 6px;"><i class="fa-solid fa-folder-check"></i> Installed</span>`;
        }

        const localVerDisplay = data.local_version !== 'Not Installed' ? `v${data.local_version}` : '<span class="text-muted">---</span>';
        const dbVerDisplay = data.db_version ? `v${data.db_version}` : '<span class="text-muted">---</span>';
        const liveVerDisplay = (data.scraped_version && data.scraped_version !== '---') ? `v${data.scraped_version}` : '<span class="text-muted">---</span>';

        tr.innerHTML = `
            <td><strong>${data.game || 'Unknown'}</strong></td>
            <td>${localVerDisplay}</td>
            <td><span style="color: var(--accent); font-weight: 500;">${dbVerDisplay}</span></td>
            <td><span style="color: #60a5fa; font-weight: 600;">${liveVerDisplay}</span></td>
            <td>${statusBadge}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="window.versionCheckerController.openUpdateUrl('${data.origin_url || ''}', '${data.game_id}')" title="Open online release in browser">
                    <i class="fa-solid fa-arrow-up-right-from-square"></i> Update
                </button>
            </td>
        `;

        this.resultsTable.prepend(tr);
    }

    async openUpdateUrl(url, gameId) {
        if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
            try {
                if (window.api && window.api.openExternal) {
                    const ok = await window.api.openExternal(url);
                    if (ok) return;
                }
            } catch (e) {}

            try {
                if (window.apiClient && window.apiClient.openExternalUrl) {
                    const res = await window.apiClient.openExternalUrl(url);
                    if (res && res.success) return;
                }
            } catch (e) {}

            window.open(url, '_blank');
        } else if (gameId && window.detailsController) {
            window.detailsController.openGameById(gameId);
        }
    }

    async saveCredentials() {
        const username = document.getElementById('vcUsernameInput')?.value || '';
        const password = document.getElementById('vcPasswordInput')?.value || '';
        const webhookUrl = document.getElementById('vcWebhookInput')?.value || '';
        const enableWebhook = document.getElementById('vcEnableWebhookCheck')?.checked || false;

        try {
            await window.apiClient.saveVCCredentials({
                username,
                password,
                webhook_url: webhookUrl,
                enable_webhook: enableWebhook
            });
            window.uiController.showToast('Version checker credentials saved', 'success');
        } catch (err) {
            window.uiController.showToast('Failed to save credentials', 'danger');
        }
    }

    updateButtons() {
        if (!this.scanOfmeBtn) this.queryElements();
        if (this.scanOfmeBtn) this.scanOfmeBtn.disabled = this.isScanning;
        if (this.scanSteamripBtn) this.scanSteamripBtn.disabled = this.isScanning;
        if (this.scanAllSourcesBtn) this.scanAllSourcesBtn.disabled = this.isScanning;
        if (this.stopBtn) this.stopBtn.disabled = !this.isScanning;
    }
}

window.versionCheckerController = new VersionCheckerController();
