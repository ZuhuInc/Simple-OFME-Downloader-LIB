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
        }
    }

    handleExtractionUpdate(data) {
        if (data.status === 'extracting') {
            window.uiController.showToast(`Extracting: ${data.message || 'Please wait...'}`, 'info');
        } else if (data.status === 'success') {
            window.uiController.showToast(`Extraction complete! Saved to ${data.dest || 'folder'}`, 'success');
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

        div.innerHTML = `
            <div class="download-card-header">
                <div class="download-title-area">
                    <i class="fa-solid fa-cloud-arrow-down download-icon"></i>
                    <div>
                        <h4 class="download-title">${title}</h4>
                        <span class="download-subtitle">${job.filename || 'Archive'} &bull; ${downloadedFormatted} / ${totalFormatted}</span>
                    </div>
                </div>
                <div class="download-actions">
                    <span class="download-speed-badge">${speedFormatted}</span>
                    ${job.status === 'downloading' ? `
                        <button class="btn-icon" title="Pause" onclick="window.downloadController.pauseJob(${job.id})">
                            <i class="fa-solid fa-pause"></i>
                        </button>
                    ` : (job.status === 'paused' ? `
                        <button class="btn-icon" title="Resume" onclick="window.downloadController.resumeJob(${job.id})">
                            <i class="fa-solid fa-play"></i>
                        </button>
                    ` : '')}
                    ${job.status !== 'completed' ? `
                        <button class="btn-icon btn-icon-danger" title="Cancel" onclick="window.downloadController.cancelJob(${job.id})">
                            <i class="fa-solid fa-xmark"></i>
                        </button>
                    ` : `
                        <button class="btn btn-sm btn-primary" onclick="window.downloadController.extractJob(${job.id})">
                            <i class="fa-solid fa-file-zipper"></i> Extract
                        </button>
                    `}
                </div>
            </div>
            <div class="download-progress-bar">
                <div class="progress-bar-fill" style="width: ${percent}%;"></div>
            </div>
            <div class="download-card-footer">
                <span class="download-status-label status-text-${job.status}">${job.status.toUpperCase()} (${percent}%)</span>
                <span class="download-eta">${job.eta ? 'ETA: ' + job.eta : ''}</span>
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

        const percent = (job.progress || 0).toFixed(1);
        const fill = card.querySelector('.progress-bar-fill');
        if (fill) fill.style.width = `${percent}%`;

        const speedBadge = card.querySelector('.download-speed-badge');
        if (speedBadge) speedBadge.textContent = this.formatSpeed(job.speed_bytes || 0);

        const statusLabel = card.querySelector('.download-status-label');
        if (statusLabel) statusLabel.textContent = `${job.status.toUpperCase()} (${percent}%)`;

        const subtitle = card.querySelector('.download-subtitle');
        if (subtitle) {
            subtitle.innerHTML = `${job.filename || 'Archive'} &bull; ${this.formatBytes(job.downloaded_bytes || 0)} / ${this.formatBytes(job.total_bytes || 0)}`;
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

        window.uiController.showToast('Starting WinRAR extraction...', 'info');
        try {
            await window.apiClient.extractArchive({
                archive_path: job.dest_file,
                title: job.meta?.title
            });
        } catch (err) {
            window.uiController.showToast(`Extraction trigger failed: ${err.message}`, 'danger');
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
}

window.downloadController = new DownloadController();
