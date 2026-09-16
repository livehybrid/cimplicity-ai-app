import React, { useState, useMemo } from 'react';
import PropTypes from 'prop-types';
import Button from '@splunk/react-ui/Button';
import ControlGroup from '@splunk/react-ui/ControlGroup';
import Heading from '@splunk/react-ui/Heading';
import Message from '@splunk/react-ui/Message';
import Switch from '@splunk/react-ui/Switch';
import WaitSpinner from '@splunk/react-ui/WaitSpinner';
import Table from '@splunk/react-ui/Table';
import Card from '@splunk/react-ui/Card';
import P from '@splunk/react-ui/Paragraph';
import Text from '@splunk/react-ui/Text';
import styled from 'styled-components';
import { variables } from '@splunk/themes';

const PreviewContainer = styled.div`
    margin-top: 20px;
    padding: 15px;
    background-color: ${variables.backgroundColorSection};
    border: 1px solid ${variables.borderColor};
    color: ${variables.textColor};
    border-radius: 4px;
    font-family: 'Courier New', monospace;
    font-size: 12px;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 200px;
    overflow-y: auto;
`;

const OriginalDataContainer = styled.div`
    margin-top: 10px;
    padding: 15px;
    background-color: ${variables.backgroundColor};
    border: 1px solid ${variables.borderColor};
    color: ${variables.textColor};
    border-radius: 4px;
    font-family: 'Courier New', monospace;
    font-size: 12px;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 200px;
    overflow-y: auto;
`;

const StyledPatternSection = styled.div`
    margin-top: 20px;
    border: 1px solid ${variables.borderColor};
    border-radius: 4px;
    padding: 15px;
`;

const StyledPatternForm = styled.div`
    border: 1px solid ${variables.borderColor};
    border-radius: 4px;
    padding: 15px;
    margin-bottom: 15px;
`;

const PII_TYPE_ALLOWLIST = [
    'EMAIL', 'IP_ADDRESS', 'IPADDRESSDETECTOR', 'US_BANK_NUMBER', 'CREDIT_CARD', 'CREDITCARD', 'PHONE_NUMBER', 'PHONEDETECTOR', 'SSN', 'PASSPORT', 'PERSON', 'ADDRESS', 'MAC_ADDRESS', 'IBAN', 'SWIFT_CODE', 'URL', 'URLDETECTOR', 'USER_ID', 'USERNAME', 'PASSWORD', 'TOKEN', 'API_KEY', 'ACCESS_KEY', 'SECRET_KEY', 'AWS_KEY', 'GCP_KEY', 'AZURE_KEY', 'PRIVATE_KEY', 'LICENSE_PLATE', 'MEDICAL', 'HEALTH', 'NATIONAL_ID', 'TAX_ID', 'DRIVER_LICENSE', 'VEHICLE_ID', 'DEVICE_ID', 'COOKIE', 'SESSION_ID', 'FACE_ID', 'VOICE_ID', 'FINGERPRINT', 'BIOMETRIC', 'GEOLOCATION', 'LOCATION', 'BANK_ACCOUNT', 'ROUTING_NUMBER', 'ACCOUNT_NUMBER', 'CARD_NUMBER', 'CVV', 'EXPIRY_DATE', 'SECURITY_CODE', 'PIN', 'MOTHER_MAIDEN_NAME', 'BIRTHDATE', 'BIRTH_PLACE', 'EMPLOYEE_ID', 'STUDENT_ID', 'CUSTOMER_ID', 'MEMBER_ID', 'INSURANCE_ID', 'POLICY_NUMBER', 'ORDER_ID', 'TRANSACTION_ID', 'TICKET_ID', 'RESERVATION_ID', 'BOOKING_ID', 'REFERENCE_NUMBER', 'SERIAL_NUMBER', 'IMEI', 'IMSI', 'MSISDN', 'ICCID', 'PLATE_NUMBER', 'VIN', 'REGISTRATION_NUMBER', 'OTHER' // Add more as needed
];
const PII_TYPE_IGNORELIST = [
    'DATE_TIME', 'TIME', 'DATE', 'DATETIME', 'TIMESTAMP' // Add more as needed
];

