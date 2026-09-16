import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from '@jest/globals';
import '@testing-library/jest-dom';
import { SplunkThemeProvider } from '@splunk/themes';
import ConfigurationGenerator from '../ConfigurationGenerator';

const extractedFields = [
    { name: 'email', type: 'email', value: 'test@example.com' },
    { name: 'user', type: 'string', value: 'alice' },
];
const cimMapping = { email: 'user_email', user: 'user' };
const piiResults = {
    results: [{ field: 'email', type: 'EMAIL', regex_pattern: '[^@\\s]+@[^\\s]+' }],
    allResults: [],
    customPatterns: [],
};

const renderGenerator = () =>
    render(
        <SplunkThemeProvider family="prisma" colorScheme="light" density="comfortable">
            <ConfigurationGenerator
                extractedFields={extractedFields}
                cimMapping={cimMapping}
                piiResults={piiResults}
                sampleData="email=test@example.com user=alice"
                onBack={() => {}}
                onFinish={() => {}}
            />
        </SplunkThemeProvider>
    );

describe('ConfigurationGenerator', () => {
    it('renders copy and download actions for the generated configs', () => {
        renderGenerator();
        expect(screen.getAllByRole('button', { name: /copy to clipboard/i }).length).toBeGreaterThan(0);
        expect(screen.getAllByRole('button', { name: /download/i }).length).toBeGreaterThan(0);
    });

    it('generates props.conf with CIM aliases and PII redaction from piiResults.results', () => {
        renderGenerator();
        const textareas = screen.getAllByRole('textbox');
        const propsConf = textareas.map((t) => t.value).find((v) => v && v.includes('FIELDALIAS'));
        expect(propsConf).toBeDefined();
        expect(propsConf).toContain('FIELDALIAS-email = email AS user_email');
        expect(propsConf).toContain('SEDCMD-redact_email');
    });
});
