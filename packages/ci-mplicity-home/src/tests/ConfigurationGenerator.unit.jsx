import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from '@jest/globals';
import ConfigurationGenerator from '../ConfigurationGenerator';

describe('ConfigurationGenerator', () => {
    const extractedFields = [
        { name: 'email' },
        { name: 'user' },
    ];
    const cimMapping = { email: 'user_email', user: 'user' };
    const piiResults = [
        { name: 'email', isPII: true },
        { name: 'user', isPII: false },
    ];
    it('renders config summary and buttons', () => {
        render(<ConfigurationGenerator extractedFields={extractedFields} cimMapping={cimMapping} piiResults={piiResults} onBack={() => {}} />);
        expect(screen.getByText('email')).toBeInTheDocument();
        expect(screen.getByText('user')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /download config/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /copy config/i })).toBeInTheDocument();
        expect(screen.getByText(/user_email/)).toBeInTheDocument();
        expect(screen.getByText(/No/)).toBeInTheDocument();
        expect(screen.getByText(/PII/)).toBeInTheDocument();
        expect(screen.getByText(/configuration generation/i)).toBeInTheDocument();
    });
}); 