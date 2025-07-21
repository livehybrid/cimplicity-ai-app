/**
 * FieldExtraction.jsx - Splunk UI migration of prototype Field Extraction step
 * Supports: Existing fields, Auto Detect, Custom Regex, (AI tab placeholder)
 */
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import Card from '@splunk/react-ui/Card';
import Button from '@splunk/react-ui/Button';
import TabLayout from '@splunk/react-ui/TabLayout';
import Table from '@splunk/react-ui/Table';
import Text from '@splunk/react-ui/Text';
import Message from '@splunk/react-ui/Message';
import TextArea from '@splunk/react-ui/TextArea';
import Chip from '@splunk/react-ui/Chip';
import Typography from '@splunk/react-ui/Typography';
// Box and Layout components don't exist in Splunk React UI
// Using styled-components instead
import styled from 'styled-components';
import Switch from '@splunk/react-ui/Switch';
import WaitSpinner from '@splunk/react-ui/WaitSpinner';
import P from '@splunk/react-ui/Paragraph';
// Remove useTheme import
// For all inline styles that reference theme.*, move those styles into styled-components.
// For example, create new styled components for:
// - The TextArea in the AI tab (StyledTextArea)
// - The preview container (StyledPreviewBox)
// - The highlighted sample data container (StyledSampleDataBox)
// Use theme.backgroundColorPage, theme.textColor, theme.borderColor, theme.backgroundColorSecondary, etc., in these styled-components.
// Replace all inline style usages with these styled-components.
// Do not use useTheme or theme in any inline style.

const StyledHighlight = styled.span`
    background-color: ${props => props.color}20;
    border: 1px solid ${props => props.color};
    padding: 2px 4px;
    border-radius: 3px;
    font-weight: 500;
    display: inline-block;
`;

const StyledPreview = styled.div`
    background: ${({ theme }) => theme.backgroundColorPage};
    border: 1px solid ${({ theme }) => theme.borderColor};
    color: ${({ theme }) => theme.textColor};
    border-radius: 4px;
    padding: 12px;
    margin-top: 8px;
    font-family: monospace;
    font-size: 13px;
    max-height: 200px;
    overflow: auto;
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

const AiCard = styled(Card)`
    margin-top: 20px;
`;

const ResultsHeader = styled.h3`
    margin-top: 20px;
    margin-bottom: 10px;
`;

const ErrorMessage = styled(P)`
    color: red;
`;

const RegexCell = styled(Table.Cell)`
    font-family: monospace;
    font-size: 12px;
    white-space: pre-wrap;
    word-break: break-all;
`;

// Add styled-components for theme-dependent elements
const StyledTextArea = styled(TextArea)`
    font-family: monospace;
    margin-bottom: 8px;
    background-color: ${({ theme }) => theme.backgroundColorPage};
    color: ${({ theme }) => theme.textColor};
    border-color: ${({ theme }) => theme.borderColor};
`;

const StyledPreviewBox = styled.div`
    margin-top: 8px;
    padding: 8px;
    background-color: ${({ theme }) => theme.backgroundColorSecondary};
    border-radius: 4px;
    border: 1px solid ${({ theme }) => theme.borderColor};
`;

const StyledSampleDataBox = styled.div`
    padding: 12px;
    background-color: ${({ theme }) => theme.backgroundColorSecondary};
    border: 1px solid ${({ theme }) => theme.borderColor};
    border-radius: 4px;
    font-family: monospace;
    font-size: 13px;
    white-space: pre-wrap;
    color: ${({ theme }) => theme.textColor};
