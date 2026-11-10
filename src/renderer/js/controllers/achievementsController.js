/**
 * Fanta OFME Downloader - Achievements Controller
 * Manages the Achievements dashboard, searches installed games, renders progress bars,
 * synthesizes the authentic Fanta soda can "crack & fizz" audio via Web Audio API,
 * and renders the middle-bottom animated bubble achievement toast.
 */

class AchievementsController {
    constructor() {
        this.games = [];
        this.selectedGame = null;
        this.selectedAchievements = [];
        this.activeFilter = 'all'; // all, unlocked, locked
        this.searchQuery = '';
        this.audioCtx = null;

        this.init();
    }

    init() {
        // Socket listener for real-time achievement pops
        if (window.apiClient) {
            window.apiClient.on('achievement_unlocked', (data) => {
                this.showAchievementToast(data);
                // If currently viewing this game, refresh its UI
                if (this.selectedGame && (this.selectedGame.title === data.game_title || this.selectedGame.appid === data.appid)) {
                    this.loadGameAchievements(this.selectedGame.title, this.selectedGame.appid);
                }
                // Refresh summary progress
                this.loadSummary(false);
            });
        }

        this.bindEvents();
    }

    bindEvents() {
        // Search games input
        const searchInput = document.getElementById('achievementSearchInput');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchQuery = e.target.value.toLowerCase().trim();
                this.renderGamesList();
            });
        }

        // Filter pills for achievements
        const filterPills = document.querySelectorAll('#achievementsFilterPills .filter-pill');
        filterPills.forEach(pill => {
            pill.addEventListener('click', () => {
                filterPills.forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                this.activeFilter = pill.getAttribute('data-filter') || 'all';
                this.renderAchievementsGrid();
            });
        });

        // Global Test Notification button
        const testBtn = document.getElementById('testAchievementToastBtn');
        if (testBtn) {
            testBtn.addEventListener('click', () => {
                this.triggerTestNotification();
            });
        }

        // Reset game unlocks button
        const resetBtn = document.getElementById('resetGameUnlocksBtn');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                this.resetCurrentGameUnlocks();
            });
        }
    }

    // -------------------------------------------------------------------------
    // Data Loading
    // -------------------------------------------------------------------------
    async loadSummary(selectFirst = true) {
        const listContainer = document.getElementById('achievementsGamesList');
        if (!listContainer) return;

        try {
            const res = await window.apiClient.getAchievementsSummary();
            if (res && res.success) {
                this.games = res.games || [];

                // Update summary stats
                const totalGamesEl = document.getElementById('achTotalGamesCount');
                const totalAchEl = document.getElementById('achTotalUnlockedCount');
                const overallPctEl = document.getElementById('achOverallPercentage');
                const overallBarEl = document.getElementById('achOverallProgressBar');

                if (totalGamesEl) totalGamesEl.textContent = res.total_games;
                if (totalAchEl) totalAchEl.textContent = `${res.total_unlocked} / ${res.total_achievements}`;
                if (overallPctEl) overallPctEl.textContent = `${res.overall_percentage}%`;
                if (overallBarEl) overallBarEl.style.width = `${res.overall_percentage}%`;

                this.renderGamesList();

                if (selectFirst && this.games.length > 0 && !this.selectedGame) {
                    this.selectGame(this.games[0]);
                }
            }
        } catch (err) {
            console.error('[Achievements] Failed to load summary:', err);
            listContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <p>Failed to load achievements data.</p>
                </div>
            `;
        }
    }

    renderGamesList() {
        const listContainer = document.getElementById('achievementsGamesList');
        if (!listContainer) return;

        const filtered = this.games.filter(g => {
            if (!this.searchQuery) return true;
            return g.title.toLowerCase().includes(this.searchQuery);
        });

        if (filtered.length === 0) {
            listContainer.innerHTML = `
                <div class="ach-no-games">
                    <i class="fa-solid fa-gamepad"></i>
                    <p>${this.searchQuery ? 'No matching installed games found.' : 'No installed games found in library.'}</p>
                </div>
            `;
            return;
        }

        listContainer.innerHTML = filtered.map(g => {
            const isSelected = this.selectedGame && this.selectedGame.title === g.title;
            const pct = g.percentage || 0;
            const thumb = g.thumbnail || 'assets/OFME-DWND-ICO.ico';

            return `
                <div class="ach-game-card ${isSelected ? 'active' : ''}" data-title="${encodeURIComponent(g.title)}" data-appid="${g.appid || ''}">
                    <img class="ach-game-thumb" src="${thumb}" alt="${g.title}" onerror="this.src='assets/OFME-DWND-ICO.ico'" />
                    <div class="ach-game-info">
                        <div class="ach-game-title" title="${g.title}">${g.title}</div>
                        <div class="ach-game-stats-row">
                            <span class="ach-stat-count"><i class="fa-solid fa-trophy"></i> ${g.unlocked_count} / ${g.total}</span>
                            <span class="ach-stat-pct">${pct}%</span>
                        </div>
                        <div class="ach-progress-track">
                            <div class="ach-progress-fill" style="width: ${pct}%"></div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // Attach click handlers
        listContainer.querySelectorAll('.ach-game-card').forEach(card => {
            card.addEventListener('click', () => {
                const title = decodeURIComponent(card.getAttribute('data-title'));
                const appid = card.getAttribute('data-appid');
                const game = this.games.find(g => g.title === title) || { title, appid };
                this.selectGame(game);
            });
        });
    }

    async selectGame(game) {
        this.selectedGame = game;
        this.renderGamesList(); // Update active highlight

        // Update details header
        const detailTitle = document.getElementById('achDetailTitle');
        const detailThumb = document.getElementById('achDetailThumb');
        const detailStats = document.getElementById('achDetailStats');
        const detailBar = document.getElementById('achDetailProgressBar');

        if (detailTitle) detailTitle.textContent = game.title;
        if (detailThumb) detailThumb.src = game.thumbnail || 'assets/OFME-DWND-ICO.ico';
        if (detailStats) detailStats.textContent = `${game.unlocked_count || 0} / ${game.total || 0} Unlocked (${game.percentage || 0}%)`;
        if (detailBar) detailBar.style.width = `${game.percentage || 0}%`;

        await this.loadGameAchievements(game.title, game.appid);
    }

    async loadGameAchievements(title, appid = '') {
        const gridContainer = document.getElementById('achievementsGrid');
        if (!gridContainer) return;

        gridContainer.innerHTML = `
            <div class="ach-loading-spinner">
                <i class="fa-solid fa-spinner fa-spin"></i>
                <p>Fetching official Steam achievements for ${title}...</p>
            </div>
        `;

        try {
            const res = await window.apiClient.getGameAchievements(title, appid);
            if (res && res.success && res.data) {
                this.selectedAchievements = res.data.achievements || [];

                // Update header counts
                const detailStats = document.getElementById('achDetailStats');
                const detailBar = document.getElementById('achDetailProgressBar');
                if (detailStats) detailStats.textContent = `${res.data.unlocked_count} / ${res.data.total} Unlocked (${res.data.percentage}%)`;
                if (detailBar) detailBar.style.width = `${res.data.percentage}%`;

                // Update filter pill counts
                const pillAll = document.querySelector('#achievementsFilterPills [data-filter="all"]');
                const pillUnlocked = document.querySelector('#achievementsFilterPills [data-filter="unlocked"]');
                const pillLocked = document.querySelector('#achievementsFilterPills [data-filter="locked"]');

                if (pillAll) pillAll.textContent = `ALL (${res.data.total})`;
                if (pillUnlocked) pillUnlocked.textContent = `UNLOCKED (${res.data.unlocked_count})`;
                if (pillLocked) pillLocked.textContent = `LOCKED (${res.data.total - res.data.unlocked_count})`;

                this.renderAchievementsGrid();
            } else {
                gridContainer.innerHTML = `
                    <div class="ach-empty-grid">
                        <i class="fa-solid fa-circle-question"></i>
                        <p>${res.data?.error || 'No achievements found for this game.'}</p>
                    </div>
                `;
            }
        } catch (err) {
            console.error('[Achievements] Error loading game achievements:', err);
            gridContainer.innerHTML = `
                <div class="ach-empty-grid">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <p>Failed to retrieve achievements from Steam: ${err.message}</p>
                </div>
            `;
        }
    }

    renderAchievementsGrid() {
        const gridContainer = document.getElementById('achievementsGrid');
        if (!gridContainer) return;

        let list = this.selectedAchievements;
        if (this.activeFilter === 'unlocked') {
            list = list.filter(a => a.unlocked);
        } else if (this.activeFilter === 'locked') {
            list = list.filter(a => !a.unlocked);
        }

        if (list.length === 0) {
            gridContainer.innerHTML = `
                <div class="ach-empty-grid">
                    <i class="fa-solid fa-trophy"></i>
                    <p>No achievements match the "${this.activeFilter.toUpperCase()}" filter.</p>
                </div>
            `;
            return;
        }

        gridContainer.innerHTML = list.map(a => {
            const isUnlocked = a.unlocked;
            const iconUrl = isUnlocked ? (a.icon || a.icon_gray) : (a.icon_gray || a.icon);
            const dateStr = a.unlocked_at ? new Date(a.unlocked_at * 1000).toLocaleDateString(undefined, {
                year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
            }) : null;

            return `
                <div class="ach-card ${isUnlocked ? 'unlocked' : 'locked'} glass-card">
                    <div class="ach-card-icon-wrapper">
                        <img class="ach-card-icon" src="${iconUrl}" alt="${a.name}" onerror="this.src='assets/OFME-DWND-ICO.ico'" />
                        ${isUnlocked ? '<span class="ach-unlocked-badge"><i class="fa-solid fa-check"></i></span>' : '<span class="ach-locked-badge"><i class="fa-solid fa-lock"></i></span>'}
                    </div>
                    <div class="ach-card-content">
                        <div class="ach-card-title">${a.name}</div>
                        <div class="ach-card-desc">${a.description || 'Hidden achievement.'}</div>
                        ${isUnlocked && dateStr ? `<div class="ach-card-date"><i class="fa-regular fa-clock"></i> Unlocked on ${dateStr}</div>` : ''}
                    </div>
                    <button class="ach-card-test-btn" title="Simulate Pop-up for this Achievement" data-apiname="${a.api_name}">
                        <i class="fa-solid fa-bell"></i>
                    </button>
                </div>
            `;
        }).join('');

        // Wire click handlers for individual test popups
        gridContainer.querySelectorAll('.ach-card-test-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const apiName = btn.getAttribute('data-apiname');
                this.triggerTestNotification(apiName);
            });
        });
    }

    // -------------------------------------------------------------------------
    // Testing & Resets
    // -------------------------------------------------------------------------
    async triggerTestNotification(apiName = null) {
        const title = this.selectedGame ? this.selectedGame.title : 'Fanta OFME';
        const appid = this.selectedGame ? this.selectedGame.appid : '252490';

        try {
            await window.apiClient.triggerTestUnlock({
                title,
                appid,
                api_name: apiName
            });
        } catch (err) {
            console.error('[Achievements] Failed to trigger test unlock:', err);
            // Fallback: trigger local toast anyway
            this.showAchievementToast({
                game_title: title,
                name: 'Pop The Top!',
                description: 'Cracked open a refreshing Fanta OFME achievement test.',
                icon: 'https://cdn.fastly.steamstatic.com/steamcommunity/public/images/apps/252490/8dde5848abac85e61a376bcadc2a6f267c909324.jpg'
            });
        }
    }

    async resetCurrentGameUnlocks() {
        if (!this.selectedGame) return;
        const confirmReset = confirm(`Are you sure you want to reset all unlocked achievements for "${this.selectedGame.title}"?`);
        if (!confirmReset) return;

        try {
            await window.apiClient.resetGameAchievements({
                title: this.selectedGame.title,
                appid: this.selectedGame.appid
            });
            await this.loadGameAchievements(this.selectedGame.title, this.selectedGame.appid);
            await this.loadSummary(false);
        } catch (err) {
            alert('Failed to reset unlocks: ' + err.message);
        }
    }

    // -------------------------------------------------------------------------
    // Audio Playback & Sound Synthesizer Fallback
    // -------------------------------------------------------------------------
    getAchievementSettings() {
        const s = window.settingsController?.settings || {};
        return {
            overlay_enabled: s.ach_overlay_enabled !== false,
            sound_enabled: s.ach_sound_enabled !== false,
            volume: s.ach_volume !== undefined ? Number(s.ach_volume) : 80,
            duration: Number(s.ach_duration) || 4500
        };
    }

    playSodaCanSound() {
        const { sound_enabled, volume } = this.getAchievementSettings();
        if (!sound_enabled) return;

        const vol = Math.max(0, Math.min(1, volume / 100));
        try {
            const audio = new Audio('assets/sodaCan.mp3');
            audio.volume = vol;
            audio.play().catch(e => {
                console.warn('[Achievements] Audio file playback fallback to synth:', e);
                this.playSynthSodaSound(vol);
            });
        } catch (e) {
            this.playSynthSodaSound(vol);
        }
    }

    playSynthSodaSound(volMultiplier = 0.8) {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;

            if (!this.audioCtx) {
                this.audioCtx = new AudioContext();
            }

            if (this.audioCtx.state === 'suspended') {
                this.audioCtx.resume();
            }

            const ctx = this.audioCtx;
            const now = ctx.currentTime;

            // 1. Initial Metallic Tab "Crack/Snap"
            const snapOsc = ctx.createOscillator();
            const snapGain = ctx.createGain();
            snapOsc.type = 'triangle';
            snapOsc.frequency.setValueAtTime(320, now);
            snapOsc.frequency.exponentialRampToValueAtTime(120, now + 0.06);

            snapGain.gain.setValueAtTime(0.7 * volMultiplier, now);
            snapGain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);

            snapOsc.connect(snapGain);
            snapGain.connect(ctx.destination);
            snapOsc.start(now);
            snapOsc.stop(now + 0.08);

            // 2. High-pressure Gas Release "Psssshh"
            const bufferSize = ctx.sampleRate * 0.4;
            const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
            const output = noiseBuffer.getChannelData(0);
            for (let i = 0; i < bufferSize; i++) {
                output[i] = Math.random() * 2 - 1;
            }

            const whiteNoise = ctx.createBufferSource();
            whiteNoise.buffer = noiseBuffer;

            const bandpass = ctx.createBiquadFilter();
            bandpass.type = 'bandpass';
            bandpass.frequency.setValueAtTime(2400, now);
            bandpass.Q.setValueAtTime(1.5, now);

            const hissGain = ctx.createGain();
            hissGain.gain.setValueAtTime(0.01, now);
            hissGain.gain.exponentialRampToValueAtTime(0.65 * volMultiplier, now + 0.02);
            hissGain.gain.exponentialRampToValueAtTime(0.001, now + 0.38);

            whiteNoise.connect(bandpass);
            bandpass.connect(hissGain);
            hissGain.connect(ctx.destination);
            whiteNoise.start(now + 0.01);

            // 3. Carbonated Refreshing Fizz Crackle Tail
            const fizzSize = ctx.sampleRate * 1.1;
            const fizzBuffer = ctx.createBuffer(1, fizzSize, ctx.sampleRate);
            const fizzData = fizzBuffer.getChannelData(0);
            for (let i = 0; i < fizzSize; i++) {
                fizzData[i] = (Math.random() > 0.88 ? (Math.random() * 2 - 1) : 0);
            }

            const fizzSource = ctx.createBufferSource();
            fizzSource.buffer = fizzBuffer;

            const highpass = ctx.createBiquadFilter();
            highpass.type = 'highpass';
            highpass.frequency.setValueAtTime(4500, now);

            const fizzGain = ctx.createGain();
            fizzGain.gain.setValueAtTime(0.01, now + 0.04);
            fizzGain.gain.exponentialRampToValueAtTime(0.4 * volMultiplier, now + 0.12);
            fizzGain.gain.exponentialRampToValueAtTime(0.0001, now + 1.1);

            fizzSource.connect(highpass);
            highpass.connect(fizzGain);
            fizzGain.connect(ctx.destination);
            fizzSource.start(now + 0.04);

        } catch (e) {
            console.warn('[Achievements] Audio synthesis skipped:', e);
        }
    }

    // -------------------------------------------------------------------------
    // Achievement Unlock Notifications (In-Game Desktop Overlay + Simple In-Menu Toast)
    // -------------------------------------------------------------------------
    showAchievementToast(data) {
        const settings = this.getAchievementSettings();

        // 1. Trigger native desktop overlay window (displays over fullscreen/windowed games)
        const api = window.api || window.fantaAPI;
        if (settings.overlay_enabled && api && typeof api.showAchievementOverlay === 'function') {
            api.showAchievementOverlay({
                ...data,
                sound_enabled: settings.sound_enabled,
                volume: settings.volume,
                duration: settings.duration
            });
        }

        // 2. Play the soda can crack sound
        this.playSodaCanSound();

        // 3. Simple in-app info notification in the bottom right (like download updates)
        if (window.uiController && typeof window.uiController.showToast === 'function') {
            const achName = data.name || data.api_name || 'Achievement Unlocked';
            const gameTitle = data.game_title ? ` (${data.game_title})` : '';
            window.uiController.showToast(
                `Achievement Unlocked: <strong>${achName}</strong>${gameTitle}`,
                'success',
                settings.duration
            );
        }
    }
}

window.achievementsController = new AchievementsController();

