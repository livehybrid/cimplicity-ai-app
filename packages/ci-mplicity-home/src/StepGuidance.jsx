import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import Heading from '@splunk/react-ui/Heading';
import Paragraph from '@splunk/react-ui/Paragraph';
import Message from '@splunk/react-ui/Message';
import WaitSpinner from '@splunk/react-ui/WaitSpinner';
import styled from 'styled-components';
import { getRequest } from './utils/api';
import AiBadge from './AiBadge';
import { CIM_MODELS } from './CIMMapping';

// Per-step content for the right-hand "Help & Context" sidebar. Keyed by the
// STEPS numbers in CiMplicityHome (not imported from there, which would be a
// circular import).

const GuideList = styled.ul`
    margin: 8px 0 0;
    padding-left: 16px;
    font-size: 12px;
    line-height: 1.5;

    li {
        margin-bottom: 8px;
    }
`;

const ModelList = styled.dl`
    margin: 8px 0 0;
    font-size: 12px;
    line-height: 1.45;

    dt {
        font-weight: 600;
        margin-top: 8px;
    }

    dd {
        margin: 0;
        opacity: 0.8;
    }
`;

const SmallParagraph = styled(Paragraph)`
    font-size: 12px;
`;

const AiLegend = () => (
    <SmallParagraph style={{ marginTop: 12 }}>
        Actions marked <AiBadge /> send your sample to the AI model set under
        Configuration, AI Configuration. Everything else runs locally in Splunk.
    </SmallParagraph>
);

// Where the CIM field definitions on the mapping step actually come from:
// bin/load_cim_models.py reads the data model JSON shipped inside the
// Splunk_SA_CIM app on this search head, falling back to a built-in subset
// when the app is absent. Surfacing the installed version (via the apps/local
// EAI endpoint) tells the user exactly which CIM release they are mapping to.
const CimSourceInfo = () => {
    const [cimApp, setCimApp] = useState({ loading: true, installed: false, version: null });

    useEffect(() => {
        const controller = new AbortController();
        getRequest({ endpointUrl: 'apps/local/Splunk_SA_CIM', signal: controller.signal })
            .then((data) => {
                const content = (data.entry && data.entry[0] && data.entry[0].content) || {};
                setCimApp({ loading: false, installed: true, version: content.version || null });
            })
            .catch((err) => {
                if (err.name !== 'AbortError') {
                    setCimApp({ loading: false, installed: false, version: null });
                }
            });
        return () => controller.abort();
    }, []);

    if (cimApp.loading) {
        return (
            <SmallParagraph>
                <WaitSpinner size="small" /> Checking the installed CIM version...
            </SmallParagraph>
        );
    }

    return (
        <>
            {cimApp.installed ? (
                <SmallParagraph>
                    Field definitions load live from the Splunk Common Information Model app
                    installed on this search head (Splunk_SA_CIM
                    {cimApp.version ? ` v${cimApp.version}` : ''}), so the fields you map to
                    match that CIM release exactly.
                </SmallParagraph>
            ) : (
                <Message appearance="fill" type="warning" style={{ marginBottom: 8 }}>
                    Splunk_SA_CIM is not installed (or not readable), so a built-in fallback
                    subset of CIM fields is used. Install the Splunk Common Information Model
                    app from Splunkbase for the full, current definitions.
                </Message>
            )}
            <SmallParagraph>
                To map against the latest CIM, update the Splunk Common Information Model app
                (Splunk Web: Apps, Manage Apps, check for updates, or download it from
                Splunkbase) and then revisit this step.
            </SmallParagraph>
        </>
    );
};

const DataInputGuide = () => (
    <>
        <Paragraph>
            Provide a sample of the data you want to onboard. One representative event is
            enough; everything that follows works from this sample.
        </Paragraph>
        <GuideList>
            <li>
                <strong>Paste Sample:</strong> paste raw events directly, or load a built-in
                Apache, JSON or CSV template to explore the workflow.
            </li>
            <li>
                <strong>Upload File:</strong> reads a log file in your browser and uses its
                content as the sample. Nothing is uploaded to or indexed in Splunk.
            </li>
            <li>
                <strong>From Splunk:</strong> pick an index, then a sourcetype (those seen in
                the last 24 hours), then Fetch Events lists recent matching events to choose
                from. Pick one that is representative: a sourcetype often mixes formats, and
                seeding the workflow from an unusual event produces extractions that fit
                nothing. Refresh events re-runs the search for a newer set.
            </li>
        </GuideList>
        <AiLegend />
    </>
);

const FieldExtractionGuide = () => (
    <>
        <Paragraph>
            Extract fields from your sample. The tabs are alternative routes to the same
            result and you can combine them; extracted fields feed the CIM mapping step.
        </Paragraph>
        <GuideList>
            <li>
                <strong>Existing:</strong> fields Splunk already extracts for this sourcetype
                (shown when the sample was fetched from Splunk).
            </li>
            <li>
                <strong>Auto Detect:</strong> local pattern matching for common fields, plus
                timestamp settings (TIME_PREFIX, TIME_FORMAT and lookahead).
            </li>
            <li>
                <strong>Custom:</strong> write your own regex with named capture groups and
                preview what it matches.
            </li>
            <li>
                <strong>Ask AI</strong> <AiBadge compact />: sends the sample and an optional
                description to your configured model, which suggests fields, regexes and
                timestamp settings for you to review.
            </li>
        </GuideList>
        <AiLegend />
    </>
);

const CimMappingGuide = () => (
    <>
        <Paragraph>
            The likeliest data model is pre-selected by counting local field-name matches
            (counts shown in the picker); change it if another model fits better. Suggestions
            in the table come from that local matching, and the Ask AI button <AiBadge compact />{' '}
            sends your fields to the configured model for richer suggestions with confidence
            and reasoning. The quality score shows how much of the model you have covered.
        </Paragraph>
        <CimSourceInfo />
        <Heading level={4} style={{ marginTop: 16, marginBottom: 0 }}>
            Model quick reference
        </Heading>
        <ModelList>
            {CIM_MODELS.map((model) => (
                <React.Fragment key={model.id}>
                    <dt>{model.label}</dt>
                    <dd>{model.description}</dd>
                </React.Fragment>
            ))}
        </ModelList>
    </>
);

const PiiDetectionGuide = () => (
    <>
        <Paragraph>
            PII detection runs locally in Splunk using the bundled scrubadub library; your
            data is not sent to the AI service in this step. The active detector set is
            chosen under Configuration, PII Detectors.
        </Paragraph>
        <Paragraph>
            Review what was found, untick anything you want to keep and add custom regex
            patterns for site-specific identifiers. Selected items become redaction rules in
            the generated configuration.
        </Paragraph>
    </>
);

const ConfigurationGuide = () => (
    <>
        <Paragraph>
            Review the generated configuration: sourcetype definition, timestamp settings,
            field extractions and the PII redaction rules you selected.
        </Paragraph>
        <Paragraph>
            Download the files and deploy them to the Splunk tier where they apply
            (index-time settings on indexers or heavy forwarders, search-time extractions on
            search heads). Finish resets the workflow for the next data source.
        </Paragraph>
    </>
);

const GUIDES = {
    1: DataInputGuide,
    2: FieldExtractionGuide,
    3: CimMappingGuide,
    4: PiiDetectionGuide,
    5: ConfigurationGuide,
};

const StepGuidance = ({ stepId }) => {
    const Guide = GUIDES[stepId];
    return Guide ? <Guide /> : null;
};

StepGuidance.propTypes = {
    stepId: PropTypes.number.isRequired,
};

export default StepGuidance;
