/**
 * Version Checker Controller
 * Audits installed games against Online-Fix.me and SteamRIP updates,
 * handles webhook alerts, and manages credential auto-fill.
 */

class VersionCheckerController {
    constructor() {
        this.isScanning = false;
        this.isBatchUpdating = false;
        this.resultsTable = null;
        this.scanOfmeBtn = null;
        this.scanSteamripBtn = null;
        this.scanAllSourcesBtn = null;
        this.installedOnlyCheck = null;
        this.enableBypassCheck = null;
        this.fastScanToggle = null;
        this.enableCacheCheck = null;
        this.manageBypassesBtn = null;
        this.bypassCountBadge = null;
        this.updateAllBtn = null;
        this.outdatedCountBadge = null;
        this.stopBtn = null;
        this.progressBar = null;
        this.scanStatusText = null;

        this.bypassModal = null;
        this.bypassList = [];
        this.batchUpdateModal = null;
        this.detectedOutdated = [];
    }

    init() {
        this.queryElements();
        this.loadAuditPreferences();
        this.bindEvents();
        this.loadSavedCredentials();
        this.refreshBypassList();
    }

    loadAuditPreferences() {
        if (!this.fastScanToggle) this.fastScanToggle = document.getElementById('vcFastScanToggle');
        if (!this.installedOnlyCheck) this.installedOnlyCheck = document.getElementById('vcInstalledOnlyCheck');
        if (!this.enableBypassCheck) this.enableBypassCheck = document.getElementById('vcEnableBypassCheck');
        if (!this.enableCacheCheck) this.enableCacheCheck = document.getElementById('vcEnableCacheCheck');

        // All 4 scan settings off (false) by default if there is no saved setting:
        const savedFastScan = localStorage.getItem('vc_fast_scan');
        const savedInstalledOnly = localStorage.getItem('vc_installed_only');
        const savedApplyBypass = localStorage.getItem('vc_apply_bypass');
        const savedEnableCache = localStorage.getItem('vc_enable_cache');

        if (this.fastScanToggle) {
            this.fastScanToggle.checked = savedFastScan !== null ? (savedFastScan === 'true') : false;
        }
        if (this.installedOnlyCheck) {
            this.installedOnlyCheck.checked = savedInstalledOnly !== null ? (savedInstalledOnly === 'true') : false;
        }
        if (this.enableBypassCheck) {
            this.enableBypassCheck.checked = savedApplyBypass !== null ? (savedApplyBypass === 'true') : false;
        }
        if (this.enableCacheCheck) {
            this.enableCacheCheck.checked = savedEnableCache !== null ? (savedEnableCache === 'true') : false;
        }
    }

    queryElements() {
        this.resultsTable = document.getElementById('vcResultsTableBody');
        this.scanOfmeBtn = document.getElementById('scanOfmeBtn');
        this.scanSteamripBtn = document.getElementById('scanSteamripBtn');
        this.scanAllSourcesBtn = document.getElementById('scanAllSourcesBtn');
        this.installedOnlyCheck = document.getElementById('vcInstalledOnlyCheck');
        this.enableBypassCheck = document.getElementById('vcEnableBypassCheck');
        this.fastScanToggle = document.getElementById('vcFastScanToggle');
        this.enableCacheCheck = document.getElementById('vcEnableCacheCheck');
        this.manageBypassesBtn = document.getElementById('vcManageBypassesBtn');
        this.bypassCountBadge = document.getElementById('vcBypassCount');
        this.updateAllBtn = document.getElementById('vcUpdateAllBtn');
        this.outdatedCountBadge = document.getElementById('vcOutdatedCount');
        this.stopBtn = document.getElementById('stopScanBtn');
        this.progressBar = document.getElementById('vcProgressBar');
        this.scanStatusText = document.getElementById('vcScanStatusText');

        this.bypassModal = document.getElementById('bypassManagerModal');
        this.batchUpdateModal = document.getElementById('batchUpdateConfirmModal');
    }

    isInstalledOnly() {
        if (!this.installedOnlyCheck) {
            this.installedOnlyCheck = document.getElementById('vcInstalledOnlyCheck');
        }
        return this.installedOnlyCheck ? this.installedOnlyCheck.checked : false;
    }

