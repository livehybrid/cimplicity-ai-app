import React from 'react';
import PropTypes from 'prop-types';
import Tooltip from '@splunk/react-ui/Tooltip';
import StarSparklesDouble from '@splunk/react-icons/StarSparklesDouble';
import styled from 'styled-components';
import { variables } from '@splunk/themes';

// Marks any control that sends data to the configured LLM, so users can tell
// AI actions apart from the built-in local ones at a glance.
const StyledBadge = styled.span`
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 1px 6px;
    border: 1px solid ${variables.accentColor};
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    line-height: 16px;
    color: ${variables.accentColor};
    vertical-align: middle;
`;

const AI_TOOLTIP =
    'Uses the AI model set under Configuration, AI Configuration. Your sample data is sent to that service. Actions without this marker run locally in Splunk.';

const AiBadge = ({ compact, tooltip }) => {
    const badge = (
        <StyledBadge aria-label="AI action">
            <StarSparklesDouble />
            {!compact && 'AI'}
        </StyledBadge>
    );
    return tooltip ? <Tooltip content={AI_TOOLTIP}>{badge}</Tooltip> : badge;
};

AiBadge.propTypes = {
    compact: PropTypes.bool,
    tooltip: PropTypes.bool,
};

AiBadge.defaultProps = {
    compact: false,
    tooltip: true,
};

export default AiBadge;
