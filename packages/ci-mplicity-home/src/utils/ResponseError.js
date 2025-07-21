export class ResponseError extends Error {
    constructor({ response, message }) {
        super(message);
        this.response = response;
    }
} 