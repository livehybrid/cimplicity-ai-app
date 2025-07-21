import styled from 'styled-components';
import { variables, mixins } from '@splunk/themes';

const StyledContainer = styled.div`
    ${mixins.reset('inline-block')};
    font-size: ${variables.fontSizeLarge};
    width: 100%;
    line-height: 200%;
    margin: ${variables.spacingLarge} ${variables.spacingSmall};
    padding: ${variables.spacingLarge} ${variables.spacingXXLarge};
    border-radius: ${variables.borderRadius};
    box-shadow: ${variables.overlayShadow};
    background-color: ${variables.backgroundColorSection};
`;

const StyledGreeting = styled.div`
    font-weight: bold;
    color: ${variables.brandColor};
    font-size: ${variables.fontSizeXXLarge};
`;

export { StyledContainer, StyledGreeting };
