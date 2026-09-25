/**
 * Steam Controller
 * Manages Steam library scanning, profile detection, and shortcut creation dialogs.
 */

class SteamController {
    constructor() {
        this.steamPath = '';
        this.libraries = [];
        this.accounts = [];
        this.modal = document.getElementById('steamShortcutModal');
        this.activeGame = null;
    }

    init() {
        this.bindEvents();
        this.loadSteamInfo();
    }

    bindEvents() {
        const closeBtn = document.getElementById('closeSteamModalBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeModal());
        }

        const confirmBtn = document.getElementById('confirmAddSteamBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => this.confirmAddShortcut());
        }

        const browseBtn = document.getElementById('browseSteamExeBtn');
        if (browseBtn) {
            browseBtn.addEventListener('click', async () => {
                const file = await window.api?.selectFile({
                    filters: [{ name: 'Game Executable', extensions: ['exe'] }]
                });
                const exeInput = document.getElementById('steamGameExeInput');
                if (file && exeInput) exeInput.value = file;
            });
        }
    }

    async loadSteamInfo() {
        try {
            const data = await window.apiClient.getSteamLibraries();
            this.steamPath = data.steam_path;
            this.libraries = data.libraries || [];
            
            const accData = await window.apiClient.getSteamAccounts();
            this.accounts = accData.accounts || [];
        } catch (err) {
            console.error('[SteamController] Failed to load steam info:', err);
        }
    }

    openAddShortcutDialog(game) {
        this.activeGame = game;
        if (!this.modal) return;

        const titleEl = document.getElementById('steamModalGameTitle');
        if (titleEl) titleEl.textContent = game.title;

        const exeInput = document.getElementById('steamGameExeInput');
        if (exeInput) exeInput.value = '';

        this.modal.classList.add('active');
    }

    closeModal() {
        if (this.modal) this.modal.classList.remove('active');
        this.activeGame = null;
    }

    async confirmAddShortcut() {
        if (!this.activeGame) return;
        const exePath = document.getElementById('steamGameExeInput')?.value || '';
        if (!exePath) {
            window.uiController.showToast('Please specify or browse the game executable (.exe) path.', 'warning');
            return;
        }

        try {
            const res = await window.apiClient.addSteamShortcut({
                name: this.activeGame.title,
                exe_path: exePath,
                icon_path: this.activeGame.thumbnail || ''
            });

            if (res.success) {
                window.uiController.showToast(`${this.activeGame.title} added to Steam shortcuts!`, 'success');
                this.closeModal();
            } else {
                window.uiController.showToast(res.message || 'Failed to add shortcut', 'danger');
            }
        } catch (err) {
            window.uiController.showToast(`Error adding shortcut: ${err.message}`, 'danger');
        }
    }
}

window.steamController = new SteamController();
