# CIMplicity (Backend Splunk App)

This package provides the backend logic for the CIMplicity AI Splunk App, including:
- AI-powered field extraction endpoint (Python, supports OpenRouter LLM and local fallback)
- PII detection and config generation support
- Splunk REST handler integration

## Setup
- Install dependencies as per the main repo instructions
- Configure your LLM API key in the Splunk app settings (see [main README](../../../../README.md))

## Usage
- The backend is called automatically by the UI for field extraction, PII detection, and config generation
- No direct user interaction required

## Privacy & LLM Usage
- Data sent to the AI endpoint may be forwarded to the configured LLM service for analysis
- For privacy-sensitive data, use the local fallback extraction or review your LLM provider's policy
