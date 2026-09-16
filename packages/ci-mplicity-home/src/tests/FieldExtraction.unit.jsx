import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, jest } from '@jest/globals';
import '@testing-library/jest-dom';
import { SplunkThemeProvider } from '@splunk/themes';
import FieldExtraction from '../FieldExtraction';

const renderExtraction = (props = {}) =>
    render(
        <SplunkThemeProvider family="prisma" colorScheme="light" density="comfortable">
            <FieldExtraction
                sampleData="user=alice action=login"
                onFieldsExtracted={() => {}}
                onContinueToMapping={() => {}}
                onBack={() => {}}
                onDetectFields={() => {}}
                {...props}
            />
        </SplunkThemeProvider>
    );

describe('FieldExtraction', () => {
    it('renders tabs and the sample data preview', () => {
        renderExtraction();
        expect(screen.getByText('Auto Detect')).toBeInTheDocument();
        expect(screen.getByText('Custom')).toBeInTheDocument();
        expect(screen.getByText('Ask AI')).toBeInTheDocument();
        expect(screen.getByText('Sample Data Preview:')).toBeInTheDocument();
    });

    it('converts Python named groups to JS syntax when previewing the combined regex', () => {
        renderExtraction({
            aiFieldResults: { sourcetype: 'kv_log', combined_regex: 'user=(?P<user>\\w+)' },
        });
        fireEvent.click(screen.getByText('Ask AI'));
        fireEvent.click(screen.getByText('Preview Extraction'));
        // (?P<user> must be treated as the JS named group (?<user>, so 'alice' is captured
        expect(screen.getByText(/"user": "alice"/)).toBeInTheDocument();
    });

    it('renders markup in sample data as text, not HTML (no XSS)', () => {
        const hostile = '<img src=x onerror="window.pwned=true"> user=alice';
        const { container } = renderExtraction({
            sampleData: hostile,
            existingFields: [
                { name: 'user', type: 'string', value: 'alice', confidence: 1, source: 'splunk_existing' },
            ],
        });
        // The raw markup must be rendered as inert text and never become an element
        expect(container.querySelector('img')).toBeNull();
        expect(window.pwned).toBeUndefined();
        expect(screen.getAllByText(/<img src=x/).length).toBeGreaterThan(0);
    });

    it('propagates combined regex edits via onCombinedRegexChange', () => {
        const onCombinedRegexChange = jest.fn();
        renderExtraction({
            aiFieldResults: { sourcetype: 'kv_log', combined_regex: 'user=(?P<user>\\w+)' },
            onCombinedRegexChange,
        });
        fireEvent.click(screen.getByText('Ask AI'));
        // Splunk TextArea renders a hidden shadow textarea alongside the real one
        const regexArea = screen
            .getAllByDisplayValue('user=(?P<user>\\w+)')
            .find((el) => el.getAttribute('aria-hidden') !== 'true');
        fireEvent.change(regexArea, { target: { value: 'user=(?P<username>\\w+)' } });
        expect(onCombinedRegexChange).toHaveBeenCalledWith('user=(?P<username>\\w+)');
    });
});
