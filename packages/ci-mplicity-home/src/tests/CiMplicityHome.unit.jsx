/**
 * @jest-environment jsdom
 */
import React from 'react';
import { expect, test } from '@jest/globals';
import { render, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import CiMplicityHome from '../CiMplicityHome';

test('renders Data Input step with Paste Data textarea and Analyze Data button', async () => {
    const { getByPlaceholderText, getByText } = render(<CiMplicityHome />);
    expect(getByPlaceholderText('Paste your sample log data here...')).toBeInTheDocument();
    expect(getByText('Analyze Data')).toBeInTheDocument();
});

test('Splunk Index tab renders and validates input', async () => {
    const { getByText, getByPlaceholderText, queryByText } = render(<CiMplicityHome />);
    // Switch to Splunk Index tab
    fireEvent.click(getByText('Splunk Index'));
    // Inputs and button should be present
    expect(getByPlaceholderText('Index (e.g. main)')).toBeInTheDocument();
    expect(getByPlaceholderText('Sourcetype (optional)')).toBeInTheDocument();
    expect(getByText('Fetch Sample')).toBeInTheDocument();
    // Try to fetch with empty index
    fireEvent.click(getByText('Fetch Sample'));
    await waitFor(() => {
        expect(getByText('Index is required.')).toBeInTheDocument();
    });
    // Error should disappear after entering index and clicking fetch again
    fireEvent.change(getByPlaceholderText('Index (e.g. main)'), { target: { value: 'main' } });
    fireEvent.click(getByText('Fetch Sample'));
    await waitFor(() => {
        expect(queryByText('Index is required.')).not.toBeInTheDocument();
    });
});

// TODO: Add tests for file upload, Splunk API integration, and stepper as features are migrated
