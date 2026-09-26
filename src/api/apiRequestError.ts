import { apiErrorResponseSchema } from '../../shared/contracts/apiError';

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

export async function createApiRequestError(
  response: Response,
  fallbackMessage: string,
): Promise<ApiRequestError> {
  try {
    const payload: unknown = await response.json();
    const parsed = apiErrorResponseSchema.safeParse(payload);
    if (parsed.success) {
      return new ApiRequestError(
        parsed.data.error.message,
        response.status,
        parsed.data.error.code,
      );
    }
  } catch {
    // A non-success response with an invalid body still becomes a safe client error.
  }

  return new ApiRequestError(fallbackMessage, response.status, 'INVALID_ERROR_RESPONSE');
}
