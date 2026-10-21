/*
 * A prompt textarea with a "Restore to default" button, for the Configuration
 * page's Prompts tab.
 *
 * WHY THIS EXISTS. UCC's own textarea has no way back once you have edited it.
 * Saving writes to local/, and local overrides default, so clearing the box
 * writes an empty OVERRIDE: the app falls back to the shipped prompt (empty
 * means "use the default") but the box renders blank next time, which looks
 * like the prompt has been lost. The button puts the shipped text back in the
 * box so it can be read and edited again.
 *
 * THE CONTRACT, read out of the UCC bundle rather than guessed:
 *
 *   const c = new Control(globalConfig, el, data, setValue, utilCustomFunctions);
 *   c.render();
 *   if (typeof c.validation === 'function') addCustomValidator(field, c.validation);
 *
 * `el` is a plain <span>, so this is DOM work, not React. `data` is
 * { value, mode, serviceName }. `setValue(v)` writes the field's form value.
 *
 * NOTE the constructor is NOT given the field name, which is why this is a
 * factory and each field gets a one-line module naming its own prompt.
 *
 * The default text is FETCHED from /cim-plicity/prompt_defaults rather than
 * baked in here: a copy in this file would be a fourth one and would silently
 * drift from the prompt the app actually sends.
 */

const TEXTAREA_STYLE =
    'width:100%;box-sizing:border-box;font-family:monospace;font-size:12px;' +
    'line-height:1.45;padding:8px;border:1px solid #c3cbd4;border-radius:3px;' +
    'resize:vertical;';
const BUTTON_STYLE =
    'padding:4px 10px;font-size:12px;cursor:pointer;background:#f2f4f5;' +
    'border:1px solid #c3cbd4;border-radius:3px;';

export function makePromptEditor(promptName) {
    return class PromptEditor {
        constructor(globalConfig, el, data, setValue) {
            this.appName = (globalConfig && globalConfig.meta && globalConfig.meta.name)
                || 'cim-plicity';
            this.el = el;
            this.data = data || {};
            this.setValue = setValue;
            this.defaultText = null;
        }

        // Splunk serves this page under /<locale>/app/<app>/... and proxies
        // splunkd at /<locale>/splunkd/__raw/..., so take the locale from the
        // current path rather than assuming en-US.
        endpoint() {
            const parts = window.location.pathname.split('/').filter(Boolean);
            const locale = parts.length ? parts[0] : 'en-US';
            return '/' + locale + '/splunkd/__raw/services/'
                + this.appName + '/prompt_defaults?output_mode=json';
        }

        fetchDefault() {
            return fetch(this.endpoint(), {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then((r) => (r.ok ? r.json() : null))
                .then((doc) => ((doc && doc.defaults) || {})[promptName] || null)
                .catch(() => null);
        }

        render() {
            const wrapper = document.createElement('div');
            wrapper.style.width = '100%';

            const textarea = document.createElement('textarea');
            textarea.value = this.data.value == null ? '' : String(this.data.value);
            textarea.rows = 14;
            textarea.spellcheck = false;
            textarea.setAttribute('data-test', 'prompt-editor-textarea');
            textarea.setAttribute('data-prompt', promptName);
            textarea.style.cssText = TEXTAREA_STYLE;
            textarea.addEventListener('input', () => this.setValue(textarea.value));

            const bar = document.createElement('div');
            bar.style.cssText = 'margin-top:6px;display:flex;align-items:center;gap:10px;';

            const button = document.createElement('button');
            button.type = 'button';          // otherwise it submits the form
            button.textContent = 'Restore to default';
            button.setAttribute('data-test', 'prompt-editor-restore');
            button.setAttribute('data-prompt', promptName);
            button.style.cssText = BUTTON_STYLE;

            const note = document.createElement('span');
            note.setAttribute('data-test', 'prompt-editor-note');
            note.setAttribute('data-prompt', promptName);
            note.style.cssText = 'font-size:12px;color:#5c6773;';

            const apply = (text) => {
                if (!text) {
                    note.textContent = 'Could not load the shipped prompt.';
                    return;
                }
                this.defaultText = text;
                textarea.value = text;
                this.setValue(text);
                note.textContent = 'Restored. Save to keep it.';
            };

            button.addEventListener('click', () => {
                if (this.defaultText) {
                    apply(this.defaultText);
                    return;
                }
                note.textContent = 'Loading…';
                this.fetchDefault().then(apply);
            });

            bar.appendChild(button);
            bar.appendChild(note);
            wrapper.appendChild(textarea);
            wrapper.appendChild(bar);
            this.el.appendChild(wrapper);

            // Prefetch, so the first click is instant and a broken endpoint is
            // visible before anyone relies on the button.
            this.fetchDefault().then((text) => {
                this.defaultText = text;
                if (!text) {
                    note.textContent = 'Shipped prompt unavailable.';
                }
            });
        }
    };
}
