import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import Card from '@splunk/react-ui/Card';
import Button from '@splunk/react-ui/Button';
import Typography from '@splunk/react-ui/Typography';
import TabLayout from '@splunk/react-ui/TabLayout';
import Text from '@splunk/react-ui/Text';
import ComboBox from '@splunk/react-ui/ComboBox';
import TextArea from '@splunk/react-ui/TextArea';
import File from '@splunk/react-ui/File';
import Message from '@splunk/react-ui/Message';
import ToastMessages from '@splunk/react-toast-notifications/ToastMessages';
import styled from 'styled-components';
import { getRequest, detectPii, detectFieldsWithAi } from './utils/api';
import Checkbox from '@splunk/react-ui/Checkbox';
import App from '../../../../../src/App';
import SearchJob from '@splunk/search-job';
import { app, username } from '@splunk/splunk-utils/config';
import FileJson from '@splunk/react-icons/FileJson';
import FileCsv from '@splunk/react-icons/FileCsv';
import Servers from '@splunk/react-icons/Servers';
import WaitSpinner from '@splunk/react-ui/WaitSpinner';
import FieldExtraction from './FieldExtraction';
import CIMMapping from './CIMMapping';
import PIIDetection from './PIIDetection';
import ConfigurationGenerator from './ConfigurationGenerator';

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
    background: ${({ theme }) => theme.backgroundColor};
    color: ${({ theme }) => theme.textColor};
    min-height: 100vh;
    border-right: 1px solid ${({ theme }) => theme.borderColor};
    box-shadow: 2px 0 8px 0 rgba(0, 0, 0, 0.05);
`;

const StyledLogo = styled.div`
    margin-bottom: 32px;
`;

const StyledLogoSubText = styled(Typography)`
    color: ${({ theme }) => theme.accentColor};
`;

const StyledStep = styled.div`
    display: flex;
    align-items: center;
    padding: 12px;
    margin-bottom: 8px;
    border-radius: 6px;
    cursor: ${(props) => (props.clickable ? 'pointer' : 'default')};
    background: ${(props) => (props.active ? props.theme.backgroundColorSelected : 'transparent')};
    opacity: ${(props) => (props.completed || props.active ? 1 : 0.5)};

    &:hover {
        background: ${(props) => (props.clickable ? props.theme.backgroundColorHover : 'transparent')};
    }
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
    grid-template-columns: 260px 1fr 320px;
    gap: 0;
    min-height: 100vh;
    background: ${({ theme }) => theme.backgroundColorPage};
