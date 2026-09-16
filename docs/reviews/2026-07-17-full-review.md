# CIMPlicity AI: full app review, 17-18 July 2026

Review of `cimplicity-ai-app` (branch `feat/dynamic-cim-field-loading`) against the current
`splunk-react-app` skill baseline and the newest `ucc-app-builder` learnings (MCP tool
registration via `tools.conf` + instance-aware `autoregister.py`, AppInspect Cloud vetting
gates). Conducted with a multi-agent workflow: 6 dimension reviewers plus an MCP designer,
every finding adversarially verified, then a completeness critic, then 4 parallel fix agents
and a validation pass.

**Nothing is committed.** All changes are in the working tree (deletions and moves staged
via git rm/git mv). Review before committing.

## Executive summary

- **110 findings confirmed** after adversarial verification (2 refuted), across backend REST,
  frontend React, UCC/CI/packaging, security, the feature branch and docs.
- **90 fix-now items actioned** (87 agent actions plus 4 residual handoffs closed manually).
  12 stage-spec items are specified below but deliberately not applied; 8 deferred.
- **Headline defects found and fixed:**
  - CI was broken: unpinned ucc-gen 6.x crashes purging transitive numpy pulled by unpinned
    scrubadub. Pinned ucc-gen 5.69.1 + scrubadub 2.0.1; local build now completes.
  - The branch's headline feature never activated: `load_cim_models.py` read a non-existent
    `Splunk_SA_CIM` path. Now reads `default/data/models` (with `local` override), lazily,
    with the built-in fallback retained.
  - OpenRouter API key was logged in plaintext to an indexed log; LLM responses and settings
    objects also logged. All removed.
  - `print()` calls inside the persistent-REST process corrupted the persistconn stdout
    packet protocol. Removed.
  - XSS: raw event data and LLM output injected via `dangerouslySetInnerHTML`. Now escaped.
  - The shipped page bundle was a 13.3 MB webpack development build. Now production mode:
    1.61 MB minified.
  - A stray CPython profiler binary (`_lsprof*.so`) and vendored `typing_extensions` were
    tracked and shipped; removed along with the stale AppInspect waiver for it.
- **New capability added: Splunk MCP tools.** `default/tools.conf` registers 4 tools
  (`cim_plicity_ping`, `ai_detection`, `pii_detection`, `cim_mapping`) with agent-teaching
  descriptions; `bin/autoregister.py` (ported from ucc-app-builder) self-registers them into
  the Splunk MCP Server KV on Enterprise and no-ops on Cloud; CI patches
  `reload.tools = http_post /cim-plicity/autoregister` into app.conf. Documented in
  `docs/MCP_TOOLS.md`. This is the foundation for the planned UCC App Builder integration.

## Validation status

- `pytest tests/` green (tests moved out of `ucc-app/bin/`, fixture now mirrors the real
  Splunk_SA_CIM layout, assertion-free tests given real assertions).
