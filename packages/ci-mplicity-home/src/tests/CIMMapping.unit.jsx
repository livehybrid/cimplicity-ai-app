import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from '@jest/globals';
import CIMMapping from '../CIMMapping';

describe('CIMMapping', () => {
    const extractedFields = [
        { name: 'src_ip', sampleValue: '1.2.3.4' },
        { name: 'user', sampleValue: 'alice' },
    ];
    it('renders extracted fields and disables Continue until mapped', () => {
        render(<CIMMapping extractedFields={extractedFields} onBack={() => {}} onContinue={() => {}} />);
        expect(screen.getByText('src_ip')).toBeInTheDocument();
        expect(screen.getByText('user')).toBeInTheDocument();
        const continueBtn = screen.getByRole('button', { name: /continue/i });
        expect(continueBtn).toBeDisabled();
    });
    it('enables Continue when a CIM field is mapped', () => {
        render(<CIMMapping extractedFields={extractedFields} onBack={() => {}} onContinue={() => {}} />);
        const selects = screen.getAllByRole('combobox');
        fireEvent.change(selects[0], { target: { value: 'src_ip' } });
        const continueBtn = screen.getByRole('button', { name: /continue/i });
        expect(continueBtn).not.toBeDisabled();
    });
}); 