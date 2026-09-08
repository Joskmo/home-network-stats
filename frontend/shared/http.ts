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
  updateSession: (fresh: Session) => void = () => {},
): Api {
  async function request(
    path: keyof Responses,
    options: RequestInit,
  ): Promise<unknown> {
    const response = await fetch(path, options);
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
    return data;
  }
  return async <
    P extends keyof Responses,
    B extends Payloads[P] | undefined = undefined,
  >(
    path: P,
    payload?: B,
  ): Promise<ApiResponse<P, B>> => {
    // Capture before awaiting: edits made during recovery must not change this save.
    const snapshot = payload ? structuredClone(payload) : undefined;
    const send = (csrf: string | undefined) =>
      request(
        path,
        snapshot
          ? {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ ...snapshot, csrf }),
            }
          : { cache: "no-store" },
      );
    let data: unknown;
    try {
      data = await send(session().csrf);
    } catch (error) {
      if (
        !snapshot ||
        (path !== "/api/topology" && path !== "/api/topology/preview") ||
        !(error instanceof HttpError) ||
        error.status !== 403 ||
        error.code !== "csrf_failed"
      )
        throw error;
      // Only an explicit CSRF rejection proves the mutation was not applied.
      const fresh = (await request("/api/session", {
        cache: "no-store",
      })) as Session;
      updateSession(fresh);
      if (!fresh.authenticated) {
        throw new HttpError(translate("login_required"), 401, "login_required");
      }
      if (fresh.must_change) {
        throw new HttpError(
          translate("password_change_required"),
          403,
          "password_change_required",
        );
      }
      if (typeof fresh.csrf !== "string" || !fresh.csrf) throw error;
      data = await send(fresh.csrf);
    }
    // Same-origin Python endpoints define the wire schema. Assertions stay at the transport boundary.
    return data as ApiResponse<P, B>;
  };
}
