# CIMplicity AI: Product Brief

## About the Idea

**CIMplicity AI** is an innovative Splunk App designed to dramatically simplify, accelerate, and secure the data onboarding process from inside Splunk Enterprise/Cloud as an application. It acts as an intelligent, wizard-like co-pilot, guiding users from raw log input through interactive field extraction, AI-assisted Common Information Model (CIM) mapping, and proactive PII (Personally Identifiable Information) detection.

**Core Goal:** Empower Splunk users of all skill levels to onboard new data sources quickly and accurately, ensuring the data is high-quality, CIM-compliant, and PII-aware before full ingestion. The app generates the necessary Splunk configurations (props.conf, transforms.conf) or even SPL2 ingestion (EP/IP) with ease.

This addresses the common pain points of time-consuming manual onboarding, complex CIM compliance, and the accidental ingestion of sensitive PII, thereby unlocking greater value from Splunk faster and more securely.

The app features a modern user interface built with [Splunk UI ReactJS components](https://splunkui.splunk.com/Packages/react-ui/Overview).

---

## MVP Feature-set

- **Intuitive Data Input:**
  - Paste or upload sample log data (JSON, CSV, Key-Value, basic unstructured)
  - Optionally select a preview of data from a selected Index/Sourcetype on their Splunk environment

- **Smart Field Extraction:**
  - Automatic parsing and field listing for structured data (JSON, CSV, Key-value pairs)
  - UI-driven regex assistance (e.g., highlighting text to define fields) for unstructured data

- **AI-Assisted CIM Mapping:**
  - User selects a target CIM data model
  - The app provides automatic suggestions (using fuzzy string matching, keyword analysis, and pattern recognition) for mapping extracted fields to standard CIM fields
  - Displays confidence scores for suggestions and allows user override/manual mapping

- **Proactive PII Guardian Module:**
  - Scans user-provided sample data or selected extracted fields using configurable regex patterns for common PII types (e.g., email, phone, illustrative SSN/CC patterns)
  - Visually flags fields potentially containing PII within the app’s UI

- **Configuration Generation:**
  - Automatically generates props.conf (for FIELDALIAS, EVAL, EXTRACT, KV_MODE, etc.) and transforms.conf (if complex regex used) snippets
  - Automatically generates SPL2 code to achieve the required mappings for use with Ingest/Edge processor
  - Easy output with simple next-steps for the user to make benefit of the app’s output

- **Modern UI Workflow:**
  - A step-by-step, guided experience built using the familiar Splunk UI ReactJS components

---

## Stretch Goal Feature-set

- **Integration with external LLM:**
  - Utilise OpenAI Chat Completions API to allow easy integration with local or external models using this API spec

- **AI Assisted field extraction:**
  - Offer a lightweight, local LLM model to determine potential field extractions based on the index/sourcetype and raw event example provided

- **Enhanced AI for CIM Mapping:**
  - Integrate a lightweight, local NLP model (e.g., SpaCy for Named Entity Recognition on field values to infer data types) to improve mapping suggestions

- **Advanced PII Detection:**
  - Option to use a local Python-based PII detection library (e.g., scrubadub) for more robust PII identification. Packaged with the app.

- **“Validate Configuration” Feature:**
  - Allow users to test the generated configurations against their sample data within the app, showing the CIM-normalized fields

- **“Redaction Impact Simulation” Panel:**
  - Display statistics like “X potential PII instances found in Y fields. Redacting these could impact Z events.”

- **Analyze Existing Sourcetypes:**
  - Ability to select an existing index/sourcetype to analyze its current CIM compliance and suggest improvements

---

## Constraints

- Components will leverage local processing (Python scripts, well-defined algorithms, and potentially lightweight local libraries) and will not solely rely on external large language models (LLMs) or cloud-based AI services—offering this as a capability if desired, ensuring data privacy and feasibility.
- PII detection in the MVP will be regex-based and primarily for awareness; it’s not a guaranteed redaction or compliance solution on its own.
- Initial focus on common log formats like JSON, key-value pairs, and basic unstructured text.
- Development time is limited by the hackathon timeframe, prioritizing a functional MVP.
- This could potentially be created as an external application with ties in to Splunk to pull in sample logs, thus being more readily available to more users. However, the initial MVP of the solution will be developed as an application to be installed within a Splunk environment.
