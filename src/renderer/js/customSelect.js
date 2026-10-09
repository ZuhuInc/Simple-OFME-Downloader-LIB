/**
 * Custom 1:1 Glass Dropdown Component
 * Replaces native OS <select> popups with fully styled dark-glass dropdowns
 * while keeping 2-way event and state synchronization with underlying native <select> elements.
 */

class CustomSelect {
    constructor(selectElement) {
        this.select = selectElement;
        this.wrapper = null;
        this.trigger = null;
        this.triggerText = null;
        this.menu = null;
        this.observer = null;

        this.init();
    }

    init() {
        if (this.select._customSelectInstance) {
            return;
        }
        this.select._customSelectInstance = this;

        // Create custom wrapper
        this.wrapper = document.createElement('div');
        this.wrapper.className = 'custom-select-wrapper';
        
        // Copy relevant inline styles or classes (e.g. min-width, width)
        if (this.select.style.minWidth) this.wrapper.style.minWidth = this.select.style.minWidth;
        if (this.select.style.width) this.wrapper.style.width = this.select.style.width;

        // Trigger Button
        this.trigger = document.createElement('div');
        this.trigger.className = 'custom-select-trigger';
        this.trigger.tabIndex = 0;

        this.triggerText = document.createElement('span');
        this.triggerText.className = 'custom-select-text';

        const arrow = document.createElement('i');
        arrow.className = 'fa-solid fa-chevron-down custom-select-arrow';

        this.trigger.appendChild(this.triggerText);
        this.trigger.appendChild(arrow);

        // Menu Container
        this.menu = document.createElement('div');
        this.menu.className = 'custom-select-menu custom-scroll';

        this.wrapper.appendChild(this.trigger);
        this.wrapper.appendChild(this.menu);

        // Hide native select visually but keep in DOM for change listeners & forms
        this.select.classList.add('custom-select-native-hidden');
        this.select.parentNode.insertBefore(this.wrapper, this.select.nextSibling);

        // Build options
        this.renderOptions();

        // Event Listeners
        this.bindEvents();

        // Observe DOM changes on native select (e.g. dynamic option additions)
        this.observer = new MutationObserver(() => {
            this.renderOptions();
        });
        this.observer.observe(this.select, { childList: true, subtree: true, attributes: true, attributeFilter: ['value'] });
    }

    renderOptions() {
        this.menu.innerHTML = '';
        const options = Array.from(this.select.options);
        const selectedIndex = this.select.selectedIndex >= 0 ? this.select.selectedIndex : 0;
        const selectedOption = options[selectedIndex] || options[0];

        this.triggerText.textContent = selectedOption ? selectedOption.text : 'Select...';

        options.forEach((opt, idx) => {
            const item = document.createElement('div');
            item.className = `custom-select-option ${idx === selectedIndex ? 'selected' : ''}`;
            item.dataset.value = opt.value;

            const textSpan = document.createElement('span');
            textSpan.className = 'custom-select-option-text';
            textSpan.textContent = opt.text;

            const checkIcon = document.createElement('i');
            checkIcon.className = 'fa-solid fa-check custom-select-option-check';

            item.appendChild(textSpan);
            item.appendChild(checkIcon);

            item.addEventListener('click', (e) => {
                e.stopPropagation();
                this.selectValue(opt.value);
                this.close();
            });

            this.menu.appendChild(item);
        });
    }

    selectValue(value) {
        if (this.select.value === value) {
            this.updateSelectedState();
            return;
        }

        this.select.value = value;
        this.updateSelectedState();

        // Dispatch native change event
        const event = new Event('change', { bubbles: true });
        this.select.dispatchEvent(event);
    }

    updateSelectedState() {
        const selectedIndex = this.select.selectedIndex >= 0 ? this.select.selectedIndex : 0;
        const selectedOption = this.select.options[selectedIndex];

        this.triggerText.textContent = selectedOption ? selectedOption.text : 'Select...';

        const items = this.menu.querySelectorAll('.custom-select-option');
        items.forEach((item, idx) => {
            item.classList.toggle('selected', idx === selectedIndex);
        });
    }

    bindEvents() {
        // Toggle menu on trigger click
        this.trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            if (this.wrapper.classList.contains('open')) {
                this.close();
            } else {
                CustomSelect.closeAll();
                this.open();
            }
        });

        // Keyboard navigation
        this.trigger.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
                e.preventDefault();
                this.open();
            } else if (e.key === 'Escape') {
                this.close();
            }
        });

        // Intercept programmatic .value assignments
        const desc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
        if (desc && desc.set) {
            const self = this;
            try {
                Object.defineProperty(this.select, 'value', {
                    get() {
                        return desc.get.call(this);
                    },
                    set(val) {
                        desc.set.call(this, val);
                        self.updateSelectedState();
                    },
                    configurable: true
                });
            } catch (e) {}
        }

        // Sync when native select changes programmatically
        this.select.addEventListener('change', () => {
            this.updateSelectedState();
        });
    }

    open() {
        this.wrapper.classList.add('open');
        const parentCard = this.wrapper.closest('.glass-card, .library-header, .form-row, .modal-dialog, .steam-profile-card');
        if (parentCard) {
            parentCard.classList.add('custom-select-active-parent');
        }
    }

    close() {
        this.wrapper.classList.remove('open');
        const parentCard = this.wrapper.closest('.glass-card, .library-header, .form-row, .modal-dialog, .steam-profile-card');
        if (parentCard) {
            parentCard.classList.remove('custom-select-active-parent');
        }
    }

    static closeAll() {
        document.querySelectorAll('.custom-select-wrapper.open').forEach(w => w.classList.remove('open'));
        document.querySelectorAll('.custom-select-active-parent').forEach(p => p.classList.remove('custom-select-active-parent'));
    }

    static initAll(root = document) {
        const selects = root.querySelectorAll('select.select-dropdown, select.form-select, select#steamAccountSelect, select#assistedHostSelect, select#set_speed_unit, select#hostFilterSelect, select#sortFilterSelect');
        selects.forEach(select => {
            if (!select.classList.contains('custom-select-native-hidden')) {
                new CustomSelect(select);
            } else if (select._customSelectInstance) {
                select._customSelectInstance.renderOptions();
            }
        });
    }
}

// Global outside-click closer
document.addEventListener('click', () => {
    CustomSelect.closeAll();
});

// Auto initialize on DOMContentLoaded
if (typeof window !== 'undefined') {
    window.CustomSelect = CustomSelect;
}
