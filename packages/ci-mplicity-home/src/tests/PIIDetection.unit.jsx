import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from '@jest/globals';
import PIIDetection from '../PIIDetection';

describe('PIIDetection', () => {
    const extractedFields = [
        { name: 'email', sampleValue: 'test@example.com' },
        { name: 'user', sampleValue: 'alice' },
    ];
    const cimMapping = { email: 'user_email', user: 'user' };
    it('renders fields and detects PII', () => {
        render(<PIIDetection extractedFields={extractedFields} cimMapping={cimMapping} onBack={() => {}} onContinue={() => {}} />);
        expect(screen.getByText('email')).toBeInTheDocument();
        expect(screen.getByText('user')).toBeInTheDocument();
        expect(screen.getAllByText('PII').length).toBeGreaterThan(0);
        expect(screen.getAllByText('No').length).toBeGreaterThan(0);
    });
    it('renders navigation buttons', () => {
        render(<PIIDetection extractedFields={extractedFields} cimMapping={cimMapping} onBack={() => {}} onContinue={() => {}} />);
        expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument();
    });
}); 