- Jest suites repaired and green; `ci-mplicity-home` and `cim-plicity` webpack builds green
  (only acceptable error locally: missing UCC output glob, produced by CI's ucc-gen step).
- `ucc-gen 5.69.1 build` completes with a full tree: MCP stanzas, `tools.conf`, no test
  files, no stray binaries, no `.pytest_cache` in the package.
- `splunk-appinspect` locally: the full 81 MB package OOM-kills this host's Python analyzer
  (355 MB vendored dependency tree). A reduced-scope run on a lib-pruned copy covers the
  areas the fixes touched; the authoritative full precert is the CI `quality-appinspect`
  and `quality-appinspect-api` (SLIM) jobs, which run on push.
- Reduced-scope AppInspect result (app code, conf, manifest, UI assets; vendored libs
  stripped): **0 failures, 0 errors**, 113 success, 7 warnings, 2 future-tag failures.
  The future-tag items (Splunk 10.2 `python.required` deprecation of `python.version`)
  and the `tools.conf` SHC replication warning were fixed on the spot: `python.required
  = 3.9,3.13` added to all six restmap python stanzas, new `default/server.conf` with
  `conf_replication_include.tools = true`, and the sample private IP in
  `pii_detection_standalone.py` moved to the TEST-NET range. Remaining warnings are
  pre-existing or informational (SplunkJS telemetry, UCC-generated header view, the
  skill-mandated Mako view template, `check_for_updates` true which is correct for a
  Splunkbase app).

## Actions taken

### Group A: backend REST and conf (26 actions)

- **[DONE]** restmap.conf handler module names wrong (application.AiDetection / application.PiiDetection)
  - Files: `ucc-app/default/restmap.conf`
  - Changed handler lines to ai_detection.AiDetection and pii_detection.PiiDetection (stanza names and match paths untouched; staged MCP stanzas preserved).
  - Verified: git diff HEAD shows only the two handler= lines changed in the pre-existing stanzas; each bin module still contains exactly one PersistentServerConnectionApplication subclass so persistconn auto-discovery stays valid.
- **[DONE]** web.conf has no [expose:cim_mapping]; splunkweb-proxied calls 404
  - Files: `ucc-app/default/web.conf`
  - Added [expose:cim_mapping] pattern=cim_mapping methods=POST with an explanatory comment, mirroring the sibling endpoints.
  - Verified: git diff HEAD on web.conf shows the additive stanza; pattern matches restmap [script:cim_mapping] match=/cim_mapping.
- **[PARTIAL]** Compiled binary _lsprof.cpython-39-x86_64-linux-gnu.so shipped in bin/ (AppInspect risk)
  - Files: `ucc-app/bin/_lsprof.cpython-39-x86_64-linux-gnu.so`
  - The stray .so is deleted (staged git rm). The belt-and-braces CI packaging exclusion for bin/*.so was NOT added because .github/workflows/splunk-app-ci.yml is outside this group's scope; recorded as handoff.
  - Verified: git status shows 'D ucc-app/bin/_lsprof...so'; git ls-files ucc-app/bin now lists only the five production .py files.
- **[DONE]** print() calls in lib/pii_detection_logic.py corrupt the persistconn stdout protocol
  - Files: `ucc-app/lib/pii_detection_logic.py`
  - All print() calls removed; the adjacent logging.* calls remain (load_detectors, detect paths).
  - Verified: grep 'print(' over ucc-app/lib and the four production bin handlers returns nothing; pytest suite (which imports the module under scrubadub) passes.
- **[DONE]** OpenRouter API key written to log in plaintext (ai_detection.py:112, duplicate security-critical finding)
  - Files: `ucc-app/bin/ai_detection.py`
  - Removed the API-key log line and the conf-object dumps at old lines 62/121; get_ai_secret now returns the key without logging it and settings reads log only errors.
  - Verified: grep -n api_key ucc-app/bin/*.py piped through grep -i log returns nothing; no logging call anywhere includes the credential.
- **[DONE]** ai_detection.handle parses input/auth outside try; malformed input or missing session key crashes; misleading KeyError
  - Files: `ucc-app/bin/ai_detection.py`
  - handle() now: try/except around json.loads(in_string) returning 400 structured JSON; explicit 401 JSON when system_authtoken missing (mirrors cim_mapping.py); separate 400 for malformed inner payload; the misleading blanket 'except KeyError' removed in favour of an explicit no-text 400 check.
  - Verified: Behaviour test under python3.9 with stubbed splunk modules: handle('not json') returns status 400, handle without system_authtoken returns status 401.
- **[DONE]** pii_detection returns 400 'Malformed input' when session key missing instead of 401
  - Files: `ucc-app/bin/pii_detection.py`
  - Split the checks: JSON parse failure gives 400, non-dict input gives 400, missing system_authtoken gives 401 {'error': 'No session key provided'}, malformed inner payload gives 400.
  - Verified: Code review of pii_detection.py:98-123 shows the distinct paths; py_compile and 3.9 ast check pass.
- **[DONE]** load_cim_models reads wrong Splunk_SA_CIM directory + comment-object mis-parse (covers both duplicate findings)
  - Files: `ucc-app/bin/load_cim_models.py`
  - models_dir now iterates default/data/models then local/data/models (local overrides per file, matching real Splunk_SA_CIM layout per verifyNotes); _parse_model_file unwraps {'comment': {'description': ...}} dicts with fallback to description/displayName/fieldName; calculations outputFields captured; whole load wrapped so it never raises and returns the built-in fallback models.
  - Verified: python3 -m pytest tests/test_load_cim_models.py: fixtures mirror the real default/data/models layout with comment objects and underscore modelNames; discovery, dedup, local-override and fallback tests all pass.
- **[DONE]** ai_detection.call_openrouter fallback broken: account_conf_file undefined, bare except, dead default model
  - Files: `ucc-app/bin/ai_detection.py`
  - Added get_ai_settings() helper (single ConfManager read returning {} on failure, except Exception with logging); call_openrouter binds api_endpoint and model from it with explicit working defaults before requests.post; no bare except remains; get_ai_secret reuses the same helper.
  - Verified: py_compile + 3.9 ast check; code path inspection confirms no undefined-name path (settings read failure yields {} and the defaults apply).
- **[DONE]** normalize_ai_response elif chain discards time_prefix / max_timestamp_lookahead when time_format present
  - Files: `ucc-app/bin/ai_detection.py`
  - The three flat timestamp keys are now independent ifs; the nested timestamp_analysis branch remains as a fallback and only fills keys absent from the flat response.
  - Verified: Behaviour test: flat {'time_format','time_prefix','max_timestamp_lookahead'} all preserved; nested timestamp_analysis-only response still normalises correctly.
- **[DONE]** generate_combined_regex silently degenerates to re.escape of the whole sample (PCRE (?<name>) rejected by Python re)
  - Files: `ucc-app/bin/ai_detection.py`
  - Positioning now translates (?< to (?P< via re.sub(r'\(\?<(?![=!])', ...) so lookbehinds are untouched; re.error per field is logged (field name only) instead of bare except:continue; when no field can be positioned it logs and returns None instead of an escaped-literal pattern.
  - Verified: Behaviour test under 3.9: PCRE-named-group field regexes produce a combined pattern whose named groups match the sample; unpositionable fields return None; a lookbehind-containing regex still positions.
- **[DONE]** Unused splunklib client.connect per request with spurious 500 failure mode
  - Files: `ucc-app/bin/ai_detection.py`
  - Removed the client.connect block, self.service and the splunklib.client import.
  - Verified: grep confirms no splunklib or self.service reference remains in ai_detection.py; behaviour test exercises handle() end-to-end without it.
- **[DONE]** Shipped log_level=DEBUG + handlers hardcode root DEBUG, logging tab decorative (covers both duplicate findings)
  - Files: `ucc-app/default/cim-plicity_settings.conf, ucc-app/bin/ai_detection.py, ucc-app/bin/pii_detection.py, ucc-app/bin/cim_mapping.py`
  - cim-plicity_settings.conf ships log_level = INFO; basicConfig defaults changed to INFO; each handler gained apply_log_level() reading the [logging] stanza via conf_manager at request time (after auth), falling back to INFO, so the UCC logging tab is now effective.
  - Verified: git diff shows DEBUG->INFO in the conf; grep confirms no level=logging.DEBUG remains; py_compile passes on all three handlers.
- **[DONE]** Dead imports and stale sys.path entries across all three handlers
  - Files: `ucc-app/bin/ai_detection.py, ucc-app/bin/pii_detection.py, ucc-app/bin/cim_mapping.py`
  - Removed Setup_Util, b64encode, splunk.entity, splunk.Intersplunk, splunklib.client/results imports, the duplicate 'import logging' and the nonexistent ../lib/3rdparty/linux_lib_py39 sys.path insert; import blocks now match actual usage.
  - Verified: grep for the removed names returns nothing; py_compile and the stub-import behaviour test confirm the modules import with only the remaining dependencies.
- **[DONE]** PII test files cannot fail: assertion-free tests, wrong file-structure paths, scrubadub path untested, f.start/f.end bug in standalone module
  - Files: `tests/test_pii_logic.py, tests/test_pii_simple.py, tests/test_pii_standalone.py, ucc-app/bin/pii_detection_standalone.py`
  - Rewrote all three PII test files with real assertions: test_pii_logic.py uses pytest.importorskip('scrubadub') and exercises the real detection path (email+IP with the shipped settings-default detector list, custom IP detector, custom patterns, invalid-regex resilience, no-PII case); test_pii_simple.py tests IpAddressDetector (beg/end positions) and the SEDCMD helpers; test_pii_standalone.py asserts exact regex matches and probes the real ucc-app
  - Verified: Without scrubadub: 9 passed, 2 skipped (module-level importorskip), zero PytestReturnNotNoneWarning. With scrubadub==2.0.1 in a scratch venv: 19 passed. grep confirms f.beg/f.end in pii_detection_standalone.py.
- **[DONE]** LLM responses / user-derived content logged to _internal (ai_detection content dump, cim_mapping response dump, pii custom_patterns verbatim)
  - Files: `ucc-app/bin/ai_detection.py, ucc-app/bin/cim_mapping.py, ucc-app/bin/pii_detection.py`
  - ai_detection and cim_mapping now log only response length at INFO (cim_mapping keeps undecodable content at DEBUG only); pii_detection logs custom-pattern count instead of the patterns; the existing length+sha256 masking for analysed text retained.
  - Verified: grep over bin/ shows no logging of content/response bodies at INFO; only len(content) metadata.
- **[DONE]** cim_mapping hardcodes openrouter.ai endpoint and model, ignoring configured api_endpoint
  - Files: `ucc-app/bin/cim_mapping.py`
  - call_openrouter reads api_endpoint and model from the ai_configuration stanza via the same get_ai_settings() pattern as ai_detection.py, with the shipped defaults (same URL/model) as fallback so default installs are behaviour-identical.
  - Verified: Code inspection: requests.post(url=api_endpoint, ... model) with defaults matching ucc-app/default/cim-plicity_settings.conf:2-3; py_compile passes.
- **[DONE]** Internal exception details returned to clients in 500 responses
  - Files: `ucc-app/bin/ai_detection.py, ucc-app/bin/pii_detection.py, ucc-app/bin/cim_mapping.py, ucc-app/lib/pii_detection_logic.py`
  - All 500 paths now return generic messages ('Internal error during AI detection/PII detection/CIM mapping') with the full detail logged server-side (exc_info=True); pii_detection_logic.detect_pii error dict likewise genericised.
  - Verified: grep for str(e) in return payloads across bin/ and lib/ finds none in 500 bodies; suite passes (the pii logic error path is exercised structurally by tests).
- **[DONE]** Test scripts shipped in packaged bin/ (both duplicate findings)
  - Files: `tests/test_load_cim_models.py, tests/test_pii_logic.py, tests/test_pii_simple.py, tests/test_pii_standalone.py, tests/conftest.py`
  - Four test_*.py moved from ucc-app/bin/ to repo-root tests/ via git mv (history follows; staged as renames); tests/conftest.py puts ucc-app/bin and ucc-app/lib on sys.path. pii_detection_standalone.py remains in bin/ per scope (it is the importable standalone module, not a test). The optional CI find-delete belt-and-braces is now moot for tests but recorded as handoff for the .so glob.
  - Verified: git status shows R/RM renames; python3 -m pytest tests -q passes (9 passed, 2 skipped locally; 19 passed with scrubadub installed).
- **[DONE]** CIM fields loaded at module import time; OSError kills handler and fields never refresh
  - Files: `ucc-app/bin/cim_mapping.py, ucc-app/bin/load_cim_models.py`
  - cim_mapping now lazily memoises via _get_cim_fields() (module-level cache filled on first request, so import cannot fail and a handler recycle picks up a newly installed CIM); load_cim_fields wraps its whole body in try/except returning the fallback models, covering the unguarded os.listdir calls.
  - Verified: test_falls_back_when_cim_app_absent passes; code inspection confirms no filesystem work at cim_mapping import beyond the import of load_cim_models itself (pure constants).
- **[DONE]** DA-ESS-ContentUpdate wrongly treated as Splunk_SA_CIM substitute
  - Files: `ucc-app/bin/load_cim_models.py`
  - Candidate loop now matches only entry.lower() == 'splunk_sa_cim' (case-insensitive matching preserved per verifyNotes); da-ess-contentupdate removed.
  - Verified: grep confirms no da-ess reference; load_cim_models tests pass.
- **[DONE]** test_load_cim_models fixture codifies wrong CIM layout
  - Files: `tests/test_load_cim_models.py`
  - Fixture rebuilt at etc/apps/Splunk_SA_CIM/default/data/models with underscore modelNames (Network_Traffic), nested comment objects, calculations/outputFields, dedup case, junk file, fieldless model and malformed JSON; added a local/data/models override test.
  - Verified: pytest tests/test_load_cim_models.py: 3 tests pass, including the local-override and malformed-JSON cases.
- **[SKIPPED]** Invalid cimModel (and all AI errors) returned as HTTP 200 with error payload
  - Files: ``
  - Nothing: the task's group guidance explicitly says the 200-with-error-payload shape is a deferred stage-spec item and must be left, overriding the finding's fix-now action.
  - Verified: n/a (deliberate no-op; cim_mapping.py:201 unchanged in this respect).
- **[DONE]** Tests mutate os.environ SPLUNK_HOME without restoring
  - Files: `tests/test_load_cim_models.py`
  - Each test saves the original SPLUNK_HOME and restores it (or pops it) in try/finally via _restore_home(); the standalone __main__ runner is preserved (per verifyNotes, monkeypatch would have broken it).
  - Verified: pytest passes in any order; verified by running the whole suite where later tests still see the real SPLUNK_HOME.
- **[DONE]** Dead web.conf expose stanzas for nonexistent cim-plicity_account endpoint
  - Files: `ucc-app/default/web.conf`
  - Deleted [expose:cim-plicity_account] and [expose:cim-plicity_account_specified]; everything else (settings stanzas, staged MCP wildcard expose) preserved.
  - Verified: git diff HEAD on web.conf shows exactly the two stanzas removed plus the additive cim_mapping/tools stanzas.
- **[DONE]** autoregister returns 200 on missing auth for direct callers
  - Files: `ucc-app/bin/autoregister.py`
  - Missing session key (or unavailable splunk.rest) now returns 401 with {ok:false,error} JSON; the catch-all exception path keeps never-raise 200 for reload-trigger safety; ping stays unauthenticated.
  - Verified: Code inspection of handle(): 401 branch before instance-type logic, exception branch unchanged at 200; py_compile + 3.9 ast check pass.

### Group B: frontend React (24 actions)

- **[DONE]** Broken unused import of non-existent module breaks the webpack build (CiMplicityHome.jsx:16 import App)
  - Files: `packages/ci-mplicity-home/src/CiMplicityHome.jsx`
  - The dead `import App from '../../../../../src/App'` was already removed in the working tree by an earlier interrupted pass; I verified nothing else references it and completed the half-finished import conversion that pass left behind (Typography was un-imported but still used throughout, which would have been a runtime ReferenceError).
  - Verified: corepack yarn run build compiles successfully; grep confirms no App/Typography references remain
- **[DONE]** ReferenceError: setAiFieldResults is not defined when editing the combined regex (FieldExtraction.jsx:1168)
  - Files: `packages/ci-mplicity-home/src/FieldExtraction.jsx, packages/ci-mplicity-home/src/CiMplicityHome.jsx`
  - Lifted the edit to the parent: added onCombinedRegexChange prop (with propTypes and a no-op default); CiMplicityHome owns aiFieldResults and passes handleCombinedRegexChange which does setAiFieldResults(prev => ({...prev, combined_regex: value})), so handleAcceptCombinedRegex still reads the edited value.
  - Verified: New unit test 'propagates combined regex edits via onCombinedRegexChange' passes
- **[DONE]** ReferenceError: theme is not defined in combined-regex preview inline styles (FieldExtraction.jsx:1187)
  - Files: `packages/ci-mplicity-home/src/FieldExtraction.jsx`
  - Replaced the inline-styled div/pre with StyledPreviewBox and a new StyledPreviewPre, both using @splunk/themes variables (backgroundColorSection, borderColor, textColor); no bare `theme` identifier remains anywhere in the file.
  - Verified: Unit test clicks Preview Extraction and asserts the preview renders without crashing; grep for `theme.` returns nothing
- **[DONE]** XSS: raw log data injected via dangerouslySetInnerHTML without escaping (FieldExtraction.jsx:1234/1206, both frontend-react and security findings)
  - Files: `packages/ci-mplicity-home/src/FieldExtraction.jsx`
  - Removed both dangerouslySetInnerHTML sinks entirely. Highlighting is now built as React nodes: collectFieldMatchRanges / collectCombinedRegexRanges compute non-overlapping match ranges and renderHighlightedText slices the raw text into strings plus <StyledHighlight> elements (title attr set via React, values as text children). Newlines render via white-space: pre-wrap on StyledPreview instead of <br/>. Also deleted the dead HTML-building branch i
  - Verified: Unit test feeds '<img src=x onerror=...>' sample data and asserts no img element is created, window.pwned stays undefined and the markup renders as inert text; grep confirms zero dangerouslySetInnerHTML
- **[DONE]** Python-to-JS named-group conversion is wrong: (?P< becomes \(?< (FieldExtraction.jsx:837/867/893/948)
  - Files: `packages/ci-mplicity-home/src/FieldExtraction.jsx`
  - Added a shared pythonToJsNamedGroups() helper that replaces (?P< with (?< (unescaped) and applied it at all surviving call sites (handlePreviewCombinedRegex, handleAcceptCombinedRegex, collectCombinedRegexRanges); the fourth site (handlePreviewRegex) was dead code and was deleted.
  - Verified: Node sanity check ((?P<user>\w+) captures 'alice') plus unit test asserting Preview Extraction shows the captured group for a Python-style regex
- **[DONE]** Raw HTML form controls and headings instead of @splunk/react-ui components (PIIDetection.jsx:268 et al)
  - Files: `packages/ci-mplicity-home/src/PIIDetection.jsx, packages/ci-mplicity-home/src/FieldExtraction.jsx, packages/ci-mplicity-home/src/CIMMapping.jsx`
  - PIIDetection: raw checkbox is now Switch appearance=checkbox with aria-label; the custom-pattern form uses ControlGroup + Text (labelPosition top); raw h4/h5 are Heading level 3/4; styled.h3 ResultsHeader and red ErrorMessage removed (Heading + Message type=error). FieldExtraction: raw <select>/<option> for TIME_FORMAT is now Select/Select.Option inside ControlGroup; TIME_PREFIX and MAX_TIMESTAMP_LOOKAHEAD wrapped in ControlGroup (help text on th
  - Verified: grep sweep finds no <input/<select/<option/<h1-5> in src; all 15 unit tests pass; build compiles
- **[DONE]** api.js postToEndpoint bypasses splunk-utils conventions with hardcoded app name and pre-namespaced path
  - Files: `packages/ci-mplicity-home/src/utils/api.js`
  - Already applied in the working tree by the earlier pass and verified by me: createRESTURL(endpoint, { app }) with config-derived app (emits the byte-identical /servicesNS/-/cim-plicity/<endpoint> URL so restmap/web.conf still match), APP_NAME removed, empty callApiWithRetry stub and unused postRequest/deleteRequest exports deleted. No changes needed from me beyond verification.
  - Verified: Read the diff and @splunk/splunk-utils url.js relative-path branch; build + tests green
- **[DONE]** styled-components read non-contract theme keys instead of @splunk/themes variables (CiMplicityHome.jsx:57 et al)
  - Files: `packages/ci-mplicity-home/src/CiMplicityHome.jsx, packages/ci-mplicity-home/src/FieldExtraction.jsx, packages/ci-mplicity-home/src/CIMMapping.jsx, packages/ci-mplicity-home/src/ConfigurationGenerator.jsx, packages/ci-mplicity-home/src/PIIDetection.jsx`
  - Replaced every `${({ theme }) => theme.*}` access with variables.* functions (verified against the installed @splunk/themes exports): backgroundColor, backgroundColorPage, backgroundColorSection (for the non-existent backgroundColorSecondary), backgroundColorHover (for backgroundColorSelected), textColor, borderColor, accentColor, focusColor, successColor, interactiveColorPrimary.
  - Verified: grep for `theme.<key>` across src returns nothing; node check confirmed every substituted token exists in @splunk/themes; build + tests green
- **[DONE]** Hardcoded light-theme colours break dark theme throughout (PIIDetection.jsx:29 et al, mappingConstants badge colours, global.css)
  - Files: `packages/ci-mplicity-home/src/PIIDetection.jsx, packages/ci-mplicity-home/src/FieldExtraction.jsx, packages/ci-mplicity-home/src/CIMMapping.jsx, packages/ci-mplicity-home/src/constants/mappingConstants.js, packages/ci-mplicity-home/src/global.css`
  - All hex/named colours replaced with theme tokens: PII preview containers use backgroundColorSection/backgroundColor + borderColor; FieldExtraction highlight palette is now token-based (variables.syntax* + interactiveColorPrimary via a $colorIndex prop on StyledHighlight), success text uses successColor, the existing-field asterisk uses interactiveColorPrimary; CIMMapping borders use borderColor and quality badges read the colorToken names (severi
  - Verified: grep for hex colours across src (excluding tests) returns nothing; build + tests green
- **[DONE]** Data-driven views missing visible error states (indexes/sourcetypes fetch errors swallowed)
  - Files: `packages/ci-mplicity-home/src/CiMplicityHome.jsx, packages/ci-mplicity-home/src/FieldExtraction.jsx, packages/ci-mplicity-home/src/PIIDetection.jsx`
  - Added indexesError/sourcetypesError state with dismissable Message type=error (onRequestRemove) in the From Splunk panel, plus an empty-state hint when no indexes load; converted the red-paragraph ErrorMessage usages (aiFieldError, piiError) to Message type=error.
  - Verified: PIIDetection unit test asserts the error message surfaces; tests + build green
- **[DONE]** SearchJob subscription leak: cleanup returned from a click handler is discarded (CiMplicityHome.jsx:375) + fetchIndexes ignores signal
  - Files: `packages/ci-mplicity-home/src/CiMplicityHome.jsx`
  - handleSplunkFetch now stores its subscription in a fetchSubscription ref (unsubscribing any previous one first) and a mount effect returns an unmount cleanup that unsubscribes; the useless return-from-onClick is gone. fetchIndexes now creates an AbortController, passes controller.signal to getRequest and aborts in the effect cleanup, ignoring AbortError.
  - Verified: Code inspection against the sourcetype effect's existing correct pattern; CiMplicityHome unit tests (mocked SearchJob) pass; build green
- **[DONE]** CIMMapping mode toggle initialises mappings with the stale mode (side effect inside setState updater)
  - Files: `packages/ci-mplicity-home/src/CIMMapping.jsx`
  - handleModeToggle computes newMode outside the updater, calls setMappingMode(newMode) then initializeFieldMappings(newMode); initializeFieldMappings now accepts a mode parameter defaulting to state. No side effect inside an updater any more (StrictMode-safe).
  - Verified: Unit test toggles the mode switch and asserts the table is re-seeded with extracted-field rows (header flips CIM Field to Extracted Field, clientip appears)
- **[DONE]** Unit tests are stale (assert removed UI) and 3 of 4 suites lack a jsdom environment
  - Files: `packages/ci-mplicity-home/jest.config.js, packages/ci-mplicity-home/src/tests/CiMplicityHome.unit.jsx, packages/ci-mplicity-home/src/tests/CIMMapping.unit.jsx, packages/ci-mplicity-home/src/tests/ConfigurationGenerator.unit.jsx, packages/ci-mplicity-home/src/tests/PIIDetection.unit.jsx, packages/ci-mplicity-home/src/tests/FieldExtraction.unit.jsx`
  - jest.config.js now sets testEnvironment: 'jsdom'. Rewrote all four stale suites against the current UI (correct placeholders/buttons/props shapes, piiResults as {results:[...]}/{pii_results:[...]}, SplunkThemeProvider wrapper) with jest mocks for @splunk/search-job, @splunk/splunk-utils/config and utils/api in the Home suite, and added a new FieldExtraction suite (largest component, previously untested) covering rendering, the named-group convers
  - Verified: corepack yarn@1.22.22 run test: 5 suites, 15 tests, all pass (the acceptance command)
- **[DONE]** Toast wiring broken: window.createToast never exists and duplicate ToastMessages containers
  - Files: `packages/ci-mplicity-home/src/FieldExtraction.jsx, packages/ci-mplicity-home/src/ConfigurationGenerator.jsx`
  - FieldExtraction now has a module-level createToast = makeCreateToast(Toaster) (same pattern as ConfigurationGenerator) and the surviving accept-combined-regex toast uses it with TOAST_TYPES.SUCCESS; both window.createToast guards are gone (one was inside deleted dead code). Removed ConfigurationGenerator's second <ToastMessages position="top-center"/> and its import, leaving the single <ToastMessages/> in CiMplicityHome.
  - Verified: grep: no window.createToast, exactly one ToastMessages render; tests + build green
- **[DONE]** resetFlow leaves stale extractionRegex and timeSettings for the next run
  - Files: `packages/ci-mplicity-home/src/CiMplicityHome.jsx`
  - Added module-level INITIAL_PII_DETECTION_STATE (including customPatterns, fixing the shape inconsistency) and INITIAL_TIME_SETTINGS constants used for useState init; resetFlow now also resets extractionRegex to null, timeSettings and piiDetectionState to those constants; handleDataSubmit likewise clears extractionRegex and timeSettings when new data enters the flow.
  - Verified: Code inspection (all state writers/readers traced); tests + build green
- **[DONE]** Undeclared direct dependency @splunk/react-icons; @splunk/splunk-utils misfiled in devDependencies; license fields
  - Files: `packages/ci-mplicity-home/package.json, packages/cim-plicity/package.json`
  - Already applied in the working tree by the earlier pass and verified by me: @splunk/react-icons ^5.0.0 added to dependencies, @splunk/splunk-utils ^3.2.0 moved from devDependencies to dependencies, and license set to Apache-2.0 in both package.json files (matching the root LICENSE). Ranges match the existing yarn.lock resolutions so no lockfile churn.
  - Verified: Read both package.json files and yarn.lock entries; install-consistent builds and tests pass
- **[DONE]** Template title says 'CimPlicity Demo App' and links a non-existent apple-touch-icon (main.html)
  - Files: `ucc-app/appserver/templates/main.html`
  - Already applied in the working tree by the earlier pass and verified by me: title is now 'CIMPlicity AI' and the apple-touch-icon link is removed; the rest of the template (config autoload, i18n, single page script) is unchanged.
  - Verified: Read the final file content
- **[DONE]** Production console.log debug spam with emoji markers throughout the flow
  - Files: `packages/ci-mplicity-home/src/CiMplicityHome.jsx, packages/ci-mplicity-home/src/FieldExtraction.jsx, packages/ci-mplicity-home/src/CIMMapping.jsx`
  - Deleted all 34 console.log calls (including the per-render and per-table-row ones that leaked sample data/PII to the console); kept console.error/console.warn for genuine failures and downgraded the XML-parse catch to console.warn.
  - Verified: grep -rn console.log across src returns nothing
- **[DONE]** Substantial dead code: unused AI-field editing handlers, fake API, undefined applyExtractions, unused imports and outputs
  - Files: `packages/ci-mplicity-home/src/FieldExtraction.jsx, packages/ci-mplicity-home/src/ConfigurationGenerator.jsx, packages/ci-mplicity-home/src/PIIDetection.jsx, packages/ci-mplicity-home/src/CiMplicityHome.jsx`
  - FieldExtraction: deleted the amputated per-field AI editing feature (handleEditRegex/handleRegexChange/handleSaveRegex/handleCancelEdit/allRegexesValid/handleAcceptAiFields/handlePreviewRegex + editedRegexes/regexErrors/previewedField/previewResults/selectedAiFields/modifiedAiFields state), the setTimeout fake handleExistingFieldsFetch, unused options state/handleOptionToggle, unrendered highlightedText state, AiCard/RegexCell styled components a
  - Verified: eslint no-unused-vars sweep over the five components is clean; tests + both builds green
- **[DONE]** Stepper and table controls not keyboard-accessible; inputs lack associated labels
  - Files: `packages/ci-mplicity-home/src/CiMplicityHome.jsx, packages/ci-mplicity-home/src/PIIDetection.jsx, packages/ci-mplicity-home/src/FieldExtraction.jsx`
  - StyledStep is now a real styled.button (type=button) with disabled for unreachable steps, aria-current='step' on the active step, a focus-visible outline using variables.focusColor and aria-hidden on the number/tick glyph, so back-navigation is keyboard and screen-reader accessible. The PII redact toggle is a Switch with aria-label; all form fields (time settings, custom regex, custom PII pattern, sourcetype override) are in ControlGroup so label
  - Verified: Unit test asserts later steps render as disabled buttons; RTL getByLabelText finds the redact switch; tests + build green
- **[DONE]** Unescaped user values interpolated into SPL search strings / SPL injection via index-sourcetype names (both findings)
  - Files: `packages/ci-mplicity-home/src/CiMplicityHome.jsx`
  - Added escapeSplValue (escapes backslash and double quote with \$&) and applied it to splunkIndex/splunkSourcetype in both interpolations: the metadata sourcetypes search and the fetch-sample search.
  - Verified: Code inspection of both SearchJob.create call sites; Home suite (mocked SearchJob) passes
- **[DONE]** clipboard copy has no failure handling on non-secure origins (ConfigurationGenerator.jsx:733)
  - Files: `packages/ci-mplicity-home/src/ConfigurationGenerator.jsx`
  - handleCopy is now async: feature-detects navigator.clipboard.writeText, awaits it and only toasts success on resolution; on plain-http origins it falls back to a hidden-textarea document.execCommand('copy'); any failure logs console.error and toasts TOAST_TYPES.ERROR ('Copy failed').
  - Verified: Unit test confirms the copy buttons render and the component works with the new handler; code path reviewed for both branches
- **[DONE]** Bootstrap error fallback injects the error via innerHTML; greeting and global.css dead code (both frontend and security findings)
  - Files: `packages/cim-plicity/src/main/webapp/pages/main/index.jsx, packages/cim-plicity/src/main/webapp/pages/main/StartStyles.js, packages/ci-mplicity-home/src/CiMplicityHome.jsx, packages/ci-mplicity-home/src/global.css`
  - The earlier pass already switched the getUserTheme catch to errorEl.textContent = String(e) and removed the unused StyledGreeting export/import (verified). I completed the global.css side: removed the app-grid/left-col/center-col/right-col classNames from CiMplicityHome (MainGrid styled-component is the single layout source) and stripped global.css to a comment plus the fadeIn keyframes, deleting the dead grid rules, hardcoded colours and the pre
  - Verified: cim-plicity webpack build exits 0; grep confirms the classNames are gone and nothing but the demo imports global.css
- **[DONE]** Typography used for headings/paragraphs instead of Heading and Paragraph
  - Files: `packages/ci-mplicity-home/src/CiMplicityHome.jsx, packages/ci-mplicity-home/src/FieldExtraction.jsx, packages/ci-mplicity-home/src/CIMMapping.jsx, packages/ci-mplicity-home/src/ConfigurationGenerator.jsx, packages/ci-mplicity-home/src/PIIDetection.jsx`
  - Standardised on the skill convention: every Typography usage (~30 sites) converted to Heading (levels 2-4) or Paragraph/P; inline spans inside buttons/badges use plain styled spans. Typography is no longer imported anywhere.
  - Verified: grep for Typography across src returns nothing; all tests and both builds pass

### Group C: CI, build and packaging (19 actions)

- **[DONE]** CI build breaks: unpinned ucc-gen (6.5.2) crashes purging transitive numpy pulled by unpinned scrubadub (critical)
  - Files: `.github/workflows/splunk-app-ci.yml, ucc-app/lib/requirements.txt`
  - Pinned `pip install splunk-add-on-ucc-framework==5.69.1` in the workflow with a comment explaining the 6.x RECORD-based purge crash; scrubadub==2.0.1 is pinned in ucc-app/lib/requirements.txt (pins-only ownership). Also added a fail-fast assertion after `ucc-gen build` (checks build/cim-plicity/default/app.conf exists) because ucc-gen swallows exceptions and exits 0 on partial builds, per verifyNotes.
  - Verified: Full local build in a fresh venv: `ucc-gen 5.69.1 build --source ucc-app -o <scratch>` completed (exit 0) with a COMPLETE tree: default/app.conf, restmap.conf, web.conf, bin/, app.manifest, lib/ incl 3rdparty all present
- **[DONE]** Production package built with webpack development mode + eval-source-map
  - Files: `packages/cim-plicity/bin/build.js, packages/cim-plicity/webpack.config.js`
  - nix branch of build.js now `export NODE_ENV=production && webpack --mode=production` (matching the win32 branch); webpack.config.js devtool gated: `process.env.NODE_ENV === 'production' ? false : 'eval-source-map'` with a comment.
  - Verified: Static verification of both edits (win32 branch already proves production mode works with this config). CAVEAT: the local production compile could not be completed in the sandbox — the first run was OOM-killed and a retr
- **[DONE]** CI .so cleanup glob is a no-op for nested files and would break the app if globstar were on
  - Files: `.github/workflows/splunk-app-ci.yml`
  - Removed the bogus `rm -rf temp-package/cim-plicity/lib/**/*.so` line (it silently corrupted 6 two-level packages like sklearn/regex). Replaced with `find temp-package/cim-plicity/bin -name '*.so' -type f -delete` (bin only), leaving lib/ and lib/3rdparty .so intact per group guidance.
  - Verified: Fresh ucc-gen build inspected: 21 .so under lib/3rdparty/linux_lib_py39 (needed at runtime) are untouched by the new rules; two-level lib .so (sklearn/_isotonic etc) now ship intact instead of being silently deleted. Dee
- **[PARTIAL]** Tracked binary ucc-app/bin/_lsprof.cpython-39-x86_64-linux-gnu.so unreferenced yet shipped
  - Files: `ucc-app/bin/_lsprof.cpython-39-x86_64-linux-gnu.so`
  - File is git-rm'd (staged deletion, no copy kept). The corresponding now-false waiver in .appinspect.expect.yaml could NOT be removed: that file is outside my scope — recorded as a handoff.
  - Verified: git status shows staged D; fresh ucc-gen build output bin/ contains no .so; CI additionally deletes any stray bin/*.so at packaging.
- **[DONE]** Version scheme incoherent: branch builds hardcode 1.0.0; committed globalConfig meta.version stale
  - Files: `.github/workflows/splunk-app-ci.yml, globalConfig.json`
  - Non-tag builds now derive TAG_VERSION via `git fetch --tags` + `git describe --tags --match "v*" --always` (v1.0.4-3-gHASH -> 1.0.4-3-gHASH, fallback 0.0.0-g<hash>); `--match v*` deliberately skips the stray unprefixed 1.0.0 tag. Tag builds unchanged. globalConfig meta.version restored to the committed placeholder 0.0.0+0a19330 / schemaVersion 0.0.9 after my ucc-gen run, per instructions (CI sed overwrites version in stage app.conf AND app.manife
  - Verified: YAML parses; git tag list confirms v1.0.1..v1.0.4 plus stray 1.0.0; json.load confirms restored meta fields; the existing CI sed steps rewrite both stage app.conf and app.manifest versions.
- **[DONE]** Stale ucc-app/requirements.txt ships at package root, contradicting real pins
  - Files: `ucc-app/requirements.txt`
  - git rm (staged deletion, no copy kept) — the file is never consumed by ucc-gen, which installs only from ucc-app/lib/requirements.txt.
  - Verified: Fresh ucc-gen 5.69.1 build: no requirements.txt at the package root; build log shows install from ucc-app/lib/requirements.txt only.
- **[PARTIAL]** Dead CI patch for nonexistent splunk_create.conf
  - Files: `.github/workflows/splunk-app-ci.yml`
  - Dead block removed from the workflow (superseded by the preserved MCP tools.conf reload-trigger step, which also explicitly ensures reload.cim-plicity_settings). The two copies in docs/BUILD_GUIDE.md are out of scope — handoff.
  - Verified: grep of the workflow: no splunk_create references remain; YAML parses.
- **[DONE]** Four test_*.py files ship inside package bin/
  - Files: `.github/workflows/splunk-app-ci.yml`
  - The move to /opt/aios/apps/cimplicity-ai-app/tests/ (with conftest.py adding ucc-app/bin and ucc-app/lib to sys.path) was done by the tests-owning agent and is staged. My side: defensive `find temp-package/cim-plicity/bin -name 'test_*.py' -delete` at packaging plus the CI pytest step.
  - Verified: Fresh ucc-gen build bin/ contains no test_*.py; local `python -m pytest tests/ -q` = 9 passed, 2 skipped.
- **[DONE]** No generic dotfile/junk exclusion or 755/644 permission normalisation at packaging
  - Files: `.github/workflows/splunk-app-ci.yml`
  - Replaced the two hardcoded .f2py_f2cmap deletions with generic `find temp-package/cim-plicity -name '.*' -not -name '.' -exec rm -rf {} +`, plus `find ... -type d -exec chmod 755` and `-type f -exec chmod 644` before ucc-gen package, matching the skill Quality gates.
  - Verified: Fresh build dotfile inventory: only the two 3rdparty .f2py_f2cmap files exist and the generic find covers them (and any future top-level lib copies the old hardcoded lines missed); no needed shipped file is hidden. YAML 
- **[DONE]** app.manifest releaseNotes.uri is "" instead of null
  - Files: `ucc-app/app.manifest`
  - releaseNotes.uri set to null, matching the manifest's own null convention for empty values.
  - Verified: json.load shows releaseNotes {'name': 'README', 'text': 'README.txt', 'uri': None}; final confirmation comes from the CI quality-appinspect-api (SLIM) job.
- **[DONE]** publish-gh does not depend on the API/SLIM AppInspect job
  - Files: `.github/workflows/splunk-app-ci.yml`
  - publish-gh needs now lists both appinspect and quality-appinspect-api, so a release cannot publish from a package the API/SLIM job rejects.
  - Verified: Workflow read-back confirms `needs: [appinspect, quality-appinspect-api]`; YAML parses.
- **[DONE]** .gitignore misses ucc-app/bin/.pytest_cache/ and ucc-app/lib/__pycache__/
  - Files: `.gitignore`
  - Added ucc-app/bin/.pytest_cache/, ucc-app/lib/__pycache__/, .pytest_cache/ and package-lock.json to .gitignore; the on-disk ucc-app/bin/.pytest_cache is gone.
  - Verified: `git check-ignore` matches all three new paths; ls confirms no on-disk ucc-app/bin/.pytest_cache; the generic dotfile strip at packaging is a second line of defence.
- **[DONE]** Dependabot pip config points at a manifest-less directory and misses npm/yarn
  - Files: `.github/dependabot.yml`
  - Dropped the dead "/" pip entry, kept pip at /ucc-app/lib (now has scrubadub==2.0.1 pin so updates are actionable) and added an npm ecosystem for "/" (yarn workspace root), all on target-branch develop.
  - Verified: YAML content read back; `git ls-remote` confirms origin/develop exists (existing dependabot branches already target it).
- **[DONE]** Tracked vendored wheel remnants packages/cim-plicity/lib/typing_extensions* are dead weight
  - Files: `packages/cim-plicity/lib/typing_extensions.py`
  - git rm of packages/cim-plicity/lib/typing_extensions.py and the typing_extensions-4.7.0.dist-info directory (staged deletions, no copies kept).
  - Verified: grep across packages/cim-plicity found references only inside the gitignored generated src/main/resources/splunk/lib (ucc-gen output, not the deleted vendored copy); nothing tracked imports from packages/cim-plicity/lib.
- **[DONE]** Both yarn.lock and package-lock.json tracked at root (npmClient is yarn)
  - Files: `package-lock.json, .gitignore`
  - package-lock.json git-rm'd (staged deletion) and added to .gitignore.
  - Verified: ls confirms the file is gone, yarn.lock (437 KB) present; `git check-ignore package-lock.json` matches.
- **[DONE]** Release notes README.txt is a single URL line (and github.dev typo)
  - Files: `ucc-app/README.txt`
  - Replaced with real 1.0.4 release notes (dynamic CIM field loading incl calculated fields, AI mapping suggestions, PII detection via bundled scrubadub, packaging/AppInspect fixes), British English, no em dashes, corrected link to github.com, trailing newline.
  - Verified: cat + od confirm content and trailing \n; app.manifest releaseNotes.text still points at README.txt which ships at package root (confirmed in fresh build).
- **[DONE]** New tests are never executed in CI
  - Files: `.github/workflows/splunk-app-ci.yml`
  - Added a 'Run Python tests' step after 'Install dependencies': `pip install pytest` then `python3 -m pytest tests/ -q`, before ucc-gen build/packaging.
  - Verified: Ran the identical invocation locally in the venv: 9 passed, 2 skipped in 0.3 s (heavy-dep PII tests skip gracefully when deps absent, so the step is safe in the package job); packaging still strips *.pyc/__pycache__ so n
- **[DONE]** Licence contradiction: package.json files declare UNLICENSED vs Apache-2.0 LICENSE/manifest
  - Files: `package.json`
  - Root package.json license set to "Apache-2.0" (my scope was root only; the two per-package package.json files already carry the same change from the agent that owns them).
  - Verified: git diff shows only the license line changed in root package.json; all three now read Apache-2.0, matching LICENSE and app.manifest.
- **[DONE]** Orphan UCC Monitoring Dashboard: globalConfig pages.dashboard generates an unlinked, empty view
  - Files: `globalConfig.json`
  - Removed the pages.dashboard block (minimal edit, nothing else changed in pages); kept meta version/schemaVersion at committed values per instructions.
  - Verified: Fresh ucc-gen 5.69.1 build: default/data/ui/views/ contains only configuration.xml and main.xml, no dashboard.xml; json.load confirms pages == ['configuration'].

### Group D: documentation (18 actions)

- **[DONE]** cim_mapping endpoint and dynamic CIM field loading undocumented
  - Files: `docs/CIM_MAPPING_ENDPOINT.md, README.md, docs/README.md`
  - docs/CIM_MAPPING_ENDPOINT.md documents the full contract: dual URL forms (/services/cim_mapping and /servicesNS/-/cim-plicity/cim_mapping from the [script:cim_mapping] match), request {extractedFields, cimModel}, response array [{field, cimField, confidence, reasoning}], all real error shapes, configured api_endpoint/model from cim-plicity_settings.conf [ai_configuration], and the dynamic Splunk_SA_CIM loading with the built-in authentication/net
  - Verified: Line-by-line comparison against current ucc-app/bin/cim_mapping.py and load_cim_models.py (error strings, cache logic, model paths, key derivation); relative-link checker over docs/ returned 0 broken; python3 -m pytest t
- **[DONE]** ai_detection endpoint has no documentation
  - Files: `docs/AI_DETECTION_ENDPOINT.md, docs/README.md`
  - docs/AI_DETECTION_ENDPOINT.md documents request {text, description?, selected_fields?} (including the selected_fields combined_regex behaviour the finding's verifyNotes asked for), the normalised response schema (sourcetype, fields [{name, regex}], combined_regex, time_format, time_prefix, max_timestamp_lookahead, source), OpenRouter vs local_field_extraction fallback, the 60 s timeout, real servicesNS URLs and a curl example. This session correc
  - Verified: Compared every documented field and error string against current ucc-app/bin/ai_detection.py (handle(), normalize_ai_response(), local_field_extraction(), generate_combined_regex()) and restmap.conf handler=ai_detection.
- **[DONE]** PII_DETECTION_ENDPOINT.md omits the custom_patterns request field
  - Files: `docs/PII_DETECTION_ENDPOINT.md`
  - Request Structure now shows the raw JSON body with custom_patterns as an array of {name, regex} objects, documents case-insensitive matching, upper-cased type reporting, [REDACTED_<NAME>] replacement and invalid-regex skipping, with a curl example including a custom pattern. Response Fields now states score is 1.0 for scrubadub detectors and 0.9 for custom-pattern matches.
  - Verified: Checked against ucc-app/bin/pii_detection.py (custom_patterns = posted_data.get('custom_patterns', [])) and ucc-app/lib/pii_detection_logic.py ('score': 0.9 for custom patterns); grep confirms the doc text present
- **[DONE]** PII endpoint doc gives incomplete REST path, stale splunk-app/ script location
  - Files: `docs/PII_DETECTION_ENDPOINT.md`
  - Doc now shows both real URL forms (/services/pii_detection and /servicesNS/-/cim-plicity/pii_detection, explaining the [script:] match derivation per the skill baseline), a working curl example with auth, the Splunk Web proxy route via [expose:pii_detection], and Script Location corrected to ucc-app/bin/pii_detection.py. This session also fixed the handler name to pii_detection.PiiDetection and added the 401 no-session-key error shape.
  - Verified: Checked against restmap.conf (match = /pii_detection, handler = pii_detection.PiiDetection), web.conf [expose:pii_detection] and pii_detection.py error strings; grep confirms no splunk-app/ path remains in the doc
- **[DONE]** BUILD_GUIDE and QUICK_START use stale bare ucc-gen invocation
  - Files: `docs/BUILD_GUIDE.md, docs/QUICK_START.md, docs/README.md`
  - All five occurrences (BUILD_GUIDE 2, QUICK_START 2, docs/README 1) now read `ucc-gen build --source ucc-app -o build/`, matching CI and the splunk-react-app skill's canonical build order.
  - Verified: grep for 'ucc-gen --source' and 'ucc-gen -o' across README.md and docs/ returns nothing; splunk-app-ci.yml line 76 uses the identical command
- **[DONE]** BUILD_GUIDE describes packaging and AppInspect-fix steps that no longer exist in CI
  - Files: `docs/BUILD_GUIDE.md`
  - Pipeline sections rewritten to mirror the current workflow: git-describe version derivation, the new 'Run Python tests' pytest step, the version/id sed in stage/, the conditional [triggers] logic including reload.tools = http_post /cim-plicity/autoregister and reload.cim-plicity_settings = simple, packaging via ucc-gen package (meson.build/.pyc/__pycache__/hidden-file/.so/test_*.py cleanup, 755/644 permission normalisation), no -latest tarball, a
  - Verified: Section-by-section comparison against the current .github/workflows/splunk-app-ci.yml (including the pytest and autoregister trigger blocks added by other agents this cycle)
- **[DONE]** QUICK_START and docs/README claim CI runs unit tests and ESLint
  - Files: `docs/QUICK_START.md, docs/README.md, docs/BUILD_GUIDE.md`
  - Pipeline descriptions now accurately list: Python tests (pytest tests/, the CI step another agent added), UCC generation, build/package, AppInspect CLI + API and GitHub release on version tags, with an explicit statement that Jest unit tests and ESLint are local-only today and should be run before pushing. BUILD_GUIDE's Testing Strategy section separates the pytest suite (in CI) from the Jest suite (not in CI).
  - Verified: splunk-app-ci.yml jobs enumerated (package with pytest step, appinspect, quality-appinspect-api, publish-gh; no yarn test/lint); python3 -m pytest tests/ -q passes locally (9 passed, 2 skipped) so the documented CI step 
- **[SKIPPED]** Splunkbase releaseNotes file (ucc-app/README.txt) points at github.dev with no release notes
  - Files: ``
  - Explicitly out of my scope (another agent owns ucc-app/README.txt). Verified their fix is in the tree: it now carries real v1.0.4 release notes and links https://github.com/livehybrid/cimplicity-ai-app.
  - Verified: Read current ucc-app/README.txt content
- **[DONE]** README.md links to non-existent docs/DEMO_NARRATIVE.md
  - Files: `README.md`
  - Dead reference removed; the Support section now points to the docs directory starting at docs/README.md.
  - Verified: grep DEMO_NARRATIVE returns nothing; link checker over README.md 0 broken
- **[DONE]** Package READMEs link main README four directory levels up
  - Files: `packages/cim-plicity/README.md, packages/ci-mplicity-home/README.md`
  - Both links changed from ../../../../README.md to ../../README.md.
  - Verified: Relative-link checker resolves both to the repo-root README (0 broken)
- **[DONE]** Package CHANGELOGs frozen at 0.0.1 TBA while the app ships as 1.0.4
  - Files: `packages/cim-plicity/CHANGELOG.md, packages/ci-mplicity-home/CHANGELOG.md, packages/ci-mplicity-home/README.md`
  - cim-plicity CHANGELOG backfilled with entries for 1.0.0 through v1.0.4 with release dates and per-release summaries, plus an explanatory note that app versions are derived from git tags by CI at package time (package.json stays 0.0.1). ci-mplicity-home CHANGELOG points to the app-level history and GitHub releases; its README's stale 'All changes now tracked in this README' claim replaced with links to the CHANGELOG and releases.
  - Verified: Dates cross-checked this session against `git log -1 --format=%ci <tag>` for all five tags and `gh release list` (1.0.0 2025-07-21, v1.0.1 07-22, v1.0.2 07-23, v1.0.3 08-14, v1.0.4 11-20): all match
- **[DONE]** docs/README.md index omits half the docs and carries an orphan setup stub
  - Files: `docs/README.md`
  - Documentation Index now lists all nine docs grouped as Getting Started (QUICK_START, BUILD_GUIDE), Product (PRODUCT_BRIEF, PROBLEM_SOLVED) and API Reference (AI_DETECTION_ENDPOINT, PII_DETECTION_ENDPOINT, CIM_MAPPING_ENDPOINT, MCP_TOOLS). The trailing orphan Setup Instructions stub after the footer is gone.
  - Verified: Read the full file; index entries match `ls docs/`; link checker 0 broken
- **[DONE]** scrubadub links point at the wrong GitHub org (datasnakes)
  - Files: `docs/PII_DETECTION_ENDPOINT.md, docs/PROBLEM_SOLVED.md`
  - All four occurrences now point to https://github.com/LeapBeyond/scrubadub and https://scrubadub.readthedocs.io.
  - Verified: grep datasnakes across all scoped docs returns nothing (verifier had already confirmed live: datasnakes URLs 404, LeapBeyond/readthedocs 200)
- **[DONE]** Stale splunk-app/ repo root naming, UCC mislabel, npm vs yarn
  - Files: `README.md, docs/BUILD_GUIDE.md, docs/QUICK_START.md`
  - All project trees and `cd` commands now use the real repo root cimplicity-ai-app; the BUILD_GUIDE tree includes ucc-app/; README.md's UCC expansion corrected to Universal Configuration Console; README.md Testing snippets switched from npm run to yarn. Also fixed README.md's Python prerequisite from 3.7+ to 3.9 to match the actual baseline (CI, BUILD_GUIDE, restmap python3).
  - Verified: grep sweep for 'splunk-app/', 'cd splunk-app' and 'Universal Config Converter' across scoped docs: only remaining hit is packages/ci-mplicity-home/demo/splunk-app/, which is a real directory (confirmed with find) so that
- **[DONE]** NEW: write docs/MCP_TOOLS.md documenting the MCP integration
  - Files: `docs/MCP_TOOLS.md, README.md, docs/README.md`
  - docs/MCP_TOOLS.md documents all four tools (cim_plicity_ping, ai_detection, pii_detection, cim_mapping) with purpose, real URL from each [script:] match (including the app-scoped ping at /services/cim-plicity/ping), payload, response shape and a curl example each; the Cloud (native synced-apps registrar, autoregister no-ops) vs Enterprise (KV upsert into mcp_tools/mcp_tools_enabled, idempotent, inline TOOLS table kept in lockstep with tools.conf)
  - Verified: Every claim cross-checked this session against the current ucc-app/default/tools.conf, ucc-app/bin/autoregister.py (ping response {ok, app, tools}, instance_type dispatch, kv_upsert/skipped actions, KV collection names) 
- **[DONE]** Reframe positioning as current (Splunkbase app + PLA1040) while keeping Build-a-Thon history
  - Files: `README.md`
  - Footer note now reads that CIMplicity AI started life as a Build-a-Thon entry and is now published on Splunkbase (app 7945) and is the subject of .conf26 talk PLA1040; overview links the Splunkbase listing. Build-a-Thon image and history retained; no now-false 'contest entry' claims remain.
  - Verified: Read full README.md; no remaining statements presenting the app as a pending contest entry
- **[DONE]** Discovered: ucc-app/README.md still declared the removed bin/_lsprof .so binary
  - Files: `ucc-app/README.md`
  - The binary declaration was stale after another agent deleted bin/_lsprof.cpython-39-x86_64-linux-gnu.so; the file now states no compiled binaries ship in bin/ and that CI strips *.so at package time.
  - Verified: git status shows the .so deletion; splunk-app-ci.yml confirms the bin/*.so strip step
- **[DONE]** Discovered: em dashes in scoped docs violating the style rules
  - Files: `docs/MCP_TOOLS.md, docs/AI_DETECTION_ENDPOINT.md, docs/CIM_MAPPING_ENDPOINT.md, docs/PII_DETECTION_ENDPOINT.md, docs/BUILD_GUIDE.md, docs/PRODUCT_BRIEF.md, docs/PROBLEM_SOLVED.md`
  - Replaced all 12 em dashes across the scoped docs with commas, colons, semicolons or rephrasing per the project style rules (10 introduced by this group's earlier edits, 2 pre-existing in PRODUCT_BRIEF/PROBLEM_SOLVED).
  - Verified: grep for the em dash character across all scoped .md files returns zero hits
### Residual handoffs closed manually after the fix wave

- `docs/PII_DETECTION_ENDPOINT.md`: corrected the example character offsets (email 20-40, SSN 56-67).
- `packages/ci-mplicity-home/demo/demo.jsx`: error path now uses `textContent`, not `innerHTML`.
- `.appinspect.expect.yaml`: removed the stale APPCERT-123 waiver for the deleted `_lsprof` binary.
- `docs/BUILD_GUIDE.md`: pinned `splunk-add-on-ucc-framework==5.69.1` in the two remaining unpinned lines.

## Stage-spec backlog (needs coordinated change or user decision)

- **[medium] cim_mapping returns AI-service errors with HTTP 200 and ignores the shipped api_endpoint/model settings**  
  Return 4xx/5xx when call_openrouter yields an error dict (400 for invalid model, 502/504 for AI-service failures), source api_endpoint and model from cim-plicity_settings, and decide the endpoint's fate: either wire CIMMapping.jsx to call it (aligning model ids with the dynamic keys and serving the dynamically loaded fields to the UI) or drop the s
- **[medium] Bare non-app-scoped [script:]/[expose:] names and match paths violate the skill's naming convention**  
  Rename to app-prefixed stanzas (e.g. [script:cimplicity_ai_detection]) with match = /cim_plicity/ai_detection etc, updating web.conf expose patterns and api.js postToEndpoint paths in the same change. This alters live URLs the UI depends on, so implement both sides together with a round-trip test.
- **[high] Branch goal unwired: dynamic CIM field loading has no frontend consumer and cim_mapping is not exposed in web.conf**  
  Frontend spec still needed, but update it: (1) web.conf `[expose:cim_mapping] pattern = cim_mapping, methods = POST` ALREADY exists as an uncommitted working-tree change — keep/commit it; do NOT change methods to GET (the handler is POST-only). (2) The cim_mapping endpoint is an AI mapping-suggestion endpoint (POST {extractedFields, cimModel} → Ope
- **[high] 355MB unpinned dependency tree (scrubadub → scikit-learn/scipy/numpy/nltk + solnlib's grpcio/opentelemetry) ships in lib/**  
  Write a spec for the runtime dependency set: pin every package (pip-compile against py3.9), evaluate whether scrubadub's sklearn-backed detectors are used (if not, vendor only the needed detectors or exclude), strip *-tests/tests dirs and dist-info junk in the packaging step, and record the intended package size. Needs a live Splunk round-trip of p
- **[high] No MCP tools.conf registration for the app's REST endpoints (drift from newest ucc-app-builder pattern)**  
  An implementation matching the recommendation already exists uncommitted in the working tree (ucc-app/default/tools.conf, ucc-app/bin/autoregister.py, restmap.conf/web.conf additions, CI [triggers] patch). Review it against the ucc-app-builder baseline (endpoint_name ↔ [script:] verified consistent), commit it, and verify end-to-end tool registrati
- **[medium] No authorization on custom REST endpoints that run with system credentials**  
  Add a custom capability in authorize.conf (e.g. `use_cimplicity_ai`), enforce with `capability.post = use_cimplicity_ai` on each [script:] stanza (or check the caller's roles from the session block in handle()), and grant it to admin/sc_admin/power by default. Requires updating restmap, authorize.conf, default.meta and documenting for the UI, so im
- **[medium] SSRF/egress surface: api_endpoint only length-validated, http:// accepted**  
  Add a regex validator in globalConfig.json requiring `^https://`, and in get_ai_secret/call_openrouter reject non-https endpoints server-side (defence in depth, since conf can be edited via REST directly). Consider warning in help text that the endpoint receives raw event samples.
- **[medium] ReDoS: untrusted regexes compiled and executed server-side and in browser**  
  Bound the risk: cap sample text and pattern length, reject nested quantifiers heuristically or run matching in a subprocess with a hard timeout (or bundle the `regex` module — already an os-dependentLibrary — with a timeout parameter). Needs a small spec since it touches request handling behaviour.
- **[medium] cim_mapping endpoint has no web.conf expose and the frontend never calls it; UI keeps its own hardcoded CIM model/field lists**  
  Split: (a) fix-now-safe — add [expose:cim_mapping] pattern=cim_mapping methods=POST to web.conf to match the skill convention (additive, cannot break anything). (b) stage-spec — decide whether the UI should consume backend fields: either add a GET models/fields mode on cim_mapping (plus expose) and replace CIMMapping.jsx CIM_MODELS, or keep the UI 
- **[medium] Build-a-Thon branding and hackathon framing are stale for a Splunkbase-published app headed to .conf26**  
  Reposition README.md as a released Splunkbase app (move the build-a-thon badge to an "Origins" or acknowledgments note, delete or soften the "designed for the Build-a-Thon" production caveat) and mark PRODUCT_BRIEF.md/PROBLEM_SOLVED.md as historical design docs or refresh them. Exact wording is the owner's call on positioning, so stage it rather th
- **[medium] Cross-dimension gap: the restmap rename (finding 14) and cim_mapping contract change (findings 13/77) silently break the staged MCP layer — tools.conf endpoint_name, tool descriptions and autoregister TOOLS all hardcode the current stanza names and URLs**  
  Amend finding 14's change-set to a single atomic edit across restmap.conf, web.conf, api.js, tools.conf (endpoint_name + description URLs) and autoregister.py TOOLS (endpoint paths), and add the same lockstep rule to finding 13/77's spec (tool description/inputSchema must track any cim_mapping contract change). tools.conf's own header already warns
- **[medium] No Docker dev stack or Makefile despite the skill requiring one — no reproducible local Splunk for testing or the .conf26 PLA1040 demo**  
  Add a docker-compose dev stack (Splunk 10 image, stage/ bind-mount per SKILL.md section 5, Splunk_SA_CIM installed, sample data seed) plus a Makefile target, and rehearse the full wizard flow (index select, AI detection with a configured OpenRouter key, PII scan, CIM mapping) against it before .conf26. Needs a live container run to verify, hence st

## Deferred (needs live Splunk or owner decision)

- **[low] No capability gating on endpoints that spend money via the system-auth OpenRouter key**  
  Consider adding 'capability=<custom_capability>' (with a matching [capability::] in authorize.conf) or at least an acl on the script stanzas so paid AI calls require an admin-granted role. Needs a user decision on the desired access model, and a live instance to verify enforcement.
- **[low] App icons land in app-root static/, not appserver/static/ as the skill baseline states (informational — assets are otherwise correct)**  
  Confirm against the current AppInspect icon check on the next API run; if root static/ passes (expected), update the skill reference rather than the app.
- **[high] Self-hosted runner on a PUBLIC repo with secrets and mutable workflow refs**  
  Either move CI to GitHub-hosted runners, or keep self-hosted but: restrict runner to this repo with an ephemeral/containerised runner, pin reusable workflows and actions to commit SHAs, scope the permissions block per-job (package needs none of pull-requests/actions/checks write), and confirm 'Requi
- **[low] AppInspect expect comment references an unverifiable ticket ID "APPCERT-123"**  
  Confirm with the owner whether APPCERT-123 is a real support/cert ticket; if not, remove the fake ID or replace with the genuine reference.
- **[low] No MCP tools documentation — expected once tools.conf lands (known gap)**  
  When tools.conf is added: document each tool (ai_detection, pii_detection, cim_mapping) with endpoint_name ↔ [script:] mapping and full servicesNS URLs in the endpoint docs; update README.md Key Features and docs/README.md index; document the trigger CI already stages ([triggers] reload.tools = http
- **[medium] GitHub default branch main contains none of the releases: v1.0.1-v1.0.4 and all recent work live only on develop**  
  Decide the branch model: either merge/fast-forward develop into main (reconciling the two main-only commits) so the default branch reflects the Splunkbase 1.0.4 release, or flip the GitHub default branch to develop. Do this before .conf26 PLA1040 sends people to the repo.
- **[low] Two dependabot PRs stale-open for 7-8 months (#10 actions/checkout 6, #11 actions/upload-artifact 6)**  
  Merge or close both once the CI build is repaired (confirmed finding 44 — CI is currently broken, so these cannot be validated today). Merging them will also stop dependabot re-pinging.
- **[low] Launcher route is /app/cim-plicity/main, not the skill-mandated /app/<appId>/home**  
  Owner decision: either add a home.xml alias view using the same template (keeping main as default) to converge on the convention without breaking URLs, or record cim-plicity as a grandfathered exception in the skill. Do not rename main outright on a published app.
## Refuted findings (2)

- "Ignore cache commit hides a runtime cache": refuted, the commit only gitignores `__pycache__`; the loader is read-only.
- "numpy 2.0.2 with thinc >=8.1 risks a numpy-1-built thinc": refuted from wheel metadata, the pinned spacy 3.8.7 wheel requires thinc >=8.3.4 which is numpy-2 built.

## Follow-ups (not part of this review's changes)

1. **UCC App Builder integration** (tracked as a task): now that CIMplicity's endpoints are MCP
   tools, wire the Builder's agent chat to call `cim_mapping`/`pii_detection`/`ai_detection`
   during add-on authoring, or share the React components/Python lib. Needs a live Splunk with
   both apps plus the Splunk MCP Server.
2. **skill drift**: `splunk-react-app/references/cimplicity-patterns.md` still documents the
   wrong `handler = application.ClassName` pattern (contradicts SKILL.md section 2 and this
   review's fix). Also worth adding: the persistconn print()-corruption lesson and the
   ucc-gen 6.x purge-crash pin. Skill edits need explicit approval.
3. **Repo branch strategy**: GitHub default branch `main` contains none of the v1.0.1-v1.0.4
   releases; `develop` is the real mainline. Decide and align (or retarget default branch).
4. **eslint in CI**: wire `no-console`/`no-unused-vars` to prevent regression of the cleanups.
5. **Live-Splunk verification of the MCP port** (see docs/MCP_TOOLS.md caveats): trigger fire on
   install/enable, Cloud native registration, `$arg$` body templates, ping path dispatch.

## Appendix A: verified findings (110 confirmed, 2 refuted)

Severity: C=critical H=high M=medium L=low. Action: fix-now (actioned in this review), stage-spec (needs a coordinated or user-approved change), defer (needs live Splunk or a user decision).


### Backend (persistent REST) (18)

- **[H/fix-now]** Compiled binary _lsprof.cpython-39-x86_64-linux-gnu.so shipped in bin/ — AppInspect Cloud binary-file failure risk  
  `ucc-app/bin/_lsprof.cpython-39-x86_64-linux-gnu.so` — Delete ucc-app/bin/_lsprof.cpython-39-x86_64-linux-gnu.so from the repo (it is unused) and add an exclusion in the packaging step for *.so under bin/ as a belt-and-braces measure.
- **[H/fix-now]** print() calls inside the persistent-REST process corrupt the persistconn stdout protocol  
  `ucc-app/lib/pii_detection_logic.py:105` — Replace every print() in lib/pii_detection_logic.py with the logging calls that already sit beside them (most lines have a duplicate logging.* call, so the prints can simply be deleted). Audit bin/ and lib/ for any other stdout writes reachable from a persistent handler.
- **[H/fix-now]** OpenRouter API key written to log file in plaintext  
  `ucc-app/bin/ai_detection.py:112` — Delete the line (or log only 'api_key present: bool'). Also review lines 62 and 121 which log the whole settings conf object.
- **[H/fix-now]** ai_detection.handle parses input and auth outside any try block — malformed input or missing session key crashes instead of returning 400/401 JSON  
  `ucc-app/bin/ai_detection.py:325` — Wrap the parse in try/except returning {'payload': {'error': ...}, 'status': 400}, and return status 401 with structured JSON when system_authtoken is missing, mirroring cim_mapping.py:152-155. Narrow the misleading KeyError handler.
- **[H/fix-now]** load_cim_models reads the wrong directory — dynamic CIM loading never activates on a real Splunk_SA_CIM install  
  `ucc-app/bin/load_cim_models.py:110` — Point models_dir at default/data/models (optionally merged with local/data/models), unwrap comment dicts (comment.get('description') when isinstance dict, falling back to description/displayName/name), and update test_load_cim_models.py fixtures to match the real layout and comment shape.
- **[H/fix-now]** ai_detection.call_openrouter fallback path is broken: account_conf_file undefined when conf read fails, bare except, dead default model  
  `ucc-app/bin/ai_detection.py:128` — Fetch the conf once (it is already fetched in get_ai_secret's ConfManager), bind api_endpoint and model with explicit defaults before the requests.post, and replace the bare except with 'except Exception as e' + logging.
- **[H/fix-now]** normalize_ai_response elif chain discards AI-provided time_prefix and max_timestamp_lookahead whenever time_format is present  
  `ucc-app/bin/ai_detection.py:301` — Make the three checks independent ifs (keep the timestamp_analysis fallback branch for models that nest them).
- **[H/fix-now]** generate_combined_regex silently degenerates to a re.escape of the whole sample because Python re rejects the PCRE (?<name>) groups the prompt mandates  
  `ucc-app/bin/ai_detection.py:168` — Before re.search, translate PCRE named groups to Python syntax (regex.replace('(?<', '(?P<') guarding against (?<= / (?<! lookbehinds), and log dropped fields instead of bare 'except: continue'. Return an error or null rather than an escaped-literal pattern when no field could be positioned.
- **[M/fix-now]** restmap.conf handler module names wrong (application.AiDetection / application.PiiDetection) — works only by accident  
  `ucc-app/default/restmap.conf:5` — Change to 'handler = ai_detection.AiDetection' and 'handler = pii_detection.PiiDetection' to match the documented <SCRIPT>.<CLASSNAME> convention and the baseline. Note the auto-discovery also means each handler module must contain exactly one PersistentServerConnectionApplication subclass ('More than one class implements...' raises), so keep the one-module-per-endpoint rule.
- **[M/fix-now]** web.conf has no [expose:cim_mapping] — splunkweb-proxied calls to the cim_mapping endpoint 404  
  `ucc-app/default/web.conf:19` — Add '[expose:cim_mapping]\npattern = cim_mapping\nmethods = POST' to web.conf so the registered endpoint is reachable through Splunk Web like its siblings.
- **[M/fix-now]** pii_detection returns 400 'Malformed input' when the session key is missing instead of 401  
  `ucc-app/bin/pii_detection.py:106` — Split the checks: JSON parse failure → 400; missing system_authtoken → {'error': 'No session key provided'} with status 401 (as cim_mapping.py already does).
- **[M/fix-now]** ai_detection opens an unused splunklib client connection on every request and fails the request if it cannot  
  `ucc-app/bin/ai_detection.py:329` — Delete the client.connect block and self.service, along with the now-unneeded splunklib.client import.
- **[M/stage-spec]** cim_mapping returns AI-service errors with HTTP 200 and ignores the shipped api_endpoint/model settings  
  `ucc-app/bin/cim_mapping.py:168` — Return 4xx/5xx when call_openrouter yields an error dict (400 for invalid model, 502/504 for AI-service failures), source api_endpoint and model from cim-plicity_settings, and decide the endpoint's fate: either wire CIMMapping.jsx to call it (aligning model ids with the dynamic keys and serving the dynamically loaded fields to the UI) or drop the stanza. Because it changes a request/response contr
- **[M/stage-spec]** Bare non-app-scoped [script:]/[expose:] names and match paths violate the skill's naming convention  
  `ucc-app/default/restmap.conf:1` — Rename to app-prefixed stanzas (e.g. [script:cimplicity_ai_detection]) with match = /cim_plicity/ai_detection etc, updating web.conf expose patterns and api.js postToEndpoint paths in the same change. This alters live URLs the UI depends on, so implement both sides together with a round-trip test.
- **[M/fix-now]** Shipped log_level = DEBUG and handlers hardcode DEBUG logging, ignoring the setting  
  `ucc-app/default/cim-plicity_settings.conf:8` — Ship log_level = INFO as the default and make the handlers read the [logging] stanza (solnlib conf_manager or splunktaucclib get_log_level) to set the effective level; use per-app named loggers rather than root basicConfig.
- **[M/fix-now]** PII test files cannot fail: assertion-free tests and a file-structure check probing nonexistent paths  
  `ucc-app/bin/test_pii_standalone.py:129` — Convert returns to asserts, fix the file-structure paths (or drop that test), skip-or-install scrubadub explicitly (pytest.importorskip) so the real detection path is exercised, and change f.start/f.end to f.beg/f.end in pii_detection_standalone.py. Only test_load_cim_models.py has real assertions, and those encode the wrong CIM layout (see the load_cim_models finding).
- **[L/fix-now]** Dead imports and stale sys.path entries across all three handlers  
  `ucc-app/bin/ai_detection.py:31` — Trim the import blocks to what each handler actually uses (json, os, sys, re, logging, requests, conf_manager, PersistentServerConnectionApplication) and remove the stale 3rdparty sys.path insert.
- **[L/defer]** No capability gating on endpoints that spend money via the system-auth OpenRouter key  
  `ucc-app/default/restmap.conf:15` — Consider adding 'capability=<custom_capability>' (with a matching [capability::] in authorize.conf) or at least an acl on the script stanzas so paid AI calls require an admin-granted role. Needs a user decision on the desired access model, and a live instance to verify enforcement.

### Frontend (React UI) (25)

- **[C/fix-now]** Broken unused import of non-existent module breaks the webpack build  
  `packages/ci-mplicity-home/src/CiMplicityHome.jsx:16` — Delete line 16 of CiMplicityHome.jsx (`import App from '../../../../../src/App';`). Dead import; `App` (uppercase) is never referenced and the path escapes the repo.
- **[H/fix-now]** ReferenceError: setAiFieldResults is not defined when editing the combined regex  
  `packages/ci-mplicity-home/src/FieldExtraction.jsx:1168` — Lift the edit via an `onCombinedRegexChange` prop from CiMplicityHome (which owns aiFieldResults via useState at CiMplicityHome.jsx:498), or hold a local editedCombinedRegex state initialised from the prop. Either is safe; the parent-owned option keeps handleAcceptCombinedRegex reading the edited value.
- **[H/fix-now]** ReferenceError: theme is not defined in combined-regex preview inline styles  
  `packages/ci-mplicity-home/src/FieldExtraction.jsx:1187` — Replace the inline-styled div/pre (1184-1197) with the already-defined StyledPreviewBox styled-component; note StyledPreviewBox itself uses theme.backgroundColorSecondary which resolves undefined (see finding 9), so use @splunk/themes variables there too.
- **[H/fix-now]** XSS: raw log data injected via dangerouslySetInnerHTML without escaping  
  `packages/ci-mplicity-home/src/FieldExtraction.jsx:1234` — HTML-escape the base text and the interpolated field values/title attributes before inserting highlight spans in highlightExistingFields (659-696) and highlightFieldsInSample (944-979), or better render highlights as React elements. Also delete or escape the dead HTML-building branch in extractFieldsWithRegex (619-627).
- **[H/fix-now]** Python-to-JS named-group conversion is wrong: (?P< becomes \(?< (escaped paren)  
  `packages/ci-mplicity-home/src/FieldExtraction.jsx:837` — Change the replacement to '(?<' at all four sites (837, 867, 893, 948), ideally via a shared pythonToJsNamedGroups() helper mirroring ConfigurationGenerator's convertToPCRE2NamedGroups (lines 47-50) which correctly does the inverse.
- **[H/fix-now]** Raw HTML form controls and headings instead of @splunk/react-ui components  
  `packages/ci-mplicity-home/src/PIIDetection.jsx:268` — As proposed: Switch/Checkbox for the redact toggle, ControlGroup + Text for the custom-pattern form, Select/Select.Option for TIME_FORMAT, Heading for section titles, Message type="error" for errors. The Modal suggestion for the custom-pattern form matches the skill's Modal guidance (returnFocus, closeOnClickAway={false}) but is optional; an inline ControlGroup form is also compliant.
- **[H/stage-spec]** Branch goal unwired: dynamic CIM field loading has no frontend consumer and cim_mapping is not exposed in web.conf  
  `packages/ci-mplicity-home/src/CIMMapping.jsx:20` — Frontend spec still needed, but update it: (1) web.conf `[expose:cim_mapping] pattern = cim_mapping, methods = POST` ALREADY exists as an uncommitted working-tree change — keep/commit it; do NOT change methods to GET (the handler is POST-only). (2) The cim_mapping endpoint is an AI mapping-suggestion endpoint (POST {extractedFields, cimModel} → OpenRouter suggestions, cim_mapping.py:148-170); it h
- **[M/fix-now]** api.js postToEndpoint bypasses splunk-utils conventions with hardcoded app name and pre-namespaced path  
  `packages/ci-mplicity-home/src/utils/api.js:85` — Use `createRESTURL(endpoint, { app })` with config-derived app and drop APP_NAME; with {app} and no owner, createRESTURL emits /servicesNS/-/cim-plicity/<endpoint> — byte-identical to today's URL, so the change is provably safe. Also delete the empty callApiWithRetry stub (140-142 + trailing comment 144) and the unused postRequest/deleteRequest exports.
- **[M/fix-now]** styled-components read non-contract theme keys instead of @splunk/themes variables  
  `packages/ci-mplicity-home/src/CiMplicityHome.jsx:57` — Import { variables } from '@splunk/themes' and replace ALL `${({ theme }) => theme.*}` accesses (not just the listed keys) with variables.* functions, matching StartStyles.js. Note variables.backgroundColorSecondary and variables.backgroundColorSelected do not exist in themes 1.x — substitute e.g. variables.backgroundColorSection/backgroundColorPage and variables.interactiveColorPrimary or focusCo
- **[M/fix-now]** Hardcoded light-theme colours break dark theme throughout  
  `packages/ci-mplicity-home/src/PIIDetection.jsx:29` — As proposed: replace hardcoded hex with @splunk/themes variables.* tokens; for the highlight palette and quality badges pick token-derived colours readable in both schemes.
- **[M/fix-now]** Data-driven views missing visible error states (indexes/sourcetypes fetch errors swallowed)  
  `packages/ci-mplicity-home/src/CiMplicityHome.jsx:213` — As proposed: add error state + dismissable Message type="error" for index/sourcetype load failures, an empty-state hint, and convert the red-paragraph ErrorMessage usages to Message.
- **[M/fix-now]** SearchJob subscription leak: cleanup returned from a click handler is discarded  
  `packages/ci-mplicity-home/src/CiMplicityHome.jsx:375` — As proposed: keep the fetch subscription in a ref, unsubscribe in a useEffect unmount cleanup, and pass an AbortController signal to getRequest in the indexes effect (api.js getRequest already accepts `signal`, line 38-43).
- **[M/fix-now]** CIMMapping mode toggle initialises mappings with the stale mode (side effect inside setState updater)  
  `packages/ci-mplicity-home/src/CIMMapping.jsx:207` — As proposed: compute newMode outside the updater and pass it explicitly — `initializeFieldMappings(newMode)` (change the function to accept a mode param defaulting to state) — or drive initialisation from an effect keyed on mappingMode.
- **[M/fix-now]** Unit tests are stale (assert removed UI) and 3 of 4 suites lack a jsdom environment  
  `packages/ci-mplicity-home/jest.config.js:1` — As proposed: add testEnvironment: 'jsdom' + @splunk package mocks to jest.config.js immediately; rewriting the four suites against the current UI and adding FieldExtraction/api.js coverage is the follow-on work.
- **[M/fix-now]** Toast wiring broken: window.createToast never exists and duplicate ToastMessages containers  
  `packages/ci-mplicity-home/src/FieldExtraction.jsx:820` — As proposed: one shared module-level `createToast = makeCreateToast(Toaster)` helper (pattern already in ConfigurationGenerator.jsx:16), use it in FieldExtraction, and keep the single <ToastMessages /> in CiMplicityHome (drop ConfigurationGenerator's line 770).
- **[M/fix-now]** resetFlow leaves stale extractionRegex and timeSettings for the next run  
  `packages/ci-mplicity-home/src/CiMplicityHome.jsx:596` — As proposed: reset extractionRegex to null and timeSettings/piiDetectionState to module-level initial-shape constants in resetFlow. Consider also resetting them in handleDataSubmit, which similarly clears other state (548-551) but not extractionRegex/timeSettings, so re-entering step 1 without Finish has the same staleness.
- **[M/fix-now]** Undeclared direct dependency @splunk/react-icons; @splunk/splunk-utils misfiled in devDependencies  
  `packages/ci-mplicity-home/package.json:1` — As proposed: add @splunk/react-icons (^5.0.0 to match react-ui 5's transitive) to dependencies and move @splunk/splunk-utils from devDependencies to dependencies in packages/ci-mplicity-home/package.json.
- **[M/fix-now]** Stepper and table controls not keyboard-accessible; inputs lack associated labels  
  `packages/ci-mplicity-home/src/CiMplicityHome.jsx:132` — As proposed: make StyledStep a real button (or add role="button", tabIndex={0}, onKeyDown for Enter/Space plus aria-current/aria-disabled), use ControlGroup for the form fields so labels are wired, and Switch/Checkbox with label children for toggles.
- **[L/fix-now]** Template title says 'CimPlicity Demo App' and links a non-existent apple-touch-icon  
  `ucc-app/appserver/templates/main.html:8` — Set the title to 'CIMplicity AI' and remove the apple-touch-icon link (there is no packaged apple-touch-icon; static icons are appIcon*.png under ucc-app/static which map to appserver/static, not a root-relative apple-touch-icon.png).
- **[L/fix-now]** Production console.log debug spam with emoji markers throughout the flow  
  `packages/ci-mplicity-home/src/CiMplicityHome.jsx:301` — As proposed: strip the console.log statements (keep console.error/warn for genuine failures) or gate behind a DEBUG flag. Wiring eslint no-console would prevent regression.
- **[L/fix-now]** Substantial dead code: unused AI-field editing handlers, fake API, undefined applyExtractions, unused imports and outputs  
  `packages/ci-mplicity-home/src/ConfigurationGenerator.jsx:762` — As proposed: delete the dead paths (or deliberately finish the AI per-field editing UI, since handlers 719-858 look like an amputated feature); the latent applyExtractions ReferenceError in validateConfigs should go regardless. Add eslint no-unused-vars to CI.
- **[L/fix-now]** Unescaped user values interpolated into SPL search strings  
  `packages/ci-mplicity-home/src/CiMplicityHome.jsx:309` — As proposed: escape backslashes and double quotes (value.replace(/[\\"]/g, '\\$&')) in both interpolations, or validate the ComboBox value against the fetched option lists before searching.
- **[L/fix-now]** clipboard copy has no failure handling on non-secure origins  
  `packages/ci-mplicity-home/src/ConfigurationGenerator.jsx:733` — As proposed: feature-detect navigator.clipboard, await/then the writeText promise and only toast success on resolution, toast an error on failure, with a hidden-textarea execCommand fallback for http origins.
- **[L/fix-now]** Bootstrap error fallback injects the error via innerHTML and greeting/global.css are dead code  
  `packages/cim-plicity/src/main/webapp/pages/main/index.jsx:21` — As proposed: use textContent (or render a Message) in the getUserTheme catch; remove the unused StyledGreeting import/export; and either import global.css from the component (after tokenising its colours) or delete both the file and the app-grid/left-col/center-col/right-col classNames, keeping the MainGrid styled-component as the single layout source.
- **[L/fix-now]** Typography used for headings/paragraphs instead of Heading and Paragraph  
  `packages/ci-mplicity-home/src/CiMplicityHome.jsx:120` — Standardise on Heading (appropriate levels) + Paragraph per the skill; it is a mechanical, safe sweep. Alternatively amend the skill to bless Typography — but pick one, since Paragraph (as P) and Typography as="p" currently coexist in the same files.

### UCC, build, CI and packaging (19)

- **[C/fix-now]** CI build breaks: unpinned ucc-gen (6.5.2) crashes purging transitive numpy pulled by unpinned scrubadub  
  `.github/workflows/splunk-app-ci.yml:36` — Pin `pip install splunk-add-on-ucc-framework==<last-known-good>` in .github/workflows/splunk-app-ci.yml:36 and docs/BUILD_GUIDE.md:24,40 (5.69.1 verified to predate the fragile RECORD-based package removal; 6.0.1+ all crash), and pin ucc-app/lib/requirements.txt fully (scrubadub==2.0.1 plus transitives, pip-compile vs py3.9). Note ucc-gen 6.5.2 exits 0 on this crash, so also consider a CI assertio
- **[H/fix-now]** Production package is built with webpack development mode + eval-source-map  
  `packages/cim-plicity/bin/build.js:28` — Make the nix build use `NODE_ENV=production` and `--mode=production`, and drop/gate `devtool: 'eval-source-map'` to development only (e.g. `devtool: process.env.NODE_ENV === 'production' ? false : 'eval-source-map'`). Verify with a local `yarn run build` and grep the emitted main.js for `eval(`.
- **[H/fix-now]** CI .so cleanup glob is a no-op for nested files (globstar off) and would break the app if it worked  
  `.github/workflows/splunk-app-ci.yml:111` — Replace the glob (now splunk-app-ci.yml:136) with an explicit `find temp-package/cim-plicity/lib -name '*.so' -not -path '*/3rdparty/*' -delete`, and decide per-library whether compiled deps must ship (anything whose .so is deleted must not remain in lib/ as a half-broken package). Note the current glob already silently deletes the 6 two-level .so files — audit whether any of those are load-bearin
- **[H/stage-spec]** 355MB unpinned dependency tree (scrubadub → scikit-learn/scipy/numpy/nltk + solnlib's grpcio/opentelemetry) ships in lib/  
  `ucc-app/lib/requirements.txt:4` — Write a spec for the runtime dependency set: pin every package (pip-compile against py3.9), evaluate whether scrubadub's sklearn-backed detectors are used (if not, vendor only the needed detectors or exclude), strip *-tests/tests dirs and dist-info junk in the packaging step, and record the intended package size. Needs a live Splunk round-trip of pii_detection/ai_detection to confirm nothing requi
- **[H/fix-now]** Tracked binary ucc-app/bin/_lsprof.cpython-39-x86_64-linux-gnu.so is unreferenced yet shipped and waived with a false justification  
  `ucc-app/bin/_lsprof.cpython-39-x86_64-linux-gnu.so` — Delete the file from git, drop the corresponding waiver from .appinspect.expect.yaml (keep the file only if some undocumented profiling workflow needs it, in which case document it), and re-run the appinspect CLI job to confirm the check passes clean.
- **[H/stage-spec]** No MCP tools.conf registration for the app's REST endpoints (drift from newest ucc-app-builder pattern)  
  `ucc-app/default` — An implementation matching the recommendation already exists uncommitted in the working tree (ucc-app/default/tools.conf, ucc-app/bin/autoregister.py, restmap.conf/web.conf additions, CI [triggers] patch). Review it against the ucc-app-builder baseline (endpoint_name ↔ [script:] verified consistent), commit it, and verify end-to-end tool registration on a live Splunk instance (Enterprise autoregis
- **[M/fix-now]** Version scheme incoherent: branch builds hardcode 1.0.0 below released v1.0.4; committed globalConfig meta.version is stale 0.0.0+hash  
  `.github/workflows/splunk-app-ci.yml:46` — Derive TAG_VERSION from `git describe --tags --abbrev=0` (strip leading v, fallback 0.0.0) at splunk-app-ci.yml:46; commit the pending globalConfig.json version/schema update; align ucc-app/app.manifest id.version. Also delete or normalise the stray unprefixed '1.0.0' git tag so describe-based versioning is unambiguous, and check whether the stage VERSION file needs the same sed.
- **[M/fix-now]** Stale ucc-app/requirements.txt (numpy==2.0.2, wheel URLs) is unused by ucc-gen but ships at package root, contradicting real pins  
  `ucc-app/requirements.txt:4` — Delete ucc-app/requirements.txt (or move genuinely-needed dev/test pins to a repo-root requirements-dev.txt outside the UCC source dir) so it neither ships nor suggests numpy 2.0.2 is the packaged version.
- **[M/fix-now]** Four test_*.py files ship inside package bin/  
  `ucc-app/bin/test_pii_logic.py` — Move the tests to a repo-level tests/ directory (with a conftest.py adding ucc-app/bin and ucc-app/lib to sys.path) and run them in CI before packaging; verify with pytest locally.
- **[M/fix-now]** No generic dotfile/junk exclusion or 755/644 permission normalisation at packaging  
  `.github/workflows/splunk-app-ci.yml:112` — Add generic cleanup before `ucc-gen package`: `find temp-package -name '.*' -not -name '.' -not -path '*/3rdparty/*required*' -exec rm -rf {} +` (reviewing hits), plus `find temp-package -type d -exec chmod 755 {} \;` and `-type f -exec chmod 644 {} \;`, replacing the hardcoded .f2py_f2cmap lines.
- **[M/fix-now]** app.manifest releaseNotes.uri is "" (empty string) instead of null — SLIM validation risk  
  `ucc-app/app.manifest:40` — Set `"uri": null` in ucc-app/app.manifest (releaseNotes.text README.txt is fine — the file ships at package root). Confirm via the quality-appinspect-api job or `slim validate`.
- **[M/fix-now]** publish-gh does not depend on the API/SLIM AppInspect job  
  `.github/workflows/splunk-app-ci.yml:160` — Change publish-gh to `needs: [appinspect, quality-appinspect-api]`.
- **[L/fix-now]** Dead CI patch for nonexistent splunk_create.conf (stale copy-paste, also in docs)  
  `.github/workflows/splunk-app-ci.yml:86` — Delete the dead block from the workflow and the two copies in docs/BUILD_GUIDE.md to stop the pattern propagating into other apps.
- **[L/fix-now]** .gitignore misses ucc-app/bin/.pytest_cache/ and ucc-app/lib/__pycache__/, which leak into local builds  
  `.gitignore:17` — Add `ucc-app/bin/.pytest_cache/`, `ucc-app/lib/__pycache__/` (or blanket `**/__pycache__/`, `**/.pytest_cache/`) to .gitignore, and delete the on-disk .pytest_cache.
- **[L/fix-now]** Dependabot pip config points at a directory with no manifest and misses the npm/yarn ecosystem  
  `.github/dependabot.yml:5` — Drop the dead `/` pip entry (or repoint after relocating dev requirements), keep `/ucc-app/lib/` once pins exist, and add an npm ecosystem entry for `/` (yarn workspaces).
- **[L/fix-now]** Tracked vendored wheel remnants packages/cim-plicity/lib/typing_extensions* are dead weight  
  `packages/cim-plicity/lib/typing_extensions.py` — Delete packages/cim-plicity/lib/ from git.
- **[L/fix-now]** Both yarn.lock and package-lock.json tracked at root (npmClient is yarn)  
  `package-lock.json` — Delete package-lock.json and add it to .gitignore.
- **[L/defer]** App icons land in app-root static/, not appserver/static/ as the skill baseline states (informational — assets are otherwise correct)  
  `ucc-app/static/appIcon.png` — Confirm against the current AppInspect icon check on the next API run; if root static/ passes (expected), update the skill reference rather than the app.
- **[L/fix-now]** Release notes README.txt is a single URL line  
  `ucc-app/README.txt:1` — Add per-version release notes (or generate from a CHANGELOG at package time) with a trailing newline, and correct the link from github.dev to github.com/livehybrid/cimplicity-ai-app.

### Security (13)

- **[C/fix-now]** Plaintext API key written to indexed Splunk log  
  `ucc-app/bin/ai_detection.py:112` — Delete the logging line (and never log api_key anywhere). Grep-verify no other handler logs the secret. This is a one-line removal, statically verifiable.
- **[H/fix-now]** XSS: raw event data injected via dangerouslySetInnerHTML in Field Extraction highlighting  
  `packages/ci-mplicity-home/src/FieldExtraction.jsx:1234` — HTML-escape the sample text first (e.g. escape &, <, >, ", ') and escape field names/values before building the highlight spans, or refactor to build React elements from match offsets instead of an HTML string. Apply to both highlight functions. Verifiable with a unit test feeding `<img onerror>` sample data.
- **[H/fix-now]** cim_mapping ignores configured api_endpoint and hardcodes openrouter.ai egress  
  `ucc-app/bin/cim_mapping.py:106` — Read api_endpoint and model from the ai_configuration stanza exactly as ai_detection.py does (share a helper). Statically verifiable; covered by existing conf defaults so no behaviour change for OpenRouter users.
- **[H/defer]** Self-hosted runner on a PUBLIC repo with secrets and mutable workflow refs  
  `.github/workflows/splunk-app-ci.yml:18` — Either move CI to GitHub-hosted runners, or keep self-hosted but: restrict runner to this repo with an ephemeral/containerised runner, pin reusable workflows and actions to commit SHAs, scope the permissions block per-job (package needs none of pull-requests/actions/checks write), and confirm 'Require approval for all outside collaborators' is set. Needs an infra decision from the owner.
- **[M/fix-now]** LLM responses derived from user event data logged to _internal  
  `ucc-app/bin/ai_detection.py:144` — Log only metadata at INFO (status code, model, response length, field count). Gate any content logging behind an explicit DEBUG level that is off by default, and even then redact sample values. Mirror the hash-only approach already used in pii_detection.py.
- **[M/stage-spec]** No authorization on custom REST endpoints that run with system credentials  
  `ucc-app/default/restmap.conf:15` — Add a custom capability in authorize.conf (e.g. `use_cimplicity_ai`), enforce with `capability.post = use_cimplicity_ai` on each [script:] stanza (or check the caller's roles from the session block in handle()), and grant it to admin/sc_admin/power by default. Requires updating restmap, authorize.conf, default.meta and documenting for the UI, so implement both sides together.
- **[M/stage-spec]** SSRF/egress surface: api_endpoint only length-validated, http:// accepted  
  `globalConfig.json:16` — Add a regex validator in globalConfig.json requiring `^https://`, and in get_ai_secret/call_openrouter reject non-https endpoints server-side (defence in depth, since conf can be edited via REST directly). Consider warning in help text that the endpoint receives raw event samples.
- **[M/fix-now]** Root logger hardcoded to DEBUG; shipped log_level = DEBUG; logging tab ignored  
  `ucc-app/default/cim-plicity_settings.conf:8` — Use solnlib.log.Logs / a named logger per handler, read log_level from the [logging] stanza via conf_manager at request time, and ship INFO as the packaged default. Statically verifiable plus existing unit tests.
- **[M/stage-spec]** ReDoS: untrusted regexes compiled and executed server-side and in browser  
  `ucc-app/lib/pii_detection_logic.py:128` — Bound the risk: cap sample text and pattern length, reject nested quantifiers heuristically or run matching in a subprocess with a hard timeout (or bundle the `regex` module — already an os-dependentLibrary — with a timeout parameter). Needs a small spec since it touches request handling behaviour.
- **[L/fix-now]** SPL injection via interpolated index/sourcetype names in client search  
  `packages/ci-mplicity-home/src/CiMplicityHome.jsx:309` — Escape backslashes and double quotes in splunkIndex/splunkSourcetype before interpolation (e.g. value.replace(/\\/g,'\\\\').replace(/"/g,'\\"')), or pass them as search-time token arguments.
- **[L/fix-now]** Unsanitised error rendered via innerHTML in page bootstrap  
  `packages/cim-plicity/src/main/webapp/pages/main/index.jsx:22` — Use `errorEl.textContent = String(e)`.
- **[L/fix-now]** Internal exception details returned to clients in 500 responses  
  `ucc-app/bin/ai_detection.py:377` — Return a generic message ('Internal error during AI detection') plus a correlation id, keeping the full traceback in the server log only (at non-DEBUG-leaking level per the logging finding).
- **[L/fix-now]** Test scripts with sample PII and print() debugging shipped in packaged bin/  
  `ucc-app/bin/test_pii_standalone.py:1` — Move test_*.py, *_standalone.py AND the stray _lsprof.cpython-39-x86_64-linux-gnu.so out of ucc-app/bin (tests to a top-level tests/ dir, delete the .so); replace print() in pii_detection_logic.py with the module logger.

### Feature branch (dynamic CIM loading) (10)

- **[H/fix-now]** Dynamic CIM loader reads a non-existent Splunk_SA_CIM path, so the feature never activates  
  `ucc-app/bin/load_cim_models.py:110` — Change models_dir to `default/data/models` and also merge `local/data/models` if present (local overrides default per stanza). Update the test fixture path in test_load_cim_models.py to match. No live Splunk_SA_CIM copy exists on this host to verify against, but the default/data/models location is the documented standard for all Splunk data model definitions.
- **[M/stage-spec]** cim_mapping endpoint has no web.conf expose and the frontend never calls it; UI keeps its own hardcoded CIM model/field lists  
  `ucc-app/default/web.conf:26` — Split: (a) fix-now-safe — add [expose:cim_mapping] pattern=cim_mapping methods=POST to web.conf to match the skill convention (additive, cannot break anything). (b) stage-spec — decide whether the UI should consume backend fields: either add a GET models/fields mode on cim_mapping (plus expose) and replace CIMMapping.jsx CIM_MODELS, or keep the UI static and note in CIMMapping.jsx that cim_mapping
- **[M/fix-now]** CIM fields loaded at module import time: an uncaught OSError kills the handler and fields never refresh  
  `ucc-app/bin/cim_mapping.py:45` — Wrap the whole body of load_cim_fields (or the call site) in try/except Exception returning _FALLBACK_CIM_FIELDS, and prefer lazy memoised loading inside handle() (e.g. module-level `_cache = None`; load on first request) so import can never fail and a handler recycle picks up newly installed CIM without a full splunkd restart.
- **[M/fix-now]** DA-ESS-ContentUpdate wrongly treated as a Splunk_SA_CIM substitute  
  `ucc-app/bin/load_cim_models.py:47` — Drop "da-ess-contentupdate" from the candidate list; keep only case-insensitive matching of Splunk_SA_CIM.
- **[M/fix-now]** Tests pass but codify the wrong CIM layout; fixture does not mirror real Splunk_SA_CIM  
  `ucc-app/bin/test_load_cim_models.py:21` — Fix the fixture path to default/data/models together with the loader fix, use real modelName forms (Network_Traffic, Databases, Vulnerabilities) and add cases for malformed JSON and a model with objects but no fields.
- **[M/fix-now]** New tests are never executed in CI  
  `.github/workflows/splunk-app-ci.yml:17` — Add a step after "Setup Python" (e.g. `pip install pytest && python -m pytest ucc-app/bin/test_load_cim_models.py -q`) before the package job proceeds. Note the packaging step already deletes *.pyc/__pycache__ from temp-package, so running tests in CI will not leak bytecode into the tarball.
- **[M/fix-now]** Invalid cimModel (and all AI errors) returned as HTTP 200 with an error payload  
  `ucc-app/bin/cim_mapping.py:170` — In handle(), detect `isinstance(results, dict) and "error" in results` and return status 400 for invalid model / 502 for AI-service failures; keep 200 only for a suggestions array.
- **[L/fix-now]** Test files ship inside the packaged app's bin/  
  `ucc-app/bin/test_load_cim_models.py` — Add `find temp-package/cim-plicity/bin -name "test_*.py" -delete` to the existing package cleanup block (covers the pre-existing test_pii_* files too).
- **[L/fix-now]** Tests mutate os.environ["SPLUNK_HOME"] without restoring it  
  `ucc-app/bin/test_load_cim_models.py:59` — Save and restore the original SPLUNK_HOME in try/finally in both tests (preserves the file's standalone __main__ runner, which plain monkeypatch would break), or use monkeypatch.setenv and drop the standalone runner.
- **[L/defer]** AppInspect expect comment references an unverifiable ticket ID "APPCERT-123"  
  `.appinspect.expect.yaml:2` — Confirm with the owner whether APPCERT-123 is a real support/cert ticket; if not, remove the fake ID or replace with the genuine reference.

### Documentation (16)

- **[H/fix-now]** cim_mapping endpoint and dynamic CIM field loading (the branch's feature) are completely undocumented  
  `ucc-app/default/restmap.conf:35` — Add a docs/CIM_MAPPING_ENDPOINT.md mirroring PII_DETECTION_ENDPOINT.md: request/response shape of cim_mapping.py, the Splunk_SA_CIM dynamic loading behaviour and fallback field set from load_cim_models.py, calculated-field capture, and the real URL (/servicesNS/-/cim-plicity/cim_mapping per the [script:...] match, as the splunk-react-app skill requires). Cross-link from README.md Key Features and 
- **[M/fix-now]** ai_detection endpoint has no documentation  
  `ucc-app/bin/ai_detection.py:316` — Add docs/AI_DETECTION_ENDPOINT.md documenting request payload ({text, description?, selected_fields?}), response schema (sourcetype/fields/combined regex/timestamp settings), OpenRouter vs local_field_extraction fallback behaviour, error shapes, and the real servicesNS URL. List it in docs/README.md.
- **[M/fix-now]** PII_DETECTION_ENDPOINT.md omits the custom_patterns request field the UI actually sends  
  `docs/PII_DETECTION_ENDPOINT.md:24` — Document custom_patterns in the request schema (shape of each pattern object as consumed by PiiDetectionLogic), add a request example, and note the 0.9 score for custom-pattern matches in the response-fields section.
- **[M/fix-now]** PII endpoint doc gives incomplete REST path instead of the real servicesNS URL  
  `docs/PII_DETECTION_ENDPOINT.md:13` — Update the doc to show the full URL form (/services/pii_detection and /servicesNS/-/cim-plicity/pii_detection) with a working curl example including auth header. Also fix "Script Location: splunk-app/ucc-app/bin/pii_detection.py" — the repo root is cimplicity-ai-app, not splunk-app.
- **[M/fix-now]** BUILD_GUIDE and QUICK_START use the stale `ucc-gen --source` invocation; CI uses `ucc-gen build`  
  `docs/BUILD_GUIDE.md:53` — Replace all five occurrences (BUILD_GUIDE.md:53,151; QUICK_START.md:11,24; docs/README.md:46) with `ucc-gen build --source ucc-app -o build/` so docs match CI and the skill's canonical build order. Note the bare form currently only warns but is slated for removal.
- **[M/fix-now]** BUILD_GUIDE describes packaging and AppInspect-fix steps that no longer exist in CI  
  `docs/BUILD_GUIDE.md:168` — Rewrite BUILD_GUIDE sections 6-8 and "Distribution Packages" to mirror the current workflow: ucc-gen package output naming, .pyc/__pycache__/.so/meson.build cleanup steps, conditional trigger logic, and remove the dead python.version sed and -latest tarball claims.
- **[M/fix-now]** QUICK_START and docs/README claim CI runs unit tests and ESLint; the pipeline has no test or lint step  
  `docs/QUICK_START.md:70` — Fix-now: correct QUICK_START.md and docs/README.md to state that tests/lint are local-only today. Separately (preferred follow-up), add a test/lint CI job after verifying the Jest suites in packages/ci-mplicity-home/src/tests pass locally.
- **[M/fix-now]** Splunkbase releaseNotes file points at github.dev instead of github.com and contains no release notes  
  `ucc-app/README.txt:1` — Fix the URL to https://github.com/livehybrid/cimplicity-ai-app and add minimal per-version release notes (or point to a maintained CHANGELOG). Optionally set releaseNotes.uri to null for schema hygiene — note the current "" has already passed Splunkbase publication once, so this part is polish not a gate.
- **[M/stage-spec]** Build-a-Thon branding and hackathon framing are stale for a Splunkbase-published app headed to .conf26  
  `README.md:234` — Reposition README.md as a released Splunkbase app (move the build-a-thon badge to an "Origins" or acknowledgments note, delete or soften the "designed for the Build-a-Thon" production caveat) and mark PRODUCT_BRIEF.md/PROBLEM_SOLVED.md as historical design docs or refresh them. Exact wording is the owner's call on positioning, so stage it rather than freelancing the messaging.
- **[L/fix-now]** README.md links to docs/DEMO_NARRATIVE.md which does not exist  
  `README.md:203` — Remove the reference or restore the file.
- **[L/fix-now]** Package READMEs link "main README" four directory levels up (broken relative link)  
  `packages/cim-plicity/README.md` — Change both links to ../../README.md.
- **[L/fix-now]** Package CHANGELOGs frozen at "0.0.1 — Release date: TBA" while the app ships as 1.0.4 on Splunkbase  
  `packages/cim-plicity/CHANGELOG.md` — Backfill CHANGELOG entries per released tag (v1.0.0-v1.0.4) or delete the stub CHANGELOGs in favour of a single root changelog feeding README.txt release notes; drop the stale 'all changes tracked here' claim. Note the true version sources: git tags via CI sed (globalConfig meta.version is a stale 0.0.0+0a19330, not 1.0.4).
- **[L/fix-now]** docs/README.md index omits half the docs and carries an orphan setup stub  
  `docs/README.md:5` — Index all docs (and the new CIM/AI endpoint docs once written); remove or merge the trailing Setup Instructions stub.
- **[L/fix-now]** scrubadub links point at the wrong GitHub org (datasnakes)  
  `docs/PII_DETECTION_ENDPOINT.md:5` — Update all four scrubadub links (PII_DETECTION_ENDPOINT.md:5,109,136 and PROBLEM_SOLVED.md:32) to https://github.com/LeapBeyond/scrubadub and https://scrubadub.readthedocs.io — verified live: the datasnakes URLs 404, the LeapBeyond/readthedocs URLs 200.
- **[L/fix-now]** Docs consistently use a stale "splunk-app/" repo root name and mislabel UCC  
  `docs/BUILD_GUIDE.md:34` — Global-replace splunk-app/ with cimplicity-ai-app (or a neutral <repo-root>), add ucc-app/ to the BUILD_GUIDE tree, fix the UCC expansion in README.md and switch the README Testing snippets to yarn.
- **[L/defer]** No MCP tools documentation — expected once tools.conf lands (known gap)  
  `ucc-app/default` — When tools.conf is added: document each tool (ai_detection, pii_detection, cim_mapping) with endpoint_name ↔ [script:] mapping and full servicesNS URLs in the endpoint docs; update README.md Key Features and docs/README.md index; document the trigger CI already stages ([triggers] reload.tools = http_post /cim-plicity/autoregister per splunk-app-ci.yml ~line 116, not plain simple) and Enterprise au

### Completeness critic (9)

- **[M/defer]** GitHub default branch main contains none of the releases: v1.0.1-v1.0.4 and all recent work live only on develop  
  `/opt/aios/apps/cimplicity-ai-app` — Decide the branch model: either merge/fast-forward develop into main (reconciling the two main-only commits) so the default branch reflects the Splunkbase 1.0.4 release, or flip the GitHub default branch to develop. Do this before .conf26 PLA1040 sends people to the repo.
- **[M/fix-now]** Orphan UCC Monitoring Dashboard: globalConfig pages.dashboard generates a view the shipped custom nav never links, and its panels would be empty anyway  
  `globalConfig.json` — Either delete the pages.dashboard block from globalConfig.json (simplest, removes a dead shipped page), or add `<view name="dashboard"/>` to ucc-app/default/data/ui/nav/default.xml AND adopt solnlib named-logger logging (already required by confirmed finding 70) so the panels populate. Pick one; do not leave the hidden page.
- **[M/stage-spec]** Cross-dimension gap: the restmap rename (finding 14) and cim_mapping contract change (findings 13/77) silently break the staged MCP layer — tools.conf endpoint_name, tool descriptions and autoregister TOOLS all hardcode the current stanza names and URLs  
  `ucc-app/default/tools.conf` — Amend finding 14's change-set to a single atomic edit across restmap.conf, web.conf, api.js, tools.conf (endpoint_name + description URLs) and autoregister.py TOOLS (endpoint paths), and add the same lockstep rule to finding 13/77's spec (tool description/inputSchema must track any cim_mapping contract change). tools.conf's own header already warns 'Keep this file in lockstep with the TOOLS table'
- **[M/stage-spec]** No Docker dev stack or Makefile despite the skill requiring one — no reproducible local Splunk for testing or the .conf26 PLA1040 demo  
  `/opt/aios/apps/cimplicity-ai-app` — Add a docker-compose dev stack (Splunk 10 image, stage/ bind-mount per SKILL.md section 5, Splunk_SA_CIM installed, sample data seed) plus a Makefile target, and rehearse the full wizard flow (index select, AI detection with a configured OpenRouter key, PII scan, CIM mapping) against it before .conf26. Needs a live container run to verify, hence stage-spec.
- **[L/defer]** Two dependabot PRs stale-open for 7-8 months (#10 actions/checkout 6, #11 actions/upload-artifact 6)  
  `.github/workflows/splunk-app-ci.yml` — Merge or close both once the CI build is repaired (confirmed finding 44 — CI is currently broken, so these cannot be validated today). Merging them will also stop dependabot re-pinging.
- **[L/fix-now]** Licence contradiction: root LICENSE and app.manifest declare Apache-2.0 but all three package.json files declare UNLICENSED  
  `package.json:3` — Set `"license": "Apache-2.0"` in all three package.json files (they stay `private: true`, so nothing publishes to npm; this is purely making the metadata truthful).
- **[L/fix-now]** Dead web.conf expose stanzas for a cim-plicity_account endpoint that does not exist  
  `ucc-app/default/web.conf:1` — Delete both cim-plicity_account expose stanzas from ucc-app/default/web.conf. Statically verifiable (nothing references the pattern).
- **[L/defer]** Launcher route is /app/cim-plicity/main, not the skill-mandated /app/<appId>/home  
  `ucc-app/default/data/ui/views/main.xml:1` — Owner decision: either add a home.xml alias view using the same template (keeping main as default) to converge on the convention without breaking URLs, or record cim-plicity as a grandfathered exception in the skill. Do not rename main outright on a published app.
- **[L/fix-now]** Staged autoregister handler returns HTTP 200 on missing auth and on all exceptions, violating the skill's 401-JSON auth gate for direct callers  
  `ucc-app/bin/autoregister.py:186` — Before committing the staged MCP work (confirmed finding 60's review), return 401 for missing session key and 500 for unexpected exceptions, keeping ok:false JSON; the reload trigger ignores the status code so nothing breaks. One-file edit, statically verifiable.

### Refuted during adversarial verification (2)

- **[branch-diff]** "Ignore cache" commit is gitignore-only; no runtime cache exists (question resolved, no defect) — refuted: The analysis is factually correct — verified: commit 4ecc067 changes only .gitignore (+1 line `ucc-app/bin/__pycache__/`), `git ls-files | grep __pycache__` returns 0 tracked entries, load_cim_models.py is read-only (no writes to app dir/dispatch/lookups) and splunk-app-ci.yml:134-135 deletes *.pyc 
- **[branch-diff]** numpy 2.0.2 bump with thinc floor still at 8.1 risks numpy-1-built thinc at runtime — refuted: REFUTED by wheel metadata. requirements.txt pins the spacy 3.8.7 cp39 wheel directly (line 12, files.pythonhosted.org URL); I downloaded that exact wheel and its METADATA declares `Requires-Dist: thinc<8.4.0,>=8.3.4`. Because spacy 3.8.7 is a hard pin in the same requirements file, pip resolution ca