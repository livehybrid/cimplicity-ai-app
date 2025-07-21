import { app, username, getCSRFToken } from '@splunk/splunk-utils/config';
import { getDefaultFetchInit } from '@splunk/splunk-utils/fetch';
import { createRESTURL } from '@splunk/splunk-utils/url';
import { ResponseError } from './ResponseError';
import { handleResponse, handleError } from '@splunk/splunk-utils/fetch';

const DEFAULT_PARAMS = { output_mode: 'json' };

const APP_NAME = 'cim-plicity';

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

export async function postRequest({ endpointUrl, params = {}, body, signal }) {
    const url = createUrl(endpointUrl, params);
    const defaultInit = getDefaultFetchInit();
    const headers = {
        ...defaultInit.headers,
        'Content-Type': 'application/x-www-form-urlencoded',
    };

    const options = {
        method: 'POST',
        headers,
        signal,
        body,
    };

    return fetchWithErrorHandling(url, options);
}

export async function deleteRequest({ endpointUrl, params = {}, signal }) {
    const url = createUrl(endpointUrl, params);

    const options = {
        method: 'DELETE',
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
    // The REST endpoint lives in the 'cim-plicity' app, not the current UI app context.
    const url = createRESTURL(`/servicesNS/-/${APP_NAME}/${endpoint}`, {
        owner: username,
        app: APP_NAME,
    });

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

// Improve API call with retries
async function callApiWithRetry(endpoint, data, retries=3) {
    // Implementation
}

// Update detectFieldsWithAi to use retry 