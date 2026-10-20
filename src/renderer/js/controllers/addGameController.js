/**
 * Add Game Controller (Source / Developer Mode)
 * Handles adding new games directly to local Data.json, auto-scraping release info,
 * multi-part link configuration, live cover previews, and instant library synchronization.
 */

class AddGameController {
    constructor() {
        this.modal = document.getElementById('addGameModal');
        this.openBtn = document.getElementById('openAddGameBtn');
        this.openFromSettingsBtn = document.getElementById('openAddGameFromSettingsBtn');
        this.closeBtn = document.getElementById('closeAddGameBtn');
        this.cancelBtn = document.getElementById('cancelAddGameBtn');
        this.submitBtn = document.getElementById('submitAddGameBtn');

        // Form elements
        this.form = document.getElementById('addGameForm');
        this.autoFetchInput = document.getElementById('agAutoFetchUrlInput');
        this.autoFetchBtn = document.getElementById('agAutoFetchBtn');
        this.titleInput = document.getElementById('agTitleInput');
        this.versionInput = document.getElementById('agVersionInput');
        this.hostSelect = document.getElementById('agHostSelect');
        this.sizeInput = document.getElementById('agSizeInput');
        this.categorySelect = document.getElementById('agCategorySelect');
        this.originUrlInput = document.getElementById('agOriginUrlInput');
        this.thumbnailInput = document.getElementById('agThumbnailInput');
        this.thumbPreviewImg = document.getElementById('agThumbPreviewImg');
        this.partsListContainer = document.getElementById('agPartsList');
        this.addPartBtn = document.getElementById('agAddPartBtn');
        this.pasteMultiPartsBtn = document.getElementById('agPasteMultiPartsBtn');
        this.fixUrlInput = document.getElementById('agFixUrlInput');
        this.descriptionInput = document.getElementById('agDescriptionInput');
        this.mirrorsListContainer = document.getElementById('agMirrorsList');
        this.addMirrorBtn = document.getElementById('agAddMirrorBtn');
        this.targetFileIndicator = document.getElementById('agTargetFileIndicator');
        this.sourceBadge = document.getElementById('sourceModeBadge');

        // Modal Header UI
        this.modalIconBox = document.getElementById('agModalIconBox');
        this.modalIcon = document.getElementById('agModalIcon');
        this.modalTitle = document.getElementById('agModalTitle');
        this.modalSubtitle = document.getElementById('agModalSubtitle');
        this.editingGameTitle = null;

        this.isSourceMode = false;
        this.activeDbPath = 'Data.json';
    }

    async init() {
        this.bindEvents();
        await this.checkEnvironment();
    }

    async checkEnvironment() {
        try {
            let isSource = false;
            if (window.api && typeof window.api.isSourceMode === 'function') {
                isSource = await window.api.isSourceMode();
            }

            const status = await window.apiClient.getStatus().catch(() => ({}));
            if (status && status.is_source_mode !== undefined) {
                isSource = Boolean(status.is_source_mode);
            }

            const isLocalDb = Boolean(status && status.use_local_db);

            this.isSourceMode = isSource;
            this.activeDbPath = status?.local_db_path || 'Data.json';

            if (this.sourceBadge) {
                if (isSource) {
                    this.sourceBadge.textContent = 'SOURCE MODE';
                    this.sourceBadge.className = 'status-pill status-installed';
                    this.sourceBadge.style.display = 'inline-block';
                } else {
                    this.sourceBadge.style.display = 'none';
                }
            }

            if (this.openBtn) {
                this.openBtn.style.display = (isSource || isLocalDb) ? 'inline-flex' : 'none';
            }

            const envStatus = document.getElementById('sourceEnvStatus');
            if (envStatus) {
                if (isSource) {
                    envStatus.className = 'status-pill status-installed';
                    envStatus.textContent = 'Source Dev Mode';
                } else if (isLocalDb) {
                    envStatus.className = 'status-pill status-installed';
                    envStatus.textContent = 'Local Database Active';
                } else {
                    envStatus.className = 'status-pill status-missing';
                    envStatus.textContent = 'Packaged Mode (Remote DB)';
                }
            }
        } catch (err) {
            console.error('[AddGameController] Environment check error:', err);
        }
    }

