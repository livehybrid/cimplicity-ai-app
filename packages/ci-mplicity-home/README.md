# CIMplicity Home (Splunk App UI)

This package provides the main React UI for the CIMplicity AI Splunk App, enabling wizard-driven onboarding of new data sources with AI-powered field extraction, CIM mapping, PII detection, and config generation.

## Key Features
- Paste/upload/select log data for onboarding
- AI-powered field extraction (with editable regexes, live preview, and context input)
- CIM mapping (auto/manual)
- PII detection (grouped by type, unique values)
- Configuration generation (props.conf, transforms.conf, SPL2)
- Modern Splunk React UI, step-by-step workflow

## Quick Start
1. Install dependencies (from repo root):
   ```sh
   yarn run setup
   ```
2. Start the UI (from this directory):
   ```sh
   yarn start
   ```
3. Configure your LLM API key in the Splunk app settings (see main README).

## Usage
- Follow the wizard: Data Input → Field Extraction → CIM Mapping → PII Detection → Config Generation
- See the [main README](../../../../README.md) for full documentation, privacy notes, and workflow details.

## Privacy & LLM Usage
- Your data and any provided description will be sent to the configured LLM service for analysis.
- For privacy-sensitive data, use the local fallback extraction or review your LLM provider's policy.

---

## Migration & Feature Log

### 2024-06-01
- Migrated to three-column layout using Splunk ReactUI's ColumnLayout
- Data Input, Field Extraction, CIM Mapping, PII Detection, and Config Generation steps implemented
- AI field extraction, regex editing, and live preview added
- PII detection grouped by type, unique values, and ignore-list for non-PII types
- Config generation for props.conf, transforms.conf, SPL2
- All changes now tracked in this README for future reference
