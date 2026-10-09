/**
 * Download Controller
 * Manages active downloads queue, progress updates from Socket.IO, speeds, and archive extraction triggers.
 */

class DownloadController {
    constructor() {
        this.jobs = new Map();
        this.queueContainer = document.getElementById('downloadQueueContainer');
        this.emptyState = document.getElementById('downloadEmptyState');
        this.speedUnit = 'MB/s'; // or 'Mbps'
    }

    init() {
        this.bindEvents();
        this.loadExistingDownloads();
    }

    bindEvents() {
        window.apiClient.on('download_progress', (data) => {
            this.handleProgressUpdate(data);
        });

        window.apiClient.on('extraction_status', (data) => {
            this.handleExtractionUpdate(data);
        });
    }

    async loadExistingDownloads() {
        try {
            const data = await window.apiClient.getDownloads();
            if (data.jobs && Array.isArray(data.jobs)) {
                data.jobs.forEach(job => this.jobs.set(job.id, job));
                this.renderQueue();
            }
        } catch (err) {
            console.error('[DownloadController] Failed to load jobs:', err);
        }
    }

    handleProgressUpdate(data) {
        if (!data || !data.id) return;
        this.jobs.set(data.id, data);
        this.updateJobCard(data);

        // Notify if just completed
        if (data.status === 'completed' && !data._notified) {
            data._notified = true;
            window.uiController.showToast(`Download finished: ${data.filename || data.meta?.title}`, 'success');
            if (window.libraryController) {
                window.libraryController.loadGames();
            }
        }
    }

    handleExtractionUpdate(data) {
        if (data.status === 'extracting') {
            window.uiController.showToast(`Extracting: ${data.title || data.file || 'archive'}...`, 'info');
        } else if (data.status === 'success' || data.status === 'extracted') {
            window.uiController.showToast(`Extraction complete! Ready to play in ${data.dest || data.game_dir || 'Games'}`, 'success');
            if (window.libraryController) {
                window.libraryController.loadGames();
            }
        } else if (data.status === 'error') {
            window.uiController.showToast(`Extraction error: ${data.error}`, 'danger');
        }
    }

    renderQueue() {
        if (!this.queueContainer) return;
        const jobList = Array.from(this.jobs.values());

        if (jobList.length === 0) {
            if (this.emptyState) this.emptyState.style.display = 'flex';
            this.queueContainer.innerHTML = '';
            return;
        }

        if (this.emptyState) this.emptyState.style.display = 'none';
        this.queueContainer.innerHTML = '';

        jobList.reverse().forEach(job => {
            const el = this.createJobElement(job);
            this.queueContainer.appendChild(el);
        });
    }

