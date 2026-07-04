export function statusCodeFromError(error: unknown): number {
  const candidate = error as {
    status?: unknown;
    statusCode?: unknown;
    response?: { status?: unknown; statusCode?: unknown };
    data?: { status?: unknown; statusCode?: unknown };
  } | null | undefined;

  const values = [
    candidate?.statusCode,
    candidate?.status,
    candidate?.response?.statusCode,
    candidate?.response?.status,
    candidate?.data?.statusCode,
    candidate?.data?.status,
  ];

  for (const value of values) {
    const status = Number(value);
    if (Number.isInteger(status) && status >= 100) return status;
  }
  return 0;
}

export function isOperatorAccessError(error: unknown): boolean {
  const status = statusCodeFromError(error);
  return status === 401 || status === 403;
}

export function buildAdminLoginUrl(options: {
  djangoPublicBaseUrl: string;
  nextPath?: string;
}): string {
  const baseUrl = String(options.djangoPublicBaseUrl || "").replace(/\/+$/, "");
  const nextPath = options.nextPath?.trim() || "/pos/";
  const normalizedNext = nextPath.startsWith("/") ? nextPath : `/${nextPath}`;
  return `${baseUrl}/admin/login/?next=${encodeURIComponent(normalizedNext)}`;
}
