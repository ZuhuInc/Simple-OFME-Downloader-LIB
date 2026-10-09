/**
 * Fanta OFME API Client
 * Manages HTTP communication and Socket.IO real-time streams with the Python Bridge.
 */

const API_BASE = 'http://127.0.0.1:5004';

class ApiClient {
    constructor() {
        this.socket = null;
        this.connected = false;
        this.eventListeners = new Map();
        this.initSocket();
    }

    initSocket() {
        if (typeof io === 'undefined') {
            console.warn('[API] Socket.IO library not loaded in window');
            return;
        }

        this.socket = io(API_BASE, {
            transports: ['websocket', 'polling'],
            reconnectionAttempts: 10,
            reconnectionDelay: 1000
        });

        this.socket.on('connect', () => {
            console.log('[API] Connected to Python Bridge Socket.IO');
            this.connected = true;
            this.emitLocal('bridge_status', { connected: true });
        });

        this.socket.on('disconnect', () => {
            console.log('[API] Disconnected from Python Bridge Socket.IO');
            this.connected = false;
            this.emitLocal('bridge_status', { connected: false });
        });

        this.socket.on('download_progress', (data) => {
            this.emitLocal('download_progress', data);
        });

        this.socket.on('extraction_status', (data) => {
            this.emitLocal('extraction_status', data);
        });

        this.socket.on('version_check_progress', (data) => {
            this.emitLocal('version_check_progress', data);
        });
    }

    on(event, callback) {
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, []);
        }
        this.eventListeners.get(event).push(callback);
    }

    emitLocal(event, data) {
        const listeners = this.eventListeners.get(event) || [];
        listeners.forEach(cb => {
            try {
                cb(data);
            } catch (err) {
                console.error(`[API] Error in listener for ${event}:`, err);
            }
        });
    }

    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }

        try {
            const res = await fetch(url, config);
            if (!res.ok) {
                const errData = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(errData.error || `HTTP ${res.status}`);
            }
            return await res.json();
        } catch (err) {
            console.error(`[API] Request failed for ${endpoint}:`, err);
            throw err;
        }
    }

    // API Services
    getStatus() { return this.request('/api/status'); }
    getSettings() { return this.request('/api/settings'); }
    saveSettings(settings) { return this.request('/api/settings', { method: 'POST', body: settings }); }
    getBrowsers() { return this.request('/api/browsers'); }
    openExternalUrl(url) { return this.request('/api/open-url', { method: 'POST', body: { url } }); }

    // Games
    getGames(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`/api/games${query ? '?' + query : ''}`);
    }
    refreshGames() { return this.request('/api/games/refresh', { method: 'POST' }); }
    addGame(payload) { return this.request('/api/games/add', { method: 'POST', body: payload }); }
    scrapeGameInfo(payload) { return this.request('/api/games/scrape-info', { method: 'POST', body: payload }); }
    markGameStatus(payload) { return this.request('/api/games/mark-status', { method: 'POST', body: payload }); }
    removeGame(payload) { return this.request('/api/games/remove', { method: 'POST', body: payload }); }
    removeSteamLink(payload) { return this.request('/api/games/remove-steam', { method: 'POST', body: payload }); }

    // Downloads
    getDownloads() { return this.request('/api/downloads'); }
    addDownload(url, filename, meta = {}) {
        return this.request('/api/downloads/add', { method: 'POST', body: { url, filename, meta } });
    }
    pauseDownload(job_id) { return this.request('/api/downloads/pause', { method: 'POST', body: { job_id } }); }
    resumeDownload(job_id) { return this.request('/api/downloads/resume', { method: 'POST', body: { job_id } }); }
    cancelDownload(job_id) { return this.request('/api/downloads/cancel', { method: 'POST', body: { job_id } }); }
    extractArchive(payload) { return this.request('/api/extract', { method: 'POST', body: payload }); }

    // Steam
    getSteamLibraries() { return this.request('/api/steam/libraries'); }
    getSteamAccounts() { return this.request('/api/steam/accounts'); }
    selectSteamAccount(accountId) { return this.request('/api/steam/select-account', { method: 'POST', body: { account_id: accountId } }); }
    getSteamShortcuts(accountId = '') { return this.request(`/api/steam/shortcuts${accountId ? '?account_id=' + accountId : ''}`); }
    addSteamShortcut(data) { return this.request('/api/steam/shortcuts/add', { method: 'POST', body: data }); }
    deleteSteamShortcut(payload) { return this.request('/api/steam/shortcuts/delete', { method: 'POST', body: payload }); }
    rescanSteam() { return this.request('/api/steam/rescan', { method: 'POST' }); }
    restartSteam() { return this.request('/api/steam/restart', { method: 'POST' }); }

    // Version Checker
    getVersionCheckStatus() { return this.request('/api/version-check/status'); }
    scanVersions(options = {}) { return this.request('/api/version-check/scan', { method: 'POST', body: options }); }
    stopVersionScan() { return this.request('/api/version-check/stop', { method: 'POST' }); }
    saveVCCredentials(creds) { return this.request('/api/version-check/save-creds', { method: 'POST', body: creds }); }
    scrapeGameData(payload) { return this.request('/api/version-check/scrape-game', { method: 'POST', body: payload }); }
    applyGameData(payload) { return this.request('/api/version-check/apply-game-data', { method: 'POST', body: payload }); }
}

window.apiClient = new ApiClient();
