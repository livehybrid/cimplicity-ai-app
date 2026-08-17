import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from '@jest/globals';
import '@testing-library/jest-dom';
import { SplunkThemeProvider } from '@splunk/themes';
import CIMMapping from '../CIMMapping';

const extractedFields = [
    { name: 'clientip', type: 'ip', sampleValue: '1.2.3.4' },
    { name: 'user', type: 'string', sampleValue: 'alice' },
];

const renderMapping = (props = {}) =>
    render(
        <SplunkThemeProvider family="prisma" colorScheme="light" density="comfortable">
            <CIMMapping
                extractedFields={extractedFields}
                onBack={() => {}}
                onContinue={() => {}}
                {...props}
            />
        </SplunkThemeProvider>
    );

describe('CIMMapping', () => {
    it('auto-selects the best-matching CIM model on entry', () => {
        // clientip -> src_ip and user -> user both match Authentication, so it
        // is pre-selected and the auto-pick explanation is shown
        renderMapping();
        expect(screen.getByText('How to use CIM Field Mapping')).toBeInTheDocument();
        expect(screen.getByText(/Auto-selected Authentication/)).toBeInTheDocument();
        const continueBtn = screen.getByRole('button', { name: /continue to pii detection/i });
        expect(continueBtn).not.toHaveAttribute('aria-disabled', 'true');
    });

    it('disables Continue when no model auto-matches the extracted fields', () => {
        renderMapping({ extractedFields: [{ name: 'zzz_nothing_matches_this', type: 'string' }] });
        const continueBtn = screen.getByRole('button', { name: /continue to pii detection/i });
        // Splunk Button conveys disabled state via aria-disabled
        expect(continueBtn).toHaveAttribute('aria-disabled', 'true');
    });

    it('shows CIM fields of the initial model and enables Continue', () => {
        renderMapping({ initialModel: 'web' });
        // Web model CIM fields render as mapping rows
        expect(screen.getByText('src_ip')).toBeInTheDocument();
        expect(screen.getByText('http_method')).toBeInTheDocument();
        const continueBtn = screen.getByRole('button', { name: /continue to pii detection/i });
        expect(continueBtn).not.toHaveAttribute('aria-disabled', 'true');
    });

    it('toggling the mapping mode switches the source column to extracted fields', () => {
        renderMapping({ initialModel: 'web' });
        expect(screen.getByText('CIM Field')).toBeInTheDocument();
        fireEvent.click(
            screen.getByLabelText('Map each CIM field to an extracted field (recommended)')
        );
        // After the toggle the table is seeded from the extracted fields, not the CIM model
        expect(screen.getByText('Extracted Field')).toBeInTheDocument();
        expect(screen.getByText('clientip')).toBeInTheDocument();
    });
});
