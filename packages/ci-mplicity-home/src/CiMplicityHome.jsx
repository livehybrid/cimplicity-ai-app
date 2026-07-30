import React, { useState, useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import Card from '@splunk/react-ui/Card';
import Button from '@splunk/react-ui/Button';
import Heading from '@splunk/react-ui/Heading';
import Paragraph from '@splunk/react-ui/Paragraph';
import TabLayout from '@splunk/react-ui/TabLayout';
import ComboBox from '@splunk/react-ui/ComboBox';
import TextArea from '@splunk/react-ui/TextArea';
import File from '@splunk/react-ui/File';
import Message from '@splunk/react-ui/Message';
import ToastMessages from '@splunk/react-toast-notifications/ToastMessages';
import styled from 'styled-components';
import { variables } from '@splunk/themes';
import { getRequest, detectPii, detectFieldsWithAi } from './utils/api';
import SearchJob from '@splunk/search-job';
import { app, username } from '@splunk/splunk-utils/config';
import FileJson from '@splunk/react-icons/FileJson';
import FileCsv from '@splunk/react-icons/FileCsv';
import Servers from '@splunk/react-icons/Servers';
import WaitSpinner from '@splunk/react-ui/WaitSpinner';
import FieldExtraction from './FieldExtraction';
import StepGuidance from './StepGuidance';
import CIMMapping from './CIMMapping';
import PIIDetection from './PIIDetection';
import ConfigurationGenerator from './ConfigurationGenerator';

const INITIAL_PII_DETECTION_STATE = {
    fullResults: null, // full API response
    selected: [],      // array of selected redactions
    customPatterns: [], // custom regex patterns
};

const INITIAL_TIME_SETTINGS = {
    timeFormat: '',
    timePrefix: '',
    maxTimestampLookahead: '25',
};

// Escape backslashes and double quotes so user-supplied values cannot break SPL quoting
const escapeSplValue = (value) => String(value || '').replace(/[\\"]/g, '\\$&');

const STEPS = {
    dataInput: {
        number: 1, id: 'dataInput', label: 'Data Input',
        help: 'Start by providing a sample of your log data. You can paste, upload, or fetch from Splunk.'
    },
    fieldExtraction: {
        number: 2, id: 'fieldExtraction', label: 'Field Extraction',
        help: 'Extract fields from your sample data using Auto Detect, Custom Regex, or AI. Review and adjust as needed.'
    },
    cimMapping: {
        number: 3, id: 'cimMapping', label: 'CIM Mapping',
        help: 'Map your extracted fields to Splunk CIM fields for standardized analytics.'
    },
    piiDetection: {
        number: 4, id: 'piiDetection', label: 'PII Detection',
        help: 'Detect and select which PII entities to redact from your data before indexing.'
    },
    configuration: {
        number: 5, id: 'configuration', label: 'Configuration',
        help: 'Review and download your generated Splunk configuration files, including PII redaction rules.'
    },
};

const StyledContainer = styled.div`
    padding: 24px;
    max-width: 1200px;
    margin: 0 auto;
`;

const StyledSidebar = styled.div`
    padding: 24px;
    /* Brand nav: fixed to the logo's #1e1633 in both themes, so text and
       hover states are hard-coded light rather than theme variables */
    background: #1e1633;
    color: #f4f2fa;
    min-height: 100vh;
    border-right: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: 2px 0 8px 0 rgba(0, 0, 0, 0.05);
`;

const StyledLogo = styled.div`
    margin-bottom: 32px;
`;

const StyledLogoSubText = styled(Paragraph)`
    color: rgba(255, 255, 255, 0.72);
    font-size: 13px;
`;

const StyledStep = styled.button`
    display: flex;
    align-items: center;
    width: 100%;
    padding: 12px;
    margin-bottom: 8px;
    border: 0;
    border-radius: 6px;
    font: inherit;
    text-align: left;
    color: inherit;
    cursor: ${(props) => (props.disabled ? 'default' : 'pointer')};
    background: ${(props) => (props.$active ? 'rgba(255, 255, 255, 0.14)' : 'transparent')};
    opacity: ${(props) => (props.$completed || props.$active ? 1 : 0.5)};

    &:hover:not(:disabled) {
        background: rgba(255, 255, 255, 0.08);
    }

    &:focus-visible {
        outline: 2px solid ${variables.focusColor};
        outline-offset: 2px;
    }
`;

const StyledStepNumber = styled.span`
    font-size: 18px;
    width: 22px;
    display: inline-block;
    text-align: center;
`;

const StyledStepLabel = styled.span`
    margin-left: 12px;
`;

const StyledTemplateGrid = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
`;

const StyledInputGroup = styled.div`
    display: flex;
    gap: 12px;
    margin-bottom: 12px;
    align-items: center;
`;

const StyledSection = styled.div`
    margin-bottom: 16px;
`;

const StyledPanel = styled.div``;

const MainGrid = styled.div`
    display: grid;
    /* Help sidebar grows with the viewport (up to 460px) but never below the
       original 320px, so narrow screens keep today's centre-column width */
    grid-template-columns: 260px minmax(0, 1fr) clamp(320px, 26vw, 460px);
    gap: 0;
    min-height: 100vh;
    background: ${variables.backgroundColorPage};
`;

const Stepper = ({ currentStepId, onStepClick }) => (
    <StyledSidebar>
        <StyledLogo>
            <Heading
                level={2}
                style={{ fontWeight: 'bold', fontSize: 22, letterSpacing: -1, marginBottom: 4 }}
            >
                CIMplicity AI
            </Heading>
            <StyledLogoSubText>
                Intelligent Data Onboarding for Splunk
            </StyledLogoSubText>
        </StyledLogo>
        {Object.values(STEPS).map((step) => (
            <StyledStep
                key={step.id}
                type="button"
                $active={currentStepId === step.number}
                $completed={step.number < currentStepId}
                disabled={step.number > currentStepId}
                aria-current={currentStepId === step.number ? 'step' : undefined}
                onClick={() => onStepClick(step.number)}
            >
                <StyledStepNumber aria-hidden="true">
                    {step.number < currentStepId ? '✓' : step.number}
                </StyledStepNumber>
                <StyledStepLabel>{step.label}</StyledStepLabel>
            </StyledStep>
        ))}
    </StyledSidebar>
);

const SampleDataTemplates = ({ onSampleSelect }) => {
    const templates = [
        { type: 'apache', data: '192.168.1.100 - - [01/Jan/2024:12:00:00 +0000] "GET /index.html HTTP/1.1" 200 2326' },
        { type: 'json', data: '{"timestamp":"2024-01-01T12:00:00Z","level":"INFO","message":"User login successful","userId":"12345"}' },
        { type: 'csv', data: 'timestamp,level,component,message\n2024-01-01T12:00:00Z,INFO,AUTH,Login successful' },
    ];

    const getIconForType = (type) => {
        switch (type) {
            case 'json':
                return <FileJson style={{ marginRight: 8, verticalAlign: 'middle' }} />;
            case 'csv':
                return <FileCsv style={{ marginRight: 8, verticalAlign: 'middle' }} />;
            case 'apache':
                return <Servers style={{ marginRight: 8, verticalAlign: 'middle' }} />;
            default:
                return null;
        }
    };

    return (
        <StyledTemplateGrid>
            {templates.map(({ type, data }) => (
                <Button
                    key={type}
                    appearance="secondary"
                    onClick={() => onSampleSelect(data, type)}
                    style={{ width: '100%', textAlign: 'left', padding: '12px 16px' }}
                >
                    <span style={{ display: 'flex', alignItems: 'center' }}>
                        {getIconForType(type)}
                        <span style={{ fontWeight: 500, textTransform: 'capitalize' }}>{type}</span>
                    </span>
                    <span style={{ display: 'block', marginTop: 4, opacity: 0.7 }}>
                        Sample {type.toUpperCase()} data
                    </span>
                </Button>
            ))}
        </StyledTemplateGrid>
    );
};

const DataInputStep = ({ onDataSubmit }) => {
    const [selectedFile, setSelectedFile] = useState(null);
    const [fileContent, setFileContent] = useState('');
    const [pasteContent, setPasteContent] = useState('');
    const [splunkIndex, setSplunkIndex] = useState('');
    const [splunkSourcetype, setSplunkSourcetype] = useState('');
    const [splunkError, setSplunkError] = useState('');
    const [splunkLoading, setSplunkLoading] = useState(false);
    const [indexes, setIndexes] = useState([]);
    const [sourcetypes, setSourcetypes] = useState([]);
    const [indexesLoading, setIndexesLoading] = useState(false);
    const [sourcetypesLoading, setSourcetypesLoading] = useState(false);
    const [indexesError, setIndexesError] = useState(null);
    const [sourcetypesError, setSourcetypesError] = useState(null);
    const fetchSubscription = useRef(null);

    // The fetch-sample subscription outlives the click handler; clean it up on unmount
    useEffect(() => () => {
        if (fetchSubscription.current) {
            fetchSubscription.current.unsubscribe();
        }
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        const fetchIndexes = async () => {
            setIndexesLoading(true);
            setIndexesError(null);
            try {
                // count=0 lifts Splunk's default 30-entry page size so every
                // index the user can see is listed, not just the first page
                const data = await getRequest({
                    endpointUrl: 'data/indexes',
                    params: { count: 0 },
                    signal: controller.signal,
                });
                const indexOptions = (data.entry || []).map((index) => ({
                    label: index.name,
                    value: index.name,
                }));
                setIndexes(indexOptions);
            } catch (err) {
                if (err.name !== 'AbortError') {
                    console.error('Failed to fetch indexes', err);
                    setIndexesError('Failed to load indexes. Check your Splunk connection and try again.');
                }
            } finally {
                setIndexesLoading(false);
            }
        };
        fetchIndexes();
        return () => controller.abort();
    }, []);

    useEffect(() => {
        if (splunkIndex) {
            setSourcetypesLoading(true);
            setSourcetypesError(null);
            setSourcetypes([]); // Clear previous sourcetypes
            const searchJob = SearchJob.create(
                {
                    search: `| metadata type=sourcetypes where index="${escapeSplValue(splunkIndex)}"`,
                    earliest_time: '-24h',
                    latest_time: 'now',
                },
                {
                    app,
                    owner: username,
                }
            );

            const subscription = searchJob.getResults().subscribe(
                (data) => {
                    if (data && data.results) {
                        const sourcetypeOptions = data.results
                            .map((result) => ({
                                label: result.sourcetype,
                                value: result.sourcetype,
                            }))
                            .filter(option => option.value);

                        // Remove duplicates
                        const uniqueSourcetypes = Array.from(new Map(sourcetypeOptions.map(item => [item.value, item])).values());
                        setSourcetypes(uniqueSourcetypes);
                    }
                },
                (err) => {
                    console.error('Failed to fetch sourcetypes', err);
                    setSourcetypesError('Failed to load sourcetypes for this index.');
                    setSourcetypesLoading(false);
                },
                () => {
                    setSourcetypesLoading(false);
                }
            );

            return () => {
                subscription.unsubscribe();
            };
        }
        setSourcetypes([]);
        return () => {};
    }, [splunkIndex]);

    const handleSampleSelect = (data, type) => {
        setPasteContent(data);
        onDataSubmit(data, `sample:${type}`);
    };

    const handlePasteSubmit = () => {
        if (pasteContent.trim()) {
            onDataSubmit(pasteContent, 'paste');
        }
    };

    const handleFileChange = (e) => {
        const { files } = e.target;
        if (files && files.length > 0) {
            const file = files[0];
            setSelectedFile(file);

            const reader = new FileReader();
            reader.onload = (readerEvent) => {
                const content = readerEvent.target.result;
                setFileContent(content);
                onDataSubmit(content, `file:${file.name}`);
            };
            reader.onerror = (error) => {
                console.error('File reading error:', error);
            };
            reader.readAsText(file);
        }
    };

    const handleSplunkFetch = () => {
        setSplunkLoading(true);
        setSplunkError('');
        if (fetchSubscription.current) {
            fetchSubscription.current.unsubscribe();
        }
        const searchJob = SearchJob.create(
            {
                search: `search index="${escapeSplValue(splunkIndex)}" sourcetype="${escapeSplValue(splunkSourcetype)}" | head 1`,
                earliest_time: '-24h',
                latest_time: 'now',
                adhoc_search_level: 'verbose',
            },
            {
                app,
                owner: username,
            }
        );

        fetchSubscription.current = searchJob.getResults().subscribe(
            (data) => {
                if (data && data.results && data.results.length > 0) {
                    const raw = data.results[0]._raw;

                    // Extract existing fields from the search response
                    const existingFields = [];
                    if (data.fields) {
                        data.fields.forEach(field => {
                            // Filter out internal fields (starting with _), system fields, and date_* fields
                            if (!field.name.startsWith('_') &&
                                !field.name.startsWith('date_') &&
                                !['punct', 'linecount', 'timeendpos', 'timestartpos', 'splunk_server', 'splunk_server_group'].includes(field.name)) {

                                // Get sample value from the first result
                                const sampleValue = data.results[0][field.name] || 'N/A';

                                existingFields.push({
                                    name: field.name,
                                    type: inferFieldType(sampleValue),
                                    value: String(sampleValue),
                                    confidence: 1.0,
                                    source: 'splunk_existing'
                                });
                            }
                        });
                    }

                    // Pass existing fields to the data submit handler
                    onDataSubmit(raw, `splunk:${splunkIndex}:${splunkSourcetype}`, existingFields);
                } else {
                     onDataSubmit('// No results found', 'splunk');
                }
                setSplunkLoading(false);
            },
            (err) => {
                console.error('Failed to fetch sample data', err);
                setSplunkError(err.message);
                setSplunkLoading(false);
            },
            () => {
                setSplunkLoading(false);
            }
        );
    };
    
    // Helper function to infer field type from value
    const inferFieldType = (value) => {
        if (typeof value === 'number') return 'number';
        if (typeof value === 'boolean') return 'boolean';
        const str = String(value);
        if (/^\d{4}-\d{2}-\d{2}/.test(str)) return 'timestamp';
        if (/^\d+\.\d+\.\d+\.\d+$/.test(str)) return 'ip';
        if (/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(str)) return 'email';
        if (/^\d+$/.test(str)) return 'integer';
        if (/^\d+\.\d+$/.test(str)) return 'float';
        return 'string';
    };

    return (
        <Card>
            <Card.Header title="Step 1: Provide Sample Data" />
            <Card.Body>
                <Paragraph style={{ marginBottom: 24 }}>
                    Start by providing a sample of your log data. You can paste it directly, upload a
                    file, or fetch it from an existing Splunk index.
                </Paragraph>
                <TabLayout defaultActivePanelId="paste">
                    <TabLayout.Panel label="Paste Data" panelId="paste">
                        <StyledSection>
                            <Heading level={4} style={{ marginBottom: 8 }}>
                                Paste Log Sample
                            </Heading>
                            <TextArea
                                value={pasteContent}
                                onChange={(e, { value }) => setPasteContent(value)}
                                rows={8}
                                placeholder="Paste a single event or multiple lines of raw log data here."
                            />
                            <Button
                                appearance="primary"
                                onClick={handlePasteSubmit}
                                disabled={!pasteContent.trim()}
                                style={{ marginTop: 12 }}
                            >
                                Use Pasted Text
                            </Button>
                        </StyledSection>
                        <StyledSection>
                            <Heading level={4} style={{ marginBottom: 8 }}>
                                Or Use a Template
                            </Heading>
                            <SampleDataTemplates onSampleSelect={handleSampleSelect} />
                        </StyledSection>
                    </TabLayout.Panel>
                    <TabLayout.Panel label="Upload File" panelId="upload">
                        <File
                            onRequestRemove={() => setSelectedFile(null)}
                            onChange={handleFileChange}
                            name="logFile"
                            value={selectedFile}
                        />
                        {fileContent && (
                            <TextArea
                                value={fileContent}
                                readOnly
                                rows={8}
                                style={{ marginTop: 12 }}
                            />
                        )}
                    </TabLayout.Panel>
                    <TabLayout.Panel label="From Splunk" panelId="splunk">
                        <StyledPanel>
                            <StyledInputGroup>
                                <ComboBox
                                    placeholder="Select Index"
                                    value={splunkIndex}
                                    onChange={(e, { value }) => setSplunkIndex(value)}
                                    loading={indexesLoading}
                                >
                                    {indexes.map((opt) => (
                                        <ComboBox.Option key={opt.value} {...opt} />
                                    ))}
                                </ComboBox>
                                <ComboBox
                                    placeholder="Select Sourcetype"
                                    value={splunkSourcetype}
                                    onChange={(e, { value }) => setSplunkSourcetype(value)}
                                    disabled={!splunkIndex || sourcetypesLoading}
                                    loading={sourcetypesLoading}
                                >
                                    {sourcetypes.map((opt) => (
                                        <ComboBox.Option key={opt.value} {...opt} />
                                    ))}
                                </ComboBox>
                                <Button
                                    appearance="primary"
                                    onClick={handleSplunkFetch}
                                    disabled={!splunkSourcetype || splunkLoading}
                                    icon={splunkLoading ? <WaitSpinner size="small" /> : null}
                                >
                                    {splunkLoading ? 'Fetching...' : 'Fetch Sample'}
                                </Button>
                            </StyledInputGroup>
                            {indexesError && (
                                <Message appearance="fill" type="error" onRequestRemove={() => setIndexesError(null)}>
                                    {indexesError}
                                </Message>
                            )}
                            {sourcetypesError && (
                                <Message appearance="fill" type="error" onRequestRemove={() => setSourcetypesError(null)}>
                                    {sourcetypesError}
                                </Message>
                            )}
                            {!indexesLoading && !indexesError && indexes.length === 0 && (
                                <Paragraph style={{ opacity: 0.7 }}>
                                    No indexes found. Check your permissions or add data to Splunk first.
                                </Paragraph>
                            )}
                            {splunkError && <Message type="error">{splunkError}</Message>}
                        </StyledPanel>
                    </TabLayout.Panel>
                </TabLayout>
            </Card.Body>
        </Card>
    );
};

const CiMplicityHome = ({ name = 'User' }) => {
    const [activeStepId, setActiveStepId] = useState(STEPS.dataInput.number);
    const [sampleData, setSampleData] = useState('');
    const [extractedFields, setExtractedFields] = useState(null);
    const [extractionRegex, setExtractionRegex] = useState(null);
    const [actualSourcetype, setActualSourcetype] = useState(null);
    const [cimMapping, setCimMapping] = useState({});
    const [selectedCimModel, setSelectedCimModel] = useState('');
    const [piiLoading, setPiiLoading] = useState(false);
    const [piiError, setPiiError] = useState(null);
    const [aiFieldResults, setAiFieldResults] = useState(null);
    const [aiFieldLoading, setAiFieldLoading] = useState(false);
    const [aiFieldError, setAiFieldError] = useState(null);
    const [piiDetectionState, setPiiDetectionState] = useState(INITIAL_PII_DETECTION_STATE);
    const [timeSettings, setTimeSettings] = useState(INITIAL_TIME_SETTINGS);

    const handleStepClick = (stepId) => {
        if (stepId <= activeStepId) {
            setActiveStepId(stepId);
        }
    };

    const handleDataSubmit = (data, source, existingFields = null) => {
        setSampleData(data);

        // Parse sourcetype from source if it's from Splunk
        if (source && source.startsWith('splunk:')) {
            const parts = source.split(':');
            if (parts.length >= 3) {
                setActualSourcetype(parts[2]);
            }
        } else {
            setActualSourcetype(null);
        }

        // If we have existing fields from Splunk, set them directly
        if (existingFields && existingFields.length > 0) {
            setExtractedFields(existingFields);
        } else {
            setExtractedFields(null);
        }

        setExtractionRegex(null);
        setTimeSettings(INITIAL_TIME_SETTINGS);
        setCimMapping({});
        setSelectedCimModel('');
        setAiFieldResults(null);
        setActiveStepId(STEPS.fieldExtraction.number);
    };

    const handleFieldsExtracted = (fields, extractionRegex, timeSettingsArg) => {
        setExtractedFields(fields);
        if (timeSettingsArg) setTimeSettings(timeSettingsArg);
        if (extractionRegex) setExtractionRegex(extractionRegex);
    };

    const handleContinueToMapping = () => {
        setActiveStepId(STEPS.cimMapping.number);
    };

    const handleCIMMappingContinue = (data) => {
        setCimMapping(data.mappings);
        setSelectedCimModel(data.model);
        setActiveStepId(STEPS.piiDetection.number);
    };

    const handlePIIContinue = (piiSelection) => {
        // piiSelection: { results: [selected], allResults: [all], suggestion: ..., customPatterns: [...] }
        setPiiDetectionState({
            fullResults: piiSelection.allResults,
            selected: piiSelection.results,
            suggestion: piiSelection.suggestion,
            customPatterns: piiSelection.customPatterns || [],
        });
        setActiveStepId(STEPS.configuration.number);
    };

    const handleBack = () => {
        if (activeStepId > STEPS.dataInput.number) {
            setActiveStepId(activeStepId - 1);
        }
    };

    const resetFlow = () => {
        setActiveStepId(STEPS.dataInput.number);
        setSampleData('');
        setExtractedFields(null);
        setExtractionRegex(null);
        setActualSourcetype(null);
        setCimMapping({});
        setSelectedCimModel('');
        setAiFieldResults(null);
        setPiiDetectionState(INITIAL_PII_DETECTION_STATE);
        setTimeSettings(INITIAL_TIME_SETTINGS);
    };

    const handleCombinedRegexChange = (value) => {
        setAiFieldResults((prev) => (prev ? { ...prev, combined_regex: value } : prev));
    };

    const handlePiiDetection = (customPatterns = []) => {
        if (!sampleData) {
            setPiiError(new Error('No sample data to analyze.'));
            return;
        }
        setPiiLoading(true);
        setPiiError(null);
    
        detectPii(sampleData, customPatterns)
            .then(results => {
                setPiiDetectionState(prev => ({
                    ...prev,
                    fullResults: results,
                    // If user has already selected, keep selection; else, select all by default
                    selected: prev.selected && prev.selected.length > 0 ? prev.selected : (results.pii_results || []),
                    suggestion: results.suggestion || (results.payload && results.payload.suggestion),
                }));
                setPiiLoading(false);
            })
            .catch(error => {
                setPiiError(error);
                setPiiLoading(false);
            });
    };

    const handleAiFieldDetection = (description = null) => {
        if (!sampleData) {
            setAiFieldError(new Error('No sample data to analyze.'));
            return;
        }
        setAiFieldLoading(true);
        setAiFieldError(null);
        detectFieldsWithAi(sampleData, description)
            .then(results => {
                setAiFieldResults(results);
                setAiFieldLoading(false);
                setActiveStepId(STEPS.fieldExtraction.number); // Go back to field extraction
            })
            .catch(error => {
                setAiFieldError(error);
                setAiFieldLoading(false);
            });
    };

    const renderStep = () => {
        switch (activeStepId) {
            case STEPS.dataInput.number:
                return <DataInputStep onDataSubmit={handleDataSubmit} />;
            case STEPS.fieldExtraction.number:
                return (
                    <FieldExtraction
                        sampleData={sampleData}
                        existingFields={extractedFields}
                        onFieldsExtracted={handleFieldsExtracted}
                        onContinueToMapping={handleContinueToMapping}
                        onBack={handleBack}
                        onDetectFields={handleAiFieldDetection}
                        aiFieldResults={aiFieldResults}
                        aiFieldLoading={aiFieldLoading}
                        aiFieldError={aiFieldError}
                        onCombinedRegexChange={handleCombinedRegexChange}
                        showExistingTab={extractedFields && extractedFields.length > 0}
                    />
                );
            case STEPS.cimMapping.number:
                return (
                    <CIMMapping
                        extractedFields={extractedFields}
                        onContinue={handleCIMMappingContinue}
                        onBack={handleBack}
                        initialModel={selectedCimModel}
                        initialMappings={cimMapping}
                    />
                );
            case STEPS.piiDetection.number:
                return (
                    <PIIDetection
                        sampleData={sampleData}
                        extractedFields={extractedFields}
                        cimMapping={cimMapping}
                        onContinue={(selection) => {
                            // selection: { results: [selected], customPatterns: [...] }
                            const allResults = piiDetectionState.fullResults && piiDetectionState.fullResults.pii_results ? piiDetectionState.fullResults.pii_results : [];
                            const suggestion = piiDetectionState.suggestion || (piiDetectionState.fullResults && piiDetectionState.fullResults.suggestion);
                            // Always pass a consistent object
                            handlePIIContinue({
                                results: selection.results || selection, // handle both old and new format
                                allResults,
                                suggestion,
                                customPatterns: selection.customPatterns || [],
                            });
                        }}
                        onBack={handleBack}
                        onDetectPii={handlePiiDetection}
                        piiResults={piiDetectionState.fullResults}
                        piiLoading={piiLoading}
                        piiError={piiError}
                    />
                );
            case STEPS.configuration.number:
                return (
                    <ConfigurationGenerator
                        extractedFields={extractedFields}
                        cimMapping={cimMapping}
                        piiResults={{
                            results: piiDetectionState.selected,
                            allResults: piiDetectionState.fullResults && piiDetectionState.fullResults.pii_results ? piiDetectionState.fullResults.pii_results : [],
                            suggestion: piiDetectionState.suggestion,
                            customPatterns: piiDetectionState.customPatterns,
                        }}
                        sampleData={sampleData}
                        extractionRegex={extractionRegex}
                        actualSourcetype={actualSourcetype}
                        timeSettings={timeSettings}
                        onBack={handleBack}
                        onFinish={resetFlow}
                    />
                );
            default:
                return null;
        }
    };

    return (
        <MainGrid>
            <aside>
                <Stepper currentStepId={activeStepId} onStepClick={handleStepClick} />
            </aside>
            <main>
                <StyledContainer>
                    <ToastMessages />
                    {renderStep()}
                </StyledContainer>
            </main>
            <aside>
                <Card>
                    <Card.Header
                        title={`Help: ${STEPS[Object.keys(STEPS).find(key => STEPS[key].number === activeStepId)].label}`}
                    />
                    <Card.Body>
                        <StepGuidance stepId={activeStepId} />
                    </Card.Body>
                </Card>
            </aside>
        </MainGrid>
    );
};

CiMplicityHome.propTypes = {
    name: PropTypes.string,
};

Stepper.propTypes = {
    currentStepId: PropTypes.number.isRequired,
    onStepClick: PropTypes.func.isRequired,
};

export default CiMplicityHome;
