# CIMplicity AI: Problem Solved & Integration Overview

## The Problem

Onboarding new data sources into Splunk is a critical but often complex and time-consuming process. Users face several challenges:

- **Manual Field Extraction:** Identifying and extracting fields from raw log data (JSON, CSV, key-value, or unstructured text) typically requires regex expertise and trial-and-error.
- **CIM Compliance:** Mapping extracted fields to Splunk’s Common Information Model (CIM) is tedious, error-prone, and requires deep knowledge of Splunk data models.
- **PII Risk:** Sensitive data (PII) can be accidentally indexed, creating compliance and privacy risks.
- **Configuration Complexity:** Generating the correct props.conf, transforms.conf, or SPL2 for Ingest/Edge Processors is a barrier for many users.
- **Slow Time-to-Value:** These hurdles delay the ability to search, alert, and visualize new data in Splunk.

**CIMplicity AI** addresses these pain points by providing an intelligent, guided workflow that automates and simplifies every step of the onboarding process.

---

## Target Users

- **Splunk Administrators:** Responsible for onboarding and normalizing new data sources.
- **Security & Compliance Teams:** Need to ensure PII is detected and redacted before indexing.
- **Data Engineers & Analysts:** Want high-quality, CIM-compliant data for dashboards and alerts.
- **Splunk Power Users:** Looking to accelerate onboarding and reduce manual effort.
- **Organizations with strict data privacy requirements.**

---

## Integration with Splunk

- **App-Based:** CIMplicity AI is installed as a Splunk app (compatible with Splunk Enterprise and Cloud).
- **Modern UI:** The frontend is built entirely with [Splunk ReactUI](https://splunkui.splunk.com/Packages/react-ui/Overview), ensuring a native, accessible, and responsive user experience.
- **Step-by-Step Workflow:** Users are guided through data input, field extraction, CIM mapping, PII detection, and configuration generation.
- **Backend Integration:** Python scripts handle field extraction, PII detection (using [scrubadub](https://github.com/datasnakes/scrubadub)), and AI-assisted mapping using external or local LLM services (configurable).
- **Config Output:** Generates ready-to-use Splunk configuration (props.conf) and SPL2 for Ingest/Edge Processors.
- **Direct Copy/Download:** Users can copy or download config snippets for immediate use in their Splunk environment.

---

## Key Features & Workflow

- **Data Input:** Paste, upload, or preview sample log data from Splunk.
- **Automatic Field Extraction:** Detects fields in structured and unstructured data.
- **Regex Assistance:** UI-driven regex builder for custom extractions.
- **AI-Assisted CIM Mapping:** Suggests CIM field mappings with confidence scores.
- **Proactive PII Detection:** Scans for PII using configurable patterns and custom rules.
- **Redaction Simulation:** Shows potential impact of redaction before applying.
- **Configuration Generation:** Outputs Splunk config and SPL2 for immediate deployment.
- **Modern, Accessible UI:** Built with Splunk ReactUI for seamless integration and user experience.

---

## Summary

CIMplicity AI transforms Splunk data onboarding from a manual, error-prone process into a fast, guided, and secure workflow. By combining automation, AI, and a modern Splunk ReactUI interface, it empowers users to get value from their data faster—while reducing risk and complexity. 