`;

/**
 * @param {Object} props
 * @param {string} props.sampleData - The raw log data to extract fields from
 * @param {function} props.onFieldsExtracted - Callback with extracted fields array
 * @param {function} props.onContinueToMapping - Callback to advance to next step
 * @param {function} props.onBack - Callback to go back to previous step
 * @param {Array} [props.existingFields] - Optional pre-extracted fields (e.g. from Splunk)
 * @param {string} [props.indexName] - Optional Splunk index context
 * @param {string} [props.sourcetype] - Optional Splunk sourcetype context
 * @param {bool} [props.showExistingTab] - Whether to show the existing fields tab
 */
const FieldExtraction = ({
    sampleData,
    onFieldsExtracted,
    onContinueToMapping,
    onBack,
    existingFields = null,
    indexName,
    sourcetype,
    showExistingTab = false,
    onDetectFields,
    aiFieldResults,
    aiFieldLoading,
    aiFieldError
}) => {
    console.log('🔧 FieldExtraction component rendered!');
    console.log('🔧 Sample data length:', sampleData?.length || 0);
    console.log('🔧 Existing fields received:', existingFields);
    console.log('🔧 Existing fields count:', existingFields?.length || 0);
    
    const [customRegex, setCustomRegex] = useState('');
    const [allFields, setAllFields] = useState(existingFields || []);
    const [highlightedText, setHighlightedText] = useState(sampleData || '');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [options, setOptions] = useState({
        autoDetectTypes: true,
        inferDataTypes: true,
        extractTimestamp: true,
        extractNested: true
    });
    const [aiDescription, setAiDescription] = useState('');
    const [selectedAiFields, setSelectedAiFields] = useState([]);
    const [editedRegexes, setEditedRegexes] = useState({});
    const [regexErrors, setRegexErrors] = useState({});
    const [previewedField, setPreviewedField] = useState(null);
    const [previewResults, setPreviewResults] = useState({});
    const [combinedRegexPreview, setCombinedRegexPreview] = useState(null);

    // Add new state for timestamp settings
    const [timeSettings, setTimeSettings] = useState({
        timePrefix: '',
        timeFormat: '%Y-%m-%dT%H:%M:%S',
        maxTimestampLookahead: '25'
    });

    // Add state:
    const [modifiedAiFields, setModifiedAiFields] = useState([]);

    // Initialize with existing fields from parent, but only once.
    useEffect(() => {
        console.log('🔧 useEffect: existingFields changed:', existingFields);
        if (existingFields && existingFields.length > 0) {
            console.log('🔧 Setting allFields to existingFields:', existingFields);
            setAllFields(existingFields);
        }
    }, [existingFields]);

    // Notify parent of field changes
    useEffect(() => {
        console.log('🔧 useEffect: allFields changed, notifying parent:', allFields);
        onFieldsExtracted(allFields);
    }, [allFields]);

    useEffect(() => {
        setHighlightedText(sampleData || '');
    }, [sampleData]);

    // useEffect for aiFieldResults:
    useEffect(() => {
        if (aiFieldResults?.fields) {
            setModifiedAiFields(aiFieldResults.fields);
            setSelectedAiFields(aiFieldResults.fields.map(f => f.name));
        }
    }, [aiFieldResults]);

    // --- Extraction logic ---
    function inferFieldType(value) {
        if (typeof value === 'number') return 'number';
        if (typeof value === 'boolean') return 'boolean';
        const str = String(value);
        if (/^\d{4}-\d{2}-\d{2}/.test(str)) return 'timestamp';
        if (/^\d+\.\d+\.\d+\.\d+$/.test(str)) return 'ip';
        if (/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(str)) return 'email';
        if (/^\d+$/.test(str)) return 'integer';
        if (/^\d+\.\d+$/.test(str)) return 'float';
        return 'string';
    }
    function detectPII(fieldName, value) {
        const piiPatterns = [/email/i, /ssn|social.security/i, /phone|tel/i, /credit.card|cc/i, /password|pwd/i, /user.*name|login/i];
        const valuePatterns = [/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/, /^\d{3}-\d{2}-\d{4}$/, /^\d{3}[-.]?\d{3}[-.]?\d{4}$/, /^\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}$/];
        return piiPatterns.some(p => p.test(fieldName)) || valuePatterns.some(p => p.test(value));
    }
    
    // Helper to parse a CSV line and remove quotes
    function parseCsvLine(line) {
        // This regex handles quoted fields, including commas inside them
        const regex = /(?:"([^"]*(?:""[^"]*)*)"|([^,"]*))?/g;
        const fields = [];
        let match;
        // Reset lastIndex before starting
        regex.lastIndex = 0;
        
        // We need to loop until we have consumed the entire line
        while (regex.lastIndex < line.length) {
            match = regex.exec(line);
            
            // This indicates a syntax error in the CSV line, like an unclosed quote.
            // We'll stop parsing this line to avoid infinite loops.
            if (match === null) break;
            
            // The regex has two capturing groups: one for quoted strings, one for unquoted.
            // The first group captures the content *inside* the quotes.
            // The second group captures unquoted fields.
            // We take whichever one matched. The '??' operator provides a fallback.
            fields.push(match[1]?.replace(/""/g, '"') ?? match[2] ?? '');

            // After a match, if the next character is a comma, we advance the regex index.
            // This is crucial to correctly handle empty fields (e.g., ,,)
            if (regex.lastIndex < line.length && line[regex.lastIndex] === ',') {
                regex.lastIndex++;
            }
        }
        
        return fields;
    }

    function extractFieldsAuto() {
        let newFields = [];
        let extractionRegex = null;
        setError('');
        const safeSample = sampleData || '';
        try {
            const jsonData = JSON.parse(safeSample);
            newFields = Object.entries(jsonData).map(([k, v]) => ({ 
                name: k, 
                type: inferFieldType(v), 
                value: String(v), 
                confidence: 0.95, 
                isPII: detectPII(k, String(v)),
                source: 'auto_detect',
                fromRegex: false
            }));
        } catch {
            const lines = safeSample.trim().split('\n');
            
            // Check for CSV format
            if (lines.length > 1 && lines[0].includes(',')) {
                const headers = parseCsvLine(lines[0]);
                const firstRow = parseCsvLine(lines[1] || '');
                newFields = headers.map((header, i) => ({ 
                    name: header, 
                    type: inferFieldType(firstRow[i]), 
                    value: firstRow[i] || '', 
                    confidence: 0.9, 
                    isPII: detectPII(header, firstRow[i] || ''),
                    source: 'auto_detect',
                    fromRegex: false
                }));
            } 
            // Check for Apache Common Log Format
            else if (safeSample.match(/^\d+\.\d+\.\d+\.\d+.*\[.*\].*".*".*\d+.*\d+/)) {
                // Apache Common Log Format: IP - - [timestamp] "method path protocol" status size
                const apacheRegex = /^(?<clientip>\d+\.\d+\.\d+\.\d+)\s+(?<ident>\S+)\s+(?<auth>\S+)\s+\[(?<timestamp>[^\]]+)\]\s+"(?<request>[^"]+)"\s+(?<status>\d+)\s+(?<bytes>\d+)/;
                const match = safeSample.match(apacheRegex);
                extractionRegex = apacheRegex.source;
                if (match && match.groups) {
                    const tempFields = [
                        { name: 'clientip', value: match.groups.clientip },
                        { name: 'ident', value: match.groups.ident },
                        { name: 'auth', value: match.groups.auth },
                        { name: 'timestamp', value: match.groups.timestamp },
                        { name: 'request', value: match.groups.request },
                        { name: 'status', value: match.groups.status },
                        { name: 'bytes', value: match.groups.bytes }
                    ];
                    // Parse the request field further
                    const requestParts = match.groups.request.split(' ');
                    if (requestParts.length >= 3) {
                        tempFields.push(
                            { name: 'method', value: requestParts[0] },
                            { name: 'uri', value: requestParts[1] },
                            { name: 'protocol', value: requestParts[2] }
                        );
                    }
                    newFields = tempFields.map(f => ({
                        ...f,
                        type: inferFieldType(f.value),
                        confidence: 0.95,
                        isPII: detectPII(f.name, f.value),
                        source: 'auto_detect',
                        fromRegex: false
                    }));
                    setTimeSettings({
                        timePrefix: '\\[',
                        timeFormat: '%d/%b/%Y:%H:%M:%S %z',
                        maxTimestampLookahead: '29'
                    });
                }
            }
            // Check for key-value pairs
            else {
                // Improved regex to handle quoted and unquoted values, and remove quotes from extracted values
                const kvRegex = /(\w+)=("?)([^"\s]+)\2/g;
                const matches = [...safeSample.matchAll(kvRegex)];
                newFields = matches.map(match => {
                    // Extract the value without quotes
                    const value = match[3];
                    return { 
                        name: match[1], 
                        type: inferFieldType(value), 
                        value: value, 
                        confidence: 0.8, 
                        isPII: detectPII(match[1], value),
                        source: 'auto_detect',
                        fromRegex: false
                    };
                });
            }
        }
        
        // Enhanced Syslog format detection with multiple variants
        const syslogPatterns = [
            // Standard syslog: Jan 15 10:30:00 hostname message
            { regex: /^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)$/, format: '%b %d %H:%M:%S', prefix: '^', lookahead: '15' },
            // RFC3164: <priority>timestamp hostname message
            { regex: /^<(\d+)>(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)$/, format: '%b %d %H:%M:%S', prefix: '^<\\d+>', lookahead: '15' },
            // RFC5424: <priority>version timestamp hostname app-name procid msgid message
            { regex: /^<(\d+)>(\d+)\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})?)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.*)$/, format: '%Y-%m-%dT%H:%M:%S', prefix: '^<\\d+>\\d+\\s+', lookahead: '29' }
        ];
        
        for (const pattern of syslogPatterns) {
            const match = safeSample.match(pattern.regex);
            if (match) {
                extractionRegex = pattern.regex.source;
                const baseFields = [];
                
                // Add standard syslog fields based on pattern
                if (pattern.regex.source.includes('<\\d+>')) {
                    // RFC format with priority
                    baseFields.push(
                        { name: 'priority', value: match[1] },
                        { name: 'timestamp', value: match[2] },
                        { name: 'host', value: match[3] }
                    );
                    
                    if (pattern.regex.source.includes('version')) {
                        // RFC5424 format
                        baseFields.push(
                            { name: 'version', value: match[2] },
                            { name: 'timestamp', value: match[3] },
                            { name: 'host', value: match[4] },
                            { name: 'app_name', value: match[5] },
                            { name: 'proc_id', value: match[6] },
                            { name: 'msg_id', value: match[7] },
                            { name: 'message', value: match[8] }
                        );
                    } else {
                        // RFC3164 format
                        baseFields.push(
                            { name: 'timestamp', value: match[2] },
                            { name: 'host', value: match[3] },
                            { name: 'message', value: match[4] }
                        );
                    }
                } else {
                    // Standard syslog format
                    baseFields.push(
                        { name: 'timestamp', value: match[1] },
                        { name: 'host', value: match[2] },
                        { name: 'message', value: match[3] }
                    );
                }
                
                newFields = baseFields.map(f => ({
                    ...f,
                    type: inferFieldType(f.value),
                    confidence: 0.85,
                    isPII: detectPII(f.name, f.value),
                    source: 'auto_detect',
                    fromRegex: true
                }));
                
                // Extract key-value pairs from message field
                const messageField = baseFields.find(f => f.name === 'message');
                if (messageField) {
                    const message = messageField.value;
                    // Enhanced KV regex that handles various formats
                    const kvPatterns = [
                        /(\w+)=("?)([^"\s]+)\2/g,  // Standard key=value
                        /(\w+):\s*("?)([^"\s]+)\2/g,  // key: value format
                        /(\w+)\s*=\s*("?)([^"\s]+)\2/g  // key = value with spaces
                    ];
                    
                    for (const kvPattern of kvPatterns) {
                        const kvMatches = [...message.matchAll(kvPattern)];
                        kvMatches.forEach(kvMatch => {
                            const value = kvMatch[3];
                            newFields.push({
                                name: kvMatch[1],
                                type: inferFieldType(value),
                                value: value,
                                confidence: 0.75,
                                isPII: detectPII(kvMatch[1], value),
                                source: 'auto_detect',
                                fromRegex: true
                            });
                        });
                    }
                }
                
                setTimeSettings({
                    timePrefix: pattern.prefix,
                    timeFormat: pattern.format,
                    maxTimestampLookahead: pattern.lookahead
                });
                break; // Use first matching pattern
            }
        }
        
        // Enhanced XML format detection with multiple patterns
        if (safeSample.trim().startsWith('<')) {
            try {
                // Multiple XML parsing patterns for different formats
                const xmlPatterns = [
                    // Simple tags: <tag>value</tag>
                    { regex: /<(\w+)>([^<]+)<\/\w+>/g, name: 'simple_tags' },
                    // Self-closing tags: <tag attr="value" />
                    { regex: /<(\w+)\s+([^>]+)\/>/g, name: 'self_closing' },
                    // Tags with attributes: <tag attr="value">content</tag>
                    { regex: /<(\w+)\s+([^>]+)>([^<]+)<\/\w+>/g, name: 'with_attributes' },
                    // Nested tags: <parent><child>value</child></parent>
                    { regex: /<(\w+)>([^<]+)<\/\w+>/g, name: 'nested' }
                ];
                
                let xmlFields = [];
                let xmlRegex = '';
                
                for (const pattern of xmlPatterns) {
                    const matches = [...safeSample.matchAll(pattern.regex)];
                    if (matches.length > 0) {
                        matches.forEach(match => {
                            let fieldName = match[1];
                            let fieldValue = match[2];
                            
                            // Handle attributes in self-closing tags
                            if (pattern.name === 'self_closing') {
                                // Extract attribute name and value
                                const attrMatch = match[2].match(/(\w+)="([^"]+)"/);
                                if (attrMatch) {
                                    fieldName = `${match[1]}_${attrMatch[1]}`;
                                    fieldValue = attrMatch[2];
                                }
                            }
                            
                            // Handle tags with attributes
                            if (pattern.name === 'with_attributes') {
                                fieldValue = match[3]; // Content is in group 3
                                // Also extract attributes
                                const attrMatches = match[2].matchAll(/(\w+)="([^"]+)"/g);
                                for (const attrMatch of attrMatches) {
                                    xmlFields.push({
                                        name: `${match[1]}_${attrMatch[1]}`,
                                        type: inferFieldType(attrMatch[2]),
                                        value: attrMatch[2],
                                        confidence: 0.8,
                                        isPII: detectPII(`${match[1]}_${attrMatch[1]}`, attrMatch[2]),
                                        source: 'auto_detect',
                                        fromRegex: true
                                    });
                                }
                            }
                            
                            xmlFields.push({
                                name: fieldName,
                                type: inferFieldType(fieldValue),
                                value: fieldValue,
                                confidence: 0.8,
                                isPII: detectPII(fieldName, fieldValue),
                                source: 'auto_detect',
                                fromRegex: true
                            });
                        });
                        
                        // Build extraction regex for the detected pattern
                        if (pattern.name === 'simple_tags') {
                            xmlRegex = 'EXTRACT-xml_fields = <(?<field_name>\\w+)>(?<field_value>[^<]+)</\\w+>';
                        } else if (pattern.name === 'self_closing') {
                            xmlRegex = 'EXTRACT-xml_attrs = <(?<tag_name>\\w+)\\s+(?<attr_name>\\w+)="(?<attr_value>[^"]+)"\\s*/>';
                        } else if (pattern.name === 'with_attributes') {
                            xmlRegex = 'EXTRACT-xml_with_attrs = <(?<tag_name>\\w+)\\s+[^>]+>(?<content>[^<]+)</\\w+>';
                        }
                        
                        break; // Use first pattern that finds matches
                    }
                }
                
                if (xmlFields.length > 0) {
                    newFields = xmlFields;
                    extractionRegex = xmlRegex;
                }
            } catch (e) {
                // Fallback if not XML
                console.log('XML parsing failed:', e.message);
            }
        }
        
        // Preserve existing fields and add new auto-detected fields
        const existingFields = allFields.filter(f => f.source !== 'auto_detect');
        const updatedFields = [...existingFields, ...newFields];
        setAllFields(updatedFields);
        setHighlightedText(sampleData || '');
        onFieldsExtracted(updatedFields, extractionRegex, timeSettings);
    }
    function extractFieldsWithRegex() {
        setError('');
        if (!customRegex.trim()) return;
        try {
            const regexPattern = new RegExp(customRegex, 'g');
            const matches = [...sampleData.matchAll(regexPattern)];
            const newFields = [];
            
            if (matches.length === 0) {
                setError('No matches found for this regex.');
                return;
            }
            
            // Check if regex has named groups
            const namedGroups = customRegex.match(/\(\?<([\w]+)>/g);
            
            if (namedGroups) {
                // Only process named groups if they exist
                const groupNames = namedGroups.map(g => g.match(/\(\?<([\w]+)>/)?.[1]).filter(Boolean);
                groupNames.forEach((groupName) => {
                    const values = matches.map(m => m.groups?.[groupName]).filter(Boolean);
                    if (values.length > 0) {
                        newFields.push({ 
                            name: groupName, 
                            type: inferFieldType(values[0]), 
                            value: values[0], 
                            confidence: 0.9, 
                            isPII: detectPII(groupName, values[0]),
                            source: 'custom_regex',
                            fromRegex: true
                        });
                    }
                });
            } else {
                // Only create numbered groups if there are no named groups
                if (matches[0] && matches[0].length > 1) {
                    // Numbered capture groups
                    for (let i = 1; i < matches[0].length; i++) {
                        if (matches[0][i]) {
                            const fieldName = `extracted_field_${i}`;
                            const fieldValue = matches[0][i];
                            newFields.push({ 
                                name: fieldName, 
                                type: inferFieldType(fieldValue), 
                                value: fieldValue, 
                                confidence: 0.7, 
                                isPII: detectPII(fieldName, fieldValue),
                                source: 'custom_regex',
                                fromRegex: true
                            });
                        }
                    }
                } else {
                    // No groups, use entire match
                    matches.forEach((match, idx) => {
                        const fieldName = `regex_match_${idx + 1}`;
                        const fieldValue = match[0];
                        newFields.push({ 
                            name: fieldName, 
                            type: inferFieldType(fieldValue), 
                            value: fieldValue, 
                            confidence: 0.6, 
                            isPII: detectPII(fieldName, fieldValue),
                            source: 'custom_regex',
                            fromRegex: true
                        });
                    });
                }
            }
            
            // Preserve existing fields and add new regex fields
            const existingFields = allFields.filter(f => f.source !== 'custom_regex');
            const updatedFields = [...existingFields, ...newFields];
            setAllFields(updatedFields);
            
            // Highlight matches in the sample data
            let highlighted = sampleData;
            matches.sort((a, b) => (b.index || 0) - (a.index || 0)).forEach((match) => {
                if (match.index !== undefined) {
                    const matchText = match[0];
                    const color = '#3B82F6';
                    const replacement = `<span style=\"background-color: ${color}20; border: 1px solid ${color}; padding: 2px 4px; border-radius: 3px; font-weight: 500;\">${matchText}</span>`;
                    highlighted = highlighted.slice(0, match.index) + replacement + highlighted.slice(match.index + matchText.length);
                }
            });
            setHighlightedText(highlighted);
            onFieldsExtracted(updatedFields, customRegex);
        } catch (err) {
            setError('Invalid regex: ' + err.message);
        }
    }

    const handleExistingFieldsFetch = () => {
        if (!indexName) {
            setError('Please enter an index name');
            return;
        }
        setLoading(true);
        setError('');
        // Simulated API call
        setTimeout(() => {
            const fields = [
                { name: 'timestamp', type: 'datetime', sampleValue: '2024-01-01T12:00:00Z' },
                { name: 'level', type: 'string', sampleValue: 'INFO' },
                { name: 'message', type: 'string', sampleValue: 'Sample message' },
            ];
            setAllFields(fields);
            onFieldsExtracted(fields);
            setLoading(false);
        }, 1000);
    };

    const handleOptionToggle = (option) => (e, { checked }) => {
        setOptions(prev => ({ ...prev, [option]: checked }));
    };

    // Helper function to highlight existing field values in the sample data
    const highlightExistingFields = (text) => {
        if (!text || !allFields.length) return text;
        
        let highlightedText = text;
        const existingFields = allFields.filter(f => f.source === 'splunk_existing');
        
        // Sort fields by value length (longest first) to avoid partial matches
        const sortedFields = existingFields
            .filter(f => f.value && f.value !== 'N/A' && f.value.length > 2)
            .sort((a, b) => b.value.length - a.value.length);
        
        sortedFields.forEach((field, index) => {
            const value = String(field.value);
            if (value && value !== 'N/A') {
                // Create a unique color for each field
                const colors = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#6366F1', '#14B8A6'];
                const color = colors[index % colors.length];
                
                // Escape special regex characters in the value
                const escapedValue = value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                
                try {
                    const regex = new RegExp(`\\b${escapedValue}\\b`, 'gi');
                    highlightedText = highlightedText.replace(regex, 
                        `<span style="background-color: ${color}20; border: 1px solid ${color}; padding: 1px 3px; border-radius: 3px; font-weight: 500;" title="Field: ${field.name} (${field.type})">${value}</span>`
                    );
                } catch (e) {
                    // If regex fails, try simple string replacement
                    const simpleRegex = new RegExp(escapedValue, 'gi');
                    highlightedText = highlightedText.replace(simpleRegex,
                        `<span style="background-color: ${color}20; border: 1px solid ${color}; padding: 1px 3px; border-radius: 3px; font-weight: 500;" title="Field: ${field.name} (${field.type})">${value}</span>`
                    );
                }
            }
        });
        
        return highlightedText;
    };

    const getConfidenceChip = (confidence) => {
        // Handle undefined, null, or NaN confidence values
        if (confidence === undefined || confidence === null || isNaN(confidence)) {
            return <Chip appearance="outline">N/A</Chip>;
        }
        
        let appearance = 'outline';
        if (confidence >= 0.9) appearance = 'success';
        else if (confidence >= 0.7) appearance = 'info';
        else if (confidence >= 0.5) appearance = 'warning';
        else appearance = 'error';

        return (
            <Chip appearance={appearance}>
                {Math.round(confidence * 100)}%
            </Chip>
        );
    };

    const hasData = sampleData && sampleData.trim().length > 0;

    // Handler to start editing a regex
    const handleEditRegex = (fieldName, currentRegex) => {
        setEditedRegexes(prev => ({ ...prev, [fieldName]: currentRegex }));
    };

    // Handler for regex input change
    const handleRegexChange = (fieldName, value) => {
        setEditedRegexes(prev => ({ ...prev, [fieldName]: value }));
        
        // Enhanced regex validation
        try {
            // Check for common regex issues that can cause loops
            if (value.includes('**') || value.includes('++') || value.includes('??')) {
                throw new Error('Invalid quantifier combination');
            }
            
            // Check for unescaped special characters that might cause issues
            const unescapedChars = value.match(/(?<!\\)[.*+?^${}()|[\]\\]/g);
            if (unescapedChars && unescapedChars.length > 0) {
                // Warn about unescaped characters but don't block
                console.warn('Unescaped special characters detected:', unescapedChars);
            }
            
            // Test the regex with a timeout to prevent infinite loops
            const testRegex = new RegExp(value);
            
            // Test with sample data if available
            if (sampleData) {
                const startTime = Date.now();
                const testMatch = sampleData.match(testRegex);
                const endTime = Date.now();
                
                // If regex takes too long, it might cause performance issues
                if (endTime - startTime > 100) {
                    console.warn('Regex might be slow, consider optimizing');
                }
            }
            
            setRegexErrors(prev => ({ ...prev, [fieldName]: null }));
        } catch (e) {
            setRegexErrors(prev => ({ ...prev, [fieldName]: e.message }));
        }
    };

    // Handler to save edited regex
    const handleSaveRegex = (fieldName) => {
        // Already validated on change
        setModifiedAiFields(prev => prev.map(f => 
            f.name === fieldName ? { ...f, regex: editedRegexes[fieldName] } : f
        ));
        setEditedRegexes(prev => ({ ...prev, [fieldName]: undefined }));
    };

    // Handler to cancel editing
    const handleCancelEdit = (fieldName) => {
        setEditedRegexes(prev => ({ ...prev, [fieldName]: undefined }));
        setRegexErrors(prev => ({ ...prev, [fieldName]: null }));
    };

    // Check if all regexes are valid
    const allRegexesValid = modifiedAiFields && modifiedAiFields.every(f => {
        const edit = editedRegexes[f.name];
        if (edit !== undefined) {
            return !regexErrors[f.name];
        }
        return true;
    });

    // When accepting, use edited regexes if present
    const handleAcceptAiFields = (useCombinedRegex = false) => {
        const fieldsToMap = selectedAiFields.length > 0 ? 
            modifiedAiFields.filter(f => selectedAiFields.includes(f.name)) : 
            modifiedAiFields;
        const mappedFields = fieldsToMap.map(f => {
            const regexToUse = editedRegexes[f.name] !== undefined ? editedRegexes[f.name] : f.regex;
            let sampleValue = f.sampleValue || '';
            if (!sampleValue && regexToUse && sampleData) {
                try {
                    const regex = new RegExp(regexToUse);
                    const match = sampleData.match(regex);
                    if (match && match.groups && match.groups[f.name]) {
                        sampleValue = match.groups[f.name];
                    } else if (match && match[1]) {
                        sampleValue = match[1];
                    }
                } catch (e) {
                    // If regex fails, keep empty string
                }
            }
            return {
                ...f,
                regex: regexToUse,
                value: sampleValue,
            };
        });
        const existingFields = allFields.filter(f => f.source !== 'ai_detection');
        const updatedFields = [...existingFields, ...mappedFields];
        setAllFields(updatedFields);
        const extractionRegex = useCombinedRegex && aiFieldResults.combined_regex ? 
            aiFieldResults.combined_regex : null;
        onFieldsExtracted(updatedFields, extractionRegex);
        if (window.createToast) {
            window.createToast({
                type: 'success',
                title: 'AI Fields Accepted',
                message: 'AI-suggested fields have been applied.'
            });
        }
    };

    // Handler to preview extraction for a field
    const handlePreviewRegex = (fieldName, regexPattern) => {
        if (!regexPattern || !sampleData) {
            setPreviewResults(prev => ({ ...prev, [fieldName]: { error: 'No regex or sample data.' } }));
            setPreviewedField(fieldName);
            return;
        }
        try {
            let jsRegex = regexPattern.replace(/\(\?P</g, '\\(?<');
            const regex = new RegExp(jsRegex, 'g');
            const matches = [];
            let match;
            while ((match = regex.exec(sampleData)) !== null) {
                if (match.groups && match.groups[fieldName]) {
                    matches.push(match.groups[fieldName]);
                } else if (match[1]) {
                    matches.push(match[1]);
                } else if (match[0]) {
                    matches.push(match[0]);
                }
                // Prevent infinite loop for zero-width matches
                if (regex.lastIndex === match.index) regex.lastIndex++;
            }
            setPreviewResults(prev => ({ ...prev, [fieldName]: { matches } }));
            setPreviewedField(fieldName);
        } catch (e) {
            setPreviewResults(prev => ({ ...prev, [fieldName]: { error: e.message } }));
            setPreviewedField(fieldName);
        }
    };

    // Handler to preview combined regex extraction
    const handlePreviewCombinedRegex = (combinedRegex) => {
        if (!combinedRegex || !sampleData) {
            setCombinedRegexPreview({ error: 'No regex or sample data.' });
            return;
        }
        try {
            let jsRegex = combinedRegex.replace(/\(\?P</g, '\\(?<');
            const regex = new RegExp(jsRegex, 'g');
            const matches = [];
            let match;
            while ((match = regex.exec(sampleData)) !== null) {
                if (match.groups) {
                    matches.push(match.groups);
                } else if (match[0]) {
                    matches.push({ raw: match[0] });
                }
                // Prevent infinite loop for zero-width matches
                if (regex.lastIndex === match.index) regex.lastIndex++;
            }
            setCombinedRegexPreview({ matches });
        } catch (e) {
            setCombinedRegexPreview({ error: e.message });
        }
    };

    // Handler to accept combined regex
    const handleAcceptCombinedRegex = () => {
        if (!aiFieldResults.combined_regex) return;
        
        // Extract fields from the combined regex
        const fields = [];
        try {
            let jsRegex = aiFieldResults.combined_regex.replace(/\(\?P</g, '\\(?<');
            const regex = new RegExp(jsRegex, 'g');
            const match = regex.exec(sampleData);
            
            if (match && match.groups) {
                Object.entries(match.groups).forEach(([fieldName, value]) => {
                    if (value !== undefined) {
                        fields.push({
                            name: fieldName,
                            value: value,
                            type: inferFieldType(value),
                            source: 'ai_detection',
                            hasPII: detectPII(fieldName, value)
                        });
                    }
                });
            }
        } catch (e) {
            console.error('Error extracting fields from combined regex:', e);
        }

        // Update time settings if AI detected them
        if (aiFieldResults.time_format) {
            setTimeSettings({
                timeFormat: aiFieldResults.time_format,
                timePrefix: aiFieldResults.time_prefix || '',
                maxTimestampLookahead: aiFieldResults.max_timestamp_lookahead || '25'
            });
        }

        const existingFields = allFields.filter(f => f.source !== 'ai_detection');
        const updatedFields = [...existingFields, ...fields];
        setAllFields(updatedFields);
        
        // Pass the combined regex to parent
        onFieldsExtracted(updatedFields, aiFieldResults.combined_regex, {
            timeFormat: aiFieldResults.time_format,
            timePrefix: aiFieldResults.time_prefix || '',
            maxTimestampLookahead: aiFieldResults.max_timestamp_lookahead || '25'
        });

        if (window.createToast) {
            window.createToast({
                type: 'success',
                title: 'AI Fields Accepted',
                message: 'Combined regex and time settings have been applied.'
            });
        }
    };

    // Helper to highlight fields in sample data
    const highlightFieldsInSample = (sampleData, combinedRegex) => {
        if (!sampleData || !combinedRegex) return sampleData;
        
        try {
            let jsRegex = combinedRegex.replace(/\(\?P</g, '\\(?<');
            const regex = new RegExp(jsRegex, 'g');
            let highlightedText = sampleData;
            let offset = 0;
            
            let match;
            while ((match = regex.exec(sampleData)) !== null) {
                if (match.groups) {
                    Object.entries(match.groups).forEach(([fieldName, value]) => {
                        if (value !== undefined) {
                            const start = match.index + match[0].indexOf(value);
                            const end = start + value.length;
                            
                            const before = highlightedText.substring(0, start + offset);
                            const highlighted = `<span style="background-color: #4F46E5; color: white; padding: 1px 2px; border-radius: 2px; font-weight: bold;" title="${fieldName}">${value}</span>`;
                            const after = highlightedText.substring(end + offset);
                            
                            highlightedText = before + highlighted + after;
                            offset += highlighted.length - value.length;
                        }
                    });
                }
                // Prevent infinite loop for zero-width matches
                if (regex.lastIndex === match.index) regex.lastIndex++;
            }
            
            return highlightedText;
        } catch (e) {
            console.error('Error highlighting fields:', e);
            return sampleData;
        }
    };

    // --- UI ---
    return (
        <Card style={{ width: '100%', marginTop: 24 }}>
            <Card.Header title="Field Extraction" />
            <Card.Body>
                <Typography as="p" variant="body" style={{ marginBottom: 16 }}>
                    Extract fields from your log data using patterns, regex, or AI assistance.
                </Typography>
                {(indexName || sourcetype) && (
                    <Typography as="p" variant="smallBody" style={{ marginBottom: 8, opacity: 0.7 }}>
                        {indexName && `Index: ${indexName} `}{sourcetype && `Sourcetype: ${sourcetype}`}
                    </Typography>
                )}
                <TabLayout defaultActivePanelId={showExistingTab ? "existing" : "auto"}>
                    {showExistingTab && (
                        <TabLayout.Panel label="Existing" panelId="existing">
                            <StyledBox marginBottom={16}>
                                <Typography as="h4" variant="title4" style={{ marginBottom: 8 }}>
                                    Fields Already Extracted by Splunk
                                </Typography>
                                <Typography as="p" variant="body" style={{ marginBottom: 12, opacity: 0.8 }}>
                                    These fields are already available in your Splunk search results and don't require additional extraction configuration.
                                    They are marked with an asterisk (*) in the extracted fields table below.
                                </Typography>
                                {(indexName || sourcetype) && (
                                    <Typography as="p" variant="smallBody" style={{ marginBottom: 8, opacity: 0.7 }}>
                                        {indexName && `Index: ${indexName} `}{sourcetype && `Sourcetype: ${sourcetype}`}
                                    </Typography>
                                )}
                                {allFields.filter(f => f.source === 'splunk_existing').length > 0 && (
                                    <Typography as="p" variant="body" style={{ color: '#2E7D32', fontWeight: 500 }}>
                                        ✓ Found {allFields.filter(f => f.source === 'splunk_existing').length} existing field(s) from Splunk
                                    </Typography>
                                )}
                            </StyledBox>
                        </TabLayout.Panel>
                    )}
                    <TabLayout.Panel label="Auto Detect" panelId="auto">
                        <Button appearance="primary" style={{ marginBottom: 12 }} onClick={extractFieldsAuto}>Auto Detect Fields</Button>
                        
                        <Typography as="h4" style={{ marginTop: 16, marginBottom: 8 }}>Timestamp Settings</Typography>
                        <Typography as="p" variant="smallBody" style={{ marginBottom: 12, opacity: 0.8 }}>
                            Configure timestamp extraction for your log format. These settings help Splunk parse timestamps correctly.
                        </Typography>
                        
                        <div style={{ marginBottom: 12 }}>
                            <Typography as="label" variant="body" style={{ display: 'block', marginBottom: 4 }}>
                                {'TIME_PREFIX (e.g., ^, [, <)'}
                            </Typography>
                            <Text
                                value={timeSettings.timePrefix}
                                onChange={(e, { value }) => setTimeSettings(prev => ({ ...prev, timePrefix: value }))}
                                placeholder="Leave blank if no prefix"
                                style={{ marginBottom: 8, width: '100%' }}
                            />
                        </div>
                        
                        <div style={{ marginBottom: 12 }}>
                            <Typography as="label" variant="body" style={{ display: 'block', marginBottom: 4 }}>
                                TIME_FORMAT
                            </Typography>
                            <select
                                value={timeSettings.timeFormat}
                                onChange={(e) => setTimeSettings(prev => ({ ...prev, timeFormat: e.target.value }))}
                                style={{ 
                                    width: '100%', 
                                    padding: '8px', 
                                    border: '1px solid #ccc', 
                                    borderRadius: '4px',
                                    marginBottom: 8
                                }}
                            >
                                <option value="CURRENT_TIME">CURRENT_TIME (No timestamp detected)</option>
                                <option value="%Y-%m-%dT%H:%M:%S">%Y-%m-%dT%H:%M:%S (ISO 8601)</option>
                                <option value="%b %d %H:%M:%S">%b %d %H:%M:%S (Syslog)</option>
                                <option value="%d/%b/%Y:%H:%M:%S %z">%d/%b/%Y:%H:%M:%S %z (Apache)</option>
                                <option value="%Y-%m-%d %H:%M:%S">%Y-%m-%d %H:%M:%S (Standard)</option>
                                <option value="%m/%d/%Y %H:%M:%S">%m/%d/%Y %H:%M:%S (US Format)</option>
                                <option value="%d-%m-%Y %H:%M:%S">%d-%m-%Y %H:%M:%S (EU Format)</option>
                                <option value="%Y%m%d %H:%M:%S">%Y%m%d %H:%M:%S (Compact)</option>
                            </select>
                        </div>
                        
                        <div style={{ marginBottom: 12 }}>
                            <Typography as="label" variant="body" style={{ display: 'block', marginBottom: 4 }}>
                                MAX_TIMESTAMP_LOOKAHEAD (characters)
                            </Typography>
                            <Text
                                value={timeSettings.maxTimestampLookahead}
                                onChange={(e, { value }) => setTimeSettings(prev => ({ ...prev, maxTimestampLookahead: value }))}
                                placeholder="25 (default)"
                                style={{ marginBottom: 8, width: '100%' }}
                            />
                            <Typography as="p" variant="smallBody" style={{ opacity: 0.7, fontSize: '12px' }}>
                                Maximum characters to look ahead for timestamp. Higher values may be slower but more flexible.
                            </Typography>
                        </div>
                        
                        {error && <Message appearance="fill" type="error" style={{ marginTop: 8 }}>{error}</Message>}
                    </TabLayout.Panel>
                    <TabLayout.Panel label="Custom" panelId="custom">
                        <Text
                            value={customRegex}
                            onChange={(e, { value }) => setCustomRegex(value)}
                            placeholder="(?<field_name>pattern) or (pattern)"
                            style={{ fontFamily: 'monospace', marginBottom: 8 }}
                        />
                        <Button appearance="primary" disabled={!customRegex.trim()} onClick={extractFieldsWithRegex}>Apply Regex</Button>
                        {error && <Message appearance="fill" type="error" style={{ marginTop: 8 }}>{error}</Message>}
                        <div style={{ marginTop: '16px' }}>
                            <Typography as="h4">Regex Results Preview</Typography>
                            <StyledPreview>
                                <pre>{JSON.stringify(allFields.filter(f => f.fromRegex), null, 2)}</pre>
                            </StyledPreview>
                        </div>
                    </TabLayout.Panel>
                    <TabLayout.Panel label="Ask AI" panelId="ai">
                        <Message appearance="fill" type="info" style={{ marginBottom: 16 }}>
                            <strong>Privacy Notice:</strong> Your sample data and any description you provide will be sent to the configured LLM service for analysis. Please ensure you are comfortable sharing this data with the external service.
                        </Message>
                        <StyledBox marginBottom={16}>
                            <Typography as="h4" variant="title4" style={{ marginBottom: 8 }}>
                                Data Description (Optional)
                            </Typography>
                            <Typography as="p" variant="body" style={{ marginBottom: 8, opacity: 0.8 }}>
                                Provide additional context about your log data to help the AI better understand and extract fields.
                            </Typography>
                            <StyledTextArea
                                value={aiDescription}
                                onChange={(e, { value }) => setAiDescription(value)}
                                placeholder="e.g., 'This is Apache access log data from a web server' or 'JSON logs from a Node.js application with custom fields'"
                                rows={3}
                            />
                        </StyledBox>
                        <Button
                            label={aiFieldLoading ? "Detecting..." : "Detect Fields with AI"}
                            appearance="primary"
                            onClick={() => onDetectFields(aiDescription.trim() || null)}
                            disabled={aiFieldLoading || !hasData}
                            icon={aiFieldLoading ? <WaitSpinner size="small" /> : null}
                        />
                        {!hasData && <Typography as="p" variant="body">Please provide sample data in the first step.</Typography>}

                        {aiFieldError && <ErrorMessage>Error: {aiFieldError.message}</ErrorMessage>}

                        {aiFieldResults && (
                            <>
                                <div>
                                    <strong>Suggested Sourcetype:</strong>{' '}
                                    <Chip>{aiFieldResults.sourcetype}</Chip>
                                </div>
                                {aiFieldResults.source === 'local_fallback' && (
                                     <div>
                                        <Chip appearance="warning">Used local fallback method. Results may be limited.</Chip>
                                    </div>
                                )}
                                
                                {aiFieldResults.time_format && (
                                    <div>
                                        <strong>Detected Time Format:</strong>{' '}
                                        <Chip>{aiFieldResults.time_format}</Chip>
                                        {aiFieldResults.time_prefix && (
                                            <>
                                                <strong> Time Prefix:</strong>{' '}
                                                <Chip>{aiFieldResults.time_prefix || 'none'}</Chip>
                                            </>
                                        )}
                                        {aiFieldResults.max_timestamp_lookahead && (
                                            <>
                                                <strong> Max Lookahead:</strong>{' '}
                                                <Chip>{aiFieldResults.max_timestamp_lookahead}</Chip>
                                            </>
                                        )}
                                    </div>
                                )}
                                
                                {aiFieldResults.combined_regex ? (
                                    <>
                                        <ResultsHeader>Combined Field Extraction Regex</ResultsHeader>
                                        <StyledBox marginBottom={16}>
                                            <Typography as="p" variant="body" style={{ marginBottom: 8, opacity: 0.8 }}>
                                                This regex extracts all fields from your log data in one pattern. You can modify it if needed.
                                            </Typography>
                                            <StyledTextArea
                                                value={aiFieldResults.combined_regex}
                                                onChange={(e, { value }) => {
                                                    // Update the combined regex in the results
                                                    setAiFieldResults(prev => ({
                                                        ...prev,
                                                        combined_regex: value
                                                    }));
                                                }}
                                                rows={4}
                                            />
                                            <Button 
                                                appearance="secondary" 
                                                size="small" 
                                                onClick={() => handlePreviewCombinedRegex(aiFieldResults.combined_regex)}
                                                style={{ marginRight: 8 }}
                                            >
                                                Preview Extraction
                                            </Button>
                                            {combinedRegexPreview && (
                                                <div style={{ 
                                                    marginTop: 8, 
                                                    padding: 8, 
                                                    backgroundColor: theme.backgroundColorSecondary, 
                                                    borderRadius: 4,
                                                    border: `1px solid ${theme.borderColor}`
                                                }}>
                                                    <Typography as="strong" variant="smallBody">Preview Results:</Typography>
                                                    <pre style={{ 
                                                        fontSize: 12, 
                                                        marginTop: 4,
                                                        color: theme.textColor
                                                    }}>{JSON.stringify(combinedRegexPreview, null, 2)}</pre>
                                                </div>
                                            )}
                                        </StyledBox>
                                        
                                        <StyledBox marginBottom={16}>
                                            <Typography as="h4" variant="title4" style={{ marginBottom: 8 }}>
                                                Sample Data with Highlighted Fields
                                            </Typography>
                                            <StyledSampleDataBox
                                                dangerouslySetInnerHTML={{ 
                                                    __html: highlightFieldsInSample(sampleData, aiFieldResults.combined_regex) 
                                                }}
                                            />
                                        </StyledBox>
                                        
                                        <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
                                            <Button
                                                appearance="primary"
                                                onClick={() => handleAcceptCombinedRegex()}
                                                disabled={aiFieldLoading}
                                            >
                                                Accept Combined Regex
                                            </Button>
                                        </div>
                                    </>
                                ) : (
                                    <Typography as="p" variant="body">The AI could not generate a combined regex for the provided data.</Typography>
                                )}
                            </>
                        )}
                    </TabLayout.Panel>
                </TabLayout>
                <div style={{ marginTop: 24 }}>
                    <Typography as="h5" variant="title4" style={{ fontWeight: 500 }}>
                        Sample Data Preview:
                    </Typography>
                    <StyledPreview
                        dangerouslySetInnerHTML={{ __html: highlightExistingFields(sampleData || '').replace(/\n/g, '<br/>') }}
                    />
                </div>
                <StyledBox marginTop={24}>
                    <Typography as="h3" variant="title3">Extracted Fields ({allFields.length})</Typography>
                    <Table stripe style={{ marginTop: 8 }}>
                        <Table.Head>
                            <Table.HeadCell>Field Name</Table.HeadCell>
                            <Table.HeadCell>Type</Table.HeadCell>
                            <Table.HeadCell>Confidence</Table.HeadCell>
                            <Table.HeadCell>Sample Value</Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {allFields.length === 0 ? (
                                <Table.Row>
                                    <Table.Cell colSpan={5} style={{ textAlign: 'center' }}>No fields extracted yet.</Table.Cell>
                                </Table.Row>
                            ) : (
                                allFields.map((field, idx) => (
                                    <Table.Row key={`${field.name}-${idx}`}>
                                        <Table.Cell>
                                            <StyledHighlight color="#4F46E5">
                                                {field.name}
                                                {field.source === 'splunk_existing' && <span style={{ color: '#1976D2', fontWeight: 'bold' }}>*</span>}
                                            </StyledHighlight>
                                        </Table.Cell>
                                        <Table.Cell>{field.type || 'string'}</Table.Cell>
                                       
                                        <Table.Cell>{getConfidenceChip(field.confidence)}</Table.Cell>
                                        <Table.Cell>{String(field.value)}</Table.Cell>
                                    </Table.Row>
                                ))
                            )}
                        </Table.Body>
                    </Table>
                    {allFields.some(f => f.source === 'splunk_existing') && (
                        <Typography as="p" variant="smallBody" style={{ marginTop: 8, opacity: 0.7, fontStyle: 'italic' }}>
                            * Fields marked with an asterisk are already extracted by Splunk and don't require additional configuration.
                        </Typography>
                    )}
                </StyledBox>
                <StyledLayout gutter={8} marginTop={32} style={{ justifyContent: 'space-between' }}>
                    <StyledPanel>
                        <Button appearance="secondary" onClick={onBack}>
                            Back
                        </Button>
                    </StyledPanel>
                    <StyledPanel>
                        <Button
                            appearance="primary"
                            onClick={() => onContinueToMapping()}
                            disabled={loading || allFields.length === 0}
                        >
                            Continue to Mapping
                        </Button>
                    </StyledPanel>
                </StyledLayout>
            </Card.Body>
        </Card>
    );
};

FieldExtraction.propTypes = {
    sampleData: PropTypes.string.isRequired,
    onFieldsExtracted: PropTypes.func.isRequired,
    onContinueToMapping: PropTypes.func.isRequired,
    onBack: PropTypes.func.isRequired,
    showExistingTab: PropTypes.bool,
    onDetectFields: PropTypes.func.isRequired,
    aiFieldResults: PropTypes.object,
    aiFieldLoading: PropTypes.bool,
    aiFieldError: PropTypes.object,
};

export default FieldExtraction; 