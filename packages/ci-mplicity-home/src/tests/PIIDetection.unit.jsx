import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from '@jest/globals';
import '@testing-library/jest-dom';
import { SplunkThemeProvider } from '@splunk/themes';
import PIIDetection from '../PIIDetection';

const sampleData = 'user=alice email=test@example.com';
const piiResults = {
    pii_results: [
        { type: 'EMAIL', text: 'test@example.com', start: 17, end: 33, score: 0.99, regex_pattern: '[^@\\s]+@[^\\s]+' },
    ],
};

const renderDetection = (props = {}) =>
    render(
        <SplunkThemeProvider family="prisma" colorScheme="light" density="comfortable">
            <PIIDetection
                onDetectPii={() => {}}
                sampleData={sampleData}
                onBack={() => {}}
                onContinue={() => {}}
                {...props}
            />
        </SplunkThemeProvider>
    );

describe('PIIDetection', () => {
    it('renders the scan button and navigation buttons', () => {
        renderDetection();
        expect(screen.getByRole('button', { name: /scan for pii/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument();
    });

    it('shows detected PII types with a redact toggle when results are present', () => {
        renderDetection({ piiResults });
        expect(screen.getByText('Detected PII Types')).toBeInTheDocument();
        expect(screen.getByText('EMAIL')).toBeInTheDocument();
        expect(screen.getByText('test@example.com')).toBeInTheDocument();
        expect(screen.getByLabelText('Redact EMAIL')).toBeInTheDocument();
    });

    it('surfaces detection errors via an error message', () => {
        renderDetection({ piiError: new Error('backend unavailable') });
        expect(screen.getByText(/backend unavailable/)).toBeInTheDocument();
    });
});
