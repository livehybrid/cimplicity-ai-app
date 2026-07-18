import { app } from '@splunk/splunk-utils/config';
import { getDefaultFetchInit } from '@splunk/splunk-utils/fetch';
import { createRESTURL } from '@splunk/splunk-utils/url';
import { ResponseError } from './ResponseError';
import { handleResponse, handleError } from '@splunk/splunk-utils/fetch';

const DEFAULT_PARAMS = { output_mode: 'json' };

function createUrl(endpointUrl, params) {
    const url = new URL(createRESTURL(endpointUrl, { app }), window.location.origin);
    Object.entries({ ...DEFAULT_PARAMS, ...params })
        .filter(([, value]) => value !== undefined && value !== null)
        .forEach(([key, value]) => url.searchParams.append(key, value.toString()));
    return url;
}

function handleErrorResponse(response) {
    if (!response.ok) {
        throw new ResponseError({ response, message: 'Something went wrong' });
    }
}

async function fetchWithErrorHandling(url, options) {
    const defaultInit = getDefaultFetchInit();

    const response = await fetch(url.toString(), {
        ...defaultInit,
        ...options,
    });

    handleErrorResponse(response);

    return await response.json();
}

export async function getRequest({ endpointUrl, params = {}, signal }) {
    const url = createUrl(endpointUrl, params);
    const options = {
        method: 'GET',
        signal,
    };

    return fetchWithErrorHandling(url, options);
}

/**
 * A generic helper to make POST requests to our custom endpoints.
 * @param {string} endpoint - The name of the endpoint to call (e.g., 'pii_detection').
 * @param {object} data - The JSON payload to send.
 * @returns {Promise<object>} - A promise that resolves to the JSON response from the endpoint.
 */
async function postToEndpoint(endpoint, postData) {
    // With app but no owner, createRESTURL emits /servicesNS/-/<app>/<endpoint>,
    // matching the restmap.conf and web.conf stanzas for this app.
    const url = createRESTURL(endpoint, { app });

    const defaultInit = getDefaultFetchInit();

    try {
        const response = await fetch(url, {
            ...defaultInit,
            method: 'POST',
            headers: {
                ...defaultInit.headers,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(postData),
        }).then(handleResponse(200));
        return 'payload' in response ? response.payload : response;

    } catch (error) {
        console.error(`Error calling endpoint ${endpoint}:`, error);
        const parsedError = await handleError(error);
        throw parsedError;
    }
}

/**
 * Calls the PII detection endpoint.
 * @param {string} text - The text to analyze for PII.
 * @param {Array} customPatterns - Custom regex patterns for PII detection.
 * @returns {Promise<object>} - The PII analysis results.
 */
export const detectPii = (text, customPatterns = []) => {
    return postToEndpoint('pii_detection', { text, custom_patterns: customPatterns });
};

/**
 * Calls the AI field detection endpoint.
 * @param {string} text - The sample log text to analyze.
 * @param {string} description - The description of the text.
 * @param {string[]} selectedFields - The selected fields to analyze.
 * @returns {Promise<object>} - The suggested field extractions.
 */
export const detectFieldsWithAi = (text, description = null, selectedFields = null) => {
    const payload = { text };
    if (description) {
        payload.description = description;
    }
    if (selectedFields) {
        payload.selected_fields = selectedFields;
    }
    return postToEndpoint('ai_detection', payload);
};