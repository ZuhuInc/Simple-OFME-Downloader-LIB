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
        this.targetFileIndicator = document.getElementById('agTargetFileIndicator');
        this.sourceBadge = document.getElementById('sourceModeBadge');

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
            if (status && (status.is_source_mode || status.use_local_db)) {
                isSource = true;
            }

            this.isSourceMode = isSource;
            this.activeDbPath = status.local_db_path || 'Data.json';

            if (this.sourceBadge) {
                this.sourceBadge.style.display = isSource ? 'inline-block' : 'none';
            }

            if (this.openBtn) {
                this.openBtn.style.display = isSource ? 'inline-flex' : 'none';
            }

            const envStatus = document.getElementById('sourceEnvStatus');
            if (envStatus) {
                if (isSource) {
                    envStatus.className = 'status-pill status-installed';
                    envStatus.textContent = 'Source Mode Active';
                } else {
                    envStatus.className = 'status-pill status-missing';
                    envStatus.textContent = 'Packaged Mode';
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
        if (this.targetFileIndicator) {
            this.targetFileIndicator.textContent = `Target: ${this.activeDbPath}`;
            this.targetFileIndicator.title = this.activeDbPath;
        }
        this.modal.classList.add('active');
        if (this.titleInput) setTimeout(() => this.titleInput.focus(), 100);
    }

    closeModal() {
        if (!this.modal) return;
        this.modal.classList.remove('active');
    }

    resetForm() {
        if (this.form) this.form.reset();
        if (this.autoFetchInput) this.autoFetchInput.value = '';
        if (this.partsListContainer) this.partsListContainer.innerHTML = '';
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
            window.uiController.showToast('Please paste a release URL first (Online-Fix or SteamRIP)', 'warning');
            return;
        }

        const originalBtnHtml = this.autoFetchBtn.innerHTML;
        this.autoFetchBtn.disabled = true;
        this.autoFetchBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Fetching...';

        try {
            window.uiController.showToast('Scraping release metadata & hosters...', 'info');
            const data = await window.apiClient.scrapeGameInfo({ url });

            if (!data || data.error) {
                throw new Error(data.error || 'Failed to parse game page.');
            }

            // Populate form fields
            if (data.title && this.titleInput) this.titleInput.value = data.title;
            if (data.version && this.versionInput) this.versionInput.value = data.version;
            if (data.host && this.hostSelect) this.hostSelect.value = data.host;
            if (data.approx_size && this.sizeInput) this.sizeInput.value = data.approx_size;
            if (data.description && this.descriptionInput) this.descriptionInput.value = data.description;
            if (data.thumbnail && this.thumbnailInput) {
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

        const payload = {
            title: title,
            version: this.versionInput?.value.trim() || '1.0',
            host: this.hostSelect?.value || 'GoFile',
            approx_size: this.sizeInput?.value.trim() || 'Unknown',
            category: this.categorySelect?.value || 'General',
            origin_url: this.originUrlInput?.value.trim() || '',
            thumbnail: this.thumbnailInput?.value.trim() || '',
            parts: parts,
            fix_url: this.fixUrlInput?.value.trim() || '',
            description: this.descriptionInput?.value.trim() || 'No description available.'
        };

        const originalBtnHtml = this.submitBtn.innerHTML;
        this.submitBtn.disabled = true;
        this.submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';

        try {
            const res = await window.apiClient.addGame(payload);
            if (!res.success) {
                throw new Error(res.error || 'Failed to save game to Data.json');
            }

            window.uiController.showToast(`Successfully added "${title}" to Data.json!`, 'success');
            this.closeModal();

            // Refresh library grid
            if (window.libraryController) {
                await window.libraryController.loadGames();
            }
        } catch (err) {
            console.error('[AddGameController] Save error:', err);
            window.uiController.showToast(`Failed to add game: ${err.message}`, 'danger');
        } finally {
            this.submitBtn.disabled = false;
            this.submitBtn.innerHTML = originalBtnHtml;
        }
    }
}

window.addGameController = new AddGameController();
