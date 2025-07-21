import React, { useState, useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import Card from '@splunk/react-ui/Card';
import Button from '@splunk/react-ui/Button';
import Select from '@splunk/react-ui/Select';
import Switch from '@splunk/react-ui/Switch';
import Typography from '@splunk/react-ui/Typography';
// Box and Layout components don't exist in Splunk React UI
// Using styled-components instead
import Table from '@splunk/react-ui/Table';
import Message from '@splunk/react-ui/Message';
import Chip from '@splunk/react-ui/Chip';
import styled from 'styled-components';
import { 
    generateAutoMappings, 
    calculateMappingQuality, 
    getQualityScoreConfig 
} from './constants/mappingConstants';

const CIM_MODELS = [
    {
        id: 'authentication',
        label: 'Authentication',
        description: 'Maps authentication and authorization events, including login attempts, session management, and access control.',
        fields: ['user', 'action', 'status', 'src_ip', 'dest_ip', 'app', 'reason', 'signature', 'signature_id', 'vendor_product']
    },
    {
        id: 'change',
        label: 'Change',
        description: 'Tracks changes to systems, applications, and data, including configuration changes, updates, and modifications.',
        fields: ['object', 'command', 'status', 'user', 'app', 'reason', 'object_category', 'object_path', 'result']
    },
    {
        id: 'network_traffic',
        label: 'Network Traffic',
        description: 'Maps network communication events including connections, protocols, and data transfer.',
        fields: ['src_ip', 'dest_ip', 'src_port', 'dest_port', 'protocol', 'action', 'bytes_in', 'bytes_out', 'packets_in', 'packets_out']
    },
    {
        id: 'web',
        label: 'Web',
        description: 'Maps web server and application events including HTTP requests, responses, and errors.',
        fields: ['src_ip', 'dest_ip', 'url', 'uri_path', 'http_method', 'status', 'bytes', 'response_time', 'user_agent', 'referer']
    },
    {
        id: 'malware',
        label: 'Malware',
        description: 'Maps malware detection and analysis events from security tools.',
        fields: ['file_name', 'file_hash', 'file_path', 'signature', 'vendor_product', 'action', 'user', 'dest_ip', 'src_ip']
    },
    {
        id: 'vulnerability',
        label: 'Vulnerability',
        description: 'Maps vulnerability assessment and management events.',
        fields: ['signature', 'cve', 'severity', 'category', 'dest_ip', 'dest_port', 'vendor_product', 'description']
    },
    {
        id: 'endpoint',
        label: 'Endpoint',
        description: 'Maps endpoint security events including process execution, file operations, and system changes.',
        fields: ['user', 'process', 'process_path', 'parent_process', 'file_name', 'file_path', 'action', 'dest_ip', 'src_ip']
    },
    {
        id: 'email',
        label: 'Email',
        description: 'Maps email-related events including message flow, filtering, and security.',
        fields: ['src_user', 'recipient', 'subject', 'message_id', 'action', 'vendor_product', 'file_name', 'file_hash']
    },
    {
        id: 'database',
        label: 'Database',
        description: 'Maps database access and operation events.',
        fields: ['user', 'app', 'action', 'object', 'object_category', 'src_ip', 'dest_ip', 'query', 'vendor_product']
    },
    {
        id: 'application_state',
        label: 'Application State',
        description: 'Maps application performance and availability events.',
        fields: ['app', 'status', 'action', 'duration', 'response_time', 'error_code', 'vendor_product', 'dest_ip']
    }
];

const StyledModelSelect = styled.div`
    margin-bottom: 24px;
`;

const StyledModeToggle = styled.div`
    display: flex;
    align-items: center;
    margin-bottom: 16px;
    gap: 16px;
`;

const StyledQualityScore = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
    padding: 12px;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    background: ${({ theme }) => theme.backgroundColor};
`;

const StyledQualityBadge = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: 16px;
    background: ${props => props.color};
    color: white;
    font-weight: 500;
    font-size: 14px;
`;

const StyledAutoMappingSection = styled.div`
    margin-bottom: 24px;
    padding: 16px;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    background: ${({ theme }) => theme.backgroundColorPage};
`;

const StyledBox = styled.div`
    margin-bottom: ${props => props.marginBottom || 0}px;
    margin-top: ${props => props.marginTop || 0}px;
`;

const StyledLayout = styled.div`
    display: flex;
    gap: ${props => props.gutter || 0}px;
    margin-top: ${props => props.marginTop || 0}px;
    justify-content: ${props => props.style?.justifyContent || 'flex-start'};
`;

const StyledPanel = styled.div`
    flex: 1;
`;

const CIMMapping = ({
    extractedFields = [],
    onContinue,
    onBack,
    initialModel = '',
    initialMappings = {}
}) => {
    console.log('🗺️ CIMMapping received extractedFields:', extractedFields);
    console.log('🗺️ CIMMapping field count:', extractedFields.length);
    console.log('🗺️ CIMMapping field names:', extractedFields.map(f => f.name));
    
    const [selectedModel, setSelectedModel] = useState(initialModel);
    const [mappingMode, setMappingMode] = useState('cim'); // 'cim' or 'extracted'
    const [fieldMappings, setFieldMappings] = useState(initialMappings);
    const [autoSuggestions, setAutoSuggestions] = useState({});
    const [showAutoSuggestions, setShowAutoSuggestions] = useState(false);
    const lastModel = useRef(selectedModel);
    const lastFields = useRef(extractedFields);

    useEffect(() => {
        console.log('useEffect triggered - selectedModel:', selectedModel, 'mappingMode:', mappingMode);
        if (selectedModel && (lastModel.current !== selectedModel || lastFields.current !== extractedFields)) {
            initializeFieldMappings();
            generateAutoSuggestions();
            lastModel.current = selectedModel;
            lastFields.current = extractedFields;
        }

        // If we have an initial model, but no mappings, try to initialize
        if (initialModel && Object.keys(fieldMappings).length === 0) {
            initializeFieldMappings();
        }

    }, [selectedModel, extractedFields, mappingMode, initialModel]);

    const initializeFieldMappings = () => {
        const model = CIM_MODELS.find(m => m.id === selectedModel);
        if (!model) return;

        const newMappings = {};
        if (mappingMode === 'cim') {
            model.fields.forEach(field => {
                newMappings[field] = '';
            });
        } else {
            extractedFields.forEach(field => {
                newMappings[field.name] = '';
            });
        }
        setFieldMappings(newMappings);
        console.log('Initializing mappings for mode:', mappingMode, 'with fields:', mappingMode === 'cim' ? model.fields.length : extractedFields.length);
    };

    const generateAutoSuggestions = () => {
        const model = CIM_MODELS.find(m => m.id === selectedModel);
        if (!model) return;

        const suggestions = generateAutoMappings(extractedFields, model.fields);
        setAutoSuggestions(suggestions);
        setShowAutoSuggestions(Object.keys(suggestions).length > 0);
    };

    const handleModelChange = (e, { value }) => {
        setSelectedModel(value);
    };

    const handleModeToggle = () => {
        setMappingMode(prev => {
            const newMode = prev === 'cim' ? 'extracted' : 'cim';
            console.log('Mapping mode changing to:', newMode);
            initializeFieldMappings();
            return newMode;
        });
    };

    const handleFieldMapping = (sourceField, targetField) => {
        setFieldMappings(prev => ({
            ...prev,
            [sourceField]: targetField
        }));
    };

    const handleAcceptSuggestion = (cimField, extractedField) => {
        // Apply the mapping
        if (mappingMode === 'cim') {
            handleFieldMapping(cimField, extractedField);
        } else {
            handleFieldMapping(extractedField, cimField);
        }

        // Remove from suggestions
        const newSuggestions = { ...autoSuggestions };
        delete newSuggestions[cimField];
        setAutoSuggestions(newSuggestions);
    };

    const handleAcceptAutoMappings = () => {
        if (mappingMode === 'cim') {
            setFieldMappings(prev => ({
                ...prev,
                ...autoSuggestions
            }));
        } else {
            // For extracted mode, we need to reverse the mapping
            const reversedMappings = {};
            Object.entries(autoSuggestions).forEach(([cimField, extractedField]) => {
                reversedMappings[extractedField] = cimField;
            });
            setFieldMappings(prev => ({
                ...prev,
                ...reversedMappings
            }));
        }
        setShowAutoSuggestions(false);
    };

    const getFieldOptions = () => {
        if (mappingMode === 'cim') {
            return extractedFields.map(field => ({
                label: field.name,
                value: field.name
            }));
        } else {
            const model = CIM_MODELS.find(m => m.id === selectedModel);
            return model ? model.fields.map(field => ({
                label: field,
                value: field
            })) : [];
        }
    };

    const getSourceFields = () => {
        const model = CIM_MODELS.find(m => m.id === selectedModel);
        const result = mappingMode === 'cim' ? (model ? model.fields : []) : extractedFields.map(f => f.name);
        console.log('Getting source fields for mode:', mappingMode, 'count:', result.length);
        return result;
    };

    const calculateQualityScore = () => {
        const model = CIM_MODELS.find(m => m.id === selectedModel);
        if (!model) return 0;
        
        return calculateMappingQuality(fieldMappings, model.fields.length);
    };

    const getQualityScoreDisplay = () => {
        const score = calculateQualityScore();
        const config = getQualityScoreConfig(score);
        return { score, config };
    };

    const renderAutoSuggestionsTable = () => {
        if (!showAutoSuggestions || Object.keys(autoSuggestions).length === 0) return null;

        return (
            <StyledAutoMappingSection>
                <Typography as="h4" variant="title4" style={{ marginBottom: 8 }}>
                    🤖 Automatic Mapping Suggestions
                </Typography>
                <Typography as="p" variant="body" style={{ marginBottom: 16, opacity: 0.8 }}>
                    We found potential matches between your extracted fields and CIM fields. Review and accept these suggestions to speed up your mapping process.
                </Typography>
                
                <Table stripeRows style={{ marginBottom: 16 }}>
                    <Table.Head>
                        <Table.HeadCell>CIM Field</Table.HeadCell>
                        <Table.HeadCell>Suggested Extracted Field</Table.HeadCell>
                        <Table.HeadCell>Confidence</Table.HeadCell>
                        <Table.HeadCell>Action</Table.HeadCell>
                    </Table.Head>
                    <Table.Body>
                        {Object.entries(autoSuggestions).map(([cimField, extractedField]) => (
                            <Table.Row key={cimField}>
                                <Table.Cell>{cimField}</Table.Cell>
                                <Table.Cell>{extractedField}</Table.Cell>
                                <Table.Cell>
                                    <Chip appearance="success">High</Chip>
                                </Table.Cell>
                                <Table.Cell>
                                    <Button
                                        size="small"
                                        appearance="primary"
                                        onClick={() => handleAcceptSuggestion(cimField, extractedField)}
                                    >
                                        Accept
                                    </Button>
                                </Table.Cell>
                            </Table.Row>
                        ))}
                    </Table.Body>
                </Table>

                <StyledLayout gutter={8}>
                    <Button
                        appearance="primary"
                        onClick={handleAcceptAutoMappings}
                    >
                        Accept All Suggestions
                    </Button>
                    <Button
                        appearance="secondary"
                        onClick={() => setShowAutoSuggestions(false)}
                    >
                        Dismiss
                    </Button>
                </StyledLayout>
            </StyledAutoMappingSection>
        );
    };

    return (
        <Card style={{ width: '100%', marginTop: 24 }}>
            <Card.Header title="CIM Field Mapping" />
            <Card.Body>
                <StyledBox marginBottom={20}>
                    <Typography as="h3" variant="title3" style={{ marginBottom: 4 }}>How to use CIM Field Mapping</Typography>
                    <Typography as="p" variant="body" style={{ opacity: 0.8 }}>
                        1. <strong>Select a CIM model</strong> to map your extracted fields to Splunk's Common Information Model.<br/>
                        2. After selecting a model, choose your preferred mapping mode using the toggle:<br/>
                        • CIM → Extracted: Map each CIM field to an extracted field (recommended)<br/>
                        • Extracted → CIM: Map each extracted field to a CIM field<br/>
                        3. Review automatic suggestions and accept them or manually configure mappings.
                    </Typography>
                </StyledBox>

                <StyledModelSelect>
                    <Select
                        value={selectedModel}
                        onChange={handleModelChange}
                        placeholder="Select a CIM model..."
                        filter={false}
                        allowCreate={false}
                    >
                        {CIM_MODELS.map(model => (
                            <Select.Option key={model.id} value={model.id} label={model.label}>
                                {model.label}
                            </Select.Option>
                        ))}
                    </Select>
                    {selectedModel && (
                        <Typography as="p" variant="body" style={{ marginTop: 4, opacity: 0.8 }}>
                            {CIM_MODELS.find((m) => m.id === selectedModel)?.description}
                        </Typography>
                    )}
                </StyledModelSelect>

                {selectedModel && (
                    <>
                        {/* Quality Score Display */}
                        {(() => {
                            const { score, config } = getQualityScoreDisplay();
                            return (
                                <StyledQualityScore>
                                    <Typography as="span" variant="body" style={{ fontWeight: 500 }}>
                                        Mapping Quality:
                                    </Typography>
                                    <StyledQualityBadge color={config.color}>
                                        {score}% - {config.label}
                                    </StyledQualityBadge>
                                    <Typography as="span" variant="body" style={{ opacity: 0.8 }}>
                                        {config.description}
                                    </Typography>
                                </StyledQualityScore>
                            );
                        })()}

                        {/* Auto Suggestions Table */}
                        {renderAutoSuggestionsTable()}

                        <StyledModeToggle>
                            <Switch
                                selected={mappingMode === 'extracted'}
                                onClick={handleModeToggle}
                                label={mappingMode === 'cim' ? 'Map each CIM field to an extracted field (recommended)' : 'Map each extracted field to a CIM field'}
                            >
                                {mappingMode === 'cim' ? 'Map each CIM field to an extracted field (recommended)' : 'Map each extracted field to a CIM field'}
                            </Switch>
                            
                        </StyledModeToggle>

                        {/* Manual Mapping Table */}
                        <Table stripeRows>
                            <Table.Head>
                                <Table.HeadCell>{mappingMode === 'cim' ? 'CIM Field' : 'Extracted Field'}</Table.HeadCell>
                                <Table.HeadCell>Maps To</Table.HeadCell>
                                <Table.HeadCell>Status</Table.HeadCell>
                            </Table.Head>
                            <Table.Body>
                                {getSourceFields().map(field => {
                                    console.log('Rendering row for source:', field);
                                    const mappedValue = fieldMappings[field] || '';
                                    const isMapped = mappedValue !== '';
                                    return (
                                        <Table.Row key={field}>
                                            <Table.Cell>{field}</Table.Cell>
                                            <Table.Cell>
                                                <Select
                                                    value={mappedValue}
                                                    onChange={(e, { value }) => handleFieldMapping(field, value)}
                                                    placeholder="Select field..."
                                                    filter={false}
                                                    allowCreate={false}
                                                    label="Select field..."
                                                >
                                                    <Select.Option value="">None</Select.Option>
                                                    {getFieldOptions().map(option => (
                                                        <Select.Option key={option.value} value={option.value} label={option.label}>
                                                            {option.label}
                                                        </Select.Option>
                                                    ))}
                                                </Select>
                                            </Table.Cell>
                                            <Table.Cell>
                                                {isMapped ? (
                                                    <Chip appearance="success">Mapped</Chip>
                                                ) : (
                                                    <Chip appearance="outline">Unmapped</Chip>
                                                )}
                                            </Table.Cell>
                                        </Table.Row>
                                    );
                                })}
                            </Table.Body>
                        </Table>
                    </>
                )}

                <StyledLayout gutter={8} marginTop={32} style={{ justifyContent: 'space-between' }}>
                    <StyledPanel>
                        <Button appearance="secondary" onClick={onBack}>
                            Back
                        </Button>
                    </StyledPanel>
                    <StyledPanel>
                        <Button
                            appearance="primary"
                            onClick={() => onContinue({ model: selectedModel, mappings: fieldMappings })}
                            disabled={!selectedModel}
                        >
                            Continue to PII Detection
                        </Button>
                    </StyledPanel>
                </StyledLayout>
            </Card.Body>
        </Card>
    );
};

CIMMapping.propTypes = {
    extractedFields: PropTypes.arrayOf(PropTypes.shape({
        name: PropTypes.string.isRequired,
        type: PropTypes.string,
        sampleValue: PropTypes.string
    })).isRequired,
    onContinue: PropTypes.func.isRequired,
    onBack: PropTypes.func.isRequired,
    initialModel: PropTypes.string,
    initialMappings: PropTypes.object,
};

export default CIMMapping; 