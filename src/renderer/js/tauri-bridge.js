/**
 * Tauri v2 Compatibility Bridge (`window.api` / `window.fantaAPI`)
 * Keeps existing renderer controllers working seamlessly under Tauri v2
 * without altering Electron's preload API surface.
 */
(function initTauriBridge() {
    if (window.api || !window.__TAURI__) {
        return;
    }

    const { core, event, window: tauriWindow } = window.__TAURI__;
    const invoke = core && typeof core.invoke === 'function'
        ? core.invoke.bind(core)
        : () => Promise.reject(new Error('Tauri core.invoke unavailable'));
    const listen = event && typeof event.listen === 'function'
        ? event.listen.bind(event)
        : () => Promise.resolve(() => {});

    function currentWin() {
        try {
            return tauriWindow && typeof tauriWindow.getCurrentWindow === 'function'
                ? tauriWindow.getCurrentWindow()
                : null;
        } catch {
            return null;
        }
    }

    function subscribeEvent(eventName, callback) {
        if (typeof callback !== 'function') return () => {};
        let unlistenFn = null;
        let cancelled = false;

        listen(eventName, (evt) => {
            callback(evt ? evt.payload : undefined);
        }).then((unlisten) => {
            if (cancelled) {
                unlisten();
            } else {
                unlistenFn = unlisten;
            }
        }).catch((err) => {
            console.warn(`[TauriBridge] Failed to subscribe to ${eventName}:`, err);
        });

        return () => {
            cancelled = true;
            if (typeof unlistenFn === 'function') {
                unlistenFn();
            }
        };
    }

    const exposed = {
        getAppVersion: () => invoke('get_app_version'),
        minimizeWindow: () => {
            const win = currentWin();
            if (win) win.minimize().catch((e) => console.warn('[TauriBridge] minimize error:', e));
        },
        maximizeWindow: () => {
            const win = currentWin();
            if (win) win.toggleMaximize().catch((e) => console.warn('[TauriBridge] maximize error:', e));
        },
        closeWindow: () => {
            invoke('close_app').catch(() => {
                const win = currentWin();
                if (win) win.close();
            });
        },
        selectDirectory: (defaultPath) => invoke('select_directory', { defaultPath: defaultPath || null }),
        selectFile: (options) => invoke('select_file', { options: options || null }),
        openPath: (targetPath) => invoke('open_path', { targetPath: targetPath || '' }),
        showItemInFolder: (itemPath) => invoke('show_item_in_folder', { itemPath: itemPath || '' }),
        openExternal: (url) => invoke('open_external', { url: url || '' }),
        onBackendLog: (callback) => subscribeEvent('backend-log', callback),
        getInitialLogs: () => invoke('get_initial_logs'),
        isSourceMode: () => invoke('is_source_mode'),
        isPortable: () => invoke('is_portable'),
        checkForUpdates: () => invoke('check_for_updates'),
        setBetaUpdates: (enabled) => invoke('set_beta_updates', { enabled: Boolean(enabled) }),
        startDownloadUpdate: () => invoke('start_download_update'),
        restartAndInstallUpdate: () => invoke('restart_and_install_update'),
        onUpdaterEvent: (callback) => subscribeEvent('updater-event', callback),
        showAchievementOverlay: (data) => {
            invoke('show_achievement_overlay', { data: data || {} }).catch((e) =>
                console.warn('[TauriBridge] showAchievementOverlay error:', e)
            );
        },
        hideAchievementOverlay: () => {
            invoke('hide_achievement_overlay').catch((e) =>
                console.warn('[TauriBridge] hideAchievementOverlay error:', e)
            );
        },
        onAchievementPopup: (callback) => subscribeEvent('achievement-popup', callback)
    };

    window.api = exposed;
    window.fantaAPI = exposed;
    window.electronAPI = exposed;

    function patchApiClientForRust() {
        const client = window.apiClient;
        if (!client || client._rustPatched) return;
        client._rustPatched = true;

        const origGetStatus = client.getStatus.bind(client);
        const origSaveSettings = client.saveSettings.bind(client);
        const origRefreshGames = client.refreshGames.bind(client);
        const origMarkGameStatus = client.markGameStatus.bind(client);
        const origRemoveGame = client.removeGame.bind(client);
        const origRemoveSteamLink = client.removeSteamLink.bind(client);

        client.getStatus = async () => {
            try {
                return await origGetStatus();
            } catch {
                return await invoke('rust_get_status');
            }
        };

        client.getSettings = () => invoke('rust_get_settings');

        client.saveSettings = async (settings) => {
            const res = await invoke('rust_save_settings', { settings: settings || {} });
            origSaveSettings(settings).catch(() => {});
            return res;
        };

        client.getGames = (params = {}) => invoke('rust_get_games', {
            params: {
                q: params.q || '',
                host: params.host || '',
                status: params.status || 'all',
                sort: params.sort || 'default',
                order: params.order || 'asc'
            }
        });

        client.refreshGames = async () => {
            const res = await invoke('rust_refresh_games');
            origRefreshGames().catch(() => {});
            return res;
        };

        client.markGameStatus = async (payload) => {
            try {
                return await origMarkGameStatus(payload);
            } catch {
                return await invoke('rust_mark_game_status', { payload: payload || {} });
            }
        };

        client.removeGame = async (payload) => {
            try {
                return await origRemoveGame(payload);
            } catch {
                return await invoke('rust_remove_game', { payload: payload || {} });
            }
        };

        client.removeSteamLink = async (payload) => {
            try {
                return await origRemoveSteamLink(payload);
            } catch {
                return await invoke('rust_remove_steam_link', { payload: payload || {} });
            }
        };
    }

    // Enable frameless titlebar drag & double-click maximize + Stage 4.1 Rust data bridge
    document.addEventListener('DOMContentLoaded', () => {
        patchApiClientForRust();

        const titlebar = document.querySelector('.titlebar');
        const win = currentWin();
        if (!titlebar || !win) return;

        titlebar.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            if (e.target.closest('button, a, input, select, textarea, .titlebar-controls, .no-drag')) return;
            win.startDragging().catch(() => {});
        });

        titlebar.addEventListener('dblclick', (e) => {
            if (e.target.closest('button, a, input, select, textarea, .titlebar-controls, .no-drag')) return;
            win.toggleMaximize().catch(() => {});
        });
    });
})();
