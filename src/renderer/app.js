/**
 * Fanta OFME Downloader - Main Renderer Entry
 * Bootstraps all modular controllers.
 */

document.addEventListener('DOMContentLoaded', () => {
    console.log('[Fanta OFME] Initializing frontend controllers...');

    // Initialize UI and Theme
    if (window.uiController) window.uiController.init();

    // Initialize Subsystem Controllers
    if (window.libraryController) window.libraryController.init();
    if (window.detailsController) window.detailsController.init();
    if (window.downloadController) window.downloadController.init();
    if (window.versionCheckerController) window.versionCheckerController.init();
    if (window.steamController) window.steamController.init();
    if (window.settingsController) window.settingsController.init();

    console.log('[Fanta OFME] All controllers initialized.');
});
