import React from 'react';

import layout from '@splunk/react-page';
import CiMplicityHome from '@splunk/ci-mplicity-home';
import { getUserTheme } from '@splunk/splunk-utils/themes';

import { StyledContainer } from './StartStyles';

getUserTheme()
    .then((theme) => {
        layout(
            <StyledContainer>
                <CiMplicityHome name="from inside CiMplicityHome" />
            </StyledContainer>,
            {
                // Splunk Web serves its page shell with a placeholder
                // <title>Loading...</title> and expects the page's own JS to
                // replace it. react-page only does that when pageTitle is
                // passed, so without this the browser tab reads "Loading..."
                // for the life of the page. UCC's generated pages pass their
                // own titles, which is why only this custom view was affected.
                pageTitle: 'CIMPlicity AI',
                theme,
            }
        );
    })
    .catch((e) => {
        const errorEl = document.createElement('span');
        errorEl.textContent = String(e);
        document.body.appendChild(errorEl);
    });