    createJobElement(job) {
        const div = document.createElement('div');
        div.className = `glass-card download-card status-${job.status}`;
        div.id = `job-${job.id}`;

        const percent = (job.progress || 0).toFixed(1);
        const title = job.meta?.title || job.filename || `Download #${job.id}`;
        const speedFormatted = this.formatSpeed(job.speed_bytes || 0);
        const downloadedFormatted = this.formatBytes(job.downloaded_bytes || 0);
        const totalFormatted = this.formatBytes(job.total_bytes || 0);

        const getStatusText = (status, pct) => {
            switch(status) {
                case 'resolving': return 'RESOLVING LINK...';
                case 'connecting': return 'CONNECTING TO STREAM...';
                case 'downloading': return `DOWNLOADING (${pct}%)`;
                case 'extracting': return 'EXTRACTING ARCHIVE...';
                case 'completed': return 'INSTALLED / READY';
                case 'paused': return 'PAUSED';
                case 'error': return 'DOWNLOAD ERROR';
                case 'cancelled': return 'CANCELLED';
                default: return `${status.toUpperCase()} (${pct}%)`;
            }
        };

        const getIconClass = (status) => {
            switch(status) {
                case 'error': return 'fa-solid fa-circle-exclamation';
                case 'resolving':
                case 'connecting': return 'fa-solid fa-circle-notch fa-spin';
                case 'extracting': return 'fa-solid fa-box-archive fa-bounce';
                case 'completed': return 'fa-solid fa-circle-check';
                default: return 'fa-solid fa-cloud-arrow-down';
            }
        };

        const targetFolder = job.meta?.extracted_dir || job.dest_file;

        div.innerHTML = `
            <div class="download-card-header">
                <div class="download-title-area">
                    <i class="${getIconClass(job.status)} download-icon" style="${job.status === 'error' ? 'color: var(--danger);' : (job.status === 'completed' ? 'color: var(--success);' : '')}"></i>
                    <div>
                        <h4 class="download-title">${title}</h4>
                        <span class="download-subtitle">${job.error_msg ? `<span style="color: var(--danger);"><i class="fa-solid fa-triangle-exclamation"></i> ${job.error_msg}</span>` : `${job.filename || 'Archive'} &bull; ${downloadedFormatted} / ${totalFormatted}`}</span>
                    </div>
                </div>
                <div class="download-actions">
                    <span class="download-speed-badge" style="${job.status === 'downloading' ? '' : 'display: none;'}">${speedFormatted}</span>
                    ${job.status === 'downloading' ? `
                        <button class="btn-icon" title="Pause" onclick="window.downloadController.pauseJob('${job.id}')">
                            <i class="fa-solid fa-pause"></i>
                        </button>
                    ` : (job.status === 'paused' ? `
                        <button class="btn-icon" title="Resume" onclick="window.downloadController.resumeJob('${job.id}')">
                            <i class="fa-solid fa-play"></i>
                        </button>
                    ` : '')}
                    ${job.status === 'error' && job.url ? `
                        <button class="btn btn-sm btn-secondary" title="Open Link in Browser" onclick="window.downloadController.openExternalUrl('${job.url}')">
                            <i class="fa-solid fa-arrow-up-right-from-square"></i> Open Link
                        </button>
                    ` : ''}
                    ${job.status === 'completed' && targetFolder ? `
                        <button class="btn btn-sm btn-secondary" title="Open Game Folder" onclick="window.downloadController.openFolder('${targetFolder.replace(/\\/g, '\\\\')}')">
                            <i class="fa-solid fa-folder-open"></i> Open Folder
                        </button>
                    ` : ''}
                    ${job.status === 'completed' ? `
                        <button class="btn btn-sm btn-primary" title="Extract / Re-extract" onclick="window.downloadController.extractJob('${job.id}')">
                            <i class="fa-solid fa-file-zipper"></i> Extract
                        </button>
                    ` : ''}
                    ${job.status !== 'completed' && job.status !== 'extracting' ? `
                        <button class="btn-icon btn-icon-danger" title="Cancel / Remove" onclick="window.downloadController.cancelJob('${job.id}')">
                            <i class="fa-solid fa-xmark"></i>
                        </button>
                    ` : ''}
                </div>
            </div>
            <div class="download-progress-bar">
                <div class="progress-bar-fill ${job.status === 'error' ? 'bg-danger' : (job.status === 'resolving' || job.status === 'connecting' || job.status === 'extracting' ? 'progress-indeterminate' : '')}" style="width: ${job.status === 'completed' ? 100 : percent}%;"></div>
            </div>
            <div class="download-card-footer">
                <span class="download-status-label status-text-${job.status}">${getStatusText(job.status, percent)}</span>
                <span class="download-eta">${job.eta ? 'ETA: ' + job.eta : (job.error_msg ? 'Failed' : (job.status === 'resolving' ? 'Resolving host link' : ''))}</span>
            </div>
        `;
        return div;
    }

