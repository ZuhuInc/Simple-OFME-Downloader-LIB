/**
 * Version Checker Controller
 * Audits installed games against Online-Fix.me updates and handles webhook alerts.
 */

class VersionCheckerController {
    constructor() {
        this.isScanning = false;
        this.resultsTable = document.getElementById('vcResultsTableBody');
        this.startBtn = document.getElementById('startScanBtn');
        this.stopBtn = document.getElementById('stopScanBtn');
        this.progressBar = document.getElementById('vcProgressBar');
        this.scanStatusText = document.getElementById('vcScanStatusText');
        this.auditStats = document.getElementById('vcAuditStats');
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        if (this.startBtn) {
            this.startBtn.addEventListener('click', () => this.startScan());
        }

        if (this.stopBtn) {
            this.stopBtn.addEventListener('click', () => this.stopScan());
        }

        const saveCredsBtn = document.getElementById('saveVcCredsBtn');
        if (saveCredsBtn) {
            saveCredsBtn.addEventListener('click', () => this.saveCredentials());
        }

        window.apiClient.on('version_check_progress', (data) => {
            this.handleScanProgress(data);
        });
    }

    async startScan() {
        if (this.isScanning) return;
        this.isScanning = true;
        this.updateButtons();

        if (this.scanStatusText) this.scanStatusText.textContent = 'Initializing version check scan...';
        if (this.progressBar) this.progressBar.style.width = '0%';

        try {
            const res = await window.apiClient.scanVersions();
            if (res.success) {
                window.uiController.showToast(`Version scan started for ${res.total} games`, 'info');
            }
        } catch (err) {
            this.isScanning = false;
            this.updateButtons();
            window.uiController.showToast(`Failed to start scan: ${err.message}`, 'danger');
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
                this.scanStatusText.textContent = `Checking [${current}/${total}]: ${data.game || 'Game'}`;
            }

            this.appendResultRow(data);
        } else if (data.status === 'completed') {
            this.isScanning = false;
            this.updateButtons();
            if (this.progressBar) this.progressBar.style.width = '100%';
            if (this.scanStatusText) {
                this.scanStatusText.textContent = `Audit Complete. Found ${data.updates_found || 0} updates.`;
            }
            window.uiController.showToast('Version scan complete!', 'success');
        }
    }

    appendResultRow(data) {
        if (!this.resultsTable) return;

        // Clear empty placeholder if present
        const emptyRow = this.resultsTable.querySelector('.empty-row');
        if (emptyRow) emptyRow.remove();

        const tr = document.createElement('tr');
        const hasUpdate = data.update_available;
        const statusBadge = hasUpdate
            ? `<span class="badge badge-warning">UPDATE (v${data.remote_version})</span>`
            : `<span class="badge badge-success">UP TO DATE (v${data.local_version || '1.0'})</span>`;

        tr.innerHTML = `
            <td><strong>${data.game || 'Unknown'}</strong></td>
            <td>v${data.local_version || '---'}</td>
            <td>v${data.remote_version || '---'}</td>
            <td>${statusBadge}</td>
            <td>
                ${hasUpdate ? `
                    <button class="btn btn-sm btn-primary" onclick="window.detailsController.openGameById('${data.game_id}')">
                        Update
                    </button>
                ` : '<span class="text-muted">None</span>'}
            </td>
        `;

        this.resultsTable.prepend(tr);
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
        if (this.startBtn) this.startBtn.disabled = this.isScanning;
        if (this.stopBtn) this.stopBtn.disabled = !this.isScanning;
    }
}

window.versionCheckerController = new VersionCheckerController();
