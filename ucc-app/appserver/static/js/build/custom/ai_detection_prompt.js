/*
 * The Prompts tab control for the "ai_detection" guidance.
 *
 * A one-liner per field because UCC does not pass the field name to a custom
 * control's constructor (see prompt_editor_base.js), so the prompt each control
 * edits has to be baked into which module the entity points at.
 */
import { makePromptEditor } from './prompt_editor_base.js';

export default makePromptEditor('ai_detection');