    updateJobCard(job) {
        const card = document.getElementById(`job-${job.id}`);
        if (!card) {
            this.renderQueue();
            return;
        }

        card.className = `glass-card download-card status-${job.status}`;

        const percent = (job.progress || 0).toFixed(1);
        const fill = card.querySelector('.progress-bar-fill');
        if (fill) {
            fill.style.width = `${job.status === 'completed' ? 100 : percent}%`;
            if (job.status === 'error') fill.classList.add('bg-danger');
            else fill.classList.remove('bg-danger');

            if (job.status === 'resolving' || job.status === 'connecting' || job.status === 'extracting') {
                fill.classList.add('progress-indeterminate');
            } else {
                fill.classList.remove('progress-indeterminate');
            }
        }

        const speedBadge = card.querySelector('.download-speed-badge');
        if (speedBadge) {
            if (job.status === 'downloading') {
                speedBadge.style.display = 'inline-flex';
                speedBadge.textContent = this.formatSpeed(job.speed_bytes || 0);
            } else {
                speedBadge.style.display = 'none';
            }
        }

        const statusLabel = card.querySelector('.download-status-label');
        if (statusLabel) {
            statusLabel.className = `download-status-label status-text-${job.status}`;
            if (job.status === 'extracting') statusLabel.textContent = 'EXTRACTING ARCHIVE...';
            else if (job.status === 'completed') statusLabel.textContent = 'INSTALLED / READY';
            else statusLabel.textContent = `${job.status.toUpperCase()} (${percent}%)`;
        }

        const subtitle = card.querySelector('.download-subtitle');
        if (subtitle) {
            if (job.error_msg) {
                subtitle.innerHTML = `<span style="color: var(--danger);"><i class="fa-solid fa-circle-exclamation"></i> ${job.error_msg}</span>`;
            } else {
                subtitle.innerHTML = `${job.filename || 'Archive'} &bull; ${this.formatBytes(job.downloaded_bytes || 0)} / ${this.formatBytes(job.total_bytes || 0)}`;
            }
        }

        const eta = card.querySelector('.download-eta');
        if (eta) {
            eta.textContent = job.eta ? 'ETA: ' + job.eta : (job.error_msg ? 'Failed' : '');
        }

        const icon = card.querySelector('.download-icon');
        if (icon) {
            if (job.status === 'completed') {
                icon.className = 'fa-solid fa-circle-check download-icon';
                icon.style.color = 'var(--success)';
            } else if (job.status === 'extracting') {
                icon.className = 'fa-solid fa-box-archive fa-bounce download-icon';
            }
        }
    }

    async pauseJob(jobId) {
        try {
            await window.apiClient.pauseDownload(jobId);
        } catch (err) {
            window.uiController.showToast('Failed to pause download', 'danger');
        }
    }

    async resumeJob(jobId) {
        try {
            await window.apiClient.resumeDownload(jobId);
        } catch (err) {
            window.uiController.showToast('Failed to resume download', 'danger');
        }
    }

    async cancelJob(jobId) {
        try {
            await window.apiClient.cancelDownload(jobId);
            this.jobs.delete(jobId);
            this.renderQueue();
            window.uiController.showToast('Download cancelled', 'info');
        } catch (err) {
            window.uiController.showToast('Failed to cancel download', 'danger');
        }
    }

    async extractJob(jobId) {
        const job = this.jobs.get(jobId);
        if (!job || !job.dest_file) return;

        window.uiController.showToast('Starting extraction...', 'info');
        try {
            await window.apiClient.extractArchive({
                archive_path: job.dest_file,
                title: job.meta?.title
            });
        } catch (err) {
            window.uiController.showToast(`Extraction trigger failed: ${err.message}`, 'danger');
        }
    }

    async openFolder(folderPath) {
        if (!folderPath) return;
        if (window.api && window.api.openPath) {
            const res = await window.api.openPath(folderPath);
            if (res && res.error) {
                window.uiController.showToast(`Could not open folder: ${res.error}`, 'danger');
            }
        } else {
            window.uiController.showToast(`Game path: ${folderPath}`, 'info');
        }
    }

    formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    formatSpeed(bytesPerSec) {
        if (!bytesPerSec || bytesPerSec === 0) return '0 MB/s';
        if (this.speedUnit === 'Mbps') {
            const mbps = (bytesPerSec * 8) / (1024 * 1024);
            return `${mbps.toFixed(1)} Mbps`;
        }
        const mb = bytesPerSec / (1024 * 1024);
        return `${mb.toFixed(1)} MB/s`;
    }

    openExternalUrl(url) {
        if (!url) return;
        if (window.api && window.api.openExternal) {
            window.api.openExternal(url);
        } else {
            window.open(url, '_blank');
        }
    }
}

window.downloadController = new DownloadController();
