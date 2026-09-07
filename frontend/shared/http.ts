import type {
  Api,
  ApiResponse,
  Payloads,
  Session,
  Language,
  Responses,
} from "./contracts";
export class HttpError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly retryAfter = 0,
  ) {
    super(message);
    this.name = "HttpError";
  }
}
export function asError(
  value: unknown,
): Error & Partial<Pick<HttpError, "status" | "code" | "retryAfter">> {
  return value instanceof Error ? value : new Error(String(value));
}
export function createApi(
  session: () => Readonly<Session>,
  language: () => Language,
  translate: (key: string) => string,
): Api {
  return async <
    P extends keyof Responses,
    B extends Payloads[P] | undefined = undefined,
  >(
    path: P,
    payload?: B,
  ): Promise<ApiResponse<P, B>> => {
    const response = await fetch(
      path,
      payload
        ? {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...payload, csrf: session().csrf }),
          }
        : { cache: "no-store" },
    );
    const data: unknown = await response.json();
    if (!response.ok) {
      const code =
        typeof data === "object" &&
        data !== null &&
        "error" in data &&
        typeof data.error === "string"
          ? data.error
          : "failure";
      const retryAfter = Number(response.headers.get("Retry-After")) || 0;
      const message = retryAfter
        ? (language() === "ru" ? "Повторите через " : "Retry in ") +
          retryAfter +
          (language() === "ru" ? " сек." : " seconds.")
        : translate(code);
      throw new HttpError(message, response.status, code, retryAfter);
    }
    // Same-origin Python endpoints define the wire schema. Keep the assertion at this single transport boundary.
    return data as ApiResponse<P, B>;
  };
}