const PIIDetection = ({ onDetectPii, piiResults, piiLoading, piiError, sampleData, onContinue, onBack }) => {
    const hasData = sampleData && sampleData.trim().length > 0;

    // Support both top-level and payload-wrapped results
    const piiList = piiResults && (piiResults.pii_results || (piiResults.payload && piiResults.payload.pii_results)) || [];

    // Add state for custom PII patterns
    const [customPatterns, setCustomPatterns] = useState([]);
    const [newPatternName, setNewPatternName] = useState('');
    const [newPatternRegex, setNewPatternRegex] = useState('');
    const [showCustomPatternForm, setShowCustomPatternForm] = useState(false);

    // Add custom pattern
    const addCustomPattern = () => {
        if (newPatternName.trim() && newPatternRegex.trim()) {
            setCustomPatterns(prev => [...prev, {
                name: newPatternName.trim(),
                regex: newPatternRegex.trim(),
                type: 'CUSTOM_PATTERN'
            }]);
            setNewPatternName('');
            setNewPatternRegex('');
            setShowCustomPatternForm(false);
        }
    };

    // Remove custom pattern
    const removeCustomPattern = (index) => {
        setCustomPatterns(prev => prev.filter((_, i) => i !== index));
    };

    const filteredAndGrouped = useMemo(() => {
        if (!piiList.length) return [];
        // Filter by allow/ignore list
        const filtered = piiList.filter(item => {
            const type = (item.type || '').toUpperCase();
            if (PII_TYPE_IGNORELIST.includes(type)) return false;
            if (PII_TYPE_ALLOWLIST.length > 0 && !PII_TYPE_ALLOWLIST.includes(type)) return false;
            return true;
        });
        // Group by type
        const grouped = {};
        filtered.forEach(item => {
            const type = (item.type || '').toUpperCase();
            if (!grouped[type]) grouped[type] = { type, values: new Set(), items: [] };
            grouped[type].values.add(item.text);
            grouped[type].items.push(item);
        });
        // Convert to array
        return Object.values(grouped).map(group => ({
            type: group.type,
            values: Array.from(group.values),
            count: group.values.size,
            items: group.items
        }));
    }, [piiList]);

    // State for which PII types to redact
    const [selectedTypes, setSelectedTypes] = useState(() => {
        // Default: select all types
        const sel = {};
        filteredAndGrouped.forEach(group => {
            sel[group.type] = true;
        });
        return sel;
    });

    // Update selection if new types appear
    React.useEffect(() => {
        if (filteredAndGrouped.length > 0 && Object.keys(selectedTypes).length === 0) {
            const sel = {};
            filteredAndGrouped.forEach(group => {
                sel[group.type] = true;
            });
            setSelectedTypes(sel);
        }
    }, [filteredAndGrouped]);

    const handleToggleType = (type) => {
        setSelectedTypes(prev => ({ ...prev, [type]: !prev[type] }));
    };

    const handleApplyRedaction = () => {
        // Collect all items for selected types
        const selectedEntities = filteredAndGrouped
            .filter(group => selectedTypes[group.type])
            .flatMap(group => group.items);
        onContinue({
            results: selectedEntities,
            customPatterns: customPatterns
        });
    };

    const handleContinue = () => {
        const selectedEntities = filteredAndGrouped
            .filter(group => selectedTypes[group.type])
            .flatMap(group => group.items);
        onContinue({
            results: selectedEntities.length > 0 ? selectedEntities : filteredAndGrouped.flatMap(group => group.items),
            customPatterns: customPatterns
        });
    };

    // Generate redacted preview
    const generateRedactedPreview = () => {
        if (!sampleData || filteredAndGrouped.length === 0) return sampleData;
        
        let redactedText = sampleData;
        const selectedGroups = filteredAndGrouped.filter(group => selectedTypes[group.type]);
        
        // Sort items by position in reverse order to avoid index shifting
        const allItems = selectedGroups.flatMap(group => group.items)
            .sort((a, b) => (b.start || 0) - (a.start || 0));
        
        allItems.forEach(item => {
            if (item.text && item.start !== undefined && item.end !== undefined) {
                const before = redactedText.substring(0, item.start);
                const after = redactedText.substring(item.end);
                const redactionText = `[REDACTED_${item.type}]`;
                redactedText = before + redactionText + after;
            }
        });
        
        return redactedText;
    };

    const redactedPreview = generateRedactedPreview();

    return (
        <Card>
            <Card.Header title="PII Detection" />
            <Card.Body>
                <P>
                    Analyze the sample data for Personally Identifiable Information (PII). This helps
                    ensure that sensitive data is not indexed or is properly masked.
                </P>
                
                {/* Scan Button - Centered */}
                <div style={{ textAlign: 'left', marginTop: '20px', marginBottom: '20px' }}>
                    <Button
                        label={piiLoading ? " Scanning..." : "Scan for PII"}
                        appearance="primary"
                        onClick={() => onDetectPii(customPatterns)}
                        disabled={piiLoading || !hasData}
                        icon={piiLoading ? <WaitSpinner size="small" /> : null}
                    />
                </div>
                
                {!hasData && <P>Please provide sample data in the first step.</P>}
                {piiError && (
                    <Message appearance="fill" type="error">
                        Error: {piiError.message}
                    </Message>
                )}
                
                {/* PII Analysis Results - Now properly positioned below the button */}
                {piiList.length > 0 && (
                    <div style={{ marginTop: '20px' }}>
                        {/* Fixed contradictory logic */}
                        {filteredAndGrouped.length > 0 ? (
                            <>
                                <P>
                                    <strong>Analysis Complete:</strong> Found {filteredAndGrouped.length} type(s) of PII with {filteredAndGrouped.reduce((sum, group) => sum + group.count, 0)} total instances.
                                </P>
                                <Heading level={3} style={{ marginTop: 20, marginBottom: 10 }}>Detected PII Types</Heading>
                                <Table>
                                    <Table.Head>
                                        <Table.HeadCell>Redact?</Table.HeadCell>
                                        <Table.HeadCell>Type</Table.HeadCell>
                                        <Table.HeadCell>Values to Redact</Table.HeadCell>
                                        <Table.HeadCell>Count</Table.HeadCell>
                                        <Table.HeadCell>Regex Pattern</Table.HeadCell>
                                    </Table.Head>
                                    <Table.Body>
                                        {filteredAndGrouped.map((group) => {
                                            // Get regex pattern from the first item of this type
                                            const firstItem = group.items[0];
                                            const regexPattern = firstItem?.regex_pattern || '';
                                            
                                            return (
                                                <Table.Row key={group.type}>
                                                    <Table.Cell>
                                                        <Switch
                                                            appearance="checkbox"
                                                            selected={!!selectedTypes[group.type]}
                                                            onClick={() => handleToggleType(group.type)}
                                                            aria-label={`Redact ${group.type}`}
                                                        />
                                                    </Table.Cell>
                                                    <Table.Cell>{group.type}</Table.Cell>
                                                    <Table.Cell style={{ maxWidth: 300, wordBreak: 'break-all' }}>
                                                        {group.values.join(', ')}
                                                    </Table.Cell>
                                                    <Table.Cell>{group.count}</Table.Cell>
                                                    <Table.Cell style={{ fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all' }}>
                                                        {regexPattern}
                                                    </Table.Cell>
                                                </Table.Row>
                                            );
                                        })}
                                    </Table.Body>
                                </Table>
                                
                                {/* Redacted Preview */}
                                {redactedPreview !== sampleData && (
                                    <div style={{ marginTop: '20px' }}>
                                        <Heading level={4}>Redacted Preview</Heading>
                                        <PreviewContainer>
                                            {redactedPreview}
                                        </PreviewContainer>
                                    </div>
                                )}

                                {/* Original Sample Data */}
                                <div style={{ marginTop: '20px' }}>
                                    <Heading level={4}>Original Sample Data</Heading>
                                    <OriginalDataContainer>
                                        {sampleData}
                                    </OriginalDataContainer>
                                </div>
                                
                                <Button
                                    appearance="primary"
                                    style={{ marginTop: 16 }}
                                    onClick={handleApplyRedaction}
                                    disabled={Object.values(selectedTypes).every(v => !v)}
                                >
                                    Apply Redaction
                                </Button>
                            </>
                        ) : (
                            <div style={{ textAlign: 'center', padding: '20px' }}>
                                <P>
                                    <strong>No PII Detected</strong>
                                </P>
                                <P>No PII entities were found in the sample data.</P>
                            </div>
                        )}
                    </div>
                )}
                
                {/* Custom PII Patterns Section */}
                <StyledPatternSection>
                    <Heading level={4}>Custom PII Patterns</Heading>
                    <P>Add custom regex patterns to detect specific PII types in your data.</P>

                    {/* Custom Patterns List */}
                    {customPatterns.length > 0 && (
                        <div style={{ marginBottom: '15px' }}>
                            <Heading level={4}>Active Custom Patterns:</Heading>
                            <Table>
                                <Table.Head>
                                    <Table.HeadCell>Pattern Name</Table.HeadCell>
                                    <Table.HeadCell>Regex Pattern</Table.HeadCell>
                                    <Table.HeadCell>Action</Table.HeadCell>
                                </Table.Head>
                                <Table.Body>
                                    {customPatterns.map((pattern, index) => (
                                        <Table.Row key={index}>
                                            <Table.Cell>{pattern.name}</Table.Cell>
                                            <Table.Cell style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                                                {pattern.regex}
                                            </Table.Cell>
                                            <Table.Cell>
                                                <Button
                                                    appearance="destructive"
                                                    label="Remove"
                                                    onClick={() => removeCustomPattern(index)}
                                                />
                                            </Table.Cell>
                                        </Table.Row>
                                    ))}
                                </Table.Body>
                            </Table>
                        </div>
                    )}
                    
                    {/* Add New Pattern Form */}
                    {showCustomPatternForm ? (
                        <StyledPatternForm>
                            <Heading level={4}>Add Custom Pattern</Heading>
                            <ControlGroup label="Pattern Name" labelPosition="top" style={{ marginBottom: 10 }}>
                                <Text
                                    value={newPatternName}
                                    onChange={(e, { value }) => setNewPatternName(value)}
                                    placeholder="e.g., Employee ID, Project Code"
                                />
                            </ControlGroup>
                            <ControlGroup label="Regex Pattern" labelPosition="top" style={{ marginBottom: 10 }}>
                                <Text
                                    value={newPatternRegex}
                                    onChange={(e, { value }) => setNewPatternRegex(value)}
                                    placeholder="e.g., \\bEMP\\d{6}\\b"
                                    style={{ fontFamily: 'monospace' }}
                                />
                            </ControlGroup>
                            <div style={{ display: 'flex', gap: '10px' }}>
                                <Button
                                    appearance="primary"
                                    label="Add Pattern"
                                    onClick={addCustomPattern}
                                    disabled={!newPatternName.trim() || !newPatternRegex.trim()}
                                />
                                <Button
                                    label="Cancel"
                                    onClick={() => {
                                        setShowCustomPatternForm(false);
                                        setNewPatternName('');
                                        setNewPatternRegex('');
                                    }}
                                />
                            </div>
                        </StyledPatternForm>
                    ) : (
                        <Button
                            appearance="secondary"
                            label="Add Custom Pattern"
                            onClick={() => setShowCustomPatternForm(true)}
                        />
                    )}
                </StyledPatternSection>

                <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'space-between' }}>
                    <Button onClick={onBack} label="Back" />
                    <Button onClick={handleContinue} appearance="primary" label="Continue" />
                </div>
            </Card.Body>
        </Card>
    );
};

PIIDetection.propTypes = {
    onDetectPii: PropTypes.func.isRequired,
    piiResults: PropTypes.object,
    piiLoading: PropTypes.bool,
    piiError: PropTypes.object,
    sampleData: PropTypes.string,
    onContinue: PropTypes.func.isRequired,
    onBack: PropTypes.func.isRequired,
};

export default PIIDetection; 