    isBypassEnabled() {
        if (!this.enableBypassCheck) {
            this.enableBypassCheck = document.getElementById('vcEnableBypassCheck');
        }
        return this.enableBypassCheck ? this.enableBypassCheck.checked : false;
    }

    isFastScanEnabled() {
        if (!this.fastScanToggle) {
            this.fastScanToggle = document.getElementById('vcFastScanToggle');
        }
        return this.fastScanToggle ? this.fastScanToggle.checked : false;
    }

    isCacheEnabled() {
        if (!this.enableCacheCheck) {
            this.enableCacheCheck = document.getElementById('vcEnableCacheCheck');
        }
        return this.enableCacheCheck ? this.enableCacheCheck.checked : false;
    }

    async refreshBypassList() {
        try {
            const res = await window.apiClient.getBypassList();
            if (res && res.bypass_list) {
                this.bypassList = res.bypass_list;
                if (!this.bypassCountBadge) this.bypassCountBadge = document.getElementById('vcBypassCount');
                if (this.bypassCountBadge) this.bypassCountBadge.textContent = this.bypassList.length;
            }
        } catch (e) {
            console.warn('[VC Controller] Failed to fetch bypass list:', e);
        }
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
                this.startScan({ source: 'ofme', installed_only: this.isInstalledOnly(), use_bypass: this.isBypassEnabled(), enable_cache: this.isCacheEnabled() });
            });
        }

        if (this.scanSteamripBtn) {
            this.scanSteamripBtn.addEventListener('click', () => {
                this.startScan({ source: 'sr', installed_only: this.isInstalledOnly(), use_bypass: this.isBypassEnabled(), enable_cache: this.isCacheEnabled() });
            });
        }

        if (this.scanAllSourcesBtn) {
            this.scanAllSourcesBtn.addEventListener('click', () => {
                this.startScan({ source: 'all', installed_only: this.isInstalledOnly(), use_bypass: this.isBypassEnabled(), enable_cache: this.isCacheEnabled() });
            });
        }

        if (this.stopBtn) {
            this.stopBtn.addEventListener('click', () => this.stopScan());
        }

        // Persist audit preference changes
        if (this.fastScanToggle) {
            this.fastScanToggle.addEventListener('change', () => {
                localStorage.setItem('vc_fast_scan', this.fastScanToggle.checked);
            });
        }
        if (this.installedOnlyCheck) {
            this.installedOnlyCheck.addEventListener('change', () => {
                localStorage.setItem('vc_installed_only', this.installedOnlyCheck.checked);
            });
        }
        if (this.enableBypassCheck) {
            this.enableBypassCheck.addEventListener('change', () => {
                localStorage.setItem('vc_apply_bypass', this.enableBypassCheck.checked);
            });
        }
        if (this.enableCacheCheck) {
            this.enableCacheCheck.addEventListener('change', () => {
                localStorage.setItem('vc_enable_cache', this.enableCacheCheck.checked);
            });
        }

        // Bypass Manager Modal
        if (this.manageBypassesBtn) {
            this.manageBypassesBtn.addEventListener('click', () => this.openBypassModal());
        }

        const closeBypassBtn = document.getElementById('closeBypassModalBtn');
        if (closeBypassBtn) closeBypassBtn.addEventListener('click', () => this.closeBypassModal());

        const closeBypassFooterBtn = document.getElementById('closeBypassModalFooterBtn');
        if (closeBypassFooterBtn) closeBypassFooterBtn.addEventListener('click', () => this.closeBypassModal());

        const bypassSearchInput = document.getElementById('bypassSearchInput');
        if (bypassSearchInput) {
            bypassSearchInput.addEventListener('input', (e) => this.filterBypassList(e.target.value));
        }

        const clearAllBypassesBtn = document.getElementById('clearAllBypassesBtn');
        if (clearAllBypassesBtn) {
            clearAllBypassesBtn.addEventListener('click', () => this.clearAllBypasses());
        }

        // Batch Update All Outdated Modal
        if (this.updateAllBtn) {
            this.updateAllBtn.addEventListener('click', () => this.openBatchUpdateModal());
        }

        const closeBatchBtn = document.getElementById('closeBatchUpdateModalBtn');
        if (closeBatchBtn) closeBatchBtn.addEventListener('click', () => this.closeBatchUpdateModal());

        const cancelBatchBtn = document.getElementById('cancelBatchUpdateBtn');
        if (cancelBatchBtn) cancelBatchBtn.addEventListener('click', () => this.closeBatchUpdateModal());

        const confirmBatchBtn = document.getElementById('confirmBatchUpdateBtn');
        if (confirmBatchBtn) {
            confirmBatchBtn.addEventListener('click', () => this.runBatchUpdate());
        }

        const saveCredsBtn = document.getElementById('saveVcCredsBtn');
        if (saveCredsBtn) {
            saveCredsBtn.addEventListener('click', () => this.saveCredentials());
        }

        const closeAssistedBtn = document.getElementById('closeAssistedModalBtn');
        if (closeAssistedBtn) {
            closeAssistedBtn.addEventListener('click', () => this.closeAssistedModal());
        }

        const addPartBtn = document.getElementById('assistedAddPartBtn');
        if (addPartBtn) {
            addPartBtn.addEventListener('click', () => {
                const listEl = document.getElementById('assistedPartsList');
                if (listEl) {
                    this.appendPartRowElement(listEl, listEl.children.length, '');
                }
            });
        }

        const saveAssistedBtn = document.getElementById('saveAssistedDataBtn');
        if (saveAssistedBtn) {
            saveAssistedBtn.addEventListener('click', () => this.saveAssistedData());
        }

        if (window.apiClient) {
            window.apiClient.on('version_check_progress', (data) => {
                this.handleScanProgress(data);
            });
            window.apiClient.on('batch_update_progress', (data) => {
                this.handleBatchUpdateProgress(data);
            });
        }
    }

    async startScan(options = {}) {
        if (this.isScanning) return;
        this.isScanning = true;
        this.detectedOutdated = [];
        if (!this.updateAllBtn) this.queryElements();
        if (this.updateAllBtn) this.updateAllBtn.style.display = 'none';
        if (this.outdatedCountBadge) this.outdatedCountBadge.textContent = '0';

        options.multi_threaded = this.isFastScanEnabled();
        if (options.enable_cache === undefined) {
            options.enable_cache = this.isCacheEnabled();
        }
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

        const modeLabel = options.multi_threaded ? '⚡ Fast Parallel' : 'Sequential';
        const srcName = options.source === 'ofme' ? 'Online-Fix (OFME)' : (options.source === 'sr' ? 'SteamRIP (SR)' : 'All Sources');
        const scopeName = options.installed_only ? 'Installed Only' : 'All Games';
        const cacheLabel = options.enable_cache ? 'Cache ON' : 'Cache OFF';
        if (this.scanStatusText) this.scanStatusText.textContent = `Auditing ${srcName} [${scopeName}, ${cacheLabel}] (${modeLabel})...`;
        if (this.progressBar) this.progressBar.style.width = '0%';

        try {
            const res = await window.apiClient.scanVersions(options);
            if (res && res.success) {
                window.uiController.showToast(`Audit started for ${res.total} games (${srcName} - ${modeLabel}, ${cacheLabel})`, 'info');
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
                const gameTitle = data.game || data.title;
                const exists = this.detectedOutdated.some(g => (g.title || g.game) === gameTitle);
                if (!exists) {
                    this.detectedOutdated.push({
                        title: gameTitle,
                        db_version: data.db_version,
                        latest_version: data.scraped_version || data.remote_version,
                        origin_url: data.origin_url,
                        game_id: data.game_id
                    });
                    if (this.updateAllBtn) this.updateAllBtn.style.display = 'inline-flex';
                    if (this.outdatedCountBadge) this.outdatedCountBadge.textContent = this.detectedOutdated.length;
                }
                this.appendResultRow(data);
            }
        } else if (data.status === 'completed') {
            this.isScanning = false;
            this.updateButtons();
            if (this.progressBar) this.progressBar.style.width = '100%';
            
            if (data.outdated_list && Array.isArray(data.outdated_list)) {
                this.detectedOutdated = data.outdated_list;
            }

            const count = this.detectedOutdated.length;
            if (this.scanStatusText) {
                this.scanStatusText.textContent = count > 0 
                    ? `Audit Complete. Found ${count} update${count > 1 ? 's' : ''}.`
                    : `Audit Complete. All checked games are up to date!`;
            }

            if (count > 0) {
                if (this.updateAllBtn) this.updateAllBtn.style.display = 'inline-flex';
                if (this.outdatedCountBadge) this.outdatedCountBadge.textContent = count;
            } else {
                if (this.updateAllBtn) this.updateAllBtn.style.display = 'none';
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

    formatVersionBadge(ver) {
        if (!ver || ver === '---' || ver === 'Not Installed') {
            return '<span class="text-muted">---</span>';
        }
        const clean = String(ver).trim().replace(/^(?:Build|v|ver|version)\s*/i, '');
        return /^\d/.test(clean) ? 'v' + clean : clean;
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

        const localVerDisplay = data.local_version !== 'Not Installed' ? this.formatVersionBadge(data.local_version) : '<span class="text-muted">---</span>';
        const dbVerDisplay = data.db_version ? this.formatVersionBadge(data.db_version) : '<span class="text-muted">---</span>';
        const liveVerDisplay = (data.scraped_version && data.scraped_version !== '---') ? this.formatVersionBadge(data.scraped_version) : '<span class="text-muted">---</span>';

        const safeTitle = (data.game || 'Game').replace(/'/g, "\\'");
        const safeUrl = (data.origin_url || '').replace(/'/g, "\\'");

        tr.innerHTML = `
            <td><strong>${data.game || 'Unknown'}</strong></td>
            <td>${localVerDisplay}</td>
            <td><span style="color: var(--accent); font-weight: 500;">${dbVerDisplay}</span></td>
            <td><span style="color: #60a5fa; font-weight: 600;">${liveVerDisplay}</span></td>
            <td>${statusBadge}</td>
            <td>
                <div style="display: flex; gap: 6px; align-items: center;">
                    <button class="btn btn-sm btn-secondary btn-icon" onclick="window.versionCheckerController.openUpdateUrl('${safeUrl}', '${data.game_id || ''}')" title="Open online release in browser">
                        <i class="fa-solid fa-arrow-up-right-from-square"></i>
                    </button>
                    <button class="btn btn-sm btn-primary btn-icon" onclick="window.versionCheckerController.openAssistedUpdater('${safeUrl}', '${safeTitle}')" title="Assisted Auto-Fill from Online-Fix">
                        <i class="fa-solid fa-robot"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary btn-icon" onclick="window.versionCheckerController.toggleBypassForGame('${safeTitle}', this)" title="Bypass this game from future audits">
                        <i class="fa-solid fa-bell-slash"></i>
                    </button>
                </div>
            </td>
        `;

        this.resultsTable.prepend(tr);
    }

    async toggleBypassForGame(gameTitle, btnEl = null) {
        if (!gameTitle) return;
        try {
            const res = await window.apiClient.toggleBypass(gameTitle);
            if (res && res.success) {
                if (res.bypassed) {
                    window.uiController.showToast(`Bypassed "${gameTitle}" from future audits`, 'warning');
                    if (btnEl) {
                        btnEl.style.color = 'var(--accent)';
                        btnEl.style.borderColor = 'var(--accent)';
                        btnEl.title = 'Bypassed in audits (Click to remove bypass)';
                    }
                } else {
                    window.uiController.showToast(`Included "${gameTitle}" in future audits`, 'success');
                    if (btnEl) {
                        btnEl.style.color = '';
                        btnEl.style.borderColor = '';
                        btnEl.title = 'Bypass this game from future audits';
                    }
                }
                await this.refreshBypassList();
            }
        } catch (err) {
            console.error('[VC Controller] Toggle bypass error:', err);
            window.uiController.showToast('Failed to toggle bypass for game', 'danger');
        }
    }

    async openBypassModal() {
        if (!this.bypassModal) this.bypassModal = document.getElementById('bypassManagerModal');
        if (!this.bypassModal) return;

        await this.refreshBypassList();
        const searchInput = document.getElementById('bypassSearchInput');
        if (searchInput) searchInput.value = '';
        this.renderBypassList();
        this.bypassModal.classList.add('active');
    }

    closeBypassModal() {
        if (!this.bypassModal) this.bypassModal = document.getElementById('bypassManagerModal');
        if (this.bypassModal) this.bypassModal.classList.remove('active');
    }

    renderBypassList(filterText = '') {
        const container = document.getElementById('bypassListContainer');
        if (!container) return;

        const term = (filterText || '').trim().toLowerCase();
        const filtered = term ? this.bypassList.filter(t => t.toLowerCase().includes(term)) : this.bypassList;

        if (filtered.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; color: var(--text-muted); padding: 36px 14px; background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); border: 1px dashed var(--border-glass);">
                    <i class="fa-solid fa-bell-slash" style="font-size: 26px; color: var(--text-muted); margin-bottom: 8px; display: block;"></i>
                    ${term ? 'No bypassed games match your search query.' : 'No games currently bypassed from live audits.'}
                </div>
            `;
            return;
        }

        container.innerHTML = '';
        filtered.forEach(title => {
            const row = document.createElement('div');
            row.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-glass); border-radius: var(--radius-sm); transition: var(--transition);';
            row.onmouseenter = () => row.style.background = 'rgba(255,255,255,0.06)';
            row.onmouseleave = () => row.style.background = 'rgba(255,255,255,0.03)';

            const safeTitle = title.replace(/'/g, "\\'");
            row.innerHTML = `
                <div style="display: flex; align-items: center; gap: 10px; overflow: hidden;">
                    <i class="fa-solid fa-gamepad" style="color: var(--accent); font-size: 13px;"></i>
                    <span style="font-weight: 500; color: #fff; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; overflow: hidden;">${title}</span>
                </div>
                <button type="button" class="btn btn-secondary btn-sm" style="color: var(--danger); padding: 4px 8px;" onclick="window.versionCheckerController.removeBypassItem('${safeTitle}')" title="Remove from bypass list">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            `;
            container.appendChild(row);
        });
    }

    filterBypassList(filterText) {
        this.renderBypassList(filterText);
    }

    async removeBypassItem(gameTitle) {
        if (!gameTitle) return;
        try {
            const res = await window.apiClient.toggleBypass(gameTitle, false);
            if (res && res.success) {
                window.uiController.showToast(`Removed "${gameTitle}" from bypass list`, 'success');
                this.bypassList = res.bypass_list || [];
                if (!this.bypassCountBadge) this.bypassCountBadge = document.getElementById('vcBypassCount');
                if (this.bypassCountBadge) this.bypassCountBadge.textContent = this.bypassList.length;
                const searchInput = document.getElementById('bypassSearchInput');
                this.renderBypassList(searchInput ? searchInput.value : '');
            }
        } catch (e) {
            window.uiController.showToast(`Failed to remove bypass: ${e.message}`, 'danger');
        }
    }

    async clearAllBypasses() {
        if (this.bypassList.length === 0) return;
        if (!confirm('Are you sure you want to clear all bypassed games? They will be audited in future checks.')) {
            return;
        }
        try {
            const res = await window.apiClient.clearBypassList();
            if (res && res.success) {
                this.bypassList = [];
                if (!this.bypassCountBadge) this.bypassCountBadge = document.getElementById('vcBypassCount');
                if (this.bypassCountBadge) this.bypassCountBadge.textContent = '0';
                this.renderBypassList();
                window.uiController.showToast('Bypass list cleared successfully', 'success');
            }
        } catch (e) {
            window.uiController.showToast(`Failed to clear bypass list: ${e.message}`, 'danger');
        }
    }

    openBatchUpdateModal() {
        if (!this.detectedOutdated || this.detectedOutdated.length === 0) {
            window.uiController.showToast('No outdated games available to update.', 'info');
            return;
        }

        if (!this.batchUpdateModal) this.batchUpdateModal = document.getElementById('batchUpdateConfirmModal');
        if (!this.batchUpdateModal) return;

        const tbody = document.getElementById('batchUpdatePreviewTableBody');
        if (tbody) {
            tbody.innerHTML = '';
            this.detectedOutdated.forEach(g => {
                const tr = document.createElement('tr');
                const title = g.title || g.game || 'Unknown';
                const curVer = this.formatVersionBadge(g.db_version);
                const newVer = this.formatVersionBadge(g.latest_version || g.scraped_version || g.remote_version);
                tr.innerHTML = `
                    <td><strong>${title}</strong></td>
                    <td><span style="color: var(--text-muted);">${curVer}</span></td>
                    <td><span style="color: #60a5fa; font-weight: 600;">${newVer}</span></td>
                `;
                tbody.appendChild(tr);
            });
        }

        const totalNotice = document.getElementById('batchUpdateTotalNotice');
        if (totalNotice) {
            totalNotice.textContent = `${this.detectedOutdated.length} game${this.detectedOutdated.length > 1 ? 's' : ''} ready to update`;
        }

        const progressSection = document.getElementById('batchUpdateProgressSection');
        if (progressSection) progressSection.style.display = 'none';

        const confirmBtn = document.getElementById('confirmBatchUpdateBtn');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> Confirm & Update All';
        }

        this.batchUpdateModal.classList.add('active');
    }

    closeBatchUpdateModal() {
        if (this.isBatchUpdating) {
            window.uiController.showToast('Batch update is running in the background...', 'info');
        }
        if (!this.batchUpdateModal) this.batchUpdateModal = document.getElementById('batchUpdateConfirmModal');
        if (this.batchUpdateModal) this.batchUpdateModal.classList.remove('active');
    }

    async runBatchUpdate() {
        if (this.isBatchUpdating || !this.detectedOutdated.length) return;
        this.isBatchUpdating = true;

        const confirmBtn = document.getElementById('confirmBatchUpdateBtn');
        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Updating...';
        }

        const progressSection = document.getElementById('batchUpdateProgressSection');
        if (progressSection) progressSection.style.display = 'flex';

        const statusText = document.getElementById('batchUpdateStatusText');
        const progressBar = document.getElementById('batchUpdateProgressBar');
        const percentText = document.getElementById('batchUpdatePercentText');

        if (statusText) statusText.textContent = `Updating [0/${this.detectedOutdated.length}]...`;
        if (progressBar) progressBar.style.width = '0%';
        if (percentText) percentText.textContent = '0%';

        window.uiController.showToast(`Batch update started for ${this.detectedOutdated.length} games...`, 'info');

        try {
            const res = await window.apiClient.batchUpdateGames({
                games: this.detectedOutdated,
                preferred_host: 'GoFile'
            });

            this.isBatchUpdating = false;

            if (res && res.success) {
                window.uiController.showToast(`Batch update complete! (${res.updated_count}/${res.total} games updated)`, 'success');
                if (statusText) statusText.textContent = `Finished! ${res.updated_count}/${res.total} games updated in Data.json.`;
                if (progressBar) progressBar.style.width = '100%';
                if (percentText) percentText.textContent = '100%';

                if (window.libraryController) {
                    await window.libraryController.loadGames();
                }

                // Clear detected outdated games and hide button
                this.detectedOutdated = [];
                if (this.updateAllBtn) this.updateAllBtn.style.display = 'none';

                setTimeout(() => {
                    this.closeBatchUpdateModal();
                }, 1400);
            } else {
                window.uiController.showToast(`Batch update failed: ${res?.error || 'Unknown error'}`, 'danger');
                if (confirmBtn) confirmBtn.disabled = false;
            }
        } catch (err) {
            this.isBatchUpdating = false;
            console.error('[VC Controller] Batch update error:', err);
            window.uiController.showToast(`Batch update failed: ${err.message}`, 'danger');
            if (confirmBtn) {
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = '<i class="fa-solid fa-rotate-right"></i> Retry Update';
            }
        }
    }

    handleBatchUpdateProgress(data) {
        if (!data) return;
        const statusText = document.getElementById('batchUpdateStatusText');
        const progressBar = document.getElementById('batchUpdateProgressBar');
        const percentText = document.getElementById('batchUpdatePercentText');

        if (data.status === 'updating') {
            const current = data.current || 0;
            const total = data.total || 1;
            const pct = Math.min(100, Math.round((current / total) * 100));

            if (statusText) statusText.textContent = `Updating [${current}/${total}]: ${data.game || 'Game'}...`;
            if (progressBar) progressBar.style.width = `${pct}%`;
            if (percentText) percentText.textContent = `${pct}%`;
        } else if (data.status === 'completed') {
            if (statusText) statusText.textContent = `Complete! ${data.success_count}/${data.total} games updated.`;
            if (progressBar) progressBar.style.width = '100%';
            if (percentText) percentText.textContent = '100%';
        }
    }

    async openAssistedUpdater(originUrl, gameTitle) {
        if (!originUrl && !gameTitle) {
            window.uiController.showToast('No URL or game title provided', 'warning');
            return;
        }

        const modal = document.getElementById('assistedUpdaterModal');
        if (!modal) return;

        window.uiController.showToast(`Scraping Online-Fix release data for ${gameTitle || 'game'}...`, 'info');

        try {
            const res = await window.apiClient.scrapeGameData({
                origin_url: originUrl,
                game_title: gameTitle,
                preferred_host: 'GoFile'
            });

            if (!res || !res.success) {
                window.uiController.showToast(`Scraper warning: ${res?.error || 'Could not fetch live mirrors'}. Opening form with existing info.`, 'warning');
            }

            this.currentScrapedData = res || {};
            this.populateAssistedForm(res, gameTitle, originUrl);
            modal.classList.add('active');
        } catch (err) {
            console.error('[VC Controller] Scrape error:', err);
            window.uiController.showToast(`Scrape failed: ${err.message}. Opening manual form.`, 'warning');
            this.populateAssistedForm({}, gameTitle, originUrl);
            modal.classList.add('active');
        }
    }

    populateAssistedForm(data, fallbackTitle, fallbackUrl) {
        const titleInput = document.getElementById('assistedGameTitleInput');
        const verInput = document.getElementById('assistedVersionInput');
        const hostSelect = document.getElementById('assistedHostSelect');
        const sizeInput = document.getElementById('assistedSizeInput');
        const fixInput = document.getElementById('assistedFixUrlInput');
        const originInput = document.getElementById('assistedOriginUrlInput');
        const catInput = document.getElementById('assistedCategoryInput');

        const reqTitle = (data.title || fallbackTitle || '').trim().toLowerCase();
        const reqUrl = (data.origin_url || fallbackUrl || '').trim().toLowerCase();

        const existingGame = (window.libraryController?.games || []).find(g => 
            (reqTitle && g.title?.trim().toLowerCase() === reqTitle) ||
            (reqUrl && g.origin_url && g.origin_url.trim().toLowerCase() === reqUrl)
        );

        if (titleInput) titleInput.value = fallbackTitle || existingGame?.title || data.title || '';
        this.currentExistingGame = existingGame;
        if (verInput) verInput.value = data.version || existingGame?.version || '1.0';
        
        const oldSize = existingGame?.approx_size || existingGame?.size || '';
        let resolvedSize = '';
        if (data.approx_size && data.approx_size !== 'N/A') {
            resolvedSize = data.approx_size;
        } else if (oldSize && oldSize !== 'N/A') {
            resolvedSize = oldSize;
        }
        if (sizeInput) sizeInput.value = resolvedSize;

        if (fixInput) fixInput.value = data.fix_url || existingGame?.fix_url || '';
        if (originInput) originInput.value = data.origin_url || fallbackUrl || existingGame?.origin_url || '';
        if (catInput) catInput.value = data.category || existingGame?.category || 'General';

        // Populate available hosts in dropdown if scraped
        if (hostSelect) {
            hostSelect.innerHTML = '';
            const hosts = (data.available_hosts && Object.keys(data.available_hosts).length > 0)
                ? Object.keys(data.available_hosts)
                : ['GoFile', 'VikingFile', 'Pixeldrain', '1Fichier', 'Google Drive', 'Direct'];

            hosts.forEach(h => {
                const opt = document.createElement('option');
                opt.value = h;
                opt.textContent = h;
                if (h === (data.host || 'GoFile')) opt.selected = true;
                hostSelect.appendChild(opt);
            });

            hostSelect.onchange = () => this.onHostDropdownChanged(hostSelect.value);
        }

        this.renderPartsList(data.parts && data.parts.length > 0 ? data.parts : ['']);
    }

    onHostDropdownChanged(selectedHost) {
        if (!this.currentScrapedData || !this.currentScrapedData.available_hosts) return;
        const hostData = this.currentScrapedData.available_hosts[selectedHost];
        if (hostData) {
            const fixInput = document.getElementById('assistedFixUrlInput');
            if (fixInput) fixInput.value = hostData.fix_url || '';
            this.renderPartsList(hostData.parts && hostData.parts.length > 0 ? hostData.parts : ['']);
            window.uiController.showToast(`Switched to ${selectedHost} mirrors`, 'info');
        }
    }

    renderPartsList(parts = ['']) {
        const listEl = document.getElementById('assistedPartsList');
        if (!listEl) return;
        listEl.innerHTML = '';

        if (!parts || parts.length === 0) parts = [''];

        parts.forEach((partUrl, idx) => {
            this.appendPartRowElement(listEl, idx, partUrl);
        });
    }

    appendPartRowElement(container, idx, value = '') {
        const row = document.createElement('div');
        row.className = 'part-row';
        row.dataset.index = idx;

        row.innerHTML = `
            <span class="part-badge">Part ${idx + 1}</span>
            <input type="text" class="form-input part-input" placeholder="https://gofile.io/d/..." value="${value}">
            <button type="button" class="part-btn-del" title="Remove part"><i class="fa-solid fa-minus"></i></button>
        `;

        row.querySelector('.part-btn-del').addEventListener('click', () => {
            if (container.children.length <= 1) {
                row.querySelector('.part-input').value = '';
            } else {
                row.remove();
                this.reindexPartsList();
            }
        });

        container.appendChild(row);
    }

    reindexPartsList() {
        const listEl = document.getElementById('assistedPartsList');
        if (!listEl) return;
        const rows = listEl.querySelectorAll('.part-row');
        rows.forEach((r, i) => {
            r.dataset.index = i;
            const badge = r.querySelector('.part-badge');
            if (badge) badge.textContent = `Part ${i + 1}`;
        });
    }

    closeAssistedModal() {
        const modal = document.getElementById('assistedUpdaterModal');
        if (modal) modal.classList.remove('active');
    }

    async saveAssistedData() {
        const titleInput = document.getElementById('assistedGameTitleInput');
        const verInput = document.getElementById('assistedVersionInput');
        const hostSelect = document.getElementById('assistedHostSelect');
        const sizeInput = document.getElementById('assistedSizeInput');
        const fixInput = document.getElementById('assistedFixUrlInput');
        const originInput = document.getElementById('assistedOriginUrlInput');
        const catInput = document.getElementById('assistedCategoryInput');
        const listEl = document.getElementById('assistedPartsList');

        const title = titleInput?.value.trim() || '';
        const version = verInput?.value.trim() || '1.0';
        const host = hostSelect?.value || 'GoFile';
        const approxSize = sizeInput?.value.trim() || '';
        const fixUrl = fixInput?.value.trim() || '';
        const originUrl = originInput?.value.trim() || '';
        const category = catInput?.value.trim() || 'General';

        if (!title) {
            window.uiController.showToast('Please enter a game title', 'warning');
            return;
        }

        const partInputs = listEl ? listEl.querySelectorAll('.part-input') : [];
        const parts = [];
        partInputs.forEach(p => {
            const val = p.value.trim();
            if (val && (val.startsWith('http://') || val.startsWith('https://'))) {
                parts.push(val);
            }
        });

        if (parts.length === 0) {
            window.uiController.showToast('Please provide at least one valid download part URL', 'warning');
            return;
        }

        const saveBtn = document.getElementById('saveAssistedDataBtn');
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
        }

        try {
            const payload = {
                title,
                version,
                host,
                approx_size: approxSize,
                fix_url: fixUrl,
                origin_url: originUrl,
                category,
                parts,
                thumbnail: this.currentScrapedData?.thumbnail || this.currentExistingGame?.thumbnail || '',
                description: this.currentScrapedData?.description || this.currentExistingGame?.description || ''
            };

            const res = await window.apiClient.applyGameData(payload);
            if (res && res.success) {
                window.uiController.showToast(`Updated ${title} in Data.json!`, 'success');
                this.closeAssistedModal();
                if (window.libraryController) window.libraryController.loadGames();
            } else {
                window.uiController.showToast(`Error: ${res?.error || 'Failed to save game'}`, 'danger');
            }
        } catch (err) {
            console.error('[VC Controller] Save error:', err);
            window.uiController.showToast(`Failed to save: ${err.message}`, 'danger');
        } finally {
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save & Apply to Data.json';
            }
        }
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