`;

const Stepper = ({ currentStepId, onStepClick }) => (
    <StyledSidebar>
        <StyledLogo>
            <Typography
                as="h1"
                variant="title1"
                style={{ fontWeight: 'bold', fontSize: 22, letterSpacing: -1, marginBottom: 4 }}
            >
                CIMplicity AI
            </Typography>
            <StyledLogoSubText as="p" variant="smallBody" style={{ fontSize: 13 }}>
                Intelligent Data Onboarding for Splunk
            </StyledLogoSubText>
        </StyledLogo>
        {Object.values(STEPS).map((step) => (
            <StyledStep
                key={step.id}
                active={currentStepId === step.number}
                completed={step.number < currentStepId}
                clickable={step.number <= currentStepId}
                onClick={() => step.number <= currentStepId && onStepClick(step.number)}
            >
                <Typography as="span" variant="body" style={{ fontSize: 18, width: 22, display: 'inline-block', textAlign: 'center' }}>
                    {step.number < currentStepId ? '✓' : step.number}
                </Typography>
                <Typography as="span" variant="body" style={{ marginLeft: 12 }}>{step.label}</Typography>
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
                        <Typography as="div" variant="body" style={{ fontWeight: 500, textTransform: 'capitalize' }}>{type}</Typography>
                    </span>
                    <Typography as="div" variant="smallBody" style={{ display: 'block', marginTop: 4, opacity: 0.7 }}>
                        Sample {type.toUpperCase()} data
                    </Typography>
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

    useEffect(() => {
        const fetchIndexes = async () => {
            setIndexesLoading(true);
            try {
                const data = await getRequest({ endpointUrl: 'data/indexes' });
                const indexOptions = (data.entry || []).map((index) => ({
                    label: index.name,
                    value: index.name,
                }));
                setIndexes(indexOptions);
            } catch (err) {
                console.error('Failed to fetch indexes', err);
            } finally {
                setIndexesLoading(false);
            }
        };
        fetchIndexes();
    }, []);

    useEffect(() => {
        if (splunkIndex) {
            setSourcetypesLoading(true);
            setSourcetypes([]); // Clear previous sourcetypes
            const searchJob = SearchJob.create(
                {
                    search: `| metadata type=sourcetypes where index="${splunkIndex}"`,
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
        console.log('🔥 SPLUNK FETCH CLICKED!');
        console.log('Index:', splunkIndex);
        console.log('Sourcetype:', splunkSourcetype);
        
        setSplunkLoading(true);
        setSplunkError('');
        const searchJob = SearchJob.create(
            {
                search: `search index="${splunkIndex}" sourcetype="${splunkSourcetype}" | head 1`,
                earliest_time: '-24h',
                latest_time: 'now',
                adhoc_search_level: 'verbose',
            },
            {
                app,
                owner: username,
            }
        );

        const subscription = searchJob.getResults().subscribe(
            (data) => {
                console.log('🔍 SEARCH RESULTS RECEIVED:', data);
                console.log('🔍 Available fields:', data.fields?.map(f => f.name));
                
                if (data && data.results && data.results.length > 0) {
                    const raw = data.results[0]._raw;
                    
                    // Extract existing fields from the search response
                    const existingFields = [];
                    if (data.fields) {
                        console.log('🔍 Processing fields from search response...');
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
                                
                                console.log(`🔍 Added existing field: ${field.name} = ${sampleValue}`);
                            } else {
                                console.log(`🔍 Filtered out system field: ${field.name}`);
                            }
                        });
                    }
                    
                    console.log('🔍 Final existing fields:', existingFields);
                    
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

        return () => {
            subscription.unsubscribe();
        };
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
                <Typography as="p" variant="body" style={{ marginBottom: 24 }}>
                    Start by providing a sample of your log data. You can paste it directly, upload a
                    file, or fetch it from an existing Splunk index.
                </Typography>
                <TabLayout defaultActivePanelId="paste">
                    <TabLayout.Panel label="Paste Data" panelId="paste">
                        <StyledSection>
                            <Typography as="h4" variant="title4" style={{ marginBottom: 8 }}>
                                Paste Log Sample
                            </Typography>
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
                            <Typography as="h4" variant="title4" style={{ marginBottom: 8 }}>
                                Or Use a Template
                            </Typography>
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
    const [piiResults, setPiiResults] = useState(null);
    const [piiLoading, setPiiLoading] = useState(false);
    const [piiError, setPiiError] = useState(null);
    const [aiFieldResults, setAiFieldResults] = useState(null);
    const [aiFieldLoading, setAiFieldLoading] = useState(false);
    const [aiFieldError, setAiFieldError] = useState(null);
    const [piiDetectionState, setPiiDetectionState] = useState({
        fullResults: null, // full API response
        selected: [],      // array of selected redactions
        customPatterns: [], // custom regex patterns
    });
    const [timeSettings, setTimeSettings] = useState({
        timeFormat: '',
        timePrefix: '',
        maxTimestampLookahead: '25',
    });

    const handleStepClick = (stepId) => {
        if (stepId <= activeStepId) {
            setActiveStepId(stepId);
        }
    };

    const handleDataSubmit = (data, source, existingFields = null) => {
        console.log('🎯 MAIN handleDataSubmit called!');
        console.log('Data length:', data?.length || 0);
        console.log('Source:', source);
        console.log('Existing fields received:', existingFields);
        console.log('Existing fields count:', existingFields?.length || 0);
        
        setSampleData(data);
        
        // Parse sourcetype from source if it's from Splunk
        if (source && source.startsWith('splunk:')) {
            const parts = source.split(':');
            if (parts.length >= 3) {
                const sourcetype = parts[2];
                console.log('🎯 Extracted sourcetype from Splunk data:', sourcetype);
                setActualSourcetype(sourcetype);
            }
        } else {
            setActualSourcetype(null);
        }
        
        // If we have existing fields from Splunk, set them directly
        if (existingFields && existingFields.length > 0) {
            console.log('🎯 Setting existing fields as extracted fields:', existingFields);
            setExtractedFields(existingFields);
        } else {
            console.log('🎯 No existing fields provided, clearing extracted fields');
            setExtractedFields(null);
        }
        
        setCimMapping({});
        setSelectedCimModel('');
        setPiiResults(null);
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

    const handleCimModelChange = (model) => {
        setSelectedCimModel(model);
    };

    const handleCimMappingChange = (mappings) => {
        setCimMapping(mappings);
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
        setActualSourcetype(null);
        setCimMapping({});
        setSelectedCimModel('');
        setPiiResults(null);
        setAiFieldResults(null);
        setPiiDetectionState({
            fullResults: null,
            selected: [],
        });
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
                        selectedRedactions={piiDetectionState.selected}
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
                console.log('default', activeStepId);
                return null;
        }
    };

    return (
        <MainGrid className="app-grid">
            <aside className="left-col">
                <Stepper currentStepId={activeStepId} onStepClick={handleStepClick} />
            </aside>
            <main className="center-col">
                <StyledContainer>
                    <ToastMessages />
                    {renderStep()}
                </StyledContainer>
            </main>
            <aside className="right-col">
                <Card>
                    <Card.Header title="Help & Context" />
                    <Card.Body>
                        <Typography as="p" variant="body">{STEPS[Object.keys(STEPS).find(key => STEPS[key].number === activeStepId)].help}</Typography>
                        <Typography as="p" variant="body" style={{ marginTop: 8 }}>
                            <strong>Currently on:</strong> {STEPS[Object.keys(STEPS).find(key => STEPS[key].number === activeStepId)].label}
                        </Typography>
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
