import React from 'react';
import { expect, test, jest } from '@jest/globals';
import { render, fireEvent, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { SplunkThemeProvider } from '@splunk/themes';
import CiMplicityHome from '../CiMplicityHome';

// jest.mock calls are hoisted above the imports, so the mocks apply to CiMplicityHome
jest.mock('@splunk/search-job', () => ({
    __esModule: true,
    default: {
        create: jest.fn(() => ({
            getResults: () => ({ subscribe: jest.fn(() => ({ unsubscribe: jest.fn() })) }),
        })),
    },
}));
jest.mock('@splunk/splunk-utils/config', () => ({ app: 'cim-plicity', username: 'admin' }));
jest.mock('../utils/api', () => ({
    getRequest: jest.fn(() => Promise.resolve({ entry: [{ name: 'main' }] })),
    detectPii: jest.fn(() => Promise.resolve({ pii_results: [] })),
    detectFieldsWithAi: jest.fn(() => Promise.resolve({})),
}));

const renderHome = () =>
    render(
        <SplunkThemeProvider family="prisma" colorScheme="light" density="comfortable">
            <CiMplicityHome />
        </SplunkThemeProvider>
    );

test('renders the Data Input step with paste textarea and submit button', async () => {
    renderHome();
    expect(
        screen.getByPlaceholderText('Paste a single event or multiple lines of raw log data here.')
    ).toBeInTheDocument();
    expect(screen.getByText('Use Pasted Text')).toBeInTheDocument();
    expect(screen.getByText('From Splunk')).toBeInTheDocument();
});

test('stepper renders all five steps and later steps are disabled', () => {
    renderHome();
    const stepLabels = ['Data Input', 'Field Extraction', 'CIM Mapping', 'PII Detection', 'Configuration'];
    stepLabels.forEach((label) => {
        // Labels can also appear in the help panel, so assert at least one match
        expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    });
    // Later steps cannot be reached before completing earlier ones
    const cimStep = screen.getAllByText('CIM Mapping')[0].closest('button');
    expect(cimStep).toBeDisabled();
});

test('submitting pasted text advances to the Field Extraction step', () => {
    renderHome();
    const textarea = screen.getByPlaceholderText(
        'Paste a single event or multiple lines of raw log data here.'
    );
    fireEvent.change(textarea, { target: { value: 'user=alice action=login' } });
    fireEvent.click(screen.getByText('Use Pasted Text'));
    expect(screen.getByText('Extract fields from your log data using patterns, regex, or AI assistance.')).toBeInTheDocument();
});
