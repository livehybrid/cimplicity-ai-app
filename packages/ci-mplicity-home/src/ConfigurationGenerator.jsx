import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import Card from '@splunk/react-ui/Card';
import Button from '@splunk/react-ui/Button';
import Typography from '@splunk/react-ui/Typography';
import TextArea from '@splunk/react-ui/TextArea';
import TabLayout from '@splunk/react-ui/TabLayout';
import styled from 'styled-components';
import Toaster, { makeCreateToast } from '@splunk/react-toast-notifications/Toaster';
import ToastMessages from '@splunk/react-toast-notifications/ToastMessages';
import { TOAST_TYPES } from '@splunk/react-toast-notifications/ToastConstants';
import Table from '@splunk/react-ui/Table';
import Chip from '@splunk/react-ui/Chip';
import Text from '@splunk/react-ui/Text';

const createToast = makeCreateToast(Toaster);

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

const convertToPCRE2NamedGroups = (regex) => {
    // Convert all instances of (?<fieldName> to (?P<fieldName>
    return regex.replace(/\(\?<([a-zA-Z0-9_]+)>/g, '(?P<$1>');
};

const ConfigurationGenerator = ({ extractedFields = [], cimMapping = {}, piiResults = {}, sampleData = '', extractionRegex = null, actualSourcetype = null, timeSettings = {}, onBack, onFinish }) => {
    const [propsConf, setPropsConf] = useState('');
    const [spl2IngestConf, setSpl2IngestConf] = useState('');
    const [spl2EdgeConf, setSpl2EdgeConf] = useState('');
    const [sourcetypeOverride, setSourcetypeOverride] = useState(actualSourcetype || '');

    // Add state for validation
    const [validationResults, setValidationResults] = useState(null);

    // Extract redactions and suggestion from new structure
    const redactions = piiResults && Array.isArray(piiResults.results) ? piiResults.results : [];
    const suggestion = piiResults && piiResults.suggestion ? piiResults.suggestion : '';

    // Auto-generate configurations on component mount
    useEffect(() => {
        generateConfigurations();
    // eslint-disable-next-line
    }, [extractedFields, cimMapping, piiResults, sampleData, sourcetypeOverride]);

    // Filter out Splunk existing fields for extraction
    const nonSplunkFields = extractedFields.filter(f => f.source !== 'splunk_existing');
    const hasSplunkFields = extractedFields.some(f => f.source === 'splunk_existing');

    // Helper function to convert numbered capture groups to named capture groups
    const convertNumberedToNamedCaptureGroups = (regex) => {
        // Common field names for Apache-style logs
        const commonFieldNames = [
            'clientip', 'ident', 'auth', 'timestamp', 'request', 'method', 'uri', 'protocol', 
            'status', 'bytes', 'referer', 'useragent', 'req_time', 'cookie', 'respTime', 'version',
            'host', 'port', 'path', 'query', 'fragment', 'scheme', 'user', 'password'
        ];
        
        let result = regex;
        let groupIndex = 1;
        
        // Replace numbered capture groups with named capture groups
        result = result.replace(/\(([^)]+)\)/g, (match, groupContent) => {
            // Skip if it's already a named capture group
            if (groupContent.startsWith('?<')) {
                return match;
            }
            
            // Use common field names or generate a generic name
            const fieldName = groupIndex <= commonFieldNames.length 
                ? commonFieldNames[groupIndex - 1] 
                : `field_${groupIndex}`;
            
            groupIndex++;
            return `(?<${fieldName}>${groupContent})`;
        });
        
        return result;
    };

    // Helper to detect log format and generate single anchored regex
    const detectLogFormatAndGenerateExtraction = () => {
        // If custom regex is provided, use it first
        if (extractionRegex && extractionRegex.trim()) {
            // Convert numbered capture groups to named capture groups for EXTRACT-custom_fields
            let processedRegex = extractionRegex;
            if (!extractionRegex.startsWith('EXTRACT-')) {
                // Convert numbered capture groups to named capture groups
                processedRegex = convertNumberedToNamedCaptureGroups(extractionRegex);
            }
            
            return {
                extraction: extractionRegex.startsWith('EXTRACT-') ? extractionRegex : `EXTRACT-custom_fields = ${processedRegex}`,
                timePrefix: '',
                timeFormat: '%Y-%m-%dT%H:%M:%S',
                sourcetype: 'custom_log'
            };
        }

        if (!sampleData || !nonSplunkFields || nonSplunkFields.length === 0) {
            return { extraction: '', timePrefix: '', timeFormat: '', sourcetype: 'sample_log' };
        }

        const firstLine = sampleData.trim().split('\n')[0];
        
        // Detect Apache access log format
        if (firstLine.match(/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+.*\[.*\].*".*".*[0-9]+.*[0-9]+/) && !hasSplunkFields) {
            // Only emit full apache extraction if no Splunk fields are present
            return {
                extraction: 'EXTRACT-apache_access = ^(?<clientip>\\d{1,3}(?:\\.\\d{1,3}){3})\\s+(?<ident>[^\\s]+)\\s+(?<auth>[^\\s]+)\\s+\\[(?<timestamp>[^\\]]+)\\]\\s+"(?<method>\\S+)\\s+(?<uri>\\S+)\\s+(?<protocol>[^\"]+)"\\s+(?<status>\\d{3})\\s+(?<bytes>\\d+|-)(?:\\s+"(?<referer>[^"]*)"\\s+"(?<useragent>[^"]*)")?(?:\\s+(?<req_time>\\d+))?(?:\\s+"(?<cookie>[^"]*)")?(?:\\s+(?<respTime>\\d+))?(?:\\s+"(?<version>[^"]*)")?',
                timePrefix: '[',
                timeFormat: '%d/%b/%Y:%H:%M:%S %z',
                sourcetype: 'apache_access'
            };
        }
        
        // Detect JSON format
        if (firstLine.trim().startsWith('{') && firstLine.includes(':')) {
            const fieldRegexParts = nonSplunkFields.map(field => {
                if (field.type === 'ip') {
                    return `"${field.name}"\\s*:\\s*"(?<${field.name}>\\d{1,3}(?:\\.\\d{1,3}){3})"`;
                } else if (field.type === 'email') {
                    return `"${field.name}"\\s*:\\s*"(?<${field.name}>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})"`;
                } else if (field.type === 'timestamp') {
                    return `"${field.name}"\\s*:\\s*"(?<${field.name}>[^"]+)"`;
                } else {
                    return `"${field.name}"\\s*:\\s*"(?<${field.name}>[^"]*)"`;
                }
            });
            
            // Build regex that matches the JSON structure
            const jsonRegex = '^\\{.*' + fieldRegexParts.join('.*') + '.*\\}$';
            
            return {
                extraction: `EXTRACT-json_fields = ${jsonRegex}`,
                timePrefix: firstLine.includes('"timestamp"') ? '"timestamp":"' : firstLine.includes('"time"') ? '"time":"' : '',
                timeFormat: '%Y-%m-%dT%H:%M:%S',
                sourcetype: 'json_log'
            };
        }
        
        // Detect CSV format
        if (firstLine.includes(',') && nonSplunkFields.length > 1) {
            const csvFields = nonSplunkFields.map(field => {
                if (field.type === 'ip') {
                    return `(?<${field.name}>\\d{1,3}(?:\\.\\d{1,3}){3})`;
                } else if (field.type === 'email') {
                    return `(?<${field.name}>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})`;
                } else if (field.type === 'timestamp') {
                    return `(?<${field.name}>[^,]+)`;
                } else {
                    return `(?<${field.name}>[^,]*)`;
                }
            }).join(',\\s*');
            
            return {
                extraction: `EXTRACT-csv_fields = ^${csvFields}$`,
                timePrefix: '',
                timeFormat: '%Y-%m-%d %H:%M:%S',
                sourcetype: 'csv_log'
            };
        }
        
        // Detect key-value format
        if (firstLine.includes('=')) {
            // Check for timestamp patterns in the data first
            const timestampPatterns = [
                { regex: /(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2}:\d{2})/, format: '%d/%m/%Y %H:%M:%S' },
                { regex: /(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/, format: '%Y-%m-%d %H:%M:%S' },
                { regex: /(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/, format: '%Y-%m-%dT%H:%M:%S' },
                { regex: /(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})/, format: '%b %d %H:%M:%S' },
                { regex: /(\d{2}\/\w{3}\/\d{4}:\d{2}:\d{2}:\d{2})/, format: '%d/%b/%Y:%H:%M:%S' }
            ];
            
            let timestampMatch = null;
            let timeFormat = '';
            
            for (const pattern of timestampPatterns) {
                timestampMatch = firstLine.match(pattern.regex);
                if (timestampMatch) {
                    timeFormat = pattern.format;
                    break;
                }
            }
            
            const hasTimestamp = timestampMatch !== null;
            
            // Order fields by their appearance in the first line of data
            const orderedFields = [];
            const fieldPositions = [];
            
            // Find the position of each field in the actual data
            nonSplunkFields.forEach(field => {
                const pattern = new RegExp(`\\b${field.name}=([^\\s]+)`, 'i');
                const match = firstLine.match(pattern);
                if (match) {
                    fieldPositions.push({
                        field: field,
                        position: match.index,
                        value: match[1]
                    });
                }
            });
            
            // Sort by position in the log line
            fieldPositions.sort((a, b) => a.position - b.position);
            
            // Generate regex parts in the correct order
            const kvFields = fieldPositions.map(fieldPos => {
                const field = fieldPos.field;
                if (field.type === 'ip') {
                    return `${field.name}=(?<${field.name}>\\d{1,3}(?:\\.\\d{1,3}){3})`;
                } else if (field.type === 'email') {
                    return `${field.name}=(?<${field.name}>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})`;
                } else {
                    return `${field.name}=(?<${field.name}>[^\\s]+)`;
                }
            }).join('.*');
            
            // For key-value logs, create a single comprehensive regex that uniquely identifies each field
            // This prevents individual EXTRACTs from matching wrong parts of the event
            let extraction;
            
            // Build a single regex that matches the entire log line with all fields
            const allFields = [];
            
            if (hasTimestamp) {
                for (const pattern of timestampPatterns) {
                    if (firstLine.match(pattern.regex)) {
                        const timestampRegexPattern = pattern.regex.source.slice(1, -1);
                        allFields.push(`(?<timestamp>${timestampRegexPattern})`);
                        break;
                    }
                }
            }
            
            // Add all key-value fields in order of appearance
            fieldPositions.forEach(fieldPos => {
                const field = fieldPos.field;
                if (field.type === 'ip') {
                    allFields.push(`${field.name}=(?<${field.name}>\\d{1,3}(?:\\.\\d{1,3}){3})`);
                } else if (field.type === 'email') {
                    allFields.push(`${field.name}=(?<${field.name}>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})`);
                } else {
                    // Handle quoted and unquoted values
                    allFields.push(`${field.name}=(?<${field.name}>[^\\s]+)`);
                }
            });
            
            // Create a single regex that matches the entire line with all fields
            if (allFields.length > 0) {
                extraction = `EXTRACT-kv_fields = ^.*${allFields.join('.*')}.*$`;
            } else {
                extraction = '';
            }
            
            return {
                extraction: extraction,
                timePrefix: hasTimestamp ? '' : '', // Let Splunk auto-detect timestamp if present
                timeFormat: hasTimestamp ? timeFormat : 'CURRENT_TIME',
                sourcetype: 'kv_log',
                hasTimestamp: hasTimestamp
            };
        }
        
        // If Splunk fields are present, only generate EXTRACTs for non-Splunk fields
        if (hasSplunkFields && nonSplunkFields.length > 0) {
            // Generate a single combined regex for all non-Splunk fields to ensure proper extraction
            const fieldRegexParts = nonSplunkFields.map(field => {
                if (field.type === 'ip') {
                    return `${field.name}=(?<${field.name}>\\d{1,3}(?:\\.\\d{1,3}){3})`;
                } else if (field.type === 'email') {
                    return `${field.name}=(?<${field.name}>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})`;
                } else {
                    return `${field.name}=(?<${field.name}>[^\\s]+)`;
                }
            });
            
            const combinedExtraction = `EXTRACT-non_splunk_fields = ^.*${fieldRegexParts.join('.*')}.*$`;
            
            return {
                extraction: combinedExtraction,
                timePrefix: '',
                timeFormat: '',
                sourcetype: actualSourcetype || 'custom_log',
                hasTimestamp: false
            };
        }
        
        // Fallback: generate generic extraction
        const genericFields = nonSplunkFields.map(field => {
            if (field.type === 'ip') {
                return `(?<${field.name}>\\d{1,3}(?:\\.\\d{1,3}){3})`;
            } else if (field.type === 'email') {
                return `(?<${field.name}>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})`;
            } else {
                return `(?<${field.name}>[^\\s]+)`;
            }
        }).join('.*');
        
        return {
            extraction: `EXTRACT-all_fields = ^.*${genericFields}.*$`,
            timePrefix: '',
            timeFormat: 'CURRENT_TIME',
            sourcetype: 'sample_log'
        };
    };

    const generatePropsConf = () => {
        const formatInfo = detectLogFormatAndGenerateExtraction();
        // Use sourcetype override if set, otherwise actualSourcetype or detected format
        const sourcetype = sourcetypeOverride || actualSourcetype || formatInfo.sourcetype;
        
        let config = `[${sourcetype}]\n`;
        config += `SHOULD_LINEMERGE = false\n`;
        
        // Use timeSettings if provided, otherwise detected
        const tf = timeSettings.timeFormat || formatInfo.timeFormat;
        const tp = timeSettings.timePrefix || formatInfo.timePrefix;
        const mt = timeSettings.maxTimestampLookahead || '25';
        
        // If no time format is detected, use CURRENT_TIME
        const finalTimeFormat = tf || 'CURRENT_TIME';
        const finalTimePrefix = tf ? tp : '';
        const finalMaxTimestamp = tf ? mt : '';
        
        if (finalTimeFormat !== 'CURRENT_TIME') {
            if (finalTimePrefix) config += `TIME_PREFIX = ${finalTimePrefix}\n`;
            config += `TIME_FORMAT = ${finalTimeFormat}\n`;
            config += `MAX_TIMESTAMP_LOOKAHEAD = ${finalMaxTimestamp}\n`;
        }
        config += '\n';

        // Add field extractions for non-Splunk fields only
        config += '# Field Extractions\n';
        if (formatInfo.extraction) {
            config += `${formatInfo.extraction}\n`;
            
            // Generate accurate field list based on log format
            let fieldNames;
            if (formatInfo.sourcetype === 'apache_access' && !actualSourcetype) {
                fieldNames = 'clientip, ident, auth, timestamp, method, uri, protocol, status, bytes, referer, useragent, req_time, cookie, respTime, version';
            } else if (formatInfo.sourcetype === 'custom_log' && extractionRegex) {
                // Extract field names from custom regex using named capture groups
                const namedGroups = extractionRegex.match(/\(\?<(\w+)>/g);
                if (namedGroups) {
                    fieldNames = namedGroups.map(group => group.replace(/\(\?<(\w+)>/, '$1')).join(', ');
                } else {
                    fieldNames = nonSplunkFields.map(f => f.name).join(', ');
                }
            } else if (formatInfo.sourcetype === 'kv_log' && formatInfo.hasTimestamp) {
                // Include timestamp field for key-value logs that have timestamps
                const allFields = ['timestamp', ...nonSplunkFields.map(f => f.name)];
                fieldNames = allFields.join(', ');
            } else {
                fieldNames = nonSplunkFields.map(f => f.name).join(', ');
            }
            config += `# Extracts: ${fieldNames}\n`;
        } else {
            config += '# No field extractions configured\n';
        }
        config += '\n';

        // Add field aliases (CIM mappings)
        const cimMappingEntries = Object.entries(cimMapping).filter(([_, cimField]) => cimField);
        if (cimMappingEntries.length > 0) {
            config += '# CIM Field Aliases\n';
            cimMappingEntries.forEach(([extractedField, cimField]) => {
                if (cimField !== extractedField) {
                    config += `FIELDALIAS-${extractedField} = ${extractedField} AS ${cimField}\n`;
                }
            });
            config += '\n';
        }

        // Add PII redaction rules
        if (redactions.length > 0) {
            config += '# PII Redaction Rules\n';
            redactions.forEach((result, idx) => {
                // Use regex_pattern from the PII result if available
                const pattern = result.regex_pattern || (result.sedcmd_regex && result.sedcmd_regex.pattern);
                const type = (result.type || 'custom').toLowerCase();
                const sedcmdName = `redact_${type}`;
                const replacement = `[REDACTED_${(result.type || 'custom').toUpperCase()}]`;
                if (pattern) {
                    config += `SEDCMD-${sedcmdName} = s/${pattern}/${replacement}/g\n`;
                } else {
                    // Fallback to previous logic if no regex_pattern
                    const fallback = getFieldContextRegex(result.field, result.type, sampleData);
                    config += `SEDCMD-${sedcmdName} = s/${fallback.pattern}/${replacement}/g\n`;
                }
            });
        } else {
            config += '# PII Redaction Rules (no PII detected)\n';
            config += '# SEDCMD-redact_email = s/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/[REDACTED_EMAIL]/g\n';
        }

        // Add custom PII patterns if provided
        const customPatterns = piiResults.customPatterns || [];
        if (customPatterns.length > 0) {
            config += '\n# Custom PII Redaction Rules\n';
            customPatterns.forEach((pattern, index) => {
                if (pattern.regex && pattern.regex.trim()) {
                    // Escape the regex for SEDCMD
                    const escapedRegex = pattern.regex.replace(/\//g, '\\/');
                    const patternName = (pattern.name || 'CUSTOM').toUpperCase().replace(/\s+/g, '_');
                    const sedcmdName = `redact_custom_${index + 1}`;
                    const replacement = `[REDACTED_${patternName}]`;
                    config += `SEDCMD-${sedcmdName} = s/${escapedRegex}/${replacement}/g\n`;
                }
            });
        }

        return config;
    };

    const generateSpl2IngestConf = () => {
        let config = '// SPL2 Ingest Processor Configuration\n\n';
        
        // Use combined regex if available
        if (extractionRegex && extractionRegex.trim()) {
            const pcre2Regex = convertToPCRE2NamedGroups(extractionRegex);
            config += `| rex field=_raw "${pcre2Regex}"\n`;
        } else if (piiResults && piiResults.combined_regex) {
            const pcre2Regex = convertToPCRE2NamedGroups(piiResults.combined_regex);
            config += `| rex field=_raw "${pcre2Regex}"\n`;
        } else {
            // Fallback: per-field extraction
            nonSplunkFields.forEach(field => {
                const pattern = getFieldExtractionPattern(field, sampleData);
                const pcre2Pattern = convertToPCRE2NamedGroups(pattern);
                config += `| rex field=_raw "${pcre2Pattern}"\n`;
            });
        }

        // Add CIM mappings
        Object.entries(cimMapping).forEach(([extractedField, cimField]) => {
            if (cimField && cimField !== extractedField) {
                config += `| eval ${cimField}=${extractedField}\n`;
            }
        });

        // Add PII redaction
        if (redactions.length > 0) {
            redactions.forEach(result => {
                const pattern = result.regex_pattern || (result.sedcmd_regex && result.sedcmd_regex.pattern);
                const replacement = `[REDACTED_${result.type.toUpperCase()}]`;
                if (pattern) {
                    config += `| eval ${result.field}=replace(${result.field}, "${pattern}", "${replacement}")\n`;
                } else {
                    // Fallback to previous logic if no regex_pattern
                    const fallback = getFieldContextRegex(result.field, result.type, sampleData);
                    config += `| eval ${result.field}=replace(${result.field}, "${fallback.pattern}", "${replacement}")\n`;
                }
            });
        }

        // Add custom PII redaction
        const customPatterns = piiResults.customPatterns || [];
        if (customPatterns.length > 0) {
            customPatterns.forEach((pattern, index) => {
                if (pattern.regex && pattern.regex.trim()) {
                    const escapedRegex = pattern.regex.replace(/"/g, '\\"');
                    const replacement = `[REDACTED_CUSTOM]`;
                    config += `| eval _raw=replace(_raw, "${escapedRegex}", "${replacement}")\n`;
                }
            });
        }

        return config;
    };

    const generateSpl2EdgeConf = () => {
        let config = 'version: "1.0"\n';
        config += 'pipelines:\n';
        config += '  - name: "my_pipeline"\n';
        config += '    source:\n';
        config += '      type: "file"\n';
        config += '      path: "/path/to/data"\n';
        config += '    processors:\n';
        
        // Use combined regex if available
        if (extractionRegex && extractionRegex.trim()) {
            const pcre2Regex = convertToPCRE2NamedGroups(extractionRegex);
            config += `      - type: "regex"\n`;
            config += `        field: "_raw"\n`;
            config += `        pattern: "${pcre2Regex}"\n`;
        } else if (piiResults && piiResults.combined_regex) {
            const pcre2Regex = convertToPCRE2NamedGroups(piiResults.combined_regex);
            config += `      - type: "regex"\n`;
            config += `        field: "_raw"\n`;
            config += `        pattern: "${pcre2Regex}"\n`;
        } else {
            // Fallback: per-field extraction
            nonSplunkFields.forEach(field => {
                const pattern = getFieldExtractionPattern(field, sampleData);
                const pcre2Pattern = convertToPCRE2NamedGroups(pattern);
                config += `      - type: "regex"\n`;
                config += `        field: "_raw"\n`;
                config += `        pattern: "${pcre2Pattern}"\n`;
            });
        }

        // Add PII masking processors
        if (redactions.length > 0) {
            redactions.forEach(result => {
                const pattern = result.regex_pattern || (result.sedcmd_regex && result.sedcmd_regex.pattern);
                const replacement = `[REDACTED_${result.type.toUpperCase()}]`;
                if (pattern) {
                    config += `      - type: "mask"\n`;
                    config += `        field: "${result.field}"\n`;
                    config += `        pattern: "${pattern}"\n`;
                    config += `        replacement: "${replacement}"\n`;
                } else {
                    // Fallback to previous logic if no regex_pattern
                    const fallback = getFieldContextRegex(result.field, result.type, sampleData);
                    config += `      - type: "mask"\n`;
                    config += `        field: "${result.field}"\n`;
                    config += `        pattern: "${fallback.pattern}"\n`;
                    config += `        replacement: "${replacement}"\n`;
                }
            });
        }

        // Add custom PII masking processors
        const customPatterns = piiResults.customPatterns || [];
        if (customPatterns.length > 0) {
            customPatterns.forEach(pattern => {
                if (pattern.regex && pattern.regex.trim()) {
                    const escapedRegex = pattern.regex.replace(/"/g, '\\"');
                    const replacement = `[REDACTED_CUSTOM]`;
                    config += `      - type: "mask"\n`;
                    config += `        field: "_raw"\n`;
                    config += `        pattern: "${escapedRegex}"\n`;
                    config += `        replacement: "${replacement}"\n`;
                }
            });
        }

        // Add CIM mapping processor
        const cimMappingEntries = Object.entries(cimMapping).filter(([_, cimField]) => cimField);
        if (cimMappingEntries.length > 0) {
            config += `      - type: "rename"\n`;
            config += `        mappings:\n`;
            cimMappingEntries.forEach(([extractedField, cimField]) => {
                config += `          "${extractedField}": "${cimField}"\n`;
            });
        }

        config += '    destination:\n';
        config += '      type: "splunk"\n';
        config += '      index: "main"\n';
        config += '      sourcetype: "my_custom_sourcetype"\n';

        return config;
    };

    const getFieldExtractionPattern = (field, sampleData) => {
        // Generate appropriate regex pattern based on field type and sample data
        switch (field.type) {
            case 'ip':
                return '(?<' + field.name + '>\\b(?:[0-9]{1,3}\\.){3}[0-9]{1,3}\\b)';
            case 'email':
                return '(?<' + field.name + '>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})';
            case 'timestamp':
                return '(?<' + field.name + '>[^\\s]+)';
            case 'number':
                return '(?<' + field.name + '>\\d+)';
            default:
                // Try to infer pattern from sample data
                if (sampleData && sampleData.includes(field.name + '=')) {
                    return '(?<' + field.name + '>[^\\s,]+)';
                } else if (sampleData && sampleData.includes('"' + field.name + '":')) {
                    return '"(?<' + field.name + '>[^"]*)"';
                } else {
                    return '(?<' + field.name + '>[^\\s]+)';
                }
        }
    };

    const getRedactionPattern = (type) => {
        switch (type) {
            case 'email':
                return '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}';
            case 'ip':
            case 'ip_address':
                return '\\b(?:[0-9]{1,3}\\.){3}[0-9]{1,3}\\b';
            case 'phone':
                return '\\b\\d{3}-\\d{3}-\\d{4}\\b';
            case 'ssn':
                return '\\b\\d{3}-\\d{2}-\\d{4}\\b';
            case 'credit_card':
                return '\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b';
            default:
                return '[^\\s]+';
        }
    };

    // Helper to generate a contextual regex for SEDCMD based on field, type, and sample data
    const getFieldContextRegex = (field, type, sampleData) => {
        if (!field || !sampleData) return { pattern: '[^\\s]+', replacement: `[REDACTED_${type ? type.toUpperCase() : 'PII'}]` };
        
        // Try to detect JSON format
        if (sampleData.trim().startsWith('{') && sampleData.includes(`"${field}"`)) {
            // JSON: "field":"value" -> "field":"[REDACTED_TYPE]"
            const valuePattern = getValuePattern(type);
            return {
                pattern: `"${field}"\\s*:\\s*"(${valuePattern})"`,
                replacement: `"${field}":"[REDACTED_${type ? type.toUpperCase() : 'PII'}]"`
            };
        }
        
        // Try to detect key-value format (field=value)
        if (sampleData.includes(`${field}=`)) {
            // key-value: field=value -> field=[REDACTED_TYPE]
            const valuePattern = getValuePattern(type);
            return {
                pattern: `${field}=(${valuePattern})`,
                replacement: `${field}=[REDACTED_${type ? type.toUpperCase() : 'PII'}]`
            };
        }
        
        // Try to detect CSV format
        const lines = sampleData.trim().split('\n');
        if (lines.length > 1 && lines[0].includes(field)) {
            const headers = lines[0].split(',').map(h => h.trim());
            const fieldIndex = headers.findIndex(h => h === field);
            if (fieldIndex !== -1) {
                // For CSV, we need to match the value in the specific column position
                // This is complex, so for now we'll use a simpler approach
                const valuePattern = getValuePattern(type);
                return {
                    pattern: valuePattern,
                    replacement: `[REDACTED_${type ? type.toUpperCase() : 'PII'}]`
                };
            }
        }
        
        // Try to detect Apache log format (positional)
        if (sampleData.match(/^\d+\.\d+\.\d+\.\d+.*\[.*\].*".*".*\d+.*\d+/)) {
            // For Apache logs, we need to determine the field's position
            // This is based on the field extraction logic from FieldExtraction.jsx
            const apacheFields = ['clientip', 'ident', 'auth', 'timestamp', 'request', 'status', 'bytes'];
            const fieldIndex = apacheFields.indexOf(field);
            
            if (fieldIndex !== -1) {
                // Generate a positional regex for Apache logs
                // This is a simplified version - in practice, you'd want more robust positional matching
                const valuePattern = getValuePattern(type);
                if (field === 'clientip') {
                    return {
                        pattern: `^(${valuePattern})`,
                        replacement: `[REDACTED_${type ? type.toUpperCase() : 'PII'}]`
                    };
                } else if (field === 'timestamp') {
                    return {
                        pattern: `\\[(${valuePattern})\\]`,
                        replacement: `[[REDACTED_${type ? type.toUpperCase() : 'PII'}]]`
                    };
                } else if (field === 'request') {
                    return {
                        pattern: `"(${valuePattern})"`,
                        replacement: `"[REDACTED_${type ? type.toUpperCase() : 'PII'}]"`
                    };
                }
            }
        }
        
        // Fallback: use type-specific pattern without field context
        const valuePattern = getValuePattern(type);
        return {
            pattern: valuePattern,
            replacement: `[REDACTED_${type ? type.toUpperCase() : 'PII'}]`
        };
    };
    
    // Helper to get value pattern based on PII type
    const getValuePattern = (type) => {
        switch (type) {
            case 'email':
                return '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}';
            case 'ip':
            case 'ip_address':
                return '[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}';
            case 'phone':
                return '\\d{3}-\\d{3}-\\d{4}';
            case 'ssn':
                return '\\d{3}-\\d{2}-\\d{4}';
            case 'credit_card':
                return '\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}';
            case 'timestamp':
                return '[^\\]\\s]+'; // For timestamps, be more flexible
            default:
                return '[^\\s,="]+'; // Non-whitespace, non-comma, non-quote, non-equals
        }
    };

    const generateConfigurations = () => {
        const propsConfig = generatePropsConf();
        const spl2IngestConfig = generateSpl2IngestConf();
        const spl2EdgeConfig = generateSpl2EdgeConf();
        
        setPropsConf(propsConfig);
        setSpl2IngestConf(spl2IngestConfig);
        setSpl2EdgeConf(spl2EdgeConfig);
    };

    const handleCopy = (content, name) => {
        navigator.clipboard.writeText(content);
        createToast({
            type: TOAST_TYPES.SUCCESS,
            title: 'Copied!',
            message: `${name} copied to clipboard`,
            autoDismiss: true,
        });
    };

    const handleDownload = (content, filename) => {
        const blob = new Blob([content], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        createToast({
            type: TOAST_TYPES.SUCCESS,
            title: 'Downloaded!',
            message: `${filename} has been downloaded`,
            autoDismiss: true,
        });
    };

    // Validation function
    function validateConfigs() {
        // Simulate applying props.conf
        const simulated = applyExtractions(sampleData, propsConf);
        setValidationResults(simulated);
    }

    return (
        <>
            <ToastMessages position="top-center" />
            <Card style={{ width: '100%', marginTop: 24 }}>
                <Card.Header title="Configuration Generator" />
                <Card.Body>
                    <StyledBox marginBottom={20}>
                        <Typography as="h3" variant="title3" style={{ marginBottom: 4 }}>
                            Generate Splunk Configuration Files
                        </Typography>
                        <Typography as="p" variant="body" style={{ opacity: 0.8 }}>
                            Generate proper Splunk configuration files (props.conf, transforms.conf) and SPL2 examples 
                            based on your field extractions, CIM mappings, and PII detection results.
                        </Typography>
                    </StyledBox>

                    {sampleData && (
                        <StyledBox marginBottom={24}>
                            <Typography as="h4" variant="title4" style={{ marginBottom: 8 }}>
                                Sample Data
                            </Typography>
                            <StyledPreview>
                                {sampleData}
                            </StyledPreview>
                        </StyledBox>
                    )}

                    <Card style={{ marginBottom: 16 }}>
                        <Card.Header title="Sourcetype Override" />
                        <Card.Body>
                            <Typography>Override the sourcetype stanza name for the generated configuration:</Typography>
                            <Text
                                value={sourcetypeOverride}
                                onChange={e => setSourcetypeOverride(e.target.value)}
                                placeholder="Enter sourcetype name"
                                style={{ marginTop: 8, width: '100%' }}
                            />
                        </Card.Body>
                    </Card>

                    <TabLayout defaultActivePanelId="props">
                        <TabLayout.Panel label="props.conf" panelId="props">
                            <StyledBox marginBottom={16}>
                                <Typography as="h4" variant="title4" style={{ marginBottom: 8 }}>
                                    props.conf
                                </Typography>
                                <Typography as="p" variant="body" style={{ marginBottom: 16, opacity: 0.8 }}>
                                    Configuration for defining field extractions, CIM field aliases, and PII redaction.
                                </Typography>
                                <TextArea
                                    value={propsConf}
                                    rowsMin={10}
                                    style={{ fontFamily: 'monospace', fontSize: '13px'}}
                                    readOnly
                                />
                                <StyledLayout gutter={8} marginTop={16}>
                                    <Button
                                        appearance="primary"
                                        onClick={() => handleCopy(propsConf, 'props.conf')}
                                    >
                                        Copy to Clipboard
                                    </Button>
                                    <Button
                                        appearance="secondary"
                                        onClick={() => handleDownload(propsConf, 'props.conf')}
                                    >
                                        Download
                                    </Button>
                                </StyledLayout>
                            </StyledBox>
                        </TabLayout.Panel>

                        <TabLayout.Panel label="SPL2 (Ingest & Edge)" panelId="spl2-ingest">
                            <StyledBox marginBottom={16}>
                                <Typography as="h4" variant="title4" style={{ marginBottom: 8 }}>
                                    SPL2 Ingest Processor Configuration
                                </Typography>
                                <Typography as="p" variant="body" style={{ marginBottom: 16, opacity: 0.8 }}>
                                    SPL2 configuration for Splunk Ingest Processor with field extraction and PII handling.
                                </Typography>
                                <TextArea
                                    value={spl2IngestConf}
                                    rowsMin={10}
                                    style={{ fontFamily: 'monospace', fontSize: '13px' }}
                                    readOnly
                                />
                                <StyledLayout gutter={8} marginTop={16}>
                                    <Button
                                        appearance="primary"
                                        onClick={() => handleCopy(spl2IngestConf, 'SPL2 Ingest Configuration')}
                                    >
                                        Copy to Clipboard
                                    </Button>
                                    <Button
                                        appearance="secondary"
                                        onClick={() => handleDownload(spl2IngestConf, 'spl2-ingest.js')}
                                    >
                                        Download
                                    </Button>
                                </StyledLayout>
                            </StyledBox>
                        </TabLayout.Panel>
                    </TabLayout>

                    <StyledLayout gutter={8} marginTop={32} style={{ justifyContent: 'space-between' }}>
                        <StyledPanel>
                            <Button appearance="secondary" onClick={onBack}>
                                Back
                            </Button>
                        </StyledPanel>
                        <StyledPanel>
                            <Button
                                appearance="primary"
                                onClick={() => onFinish({ propsConf, spl2IngestConf, spl2EdgeConf })}
                            >
                                Finish
                            </Button>
                        </StyledPanel>
                    </StyledLayout>
                </Card.Body>
            </Card>
        </>
    );
};

ConfigurationGenerator.propTypes = {
    extractedFields: PropTypes.arrayOf(PropTypes.shape({
        name: PropTypes.string.isRequired,
        type: PropTypes.string,
        value: PropTypes.any,
        confidence: PropTypes.number
    })).isRequired,
    cimMapping: PropTypes.object.isRequired,
    piiResults: PropTypes.shape({
        results: PropTypes.arrayOf(PropTypes.shape({
            field: PropTypes.string.isRequired,
            type: PropTypes.string.isRequired,
            value: PropTypes.string,
            confidence: PropTypes.number,
            recommendation: PropTypes.string
        })),
        autoMask: PropTypes.bool
    }).isRequired,
    sampleData: PropTypes.string,
    extractionRegex: PropTypes.string,
    onBack: PropTypes.func.isRequired,
    onFinish: PropTypes.func.isRequired,
};

export default ConfigurationGenerator;