    bindEvents() {
        if (this.openBtn) {
            this.openBtn.addEventListener('click', () => this.openModal());
        }

        if (this.openFromSettingsBtn) {
            this.openFromSettingsBtn.addEventListener('click', () => this.openModal());
        }

        if (this.closeBtn) {
            this.closeBtn.addEventListener('click', () => this.closeModal());
        }

        if (this.cancelBtn) {
            this.cancelBtn.addEventListener('click', () => this.closeModal());
        }

        if (this.modal) {
            this.modal.addEventListener('click', (e) => {
                if (e.target === this.modal) this.closeModal();
            });
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal && this.modal.classList.contains('active')) {
                this.closeModal();
            }
        });

        // Auto-fetch button
        if (this.autoFetchBtn) {
            this.autoFetchBtn.addEventListener('click', () => this.handleAutoFetch());
        }
        if (this.autoFetchInput) {
            this.autoFetchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.handleAutoFetch();
                }
            });
        }

        // Add part button
        if (this.addPartBtn) {
            this.addPartBtn.addEventListener('click', () => this.addPartRow());
        }

        // Add mirror button
        if (this.addMirrorBtn) {
            this.addMirrorBtn.addEventListener('click', () => this.addMirrorCard());
        }

        // Host selector change listener to swap mirror parts dynamically
        if (this.hostSelect) {
            this.hostSelect.addEventListener('change', () => {
                const selectedHost = this.hostSelect.value;
                if (this.currentAvailableHosts && this.currentAvailableHosts[selectedHost]) {
                    const hostData = this.currentAvailableHosts[selectedHost];
                    if (Array.isArray(hostData.parts) && hostData.parts.length > 0) {
                        this.setParts(hostData.parts);
                    }
                    if (hostData.fix_url && this.fixUrlInput) {
                        this.fixUrlInput.value = hostData.fix_url;
                    }
                    if (window.uiController) {
                        window.uiController.showToast(`Switched download parts to ${selectedHost}`, 'info');
                    }
                }
                this.refreshAllMirrorDropdowns();
            });
        }

        // Bulk paste parts
        if (this.pasteMultiPartsBtn) {
            this.pasteMultiPartsBtn.addEventListener('click', () => this.handleBulkPasteParts());
        }

        // Thumbnail live preview
        if (this.thumbnailInput) {
            this.thumbnailInput.addEventListener('input', (e) => {
                const url = e.target.value.trim();
                this.updateThumbnailPreview(url);
            });
        }

        // Submit form
        if (this.submitBtn) {
            this.submitBtn.addEventListener('click', () => this.submitGame());
        }
    }

    openModal() {
        if (!this.modal) return;
        this.resetForm();
        this.editingGameTitle = null;

        if (this.modalTitle) this.modalTitle.textContent = 'Add Game to Database';
        if (this.modalSubtitle) this.modalSubtitle.innerHTML = 'Add a new release directly into local <code style="color: var(--accent);">Data.json</code>.';
        if (this.submitBtn) this.submitBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save & Add to Data.json';
        if (this.modalIcon) this.modalIcon.className = 'fa-solid fa-square-plus';
        if (this.modalIconBox) {
            this.modalIconBox.style.background = 'rgba(212, 168, 83, 0.15)';
            this.modalIconBox.style.borderColor = 'rgba(212, 168, 83, 0.35)';
            this.modalIconBox.style.color = 'var(--accent)';
        }

        if (this.targetFileIndicator) {
            this.targetFileIndicator.textContent = `Target: ${this.activeDbPath}`;
            this.targetFileIndicator.title = this.activeDbPath;
        }
        this.modal.classList.add('active');
        if (this.titleInput) setTimeout(() => this.titleInput.focus(), 100);
    }

    openForEdit(game) {
        if (!game || !this.modal) return;
        this.resetForm();
        this.editingGameTitle = game.title;
        this.editingGame = game;

        if (this.modalTitle) this.modalTitle.textContent = `Edit Game: ${game.title}`;
        if (this.modalSubtitle) this.modalSubtitle.innerHTML = `Editing release metadata in local <code style="color: var(--accent);">Data.json</code>. Modify banner, mirrors, or links below.`;
        if (this.submitBtn) this.submitBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Changes to Data.json';
        if (this.modalIcon) this.modalIcon.className = 'fa-solid fa-pen-to-square';
        if (this.modalIconBox) {
            this.modalIconBox.style.background = 'rgba(212, 168, 83, 0.15)';
            this.modalIconBox.style.borderColor = 'rgba(212, 168, 83, 0.35)';
            this.modalIconBox.style.color = 'var(--accent)';
        }

        if (this.titleInput) this.titleInput.value = game.title || '';
        if (this.versionInput) this.versionInput.value = game.version || '1.0';
        if (this.hostSelect) this.hostSelect.value = game.host || 'GoFile';
        if (this.sizeInput) {
            const rawSz = (game.approx_size || game.size || '').trim();
            this.sizeInput.value = (!rawSz || ['n/a', 'unknown', 'none', 'null'].includes(rawSz.toLowerCase())) ? '' : rawSz;
        }
        if (this.categorySelect) this.categorySelect.value = game.category || 'General';
        if (this.originUrlInput) this.originUrlInput.value = game.origin_url || '';
        if (this.autoFetchInput) this.autoFetchInput.value = game.origin_url || '';
        if (this.thumbnailInput) {
            this.thumbnailInput.value = game.thumbnail || '';
            this.updateThumbnailPreview(game.thumbnail);
        }
        if (this.fixUrlInput) this.fixUrlInput.value = game.fix_url || '';
        if (this.descriptionInput) this.descriptionInput.value = game.description || '';

        // Pre-fill parts
        const parts = (Array.isArray(game.parts) && game.parts.length > 0)
            ? game.parts
            : (game.main_game_url ? [game.main_game_url] : (game.download_url ? [game.download_url] : []));
        this.setParts(parts);

        // Initialize available hosts map from current game data
        this.currentAvailableHosts = {};
        if (game.host) {
            this.currentAvailableHosts[game.host] = {
                parts: parts,
                fix_url: game.fix_url || ''
            };
        }
        if (game.mirrors && typeof game.mirrors === 'object') {
            for (const [mHost, mData] of Object.entries(game.mirrors)) {
                if (mData && typeof mData === 'object') {
                    const mParts = Array.isArray(mData.parts) ? mData.parts : (mData.url ? [mData.url] : []);
                    this.currentAvailableHosts[mHost] = {
                        parts: mParts,
                        fix_url: mData.fix_url || ''
                    };
                }
            }
        }

        // Pre-fill mirrors
        if (this.mirrorsListContainer) this.mirrorsListContainer.innerHTML = '';
        if (game.mirrors && typeof game.mirrors === 'object') {
            for (const [mHost, mData] of Object.entries(game.mirrors)) {
                if (mData && typeof mData === 'object') {
                    const mParts = Array.isArray(mData.parts) ? mData.parts : (mData.url ? [mData.url] : []);
                    const mFix = mData.fix_url || '';
                    this.addMirrorCard(mHost, mParts, mFix);
                }
            }
        }

        if (this.targetFileIndicator) {
            this.targetFileIndicator.textContent = `Target: ${this.activeDbPath} (Editing)`;
            this.targetFileIndicator.title = this.activeDbPath;
        }

        this.modal.classList.add('active');
        if (this.titleInput) setTimeout(() => this.titleInput.focus(), 100);
    }

    closeModal() {
        if (!this.modal) return;
        this.modal.classList.remove('active');
        this.editingGameTitle = null;
    }

    resetForm() {
        if (this.form) this.form.reset();
        this.editingGame = null;
        this.currentAvailableHosts = {};
        if (this.autoFetchInput) this.autoFetchInput.value = '';
        if (this.partsListContainer) this.partsListContainer.innerHTML = '';
        if (this.mirrorsListContainer) this.mirrorsListContainer.innerHTML = '';
        this.addPartRow(); // Start with 1 empty part row
        this.updateThumbnailPreview('');
    }

    updateThumbnailPreview(url) {
        if (!this.thumbPreviewImg) return;
        if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
            this.thumbPreviewImg.src = url;
        } else {
            this.thumbPreviewImg.src = 'assets/OFME-DWND-ICO.ico';
        }
    }

    addPartRow(url = '') {
        if (!this.partsListContainer) return;
        const partIndex = this.partsListContainer.children.length + 1;
        const row = document.createElement('div');
        row.className = 'part-row';
        row.innerHTML = `
            <span class="part-badge">Part ${partIndex}</span>
            <input type="text" class="form-input part-input" placeholder="https://gofile.io/d/... or archive download URL" value="${url}">
            <button type="button" class="part-btn-del" title="Remove Part"><i class="fa-solid fa-trash-can"></i></button>
        `;

        const delBtn = row.querySelector('.part-btn-del');
        delBtn.addEventListener('click', () => {
            row.remove();
            this.renumberParts();
        });

        this.partsListContainer.appendChild(row);
        this.renumberParts();
    }

    renumberParts() {
        if (!this.partsListContainer) return;
        const rows = this.partsListContainer.querySelectorAll('.part-row');
        rows.forEach((row, idx) => {
            const badge = row.querySelector('.part-badge');
            if (badge) badge.textContent = `Part ${idx + 1}`;
        });

        // Ensure at least 1 row exists
        if (rows.length === 0) {
            this.addPartRow();
        }
    }

    getParts() {
        if (!this.partsListContainer) return [];
        const inputs = this.partsListContainer.querySelectorAll('.part-input');
        const parts = [];
        inputs.forEach(input => {
            const val = input.value.trim();
            if (val && val.startsWith('http')) {
                parts.push(val);
            }
        });
        return parts;
    }

    setParts(partsList = []) {
        if (!this.partsListContainer) return;
        this.partsListContainer.innerHTML = '';
        if (Array.isArray(partsList) && partsList.length > 0) {
            partsList.forEach(partUrl => this.addPartRow(partUrl));
        } else {
            this.addPartRow();
        }
    }

    async handleAutoFetch() {
        const url = this.autoFetchInput?.value.trim();
        if (!url) {
            window.uiController.showToast('Please paste a release URL first (Online-Fix, SteamRIP, or Cracked-Games)', 'warning');
            return;
        }

        const originalBtnHtml = this.autoFetchBtn.innerHTML;
        this.autoFetchBtn.disabled = true;
        this.autoFetchBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Fetching...';

        try {
            window.uiController.showToast('Scraping release metadata & hosters...', 'info');
            const prefHost = window.settingsController?.settings?.preferred_host || 'GoFile';
            const data = await window.apiClient.scrapeGameInfo({ url, preferred_host: prefHost });

            if (!data || data.error) {
                throw new Error(data.error || 'Failed to parse game page.');
            }

            this.currentAvailableHosts = data.available_hosts || {};

            // Populate form fields
            if (data.title && this.titleInput) this.titleInput.value = data.title;
            if (data.version && this.versionInput) this.versionInput.value = data.version;
            if (data.host && this.hostSelect) this.hostSelect.value = data.host;
            // Approx Size: Never overwrite valid existing size with 'N/A' or 'Unknown'
            const currentSize = this.sizeInput?.value.trim() || '';
            const scrapedSize = (data.approx_size || '').trim();
            const isScrapedSizeValid = scrapedSize && !['n/a', 'unknown', 'none', 'null'].includes(scrapedSize.toLowerCase());

            if (isScrapedSizeValid) {
                if (this.sizeInput) this.sizeInput.value = scrapedSize;
            } else if (!currentSize && this.editingGame) {
                const existingSize = (this.editingGame.approx_size || this.editingGame.size || '').trim();
                if (existingSize && !['n/a', 'unknown', 'none', 'null'].includes(existingSize.toLowerCase())) {
                    if (this.sizeInput) this.sizeInput.value = existingSize;
                }
            }

            if (data.description && this.descriptionInput) this.descriptionInput.value = data.description;

            // Thumbnail: Never overwrite if editing an existing game or if input already has a thumbnail
            const currentThumb = this.thumbnailInput?.value.trim() || '';
            if (!currentThumb && !this.editingGame && data.thumbnail) {
                this.thumbnailInput.value = data.thumbnail;
                this.updateThumbnailPreview(data.thumbnail);
            }
            if (data.origin_url && this.originUrlInput) {
                this.originUrlInput.value = data.origin_url;
            } else if (this.originUrlInput) {
                this.originUrlInput.value = url;
            }
            if (data.category && this.categorySelect) this.categorySelect.value = data.category;
            if (data.fix_url && this.fixUrlInput) this.fixUrlInput.value = data.fix_url;

            // Update primary host options from available_hosts if available
            if (this.hostSelect && data.available_hosts && Object.keys(data.available_hosts).length > 0) {
                const currentPrimary = (data.host || this.hostSelect.value || '').trim();
                const availHostsList = Object.keys(data.available_hosts);
                this.hostSelect.innerHTML = availHostsList.map(h => 
                    `<option value="${h}" ${h.toLowerCase() === currentPrimary.toLowerCase() ? 'selected' : ''}>${h}</option>`
                ).join('');
                if (data.host) this.hostSelect.value = data.host;
            }

            // Parts
            if (Array.isArray(data.parts) && data.parts.length > 0) {
                this.setParts(data.parts);
            } else if (data.available_hosts) {
                // Find matching host
                const hostObj = data.available_hosts[this.hostSelect.value] || Object.values(data.available_hosts)[0];
                if (hostObj && Array.isArray(hostObj.parts)) {
                    this.setParts(hostObj.parts);
                }
            }

            // Update existing mirror cards without wiping container or auto-creating unwanted cards
            const mirrorCards = this.mirrorsListContainer ? this.mirrorsListContainer.querySelectorAll('.mirror-subcard') : [];
            mirrorCards.forEach(card => {
                const hostSelectEl = card.querySelector('.mirror-host-select');
                const fixInputEl = card.querySelector('.mirror-fix-input');
                const partsContainerEl = card.querySelector('.mirror-parts-list');
                
                const chosenHost = hostSelectEl ? hostSelectEl.value.trim() : '';
                
                // Refresh dropdown options to only currently available hosts
                const availMirrorHosts = this.getAvailableMirrorHosts(chosenHost);
                if (hostSelectEl) {
                    hostSelectEl.innerHTML = availMirrorHosts.map(h => 
                        `<option value="${h}" ${h.toLowerCase() === chosenHost.toLowerCase() ? 'selected' : ''}>${h}</option>`
                    ).join('');
                }

                // If this card's host has data in data.available_hosts, fill it!
                if (data.available_hosts && chosenHost) {
                    const matchedKey = Object.keys(data.available_hosts).find(k => k.toLowerCase() === chosenHost.toLowerCase());
                    if (matchedKey) {
                        const hData = data.available_hosts[matchedKey];
                        const mParts = Array.isArray(hData.parts) ? hData.parts : (hData.url ? [hData.url] : []);
                        if (mParts.length > 0 && partsContainerEl) {
                            partsContainerEl.innerHTML = '';
                            mParts.forEach(pUrl => {
                                const idx = partsContainerEl.children.length + 1;
                                const pRow = document.createElement('div');
                                pRow.className = 'part-row';
                                pRow.innerHTML = `
                                    <span class="part-badge" style="min-width: 48px; font-size: 10px; padding: 2px 6px;">P${idx}</span>
                                    <input type="text" class="form-input part-input mirror-part-url" style="font-size: 11px;" placeholder="https://... download part" value="${pUrl}">
                                    <button type="button" class="part-btn-del" style="width: 24px; height: 24px;" title="Remove Part"><i class="fa-solid fa-trash-can" style="font-size: 10px;"></i></button>
                                `;
                                pRow.querySelector('.part-btn-del').addEventListener('click', () => {
                                    pRow.remove();
                                    this.renumberMirrorParts(partsContainerEl);
                                });
                                partsContainerEl.appendChild(pRow);
                            });
                            this.renumberMirrorParts(partsContainerEl);
                        }
                        if (hData.fix_url && fixInputEl) {
                            fixInputEl.value = hData.fix_url;
                        }
                    }
                }
            });

            window.uiController.showToast(`Fetched details for "${data.title || 'Game'}"!`, 'success');
        } catch (err) {
            console.error('[AddGameController] AutoFetch error:', err);
            window.uiController.showToast(`Auto-fetch failed: ${err.message}`, 'danger');
        } finally {
            this.autoFetchBtn.disabled = false;
            this.autoFetchBtn.innerHTML = originalBtnHtml;
        }
    }

    async handleBulkPasteParts() {
        const text = prompt('Paste multiple download links (separated by lines or spaces):');
        if (!text) return;

        const lines = text.split(/[\r\n\s,]+/).map(s => s.trim()).filter(s => s.startsWith('http'));
        if (lines.length === 0) {
            window.uiController.showToast('No valid http links found in pasted text', 'warning');
            return;
        }

        this.setParts(lines);
        window.uiController.showToast(`Imported ${lines.length} download parts`, 'success');
    }

    async submitGame() {
        const title = this.titleInput?.value.trim();
        if (!title) {
            window.uiController.showToast('Game Title is required', 'warning');
            if (this.titleInput) this.titleInput.focus();
            return;
        }

        const parts = this.getParts();
        if (parts.length === 0) {
            window.uiController.showToast('At least one download part URL is required', 'warning');
            return;
        }

        const mirrors = this.getMirrors();

        const rawSize = this.sizeInput?.value.trim() || '';
        let finalSize = rawSize;
        if (!finalSize || ['n/a', 'unknown', 'none', 'null'].includes(finalSize.toLowerCase())) {
            const existingSize = (this.editingGame?.approx_size || this.editingGame?.size || '').trim();
            finalSize = (existingSize && !['n/a', 'unknown', 'none', 'null'].includes(existingSize.toLowerCase())) ? existingSize : 'Unknown';
        }

        let finalThumb = this.thumbnailInput?.value.trim() || '';
        if (!finalThumb && this.editingGame?.thumbnail) {
            finalThumb = this.editingGame.thumbnail.trim();
        }

        const payload = {
            title: title,
            version: this.versionInput?.value.trim() || '1.0',
            host: this.hostSelect?.value || 'GoFile',
            approx_size: finalSize,
            category: this.categorySelect?.value || 'General',
            origin_url: this.originUrlInput?.value.trim() || '',
            thumbnail: finalThumb,
            parts: parts,
            fix_url: this.fixUrlInput?.value.trim() || '',
            description: this.descriptionInput?.value.trim() || 'No description available.'
        };

        if (mirrors && Object.keys(mirrors).length > 0) {
            payload.mirrors = mirrors;
        }

        if (this.editingGameTitle) {
            payload.original_title = this.editingGameTitle;
        }

        const originalBtnHtml = this.submitBtn.innerHTML;
        this.submitBtn.disabled = true;
        this.submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';

        try {
            const res = await window.apiClient.addGame(payload);
            if (!res.success) {
                throw new Error(res.error || 'Failed to save game to Data.json');
            }

            const successMsg = this.editingGameTitle
                ? `Saved changes for "${title}" in Data.json!`
                : `Successfully added "${title}" to Data.json!`;
            window.uiController.showToast(successMsg, 'success');
            this.closeModal();

            // Refresh library grid
            if (window.libraryController) {
                await window.libraryController.loadGames();
            }
        } catch (err) {
            console.error('[AddGameController] Save error:', err);
            window.uiController.showToast(`Failed to save game: ${err.message}`, 'danger');
        } finally {
            this.submitBtn.disabled = false;
            this.submitBtn.innerHTML = originalBtnHtml;
        }
    }

    // ─── MIRROR HELPERS ───

    getAvailableMirrorHosts(currentHostForThisCard = null) {
        const primaryHost = (this.hostSelect?.value || '').trim();
        const hostsSet = new Set();

        if (this.currentAvailableHosts && Object.keys(this.currentAvailableHosts).length > 0) {
            for (const h of Object.keys(this.currentAvailableHosts)) {
                if (h && h.trim()) hostsSet.add(h.trim());
            }
        }

        if (this.editingGame?.mirrors) {
            for (const h of Object.keys(this.editingGame.mirrors)) {
                if (h && h.trim()) hostsSet.add(h.trim());
            }
        }

        if (hostsSet.size === 0) {
            ['PixelDrain', 'FileDitch', 'FileKeeper', 'VikingFile', 'GoFile', 'BuzzHeavier', '1Fichier', 'Direct'].forEach(h => hostsSet.add(h));
        }

        if (currentHostForThisCard && currentHostForThisCard.trim()) {
            hostsSet.add(currentHostForThisCard.trim());
        }

        return Array.from(hostsSet).filter(h => {
            if (h.toLowerCase() === primaryHost.toLowerCase() && h.toLowerCase() !== (currentHostForThisCard || '').toLowerCase()) {
                return false;
            }
            return true;
        });
    }

    refreshAllMirrorDropdowns() {
        if (!this.mirrorsListContainer) return;
        const mirrorCards = this.mirrorsListContainer.querySelectorAll('.mirror-subcard');
        mirrorCards.forEach(card => {
            const hostSelectEl = card.querySelector('.mirror-host-select');
            if (!hostSelectEl) return;
            const currentVal = hostSelectEl.value;
            const avail = this.getAvailableMirrorHosts(currentVal);
            hostSelectEl.innerHTML = avail.map(h => 
                `<option value="${h}" ${h.toLowerCase() === currentVal.toLowerCase() ? 'selected' : ''}>${h}</option>`
            ).join('');
        });
    }

    addMirrorCard(host = '', parts = [], fixUrl = '') {
        if (!this.mirrorsListContainer) return;
        const card = document.createElement('div');
        card.className = 'mirror-subcard';

        const existingChosenHosts = Array.from(this.mirrorsListContainer.querySelectorAll('.mirror-host-select'))
            .map(s => s.value.trim().toLowerCase());

        const availableHosts = this.getAvailableMirrorHosts(host);

        let chosenHost = host;
        if (!chosenHost) {
            chosenHost = availableHosts.find(h => !existingChosenHosts.includes(h.toLowerCase())) || availableHosts[0] || 'PixelDrain';
        }

        // If parts or fixUrl are empty, check if this host has fetched data and auto-fill!
        if ((!parts || parts.length === 0) && !fixUrl && this.currentAvailableHosts) {
            const matchKey = Object.keys(this.currentAvailableHosts).find(k => k.toLowerCase() === chosenHost.toLowerCase());
            if (matchKey) {
                const hData = this.currentAvailableHosts[matchKey];
                parts = Array.isArray(hData.parts) ? hData.parts : (hData.url ? [hData.url] : []);
                fixUrl = hData.fix_url || '';
            }
        }

        const hostOptions = availableHosts.map(h => `<option value="${h}" ${h.toLowerCase() === chosenHost.toLowerCase() ? 'selected' : ''}>${h}</option>`).join('');

        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-glass); padding-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <i class="fa-solid fa-server" style="color: var(--accent); font-size: 13px;"></i>
                    <span style="font-size: 12px; font-weight: 600; color: #fff;">Mirror Host:</span>
                    <select class="form-input mirror-host-select" style="min-width: 140px; padding: 4px 8px; font-size: 12px; cursor: pointer;">
                        ${hostOptions}
                    </select>
                </div>
                <button type="button" class="part-btn-del remove-mirror-btn" title="Remove this mirror" style="width: 24px; height: 24px;">
                    <i class="fa-solid fa-trash-can" style="font-size: 10px;"></i>
                </button>
            </div>

            <div style="display: flex; flex-direction: column; gap: 4px;">
                <label style="font-size: 11px; color: #93c5fd; display: flex; align-items: center; gap: 5px;">
                    <i class="fa-solid fa-wrench" style="font-size: 10px;"></i> Fix / Repair URL (Optional)
                </label>
                <input type="text" class="form-input mirror-fix-input" style="font-size: 11px; font-family: var(--font-mono); padding: 5px 8px;" placeholder="https://... (optional online fix for this mirror)" value="${fixUrl || ''}">
            </div>

            <div style="display: flex; flex-direction: column; gap: 6px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">Download Parts:</span>
                    <div style="display: flex; gap: 6px;">
                        <button type="button" class="btn btn-secondary mirror-add-part-btn" style="padding: 2px 8px; font-size: 10px;">
                            <i class="fa-solid fa-plus"></i> Part
                        </button>
                        <button type="button" class="btn btn-secondary mirror-bulk-parts-btn" style="padding: 2px 8px; font-size: 10px;">
                            <i class="fa-solid fa-paste"></i> Bulk Paste
                        </button>
                    </div>
                </div>
                <div class="mirror-parts-list" style="display: flex; flex-direction: column; gap: 6px; max-height: 160px; overflow-y: auto; padding-right: 4px;">
                    <!-- Mirror parts dynamically populated -->
                </div>
            </div>
        `;

        const removeBtn = card.querySelector('.remove-mirror-btn');
        removeBtn.addEventListener('click', () => card.remove());

        const partsContainer = card.querySelector('.mirror-parts-list');
        const addPartBtn = card.querySelector('.mirror-add-part-btn');
        const bulkBtn = card.querySelector('.mirror-bulk-parts-btn');

        const addMirrorPartRow = (pUrl = '') => {
            const idx = partsContainer.children.length + 1;
            const pRow = document.createElement('div');
            pRow.className = 'part-row';
            pRow.innerHTML = `
                <span class="part-badge" style="min-width: 48px; font-size: 10px; padding: 2px 6px;">P${idx}</span>
                <input type="text" class="form-input part-input mirror-part-url" style="font-size: 11px;" placeholder="https://... download part" value="${pUrl}">
                <button type="button" class="part-btn-del" style="width: 24px; height: 24px;" title="Remove Part"><i class="fa-solid fa-trash-can" style="font-size: 10px;"></i></button>
            `;
            const del = pRow.querySelector('.part-btn-del');
            del.addEventListener('click', () => {
                pRow.remove();
                this.renumberMirrorParts(partsContainer);
            });
            partsContainer.appendChild(pRow);
            this.renumberMirrorParts(partsContainer);
        };

        addPartBtn.addEventListener('click', () => addMirrorPartRow(''));

        bulkBtn.addEventListener('click', () => {
            const text = prompt('Paste mirror download links (separated by lines or spaces):');
            if (!text) return;
            const lines = text.split(/[\r\n\s,]+/).map(s => s.trim()).filter(s => s.startsWith('http'));
            if (lines.length === 0) {
                window.uiController?.showToast('No valid http links found in pasted text', 'warning');
                return;
            }
            partsContainer.innerHTML = '';
            lines.forEach(l => addMirrorPartRow(l));
            window.uiController?.showToast(`Imported ${lines.length} mirror parts`, 'success');
        });

        // Mirror host select change listener: dynamically populate parts and fix url if available!
        const hostSelectEl = card.querySelector('.mirror-host-select');
        hostSelectEl.addEventListener('change', () => {
            const selectedH = hostSelectEl.value;
            if (this.currentAvailableHosts) {
                const matchKey = Object.keys(this.currentAvailableHosts).find(k => k.toLowerCase() === selectedH.toLowerCase());
                if (matchKey) {
                    const hData = this.currentAvailableHosts[matchKey];
                    const newParts = Array.isArray(hData.parts) ? hData.parts : (hData.url ? [hData.url] : []);
                    const newFix = hData.fix_url || '';

                    partsContainer.innerHTML = '';
                    if (newParts.length > 0) {
                        newParts.forEach(p => addMirrorPartRow(p));
                    } else {
                        addMirrorPartRow('');
                    }

                    const fixInputEl = card.querySelector('.mirror-fix-input');
                    if (fixInputEl && newFix) {
                        fixInputEl.value = newFix;
                    }

                    window.uiController?.showToast(`Filled ${matchKey} mirror parts from fetched data`, 'info');
                }
            }
        });

        if (Array.isArray(parts) && parts.length > 0) {
            parts.forEach(p => addMirrorPartRow(p));
        } else {
            addMirrorPartRow('');
        }

        this.mirrorsListContainer.appendChild(card);
    }

    renumberMirrorParts(container) {
        if (!container) return;
        const rows = container.querySelectorAll('.part-row');
        rows.forEach((r, i) => {
            const badge = r.querySelector('.part-badge');
            if (badge) badge.textContent = `P${i + 1}`;
        });
        if (rows.length === 0) {
            const pRow = document.createElement('div');
            pRow.className = 'part-row';
            pRow.innerHTML = `
                <span class="part-badge" style="min-width: 48px; font-size: 10px; padding: 2px 6px;">P1</span>
                <input type="text" class="form-input part-input mirror-part-url" style="font-size: 11px;" placeholder="https://... download part" value="">
                <button type="button" class="part-btn-del" style="width: 24px; height: 24px;" title="Remove Part"><i class="fa-solid fa-trash-can" style="font-size: 10px;"></i></button>
            `;
            pRow.querySelector('.part-btn-del').addEventListener('click', () => {
                pRow.remove();
                this.renumberMirrorParts(container);
            });
            container.appendChild(pRow);
        }
    }

    getMirrors() {
        if (!this.mirrorsListContainer) return {};
        const mirrorCards = this.mirrorsListContainer.querySelectorAll('.mirror-subcard');
        const mirrorsObj = {};

        mirrorCards.forEach(card => {
            const hostSelect = card.querySelector('.mirror-host-select');
            const fixInput = card.querySelector('.mirror-fix-input');
            const partInputs = card.querySelectorAll('.mirror-part-url');

            const host = hostSelect ? hostSelect.value.trim() : '';
            if (!host) return;

            const parts = [];
            partInputs.forEach(inp => {
                const val = inp.value.trim();
                if (val && val.startsWith('http')) {
                    parts.push(val);
                }
            });

            const fixUrl = fixInput ? fixInput.value.trim() : '';

            if (parts.length > 0 || fixUrl) {
                mirrorsObj[host] = {
                    parts: parts,
                    fix_url: fixUrl
                };
            }
        });

        return mirrorsObj;
    }
}

window.addGameController = new AddGameController();
