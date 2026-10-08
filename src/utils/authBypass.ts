export function isDevelopmentAuthBypassEnabled(_isDev: boolean, _bypassFlag: string | undefined): boolean {
  // Compatibility shim: an auth bypass is intentionally unavailable in every build.
  return false;
}
